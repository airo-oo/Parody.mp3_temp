"""Coverage for local-catalog lyric recognition and confidence behavior."""

import json
import tempfile
import unittest
from pathlib import Path

from services.song_recognizer import SongRecognizer


CATALOG = [
    {
        "id": "midnight-library",
        "title": "Midnight Library",
        "artist": "Demo Ensemble",
        "lyrics": "When the midnight library lights begin to glow\nI count the paper planets in a quiet row\nTurn another page and let the city sleep\nAll the little promises are ours to keep",
    },
    {
        "id": "copper-kettle",
        "title": "Copper Kettle Morning",
        "artist": "Demo Ensemble",
        "lyrics": "Copper kettle calling on a rainy morning train\nSteam across the window writes a silver name\nCarry all the daylight in a worn out case",
    },
    {
        "id": "lantern-walk",
        "title": "Lantern Walk",
        "artist": "Demo Ensemble",
        "lyrics": "Silver lantern calling through the rain\nWe walk beside the river to the station",
    },
    {
        "id": "lantern-wait",
        "title": "Lantern Wait",
        "artist": "Demo Ensemble",
        "lyrics": "Silver lantern calling through the rain\nWe wait beside the river for the train",
    },
    {"id": "bad-entry", "title": "Missing lyrics", "artist": "Demo Ensemble"},
]


class SongRecognizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.catalog_path = Path(self.temp_directory.name) / "songs.json"
        self.catalog_path.write_text(json.dumps(CATALOG), encoding="utf-8")
        self.recognizer = SongRecognizer(self.catalog_path)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def test_exact_catalog_lyrics_are_high_confidence(self) -> None:
        result = self.recognizer.recognize("When the midnight library lights begin to glow")
        self.assertTrue(result.matched)
        self.assertEqual(result.song.id, "midnight-library")
        self.assertGreaterEqual(result.confidence, 0.85)

    def test_partial_distinctive_lyrics_match(self) -> None:
        result = self.recognizer.recognize("I count the paper planets in a quiet row\nTurn another page and let the city sleep")
        self.assertTrue(result.matched)
        self.assertEqual(result.song.title, "Midnight Library")

    def test_capitalization_does_not_change_match(self) -> None:
        result = self.recognizer.recognize("WHEN THE MIDNIGHT LIBRARY LIGHTS BEGIN TO GLOW")
        self.assertTrue(result.matched)

    def test_punctuation_and_unicode_apostrophes_are_normalized(self) -> None:
        result = self.recognizer.recognize("I COUNT the paper planets, in a quiet row!!!")
        self.assertTrue(result.matched)

    def test_one_distinctive_phrase_is_possible_match(self) -> None:
        result = self.recognizer.recognize("midnite library lights begin to glo")
        self.assertFalse(result.matched)
        self.assertEqual(result.candidates[0].id, "midnight-library")
        self.assertGreaterEqual(result.confidence, 0.70)

    def test_minor_spelling_difference_is_tolerated(self) -> None:
        result = self.recognizer.recognize("copper ketle calling on a rainy morning train")
        self.assertTrue(result.matched)
        self.assertEqual(result.song.id, "copper-kettle")

    def test_unrelated_lyrics_are_not_matched(self) -> None:
        result = self.recognizer.recognize("Volcano bicycles calculate a purple submarine")
        self.assertFalse(result.matched)
        self.assertIsNone(result.song)
        self.assertEqual(result.candidates, [])

    def test_short_generic_lyrics_are_not_confident(self) -> None:
        result = self.recognizer.recognize("I love you")
        self.assertFalse(result.matched)
        self.assertLess(result.confidence, 0.70)

    def test_similar_top_candidates_are_returned_for_choice(self) -> None:
        result = self.recognizer.recognize("Silver lantern calling through the rain")
        self.assertFalse(result.matched)
        self.assertGreaterEqual(len(result.candidates), 2)

    def test_empty_input_is_safe(self) -> None:
        result = self.recognizer.recognize("   ")
        self.assertFalse(result.matched)
        self.assertEqual(result.confidence, 0.0)

    def test_extremely_long_input_is_safe(self) -> None:
        result = self.recognizer.recognize(("When the midnight library lights begin to glow ") * 200)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.confidence, 0.0)

    def test_repeated_lines_are_safe(self) -> None:
        result = self.recognizer.recognize("When the midnight library lights begin to glow\n" * 3)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.confidence, 0.0)

    def test_malformed_catalog_entries_are_skipped(self) -> None:
        result = self.recognizer.recognize("Missing lyrics")
        self.assertFalse(result.matched)

    def test_missing_catalog_is_safe(self) -> None:
        result = SongRecognizer(Path(self.temp_directory.name) / "not-found.json").recognize("anything at all")
        self.assertFalse(result.matched)
        self.assertEqual(result.confidence, 0.0)

    def test_lyrics_file_catalog_entry_is_loaded_locally(self) -> None:
        data_directory = Path(self.temp_directory.name)
        lyrics_directory = data_directory / "lyrics"
        lyrics_directory.mkdir()
        (lyrics_directory / "local.txt").write_text(
            "Purple comet dances over an orange lake\nThe little satellite hums awake",
            encoding="utf-8",
        )
        catalog = data_directory / "file-catalog.json"
        catalog.write_text(
            json.dumps([{
                "id": "local-song", "title": "Local Song", "artist": "Demo Artist", "lyrics_file": "local.txt",
            }]),
            encoding="utf-8",
        )
        result = SongRecognizer(catalog).recognize("purple comet dances over an orange lake")
        self.assertTrue(result.matched)
        self.assertEqual(result.song.id, "local-song")

    def test_lyrics_file_cannot_escape_the_local_catalog_directory(self) -> None:
        data_directory = Path(self.temp_directory.name)
        (data_directory / "lyrics").mkdir()
        catalog = data_directory / "file-catalog.json"
        catalog.write_text(
            json.dumps([{
                "id": "unsafe", "title": "Unsafe", "artist": "Demo Artist", "lyrics_file": "../outside.txt",
            }]),
            encoding="utf-8",
        )
        result = SongRecognizer(catalog).recognize("anything distinctive here")
        self.assertFalse(result.matched)


if __name__ == "__main__":
    unittest.main()
