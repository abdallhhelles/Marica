"""
Patch notes persistence helpers.

This module tracks pending release notes in ``data/patch_notes.json`` so the
DevHub automation can announce them on the next deploy without relying on
hard-coded lists inside the cog. Notes are lightweight dictionaries:
``{"note": "message", "author": "optional", "added_at": "ISO timestamp"}``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

DEFAULT_PATCH_PATH = Path("data/patch_notes.json")


@dataclass
class PatchNote:
    """User-facing change log entry."""

    note: str
    added_at: str
    author: Optional[str] = None


class PatchNotesStore:
    """Simple JSON-backed store for pending patch notes."""

    def __init__(self, path: Path | str = DEFAULT_PATCH_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> List[PatchNote]:
        """Return all tracked notes, ignoring malformed rows."""
        if not self.path.exists():
            return []

        try:
            data = json.loads(self.path.read_text())
        except Exception:
            return []

        notes: List[PatchNote] = []
        for entry in data:
            message = str(entry.get("note", "")).strip()
            if not message:
                continue
            notes.append(
                PatchNote(
                    note=message,
                    added_at=str(entry.get("added_at", "")),
                    author=entry.get("author"),
                )
            )
        return notes

    def add(self, note: str, *, author: Optional[str] = None) -> None:
        """Append a new patch note entry to disk."""
        message = note.strip()
        if not message:
            return

        notes = self.load()
        notes.append(
            PatchNote(
                note=message,
                added_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                author=author,
            )
        )
        self._write(notes)

    def clear(self) -> None:
        """Remove all pending notes after a successful broadcast."""
        self._write([])

    def format_bullets(self) -> List[str]:
        """Return user-facing bullet text for each note."""
        bullets: List[str] = []
        for note in self.load():
            suffix = f" — {note.author}" if note.author else ""
            bullets.append(f"{note.note}{suffix}")
        return bullets

    def _write(self, notes: Iterable[PatchNote]) -> None:
        serialisable = [
            {"note": n.note, "added_at": n.added_at, "author": n.author}
            for n in notes
            if n.note
        ]
        self.path.write_text(json.dumps(serialisable, indent=2))
