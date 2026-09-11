"""Scoring and feedback for structurally faithful parody drafts."""

from __future__ import annotations

from dataclasses import dataclass

from models import ParodyRequest
from services.lyric_analyzer import LyricAnalysis, analyze_lyrics, normalize_line, rhyme_key


@dataclass(frozen=True)
class ParodyQuality:
    structure_score: float
    syllable_score: float
    rhythm_score: float
    rhyme_score: float
    theme_score: float
    singability_score: float
    humor_score: float
    overall_score: float
    failing_line_indexes: tuple[int, ...]

    @property
    def passes(self) -> bool:
        return (
            self.structure_score >= 95
            and self.syllable_score >= 76
            and self.singability_score >= 74
            and self.overall_score >= 76
        )

    def rewrite_feedback(self) -> str:
        if not self.failing_line_indexes:
            return "Improve naturalness and theme detail while preserving the exact layout."
        numbers = ", ".join(str(index + 1) for index in self.failing_line_indexes[:16])
        return (
            f"Rewrite the weak lines {numbers}. Keep all other lines, every blank line, and every "
            "section label in the same position. Match each target syllable count more closely, "
            "use natural phrasing, and preserve repeated hooks exactly."
        )


def _score_syllables(source: LyricAnalysis, candidate: LyricAnalysis) -> tuple[float, list[int]]:
    scores: list[float] = []
    failures: list[int] = []
    for original, parody in zip(source.lines, candidate.lines):
        if original.is_blank or original.is_section_label:
            continue
        difference = abs(original.syllables - parody.syllables)
        tolerance = 1 if original.syllables <= 8 else max(1, round(original.syllables * 0.15))
        if difference <= tolerance:
            # A one-syllable deviation can still be naturally singable; penalize it gently.
            score = 100.0 - 15.0 * difference / tolerance
        else:
            score = max(0.0, 85.0 - 85.0 * (difference - tolerance) / max(1, tolerance * 2))
        scores.append(score)
        if difference > tolerance:
            failures.append(original.index)
    return (sum(scores) / len(scores) if scores else 100.0), failures


def _score_structure(source: LyricAnalysis, candidate: LyricAnalysis) -> tuple[float, list[int]]:
    if source.line_count != candidate.line_count:
        return 0.0, list(range(min(source.line_count, candidate.line_count), max(source.line_count, candidate.line_count)))
    failures: list[int] = []
    score = 100.0
    for original, parody in zip(source.lines, candidate.lines):
        if original.is_blank != parody.is_blank:
            score -= 12
            failures.append(original.index)
        if original.is_section_label and original.text.strip() != parody.text.strip():
            score -= 15
            failures.append(original.index)
        if original.repeats_line is not None:
            reference = candidate.lines[original.repeats_line]
            if normalize_line(parody.text) != normalize_line(reference.text):
                score -= 8
                failures.append(original.index)
    return max(0.0, score), failures


def _score_rhyme(source: LyricAnalysis, candidate: LyricAnalysis) -> float:
    rhyme_pairs = []
    lyrical = [line for line in source.lines if not line.is_blank and not line.is_section_label]
    for offset, first in enumerate(lyrical):
        for second in lyrical[offset + 1 :]:
            if first.rhyme_key and first.rhyme_key == second.rhyme_key:
                rhyme_pairs.append((first.index, second.index))
    if not rhyme_pairs:
        return 80.0
    matches = sum(
        rhyme_key(candidate.lines[first].text) == rhyme_key(candidate.lines[second].text)
        for first, second in rhyme_pairs
    )
    return 100.0 * matches / len(rhyme_pairs)


def _score_theme(parody: LyricAnalysis, theme: str) -> float:
    theme_words = set(normalize_line(theme).split())
    lyric_lines = [line for line in parody.lines if not line.is_blank and not line.is_section_label]
    if not lyric_lines or not theme_words:
        return 0.0
    used_lines = sum(bool(theme_words & set(normalize_line(line.text).split())) for line in lyric_lines)
    coverage = used_lines / len(lyric_lines)
    return min(100.0, 25.0 + coverage * 75.0)


def validate_parody(source: LyricAnalysis, parody_lyrics: str, request: ParodyRequest) -> ParodyQuality:
    """Score a draft using structure, meter proxies, rhymes, and theme coverage."""
    candidate = analyze_lyrics(parody_lyrics)
    structure, structure_failures = _score_structure(source, candidate)
    if source.line_count != candidate.line_count:
        return ParodyQuality(structure, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, tuple(structure_failures))

    syllables, syllable_failures = _score_syllables(source, candidate)
    rhyme = _score_rhyme(source, candidate)
    theme = _score_theme(candidate, request.theme)
    word_ratios = []
    for original, parody in zip(source.lines, candidate.lines):
        if original.is_blank or original.is_section_label:
            continue
        word_ratios.append(min(1.0, len(parody.words) / max(1, len(original.words))))
    rhythm = 0.65 * syllables + 35.0 * (sum(word_ratios) / len(word_ratios) if word_ratios else 1.0)
    singability = 0.75 * syllables + 0.25 * rhythm
    humor = min(100.0, 45.0 + theme * 0.45 + min(request.chaos, 70) * 0.15)
    overall = (
        structure * 0.15
        + syllables * 0.20
        + rhythm * 0.15
        + rhyme * 0.10
        + theme * 0.15
        + singability * 0.10
        + humor * 0.10
        + 70.0 * 0.05
    )
    failures = tuple(dict.fromkeys(structure_failures + syllable_failures))
    return ParodyQuality(
        round(structure, 1), round(syllables, 1), round(rhythm, 1), round(rhyme, 1),
        round(theme, 1), round(singability, 1), round(humor, 1), round(overall, 1), failures,
    )
