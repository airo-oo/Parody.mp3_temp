"""Replaceable singing-engine interface and the lightweight demo implementation."""

from __future__ import annotations

import math
import tempfile
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from services.audio.lyric_aligner import AlignedLyrics
from services.audio.providers.diffsinger import DiffSingerCliProvider, SingingProviderError, build_singing_request


@dataclass(frozen=True)
class VoiceSegment:
    start: float
    samples: tuple[float, ...]


class SingingEngine(ABC):
    """A melody-aware singing engine; implementations never receive plain text alone."""

    @abstractmethod
    def synthesize(self, aligned_lyrics: AlignedLyrics, sample_rate: int) -> tuple[VoiceSegment, ...]:
        """Create timed vocal fragments from syllables that already carry note timing."""

    def render(self, aligned_lyrics: AlignedLyrics, output_path: Path, sample_rate: int) -> float:
        """Render the synthesized fragments; providers may override for native WAV output."""
        from services.audio.audio_renderer import render_wav

        return render_wav(self.synthesize(aligned_lyrics, sample_rate), output_path, sample_rate)


def _midi_to_frequency(pitch: int) -> float:
    return 440.0 * 2 ** ((pitch - 69) / 12)


def _vowel_colour(syllable: str) -> tuple[float, float]:
    """Choose gentle formant-like harmonics from the syllable's final vowel."""
    lower = syllable.lower()
    if "i" in lower or "e" in lower:
        return 2.2, 3.4
    if "o" in lower or "u" in lower:
        return 1.8, 2.7
    return 2.0, 3.0


class DemoSingingEngine(SingingEngine):
    """A generic synthetic vowel voice: melodic, audible, and not an artist clone."""

    def synthesize(self, aligned_lyrics: AlignedLyrics, sample_rate: int) -> tuple[VoiceSegment, ...]:
        segments: list[VoiceSegment] = []
        for syllable in aligned_lyrics.syllables:
            frame_count = max(1, round(syllable.duration * sample_rate))
            frequency = _midi_to_frequency(syllable.pitch)
            harmonic_one, harmonic_two = _vowel_colour(syllable.text)
            attack = max(1, min(round(sample_rate * 0.025), frame_count // 3))
            release = max(1, min(round(sample_rate * 0.05), frame_count // 3))
            samples: list[float] = []
            for frame in range(frame_count):
                time = frame / sample_rate
                envelope = min(1.0, frame / attack, (frame_count - frame) / release)
                tone = (
                    math.sin(2 * math.pi * frequency * time)
                    + 0.32 * math.sin(2 * math.pi * frequency * harmonic_one * time)
                    + 0.16 * math.sin(2 * math.pi * frequency * harmonic_two * time)
                )
                samples.append(0.20 * envelope * tone)
            segments.append(VoiceSegment(start=syllable.start, samples=tuple(samples)))
        return tuple(segments)


class RealSingingEngine(SingingEngine):
    """Authorized DiffSinger-backed engine that consumes the project alignment score.

    This class deliberately has no artist or commercial-voice selection.  The
    model selected by the local provider must be one the project owner may use.
    """

    def __init__(self, voice: str = "default", provider: DiffSingerCliProvider | None = None) -> None:
        self.voice = voice
        self.provider = provider or DiffSingerCliProvider()

    def synthesize(self, aligned_lyrics: AlignedLyrics, sample_rate: int) -> tuple[VoiceSegment, ...]:
        """Return provider audio as a timed segment for callers that need raw samples."""
        with tempfile.TemporaryDirectory(prefix="parody-real-voice-") as directory:
            output_path = Path(directory) / "voice.wav"
            self._generate_wav(aligned_lyrics, output_path)
            try:
                with wave.open(str(output_path), "rb") as wav_file:
                    if wav_file.getsampwidth() != 2 or wav_file.getcomptype() != "NONE":
                        raise SingingProviderError("The AI singing provider must return 16-bit PCM WAV audio.")
                    raw_samples = wav_file.readframes(wav_file.getnframes())
                    samples = tuple(
                        int.from_bytes(raw_samples[index:index + 2], "little", signed=True) / 32767.0
                        for index in range(0, len(raw_samples), 2 * wav_file.getnchannels())
                    )
            except wave.Error as error:
                raise SingingProviderError("The AI singing provider returned an invalid WAV file.") from error
        return (VoiceSegment(start=0.0, samples=samples),)

    def _generate_wav(self, aligned_lyrics: AlignedLyrics, output_path: Path) -> Path:
        return self.provider.synthesize(build_singing_request(aligned_lyrics, self.voice), output_path)

    def render(self, aligned_lyrics: AlignedLyrics, output_path: Path, sample_rate: int) -> float:
        self._generate_wav(aligned_lyrics, output_path)
        try:
            with wave.open(str(output_path), "rb") as wav_file:
                return wav_file.getnframes() / wav_file.getframerate()
        except wave.Error as error:
            raise SingingProviderError("The AI singing provider returned an invalid WAV file.") from error
