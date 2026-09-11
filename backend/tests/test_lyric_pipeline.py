"""Tests for the lyric-only parody generation pipeline."""

import unittest

from models import ParodyRequest
from services.lyric_analyzer import analyze_lyrics, estimate_syllables
from services.lyric_validator import validate_parody
from services.parody_generator import ParodyDraft, generate_preview_parody, generate_with_llm


class LyricAnalysisTests(unittest.TestCase):
    def test_short_lyrics_preserve_line_count(self) -> None:
        request = ParodyRequest(lyrics="Go\nNow", theme="exam week", mood="Funny", chaos=20)
        result = generate_preview_parody(request)
        self.assertEqual(result.parody_lyrics.count("\n"), request.lyrics.count("\n"))

    def test_multiple_sections_and_labels_are_detected(self) -> None:
        lyrics = "[Verse 1]\nI study late\n\n[Chorus]\nCoffee keeps me awake"
        analysis = analyze_lyrics(lyrics)
        self.assertTrue(analysis.lines[0].is_section_label)
        self.assertTrue(analysis.lines[2].is_blank)
        self.assertTrue(analysis.lines[3].is_section_label)

    def test_repeated_lines_are_marked(self) -> None:
        analysis = analyze_lyrics("Same hook\nSame hook\nA new line")
        self.assertEqual(analysis.lines[1].repeats_line, 0)

    def test_syllable_estimator_handles_punctuation_and_contractions(self) -> None:
        self.assertGreaterEqual(estimate_syllables("Don't panic, it's exam-night!"), 4)

    def test_syllable_estimator_handles_hyphenated_words(self) -> None:
        self.assertGreaterEqual(estimate_syllables("all-nighter"), 3)


class PreviewGeneratorTests(unittest.TestCase):
    def test_engineering_exam_theme_is_present(self) -> None:
        request = ParodyRequest(lyrics="We work all night\nThe lab is bright", theme="engineering exams", mood="Funny", chaos=35)
        result = generate_preview_parody(request)
        self.assertIn("engineering", result.parody_lyrics.lower())

    def test_repetition_is_preserved_in_preview(self) -> None:
        request = ParodyRequest(lyrics="Run away\nRun away\nPlease", theme="exam week", mood="Dramatic", chaos=50)
        result = generate_preview_parody(request)
        lines = result.parody_lyrics.splitlines()
        self.assertEqual(lines[0], lines[1])

    def test_moods_and_chaos_values_keep_layout(self) -> None:
        lyrics = "I am ready\nFor the test\n\nI am ready"
        for mood in ("Funny", "Sad", "Chaotic"):
            for chaos in (0, 45, 100):
                with self.subTest(mood=mood, chaos=chaos):
                    result = generate_preview_parody(
                        ParodyRequest(lyrics=lyrics, theme="exam week", mood=mood, chaos=chaos)
                    )
                    self.assertEqual(result.parody_lyrics.split("\n").__len__(), lyrics.split("\n").__len__())


class ValidationTests(unittest.TestCase):
    def test_validator_rewards_preserved_structure_and_repetition(self) -> None:
        request = ParodyRequest(lyrics="[Verse]\nNight falls\nNight falls", theme="exam", mood="Funny", chaos=30)
        source = analyze_lyrics(request.lyrics)
        quality = validate_parody(source, "[Verse]\nExam calls\nExam calls", request)
        self.assertEqual(quality.structure_score, 100.0)
        self.assertGreaterEqual(quality.syllable_score, 70.0)

    def test_validator_rejects_added_lines(self) -> None:
        request = ParodyRequest(lyrics="One line\nTwo lines", theme="exam", mood="Funny", chaos=30)
        quality = validate_parody(analyze_lyrics(request.lyrics), "Exam line\nTwo lines\nExtra", request)
        self.assertEqual(quality.structure_score, 0.0)

    def test_llm_orchestrator_returns_structured_contract(self) -> None:
        request = ParodyRequest(lyrics="[Verse]\nNight falls\nNight falls", theme="exam", mood="Funny", chaos=30)
        calls = []

        def request_draft(_messages: list[dict[str, str]]) -> ParodyDraft:
            calls.append(True)
            return ParodyDraft(
                title="Exam Calls",
                parody_lyrics="[Verse]\nExam calls\nExam calls",
                short_description="A funny exam parody.",
            )

        result = generate_with_llm(request, request_draft)
        self.assertEqual(result.generation_mode, "ai")
        self.assertEqual(result.parody_lyrics.splitlines()[0], "[Verse]")
        self.assertGreaterEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
