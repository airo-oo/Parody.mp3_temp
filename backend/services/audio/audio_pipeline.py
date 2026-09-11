"""Coordinate melody loading, validation, selected singing, and WAV rendering."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from services.audio.audio_renderer import AudioRenderError
from services.audio.lyric_aligner import AlignmentError, align_lyrics_to_melody
from services.audio.melody_analyzer import MelodyError, load_melody
from services.audio.providers.diffsinger import SingingConfigurationError, SingingProviderError
from services.audio.singing_engine import DemoSingingEngine, RealSingingEngine, SingingEngine


LOGGER = logging.getLogger(__name__)
GENERATED_DIRECTORY = Path(__file__).resolve().parents[2] / "generated"
MAX_SYLLABLES = 1000


class AudioPipelineError(RuntimeError):
    """A friendly error that can be safely returned by the audio API."""


class AudioConfigurationError(AudioPipelineError):
    """The selected singing engine needs local setup before it can run."""


@dataclass(frozen=True)
class GeneratedAudio:
    filename: str
    duration: float
    format: str = "wav"
    engine: str = "demo"

    @property
    def url(self) -> str:
        return f"/generated/{self.filename}"


def _select_engine(voice: str) -> tuple[str, SingingEngine]:
    load_dotenv()
    engine_name = os.getenv("SINGING_ENGINE", "demo").strip().lower()
    if engine_name == "demo":
        return engine_name, DemoSingingEngine()
    if engine_name == "real":
        return engine_name, RealSingingEngine(voice=voice)
    raise AudioConfigurationError("SINGING_ENGINE must be either 'demo' or 'real'.")


def generate_audio(
    parody_lyrics: str,
    melody_id: str = "demo-melody-001",
    voice: str = "default",
) -> GeneratedAudio:
    """Generate one project-scoped WAV with an explicitly selected singing engine."""
    try:
        LOGGER.info("[AUDIO] Loading melody")
        melody = load_melody(melody_id)
        LOGGER.info("[AUDIO] Analyzing lyrics and aligning syllables")
        aligned = align_lyrics_to_melody(parody_lyrics, melody)
        if len(aligned.syllables) > MAX_SYLLABLES:
            raise AudioPipelineError("The parody is too long to render as demo audio.")
        engine_name, engine = _select_engine(voice)
        LOGGER.info("[AUDIO] Synthesizing with configured %s singing engine", engine_name)
        filename = f"parody_{uuid4().hex}.wav"
        LOGGER.info("[AUDIO] Rendering WAV")
        duration = engine.render(aligned, GENERATED_DIRECTORY / filename, sample_rate=22050)
        LOGGER.info("[AUDIO] Complete")
        return GeneratedAudio(filename=filename, duration=round(duration, 3), engine=engine_name)
    except SingingConfigurationError as error:
        raise AudioConfigurationError(str(error)) from error
    except (MelodyError, AlignmentError, AudioRenderError, SingingProviderError) as error:
        raise AudioPipelineError(str(error)) from error
