"""
Centralized configuration loader for Marcia.
Keep all environment parsing here to avoid drift across modules.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from dotenv import load_dotenv


logger = logging.getLogger("MarciaOS.Config")


def _load_env() -> None:
    load_dotenv()


def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    return value


def _get_float(name: str, default: float) -> float:
    raw = _get_env(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid %s value %r; using %s", name, raw, default)
        return default


def _get_int(name: str, default: int) -> int:
    raw = _get_env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s value %r; using %s", name, raw, default)
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = _get_env(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    logger.warning("Invalid %s value %r; using %s", name, raw, default)
    return default


@dataclass(frozen=True)
class MarciaConfig:
    token: str | None
    ai_api_key: str | None
    ai_base_url: str
    ai_model: str
    ai_app_name: str
    ai_app_url: str | None
    mention_cooldown: float
    busy_cooldown: float
    http_timeout: float
    http_retries: int
    http_backoff: float
    http_breaker_failures: int
    http_breaker_reset: float
    metrics_interval: float
    log_command_latency: bool
    ocr_space_api_key: str | None
    ocr_space_timeout: float
    profile_scan_review_timeout: int
    profile_scan_workers: int
    profile_scan_concurrency: int
    profile_scan_release_ocr: bool


def load_config() -> MarciaConfig:
    _load_env()

    token = _get_env("TOKEN") or _get_env("DISCORD_TOKEN")
    if not _get_env("TOKEN") and _get_env("DISCORD_TOKEN"):
        logger.warning("DISCORD_TOKEN is deprecated; use TOKEN instead.")

    return MarciaConfig(
        token=token,
        ai_api_key=_get_env("MARCIA_AI_API_KEY"),
        ai_base_url=_get_env("MARCIA_AI_BASE_URL", "https://openrouter.ai/api/v1"),
        ai_model=_get_env("MARCIA_AI_MODEL", "meta-llama/llama-3.1-8b-instruct:free"),
        ai_app_name=_get_env("MARCIA_AI_APP_NAME", "Marcia"),
        ai_app_url=_get_env("MARCIA_AI_APP_URL"),
        mention_cooldown=_get_float("MARCIA_MENTION_COOLDOWN", 45.0),
        busy_cooldown=_get_float("MARCIA_BUSY_COOLDOWN", 120.0),
        http_timeout=_get_float("MARCIA_HTTP_TIMEOUT", 10.0),
        http_retries=_get_int("MARCIA_HTTP_RETRIES", 2),
        http_backoff=_get_float("MARCIA_HTTP_BACKOFF", 0.6),
        http_breaker_failures=_get_int("MARCIA_HTTP_BREAKER_FAILURES", 3),
        http_breaker_reset=_get_float("MARCIA_HTTP_BREAKER_RESET", 30.0),
        metrics_interval=_get_float("MARCIA_METRICS_INTERVAL", 120.0),
        log_command_latency=_get_bool("MARCIA_LOG_COMMAND_LATENCY", False),
        ocr_space_api_key=_get_env("OCR_SPACE_API_KEY"),
        ocr_space_timeout=_get_float("OCR_SPACE_TIMEOUT", 60.0),
        profile_scan_review_timeout=_get_int("PROFILE_SCAN_REVIEW_TIMEOUT", 90),
        profile_scan_workers=_get_int("PROFILE_SCAN_WORKERS", 1),
        profile_scan_concurrency=_get_int("PROFILE_SCAN_CONCURRENCY", 2),
        profile_scan_release_ocr=_get_bool("PROFILE_SCAN_RELEASE_OCR", True),
    )


__all__ = ["MarciaConfig", "load_config"]
