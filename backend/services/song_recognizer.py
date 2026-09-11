"""Small, local-only fuzzy song recognizer for a project-owned catalog."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from models import RecognitionResponse, SongMatch
from services.lyric_normalizer import normalize_lyrics, normalized_lines, tokens


HIGH_CONFIDENCE = 0.85
POSSIBLE_CONFIDENCE = 0.70
AMBIGUITY_MARGIN = 0.06
MAX_CANDIDATES = 3
STOP_WORDS = frozenset({"a", "an", "and", "are", "be", "but", "for", "i", "in", "is", "it", "me", "my", "of", "oh", "on", "the", "to", "we", "with", "you", "your"})
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CatalogSong:
    id: str
    title: str
    artist: str
    normalized_lyrics: str
    lyric_tokens: frozenset[str]
    chunks: tuple[str, ...]


def _character_ngrams(value: str, size: int = 3) -> set[str]:
    padded = f"  {value}  "
    return {padded[index : index + size] for index in range(max(0, len(padded) - size + 1))}


def _dice_similarity(left: str, right: str) -> float:
    left_grams, right_grams = _character_ngrams(left), _character_ngrams(right)
    if not left_grams or not right_grams:
        return 0.0
    return 2 * len(left_grams & right_grams) / (len(left_grams) + len(right_grams))


class SongRecognizer:
    """Preprocess a small JSON catalog in memory and score short lyric excerpts."""

    def __init__(self, catalog_path: Path | None = None) -> None:
        self.catalog_path = catalog_path or Path(__file__).resolve().parent.parent / "data" / "songs.json"
        self._last_mtime_ns: int | None = None
        self._songs: tuple[CatalogSong, ...] = ()
        self._document_frequency: dict[str, int] = {}

    def _read_catalog_lyrics(self, entry: dict[str, object]) -> str | None:
        """Load a project-local lyric file without allowing a path to escape data/lyrics."""
        lyrics_file = entry.get("lyrics_file")
        if isinstance(lyrics_file, str) and lyrics_file.strip():
            lyrics_directory = (self.catalog_path.parent / "lyrics").resolve()
            candidate = (lyrics_directory / lyrics_file).resolve()
            if candidate.parent != lyrics_directory:
                return None
            try:
                lyrics = candidate.read_text(encoding="utf-8")
            except OSError:
                return None
            return lyrics if lyrics.strip() else None

        # Preserve support for existing project-owned demo entries. New entries
        # should use lyrics_file so song metadata never duplicates lyric text.
        lyrics = entry.get("lyrics")
        return lyrics if isinstance(lyrics, str) and lyrics.strip() else None

    def _load_catalog(self) -> None:
        try:
            modified = self.catalog_path.stat().st_mtime_ns
        except OSError:
            self._last_mtime_ns, self._songs, self._document_frequency = None, (), {}
            return
        if modified == self._last_mtime_ns:
            return
        try:
            payload = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._last_mtime_ns, self._songs, self._document_frequency = modified, (), {}
            return
        if not isinstance(payload, list):
            self._last_mtime_ns, self._songs, self._document_frequency = modified, (), {}
            return

        songs: list[CatalogSong] = []
        seen_ids: set[str] = set()
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            identifier, title, artist = (entry.get(key) for key in ("id", "title", "artist"))
            lyrics = self._read_catalog_lyrics(entry)
            if not all(isinstance(item, str) and item.strip() for item in (identifier, title, artist, lyrics)):
                continue
            clean_id = identifier.strip()
            if clean_id in seen_ids:
                continue
            seen_ids.add(clean_id)
            lyric_lines = normalized_lines(lyrics)
            full_text = " ".join(lyric_lines)
            if not full_text:
                continue
            chunks = {full_text}
            for size in range(1, min(4, len(lyric_lines)) + 1):
                chunks.update(" ".join(lyric_lines[start : start + size]) for start in range(len(lyric_lines) - size + 1))
            songs.append(
                CatalogSong(
                    id=clean_id, title=title.strip(), artist=artist.strip(), normalized_lyrics=full_text,
                    lyric_tokens=frozenset(tokens(full_text)), chunks=tuple(chunks),
                )
            )
        frequency: dict[str, int] = {}
        for song in songs:
            for token in song.lyric_tokens - STOP_WORDS:
                frequency[token] = frequency.get(token, 0) + 1
        self._last_mtime_ns, self._songs, self._document_frequency = modified, tuple(songs), frequency
        LOGGER.info("Loaded catalog songs: %s", len(songs))

    def _distinctive_overlap(self, query_tokens: set[str], chunk: str) -> float:
        meaningful = query_tokens - STOP_WORDS
        if len(meaningful) < 2:
            return 0.0
        total = sum(math.log((len(self._songs) + 1) / (self._document_frequency.get(token, 0) + 1)) + 1 for token in meaningful)
        if total == 0:
            return 0.0
        chunk_tokens = set(tokens(chunk))
        matched = sum(
            math.log((len(self._songs) + 1) / (self._document_frequency.get(token, 0) + 1)) + 1
            for token in meaningful & chunk_tokens
        )
        return matched / total

    def _score_song(self, query: str, query_tokens: set[str], song: CatalogSong) -> float:
        best = 0.0
        for chunk in song.chunks:
            chunk_tokens = set(tokens(chunk))
            phrase = SequenceMatcher(None, query, chunk).ratio()
            exact_coverage = len(query_tokens & chunk_tokens) / max(1, len(query_tokens))
            fuzzy_coverage = sum(
                max((SequenceMatcher(None, token, candidate).ratio() for candidate in chunk_tokens), default=0.0)
                for token in query_tokens
            ) / max(1, len(query_tokens))
            token_overlap = 0.45 * exact_coverage + 0.55 * fuzzy_coverage
            char_ngrams = _dice_similarity(query, chunk)
            distinctive = self._distinctive_overlap(query_tokens, chunk)
            score = 0.38 * phrase + 0.30 * token_overlap + 0.20 * char_ngrams + 0.12 * distinctive
            best = max(best, score)

        meaningful = query_tokens - STOP_WORDS
        if len(query_tokens) < 3 or len(meaningful) < 2:
            return min(best, 0.65)
        return min(1.0, best)

    def recognize(self, lyrics: str) -> RecognitionResponse:
        self._load_catalog()
        query = normalize_lyrics(lyrics)
        query_tokens = set(tokens(query))
        if not query or not self._songs:
            return RecognitionResponse(matched=False, confidence=0.0)
        scored = sorted(
            ((self._score_song(query, query_tokens, song), song) for song in self._songs),
            key=lambda item: item[0], reverse=True,
        )
        best_score, best_song = scored[0]
        LOGGER.info(
            "Top candidates: %s",
            ", ".join(f"{song.title} — {score:.2f}" for score, song in scored[:MAX_CANDIDATES]),
        )
        candidates = [
            SongMatch(id=song.id, title=song.title, artist=song.artist, confidence=round(score, 3))
            for score, song in scored[:MAX_CANDIDATES]
            if score >= POSSIBLE_CONFIDENCE
        ]
        ambiguous = len(scored) > 1 and best_score >= POSSIBLE_CONFIDENCE and best_score - scored[1][0] < AMBIGUITY_MARGIN
        if best_score >= HIGH_CONFIDENCE and not ambiguous:
            LOGGER.info("Selected: %s", best_song.title)
            return RecognitionResponse(
                matched=True,
                confidence=round(best_score, 3),
                song=SongMatch(id=best_song.id, title=best_song.title, artist=best_song.artist, confidence=round(best_score, 3)),
            )
        if candidates:
            return RecognitionResponse(matched=False, confidence=round(best_score, 3), candidates=candidates)
        return RecognitionResponse(matched=False, confidence=round(best_score, 3))
