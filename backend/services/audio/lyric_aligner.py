"""Map all parody syllables to a fixed melody without dropping lyric content."""

from __future__ import annotations

from dataclasses import dataclass

from services.audio.melody_analyzer import Melody, MelodyNote
from services.lyric_analyzer import is_section_label, split_word_syllables, words_in


class AlignmentError(ValueError):
    """Raised when lyrics cannot form a usable syllable plan."""


@dataclass(frozen=True)
class LyricSyllable:
    text: str
    line_index: int
    line_text: str


@dataclass(frozen=True)
class AlignedSyllable:
    text: str
    line_index: int
    line_text: str
    pitch: int
    start: float
    duration: float
    note_count: int


@dataclass(frozen=True)
class AlignedLyrics:
    tempo: int
    syllables: tuple[AlignedSyllable, ...]
    duration: float


def extract_lyric_syllables(parody_lyrics: str) -> tuple[LyricSyllable, ...]:
    """Preserve input line order while ignoring blank and explicit section labels."""
    syllables: list[LyricSyllable] = []
    for line_index, line in enumerate(parody_lyrics.splitlines()):
        if not line.strip() or is_section_label(line):
            continue
        for word in words_in(line):
            syllables.extend(
                LyricSyllable(text=piece, line_index=line_index, line_text=line)
                for piece in split_word_syllables(word)
            )
    return tuple(syllables)


def _span_duration(notes: tuple[MelodyNote, ...]) -> float:
    return notes[-1].start + notes[-1].duration - notes[0].start


def align_lyrics_to_melody(parody_lyrics: str, melody: Melody) -> AlignedLyrics:
    """Distribute notes or syllables proportionally; neither side is silently truncated."""
    syllables = extract_lyric_syllables(parody_lyrics)
    if not syllables:
        raise AlignmentError("The parody does not contain usable words for audio generation.")
    notes = melody.notes
    if not notes:
        raise AlignmentError("The melody does not contain notes.")

    aligned: list[AlignedSyllable] = []
    if len(notes) >= len(syllables):
        # A syllable may sustain across several notes when the melody has extra detail.
        for index, syllable in enumerate(syllables):
            start_index = index * len(notes) // len(syllables)
            end_index = max(start_index + 1, (index + 1) * len(notes) // len(syllables))
            note_slice = notes[start_index:end_index]
            aligned.append(
                AlignedSyllable(
                    text=syllable.text, line_index=syllable.line_index, line_text=syllable.line_text,
                    pitch=note_slice[0].pitch, start=note_slice[0].start,
                    duration=_span_duration(note_slice), note_count=len(note_slice),
                )
            )
    else:
        # Several short syllables can share one note, each receiving an equal time slice.
        for note_index, note in enumerate(notes):
            start_index = note_index * len(syllables) // len(notes)
            end_index = max(start_index + 1, (note_index + 1) * len(syllables) // len(notes))
            group = syllables[start_index:end_index]
            duration = note.duration / len(group)
            for offset, syllable in enumerate(group):
                aligned.append(
                    AlignedSyllable(
                        text=syllable.text, line_index=syllable.line_index, line_text=syllable.line_text,
                        pitch=note.pitch, start=note.start + offset * duration,
                        duration=duration, note_count=1,
                    )
                )
    end_time = max(item.start + item.duration for item in aligned)
    return AlignedLyrics(tempo=melody.tempo, syllables=tuple(aligned), duration=end_time)
