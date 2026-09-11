"""Local command adapter for an authorized DiffSinger-compatible installation.

The project intentionally does not bundle a checkpoint or a voice.  The command
configured by the project owner receives a JSON score and writes a mono/stereo
PCM WAV.  This keeps model and voice licensing separate from the web app.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from services.audio.lyric_aligner import AlignedLyrics


class SingingProviderError(RuntimeError):
    """A safe configuration or provider error for the audio API."""


class SingingConfigurationError(SingingProviderError):
    """The real provider is selected but has not been locally configured."""


@dataclass(frozen=True)
class SingingNote:
    syllable: str
    lyric: str
    pitch: int
    start: float
    duration: float
    phrase: int


@dataclass(frozen=True)
class SingingRequest:
    tempo: int
    notes: tuple[SingingNote, ...]
    voice: str

    def as_dict(self) -> dict[str, object]:
        return {
            "tempo": self.tempo,
            "voice": self.voice,
            "notes": [
                {
                    "syllable": note.syllable,
                    "lyric": note.lyric,
                    "pitch": note.pitch,
                    "start": note.start,
                    "duration": note.duration,
                    "phrase": note.phrase,
                }
                for note in self.notes
            ],
        }


def build_singing_request(aligned_lyrics: AlignedLyrics, voice: str = "default") -> SingingRequest:
    """Convert the existing alignment into a provider-neutral score.

    Each entry carries the rendered syllable plus its MIDI pitch, onset, duration,
    and source phrase.  A provider that needs phonemes can use ``lyric`` with its
    own language/model-specific G2P, rather than receiving unstructured prose.
    """
    notes = tuple(
        SingingNote(
            syllable=item.text,
            lyric=item.line_text,
            pitch=item.pitch,
            start=round(item.start, 5),
            duration=round(item.duration, 5),
            phrase=item.line_index,
        )
        for item in aligned_lyrics.syllables
    )
    if not notes:
        raise SingingProviderError("The generated lyrics don't fit the selected melody. Try regenerating the lyrics.")
    return SingingRequest(tempo=aligned_lyrics.tempo, notes=notes, voice=voice)


class DiffSingerCliProvider:
    """Invoke a local, authorized DiffSinger wrapper without exposing it to HTTP clients.

    ``DIFFSINGER_COMMAND`` must include both ``{score_path}`` and ``{output_path}``
    placeholders.  It is tokenized and launched without a shell.  The wrapper is
    responsible for selecting an installed, licensed English-capable model.
    """

    def __init__(self, command: str | None = None) -> None:
        load_dotenv()
        self.command = command if command is not None else os.getenv("DIFFSINGER_COMMAND")

    def _arguments(self, score_path: Path, output_path: Path) -> list[str]:
        if not self.command:
            raise SingingConfigurationError(
                "AI singing is not configured. Set DIFFSINGER_COMMAND in backend/.env or use the demo voice."
            )
        if "{score_path}" not in self.command or "{output_path}" not in self.command:
            raise SingingConfigurationError(
                "DIFFSINGER_COMMAND must contain {score_path} and {output_path} placeholders."
            )
        try:
            return shlex.split(
                self.command.format(score_path=str(score_path), output_path=str(output_path)), posix=False
            )
        except ValueError as error:
            raise SingingConfigurationError("DIFFSINGER_COMMAND is invalid.") from error

    def synthesize(self, request: SingingRequest, output_path: Path) -> Path:
        with tempfile.TemporaryDirectory(prefix="parody-diffsinger-") as directory:
            score_path = Path(directory) / "score.json"
            score_path.write_text(json.dumps(request.as_dict(), ensure_ascii=False), encoding="utf-8")
            try:
                completed = subprocess.run(
                    self._arguments(score_path, output_path),
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
            except FileNotFoundError as error:
                raise SingingProviderError("The configured AI singing command could not be found.") from error
            except subprocess.TimeoutExpired as error:
                raise SingingProviderError("AI singing timed out. Try a shorter parody or check the singing engine.") from error
            except OSError as error:
                raise SingingProviderError("AI singing could not be started. Check the singing engine configuration.") from error
            if completed.returncode != 0:
                raise SingingProviderError("AI singing could not be generated. Check the singing engine configuration.")

        if not output_path.is_file():
            raise SingingProviderError("The AI singing provider did not return a WAV file.")
        try:
            with wave.open(str(output_path), "rb") as wav_file:
                if wav_file.getnframes() <= 0 or wav_file.getframerate() <= 0:
                    raise SingingProviderError("The AI singing provider returned an empty WAV file.")
        except wave.Error as error:
            raise SingingProviderError("The AI singing provider returned an invalid WAV file.") from error
        return output_path
