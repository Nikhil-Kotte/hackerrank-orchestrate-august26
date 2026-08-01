import hashlib
import json
import sys
from pathlib import Path
from typing import Protocol

AUDIO_SUFFIXES = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm")


class Extractor(Protocol):
    """Anything that turns a media file into text."""

    def text_for(self, media_id: str, file_path: Path | None) -> str: ...


def is_audio(file_path: Path | None) -> bool:
    return bool(file_path) and Path(file_path).suffix.lower() in AUDIO_SUFFIXES


class ByMediaType:
    """Voice notes need a speech model; posters and screenshots need a vision model."""

    def __init__(self, audio: Extractor | None, default: Extractor | None) -> None:
        self.audio = audio
        self.default = default

    def text_for(self, media_id: str, file_path: Path | None) -> str:
        inner = self.audio if (self.audio and is_audio(file_path)) else self.default
        return inner.text_for(media_id, file_path)


class StubExtractor:
    def __init__(self, transcripts: dict) -> None:
        self.transcripts = transcripts

    def text_for(self, media_id: str, file_path: Path | None) -> str:
        return self.transcripts.get(media_id, "")


class NullExtractor:
    def text_for(self, media_id: str, file_path: Path | None) -> str:
        raise RuntimeError(
            "no media extractor configured; set OPENROUTER_API_KEY to refresh the cache"
        )


class CachedExtractor:
    """Replays committed extractions; delegates only on a miss."""

    def __init__(self, inner: Extractor, cache_path: str | Path, refresh: bool = False) -> None:
        self.inner = inner
        self.cache_path = Path(cache_path)
        self.refresh = refresh
        self.entries = self._load()

    def _load(self) -> dict:
        if self.cache_path.exists():
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        return {}

    def text_for(self, media_id: str, file_path: Path | None) -> str:
        key = self._key(media_id, file_path)
        if not self.refresh and key in self.entries:
            return self.entries[key]
        try:
            text = self.inner.text_for(media_id, file_path)
        except Exception as error:
            print(f"warning: media extraction failed for {media_id}: {error}", file=sys.stderr)
            return ""
        self.entries[key] = text
        self._save()
        return text

    def _key(self, media_id: str, file_path: Path | None) -> str:
        path = Path(file_path) if file_path else None
        if path and path.exists():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        else:
            digest = "missing"
        return f"{media_id}:{digest}"

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(self.entries, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
