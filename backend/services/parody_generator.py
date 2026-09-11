"""Generation orchestration: analysis, structured drafting, validation, and rewrites."""

from __future__ import annotations

import re
from collections.abc import Callable

from pydantic import BaseModel, Field

from models import ParodyRequest, ParodyResponse
from services.lyric_analyzer import LyricAnalysis, analyze_lyrics, estimate_word_syllables, normalize_line
from services.lyric_validator import ParodyQuality, validate_parody


MAX_REWRITE_PASSES = 3


class ParodyDraft(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    parody_lyrics: str = Field(min_length=1, max_length=12000)
    short_description: str = Field(min_length=1, max_length=500)


DraftRequester = Callable[[list[dict[str, str]]], ParodyDraft]


SYSTEM_PROMPT = """You write polished, singable parody lyrics from lyrics supplied directly by a user.
Never claim to recognize the song, retrieve lyrics, or know the melody. Preserve the supplied layout
exactly: same total line count, blank lines, section labels, repeated lines, and section order. For every
lyrical line, target the supplied syllable count (usually within one) and its concise rhythmic shape.
Keep rhyme relationships where the blueprint identifies them. Make a coherent story about the requested
theme across every section. Mood and chaos affect imagery and jokes, but chaos is never random filler.
Use conversational English that is easy to sing. Return only the requested structured draft."""


def _initial_prompt(request: ParodyRequest, analysis: LyricAnalysis) -> str:
    return f"""STAGE 1 ANALYSIS (already completed; use it internally)
Line blueprint:
{analysis.prompt_blueprint()}

STAGE 2 GENERATION
Original lyrics, supplied by the user:
---
{request.lyrics}
---
Theme: {request.theme}
Mood: {request.mood}
Chaos: {request.chaos}/100

Write the full parody now. Do not add labels that the user did not supply, and do not add commentary."""


def _rewrite_prompt(request: ParodyRequest, analysis: LyricAnalysis, draft: ParodyDraft, quality: ParodyQuality) -> str:
    return f"""VALIDATION RESULT
Structure score: {quality.structure_score}; syllable score: {quality.syllable_score};
rhythm score: {quality.rhythm_score}; rhyme score: {quality.rhyme_score}; overall: {quality.overall_score}.
{quality.rewrite_feedback()}

Original line blueprint:
{analysis.prompt_blueprint()}

Current full parody draft:
---
{draft.parody_lyrics}
---
Theme: {request.theme}; mood: {request.mood}; chaos: {request.chaos}/100.
Return a complete improved draft, not just changed lines."""


def generate_with_llm(request: ParodyRequest, request_draft: DraftRequester) -> ParodyResponse:
    """Use at most three validation-driven attempts and return the best complete draft."""
    analysis = analyze_lyrics(request.lyrics)
    best_draft: ParodyDraft | None = None
    best_quality: ParodyQuality | None = None
    prompt = _initial_prompt(request, analysis)

    for _ in range(MAX_REWRITE_PASSES):
        draft = request_draft([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ])
        quality = validate_parody(analysis, draft.parody_lyrics, request)
        if best_quality is None or quality.overall_score > best_quality.overall_score:
            best_draft, best_quality = draft, quality
        if quality.passes:
            break
        prompt = _rewrite_prompt(request, analysis, draft, quality)

    if best_draft is None:
        raise ValueError("The parody writer returned no draft.")
    return ParodyResponse(
        title=best_draft.title,
        parody_lyrics=best_draft.parody_lyrics,
        short_description=best_draft.short_description,
        generation_mode="ai",
    )


def _theme_options(theme: str, chaos: int) -> tuple[str, ...]:
    words = tuple(normalize_line(theme).split()) or ("trouble",)
    lowered = " ".join(words)
    options = list(words)
    if "exam" in lowered or "study" in lowered or "engineering" in lowered:
        options.extend(("exam", "notes", "deadline", "coffee", "formula", "panic"))
    else:
        options.extend(("plans", "trouble", "deadline", "coffee"))
    if chaos >= 60:
        options.extend(("mayhem", "disaster"))
    return tuple(dict.fromkeys(options))


def _replace_one_word(line: str, options: tuple[str, ...]) -> str:
    words = list(re.finditer(r"[A-Za-z]+(?:['’][A-Za-z]+)?", line))
    if not words:
        return line
    selector = sum(ord(character) for character in normalize_line(line))
    option = options[selector % len(options)]
    replacement_syllables = estimate_word_syllables(option)
    target = min(
        range(len(words)),
        key=lambda index: (abs(estimate_word_syllables(words[index].group(0)) - replacement_syllables), index),
    )
    chosen = words[target]
    if chosen.group(0).istitle():
        option = option.title()
    return f"{line[:chosen.start()]}{option}{line[chosen.end():]}"


def generate_preview_parody(request: ParodyRequest) -> ParodyResponse:
    """Provide a deterministic, layout-preserving preview when no LLM credential exists."""
    analysis = analyze_lyrics(request.lyrics)
    options = _theme_options(request.theme, request.chaos)
    primary_theme_word = normalize_line(request.theme).split()[0]
    replacements: dict[str, str] = {}
    output: list[str] = []
    first_lyric_line = True
    for line in analysis.lines:
        if line.is_blank or line.is_section_label:
            output.append(line.text)
            continue
        key = normalize_line(line.text)
        if key not in replacements:
            line_options = (primary_theme_word,) if first_lyric_line else options
            replacements[key] = _replace_one_word(line.text, line_options)
        output.append(replacements[key])
        first_lyric_line = False
    return ParodyResponse(
        title=f"{request.theme.title()}: The {request.mood.title()} Cut"[:160],
        parody_lyrics="\n".join(output),
        short_description=(
            f"A structure-preserving {request.mood.lower()} preview about {request.theme}. "
            "Add an OpenAI key to enable iterative AI lyric writing."
        ),
        generation_mode="demo",
    )
