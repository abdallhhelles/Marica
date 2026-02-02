"""
Shared HTTP client with retries, backoff, and circuit breaker support.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass

import httpx

from utils.telemetry import record_external_call, record_rate_limit


logger = logging.getLogger("MarciaOS.Http")


class CircuitBreakerOpen(RuntimeError):
    pass


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    reset_after: float = 30.0
    failure_count: int = 0
    opened_at: float | None = None

    def allow(self) -> bool:
        if self.opened_at is None:
            return True
        if (time.monotonic() - self.opened_at) >= self.reset_after:
            self.opened_at = None
            self.failure_count = 0
            return True
        return False

    def record_success(self) -> None:
        self.failure_count = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.opened_at = time.monotonic()


class HttpClient:
    def __init__(
        self,
        *,
        timeout: float,
        retries: int,
        backoff: float,
        breaker_failures: int,
        breaker_reset: float,
    ) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self._retries = max(0, retries)
        self._backoff = max(0.1, backoff)
        self._breakers: dict[str, CircuitBreaker] = {}
        self._breaker_failures = breaker_failures
        self._breaker_reset = breaker_reset

    async def aclose(self) -> None:
        await self._client.aclose()

    def _breaker_for(self, service: str) -> CircuitBreaker:
        breaker = self._breakers.get(service)
        if breaker is None:
            breaker = CircuitBreaker(
                failure_threshold=self._breaker_failures,
                reset_after=self._breaker_reset,
            )
            self._breakers[service] = breaker
        return breaker

    async def request(
        self,
        service: str,
        method: str,
        url: str,
        *,
        retries: int | None = None,
        retry_for_status: tuple[int, ...] = (500, 502, 503, 504),
        retry_on: tuple[type[BaseException], ...] = (httpx.RequestError,),
        safe: bool = True,
        **kwargs,
    ) -> httpx.Response:
        breaker = self._breaker_for(service)
        if not breaker.allow():
            raise CircuitBreakerOpen(f"Circuit breaker open for {service}")

        attempts = retries if retries is not None else self._retries
        attempts = max(0, attempts)
        last_exc: BaseException | None = None
        start_overall = time.monotonic()

        for attempt in range(attempts + 1):
            start = time.monotonic()
            try:
                response = await self._client.request(method, url, **kwargs)
                duration_ms = (time.monotonic() - start) * 1000
                if response.status_code == 429:
                    retry_after = None
                    try:
                        retry_after = float(response.headers.get("Retry-After", "0"))
                    except ValueError:
                        retry_after = None
                    record_rate_limit(service=service, retry_after=retry_after)
                    if safe and attempt < attempts and retry_after:
                        await asyncio.sleep(retry_after)
                        continue
                if response.status_code in retry_for_status and safe and attempt < attempts:
                    await self._sleep_backoff(attempt)
                    continue
                if response.is_success:
                    breaker.record_success()
                else:
                    breaker.record_failure()
                record_external_call(
                    service=service,
                    duration_ms=duration_ms,
                    success=response.is_success,
                    status_code=response.status_code,
                    retries=attempt,
                )
                return response
            except retry_on as exc:
                last_exc = exc
                if safe and attempt < attempts:
                    await self._sleep_backoff(attempt)
                    continue
                breaker.record_failure()
                duration_ms = (time.monotonic() - start_overall) * 1000
                record_external_call(
                    service=service,
                    duration_ms=duration_ms,
                    success=False,
                    status_code=None,
                    retries=attempt,
                    error=str(exc),
                )
                raise
            except Exception as exc:
                last_exc = exc
                breaker.record_failure()
                duration_ms = (time.monotonic() - start_overall) * 1000
                record_external_call(
                    service=service,
                    duration_ms=duration_ms,
                    success=False,
                    status_code=None,
                    retries=attempt,
                    error=str(exc),
                )
                raise

        breaker.record_failure()
        duration_ms = (time.monotonic() - start_overall) * 1000
        record_external_call(
            service=service,
            duration_ms=duration_ms,
            success=False,
            status_code=None,
            retries=attempts,
            error=str(last_exc) if last_exc else "unknown",
        )
        raise last_exc or RuntimeError("HTTP request failed")

    async def _sleep_backoff(self, attempt: int) -> None:
        jitter = random.uniform(0.0, 0.2)
        delay = self._backoff * (2**attempt) + jitter
        await asyncio.sleep(delay)


__all__ = ["HttpClient", "CircuitBreakerOpen"]
