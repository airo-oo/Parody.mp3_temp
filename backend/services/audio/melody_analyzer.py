"""Load a local melody timing plan without treating lyrics as melody data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class MelodyError(ValueError):
    """Raised when a requested local melody is missing or invalid."""


@dataclass(frozen=True)
class MelodyNote:
    pitch: int
    start: float
    duration: float


@dataclass(frozen=True)
class Melody:
    id: str
    tempo: int
    notes: tuple[MelodyNote, ...]


def load_melody(melody_id: str, data_directory: Path | None = None) -> Melody:
    """Load one authorized/project-owned JSON melody plan by identifier."""
    if melody_id != "demo-melody-001":
        raise MelodyError("The requested melody is not available.")
    directory = data_directory or Path(__file__).resolve().parents[2] / "data"
    source = directory / "demo_melody.json"
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MelodyError("The demo melody could not be loaded.") from error

    tempo, raw_notes = payload.get("tempo"), payload.get("notes")
    if not isinstance(tempo, int) or tempo <= 0 or not isinstance(raw_notes, list) or not raw_notes:
        raise MelodyError("The melody file is invalid.")
    notes: list[MelodyNote] = []
    previous_start = -1.0
    for raw_note in raw_notes:
        if not isinstance(raw_note, dict):
            raise MelodyError("The melody contains an invalid note.")
        pitch, start, duration = raw_note.get("pitch"), raw_note.get("start"), raw_note.get("duration")
        if (
            not isinstance(pitch, int)
            or not 0 <= pitch <= 127
            or not isinstance(start, (int, float))
            or not isinstance(duration, (int, float))
            or start < previous_start
            or duration <= 0
        ):
            raise MelodyError("The melody contains an invalid note.")
        notes.append(MelodyNote(pitch=pitch, start=float(start), duration=float(duration)))
        previous_start = float(start)
    return Melody(id=melody_id, tempo=tempo, notes=tuple(notes))
