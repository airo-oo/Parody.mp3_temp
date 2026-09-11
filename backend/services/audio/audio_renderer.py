"""Render timed neutral-voice fragments to a safely normalized WAV file."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from services.audio.singing_engine import VoiceSegment


class AudioRenderError(RuntimeError):
    """Raised when WAV rendering cannot complete."""


def render_wav(segments: tuple[VoiceSegment, ...], output_path: Path, sample_rate: int = 22050) -> float:
    """Mix segments, normalize peaks, and export a mono 16-bit PCM WAV."""
    if not segments:
        raise AudioRenderError("There are no audio segments to render.")
    frame_count = max(
        round(segment.start * sample_rate) + len(segment.samples)
        for segment in segments
    )
    if frame_count <= 0:
        raise AudioRenderError("The rendered audio has no duration.")
    mix = [0.0] * frame_count
    for segment in segments:
        start_frame = round(segment.start * sample_rate)
        for offset, sample in enumerate(segment.samples):
            mix[start_frame + offset] += sample
    peak = max((abs(sample) for sample in mix), default=0.0)
    if peak == 0:
        raise AudioRenderError("The audio engine produced silence.")
    scale = min(1.0, 0.92 / peak)
    pcm = b"".join(
        struct.pack("<h", max(-32767, min(32767, round(sample * scale * 32767))))
        for sample in mix
    )
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm)
    except (OSError, wave.Error) as error:
        raise AudioRenderError("The WAV file could not be written.") from error
    return frame_count / sample_rate
