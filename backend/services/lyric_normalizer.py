"""Safe text normalization shared only by the local song-recognition feature."""

from __future__ import annotations

import re
import unicodedata


def normalize_lyrics(value: str) -> str:
    """Normalize comparison text while retaining Unicode letters and digits."""
    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("’", "'").replace("`", "'").replace("_", " ")
    normalized = re.sub(r"[^\w\s']", " ", normalized, flags=re.UNICODE)
    normalized = normalized.replace("'", "")
    return " ".join(normalized.split())


def normalized_lines(value: str) -> tuple[str, ...]:
    """Return non-empty normalized lines for local phrase-window matching."""
    if not isinstance(value, str):
        return ()
    return tuple(line for line in (normalize_lyrics(item) for item in value.splitlines()) if line)


def tokens(value: str) -> tuple[str, ...]:
    return tuple(normalize_lyrics(value).split())
