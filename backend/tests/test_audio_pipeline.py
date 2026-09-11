"""Tests for the dependency-free melody-aligned demo audio pipeline."""

import json
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from models import AudioGenerationRequest
from routes.audio import generate_parody_audio
from services.audio import audio_pipeline
from services.audio.audio_renderer import render_wav
from services.audio.lyric_aligner import AlignmentError, align_lyrics_to_melody, extract_lyric_syllables
from services.audio.melody_analyzer import Melody, MelodyError, MelodyNote, load_melody
from services.audio.providers.diffsinger import DiffSingerCliProvider, SingingConfigurationError, build_singing_request
from services.audio.singing_engine import RealSingingEngine, VoiceSegment
from services.lyric_analyzer import split_word_syllables


class AudioPipelineTests(unittest.TestCase):
    def test_lyric_syllable_extraction_preserves_repeated_chorus(self) -> None:
        syllables = extract_lyric_syllables("[Chorus]\nExam week calling\nExam week calling")
        self.assertGreater(len(syllables), 0)
        halfway = len(syllables) // 2
        self.assertEqual([item.text for item in syllables[:halfway]], [item.text for item in syllables[halfway:]])

    def test_word_syllable_split_matches_lightweight_estimator(self) -> None:
        self.assertEqual(len(split_word_syllables("exam")), 2)

    def test_demo_melody_loads(self) -> None:
        melody = load_melody("demo-melody-001")
        self.assertGreater(melody.tempo, 0)
        self.assertGreater(len(melody.notes), 0)

    def test_invalid_melody_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "demo_melody.json").write_text(json.dumps({"tempo": 0, "notes": []}), encoding="utf-8")
            with self.assertRaises(MelodyError):
                load_melody("demo-melody-001", Path(directory))

    def test_short_lyric_aligns_to_many_notes(self) -> None:
        aligned = align_lyrics_to_melody("Exam", load_melody("demo-melody-001"))
        self.assertEqual(len(aligned.syllables), 2)
        self.assertGreater(aligned.syllables[0].note_count, 1)

    def test_long_lyric_is_not_truncated(self) -> None:
        lyrics = "banana " * 100
        aligned = align_lyrics_to_melody(lyrics, load_melody("demo-melody-001"))
        self.assertEqual(len(aligned.syllables), len(extract_lyric_syllables(lyrics)))

    def test_more_syllables_than_notes_share_timing(self) -> None:
        melody = Melody("tiny", 100, (MelodyNote(60, 0.0, 1.0),))
        aligned = align_lyrics_to_melody("banana banana", melody)
        self.assertGreater(len(aligned.syllables), 1)
        self.assertTrue(all(item.pitch == 60 for item in aligned.syllables))

    def test_more_notes_than_syllables_allow_sustain(self) -> None:
        melody = Melody("wide", 100, tuple(MelodyNote(60 + index, index * 0.2, 0.2) for index in range(4)))
        aligned = align_lyrics_to_melody("Exam", melody)
        self.assertTrue(all(item.note_count >= 1 for item in aligned.syllables))

    def test_empty_lyrics_fail_cleanly(self) -> None:
        with self.assertRaises(AlignmentError):
            align_lyrics_to_melody("[Verse]\n\n", load_melody("demo-melody-001"))

    def test_renderer_creates_a_wav(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "voice.wav"
            duration = render_wav((VoiceSegment(0.0, (0.1, -0.1, 0.1)),), output, sample_rate=10)
            self.assertTrue(output.exists())
            self.assertGreater(duration, 0)

    def test_pipeline_creates_non_zero_duration_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous_directory = audio_pipeline.GENERATED_DIRECTORY
            audio_pipeline.GENERATED_DIRECTORY = Path(directory)
            try:
                generated = audio_pipeline.generate_audio("Exam week is calling\nCoffee keeps me going")
                output = Path(directory) / generated.filename
                self.assertTrue(output.exists())
                with wave.open(str(output), "rb") as wav_file:
                    self.assertGreater(wav_file.getnframes() / wav_file.getframerate(), 0)
            finally:
                audio_pipeline.GENERATED_DIRECTORY = previous_directory

    def test_audio_route_returns_a_safe_generated_url(self) -> None:
        response = generate_parody_audio(AudioGenerationRequest(parody_lyrics="Exam week is calling"))
        self.assertTrue(response.success)
        self.assertTrue(response.audio_url.startswith("/generated/parody_"))
        self.assertEqual(response.format, "wav")
        self.assertEqual(response.engine, "demo")

    def test_real_engine_initializes_without_provider_credentials(self) -> None:
        engine = RealSingingEngine(provider=DiffSingerCliProvider(command="runner --score {score_path} --output {output_path}"))
        self.assertEqual(engine.voice, "default")

    def test_real_engine_requires_a_configured_command(self) -> None:
        with patch.dict(os.environ, {"DIFFSINGER_COMMAND": ""}, clear=False):
            with self.assertRaises(SingingConfigurationError):
                DiffSingerCliProvider()._arguments(Path("score.json"), Path("voice.wav"))

    def test_singing_request_preserves_pitch_timing_and_phrases(self) -> None:
        aligned = align_lyrics_to_melody("Exam week\nCoffee now", load_melody("demo-melody-001"))
        request = build_singing_request(aligned)
        self.assertEqual(request.tempo, 100)
        self.assertEqual(len(request.notes), len(aligned.syllables))
        self.assertEqual(request.notes[0].pitch, aligned.syllables[0].pitch)
        self.assertEqual(request.notes[0].start, round(aligned.syllables[0].start, 5))
        self.assertTrue(any(note.phrase == 1 for note in request.notes))

    def test_real_engine_mode_returns_a_configuration_error_without_fallback(self) -> None:
        with patch.dict(os.environ, {"SINGING_ENGINE": "real", "DIFFSINGER_COMMAND": ""}, clear=False):
            with self.assertRaises(audio_pipeline.AudioConfigurationError):
                audio_pipeline.generate_audio("Exam week is calling")

    def test_provider_writes_and_validates_real_engine_wav_response(self) -> None:
        request = build_singing_request(align_lyrics_to_melody("Exam week", load_melody("demo-melody-001")))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "provider.wav"
            provider = DiffSingerCliProvider(command="runner --score {score_path} --output {output_path}")

            def fake_run(arguments, **_kwargs):
                score_path = Path(arguments[arguments.index("--score") + 1])
                score = json.loads(score_path.read_text(encoding="utf-8"))
                self.assertEqual(score["notes"][0]["pitch"], request.notes[0].pitch)
                with wave.open(str(output), "wb") as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(22050)
                    wav_file.writeframes(b"\x00\x00" * 22050)
                return __import__("subprocess").CompletedProcess(arguments, 0)

            with patch("services.audio.providers.diffsinger.subprocess.run", side_effect=fake_run):
                returned = provider.synthesize(request, output)
            self.assertEqual(returned, output)
            with wave.open(str(output), "rb") as wav_file:
                self.assertEqual(wav_file.getnframes() / wav_file.getframerate(), 1)

    def test_regenerated_lyrics_create_independent_demo_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous_directory = audio_pipeline.GENERATED_DIRECTORY
            audio_pipeline.GENERATED_DIRECTORY = Path(directory)
            try:
                first = audio_pipeline.generate_audio("Exam week is calling")
                second = audio_pipeline.generate_audio("Coffee keeps me going")
                self.assertNotEqual(first.filename, second.filename)
                self.assertTrue((Path(directory) / first.filename).exists())
                self.assertTrue((Path(directory) / second.filename).exists())
            finally:
                audio_pipeline.GENERATED_DIRECTORY = previous_directory

    def test_real_engine_configuration_error_is_safe_at_route_boundary(self) -> None:
        with patch.dict(os.environ, {"SINGING_ENGINE": "real", "DIFFSINGER_COMMAND": ""}, clear=False):
            with self.assertRaises(HTTPException) as raised:
                generate_parody_audio(AudioGenerationRequest(parody_lyrics="Exam week is calling"))
        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("AI singing is not configured", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
