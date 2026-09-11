"""Lightweight, dependency-free analysis of user-supplied lyric structure."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass


WORD_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?|\d+(?:st|nd|rd|th)?")
SECTION_RE = re.compile(
    r"^\s*(?:\[[^\]]{1,40}\]|(?:verse|chorus|pre[- ]?chorus|bridge|intro|outro|hook)\s*\d*\s*:?)\s*$",
    re.IGNORECASE,
)
VOWEL_GROUP_RE = re.compile(r"[aeiouy]+", re.IGNORECASE)

SYLLABLE_EXCEPTIONS = {
    "are": 1,
    "every": 2,
    "fire": 1,
    "hour": 1,
    "queue": 1,
    "people": 2,
    "rhythm": 2,
    "science": 2,
    "world": 1,
}


@dataclass(frozen=True)
class LineAnalysis:
    index: int
    text: str
    words: tuple[str, ...]
    syllables: int
    rhyme_key: str
    is_blank: bool
    is_section_label: bool
    repeats_line: int | None


@dataclass(frozen=True)
class LyricAnalysis:
    lines: tuple[LineAnalysis, ...]
    section_starts: tuple[int, ...]

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def prompt_blueprint(self) -> str:
        """Return compact per-line constraints for an LLM prompt."""
        blueprint = []
        for line in self.lines:
            if line.is_blank:
                blueprint.append(f"{line.index + 1:02d}: blank line")
            elif line.is_section_label:
                blueprint.append(f"{line.index + 1:02d}: section label — copy exactly")
            else:
                repeated = f", repeat of line {line.repeats_line + 1}" if line.repeats_line is not None else ""
                blueprint.append(
                    f"{line.index + 1:02d}: {line.syllables} syllables, "
                    f"{len(line.words)} words, rhyme key '{line.rhyme_key or '-'}'{repeated}"
                )
        return "\n".join(blueprint)


def words_in(text: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in WORD_RE.finditer(text))


def normalize_line(text: str) -> str:
    return " ".join(word.lower() for word in words_in(text))


def is_section_label(text: str) -> bool:
    return bool(SECTION_RE.match(text))


def estimate_word_syllables(word: str) -> int:
    """Estimate syllables without failing on names, punctuation, or contractions."""
    cleaned = re.sub(r"[^a-z]", "", word.lower().replace("’", "'"))
    if not cleaned:
        return 0
    if cleaned in SYLLABLE_EXCEPTIONS:
        return SYLLABLE_EXCEPTIONS[cleaned]
    if cleaned.isdigit():
        return len(cleaned)

    groups = len(VOWEL_GROUP_RE.findall(cleaned))
    if groups == 0:
        return 1
    if cleaned.endswith("e") and not cleaned.endswith(("le", "ye")) and groups > 1:
        groups -= 1
    if cleaned.endswith("ed") and len(cleaned) > 3 and not cleaned.endswith(("ted", "ded")) and groups > 1:
        groups -= 1
    if cleaned.endswith("es") and len(cleaned) > 3 and not cleaned.endswith(("ses", "xes", "zes", "ches", "shes")) and groups > 1:
        groups -= 1
    return max(1, groups)


def estimate_syllables(text: str) -> int:
    return sum(estimate_word_syllables(word) for word in words_in(text))


def split_word_syllables(word: str) -> tuple[str, ...]:
    """Split a word into pronounceable-looking pieces for the demo singing engine.

    This deliberately stays lightweight: it mirrors the existing syllable estimator
    rather than adding a second dependency or pretending to be a phonetic dictionary.
    """
    visible_word = word.strip()
    cleaned = re.sub(r"[^A-Za-z]", "", visible_word)
    target_count = estimate_word_syllables(visible_word)
    if not cleaned or target_count <= 1:
        return (visible_word,) if visible_word else ()

    vowel_groups = list(VOWEL_GROUP_RE.finditer(cleaned))
    boundaries = [group.end() for group in vowel_groups[:-1]]
    if len(boundaries) >= target_count - 1:
        boundaries = boundaries[: target_count - 1]
    else:
        # Unusual words can have fewer visible vowel groups than the heuristic count.
        boundaries = [round(len(cleaned) * index / target_count) for index in range(1, target_count)]

    pieces: list[str] = []
    start = 0
    for boundary in boundaries:
        boundary = max(start + 1, min(len(cleaned) - 1, boundary))
        pieces.append(cleaned[start:boundary])
        start = boundary
    pieces.append(cleaned[start:])
    # Avoid a visually awkward one-letter opening like "E / xam" in the demo voice.
    for index in range(len(pieces) - 1):
        if len(pieces[index]) == 1 and len(pieces[index + 1]) > 1:
            pieces[index] += pieces[index + 1][0]
            pieces[index + 1] = pieces[index + 1][1:]
    return tuple(piece for piece in pieces if piece)


def rhyme_key(text: str) -> str:
    """Return a forgiving spelling-based ending key for perfect and near-rhyme checks."""
    words = words_in(text)
    if not words:
        return ""
    word = re.sub(r"[^a-z]", "", words[-1].lower())
    if not word:
        return ""
    last_vowel = max((word.rfind(vowel) for vowel in "aeiouy"), default=-1)
    if last_vowel < 0:
        return word[-3:]
    suffix = word[last_vowel:]
    suffix = suffix.replace("igh", "i").replace("y", "i")
    return suffix[-4:]


def analyze_lyrics(lyrics: str) -> LyricAnalysis:
    """Map the exact supplied layout and its practical singability constraints."""
    raw_lines = lyrics.split("\n")
    seen: dict[str, int] = {}
    sections: list[int] = []
    lines: list[LineAnalysis] = []
    for index, text in enumerate(raw_lines):
        blank = not text.strip()
        label = not blank and is_section_label(text)
        normalized = normalize_line(text)
        repeated = seen.get(normalized) if normalized and not label else None
        if normalized and not label and normalized not in seen:
            seen[normalized] = index
        if label or (index == 0 and not blank) or (index > 0 and not blank and not raw_lines[index - 1].strip()):
            sections.append(index)
        lines.append(
            LineAnalysis(
                index=index,
                text=text,
                words=words_in(text),
                syllables=0 if blank or label else estimate_syllables(text),
                rhyme_key="" if blank or label else rhyme_key(text),
                is_blank=blank,
                is_section_label=label,
                repeats_line=repeated,
            )
        )
    return LyricAnalysis(lines=tuple(lines), section_starts=tuple(sections))
