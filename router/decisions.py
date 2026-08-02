import hashlib
import json
import sys
from pathlib import Path

DEFAULT_DECISIONS = "cache/decisions.json"


class Decisions:
    """Content-hashed verdict cache for the adjudicator, mirroring CachedExtractor.

    The key is message_id plus a digest of the canonicalized context (sorted keys, stable
    field order), so a verdict is replayed only when the same context is adjudicated again.
    """

    def __init__(self, path: Path | str = DEFAULT_DECISIONS, refresh: bool = False) -> None:
        self.path = Path(path)
        self.refresh = refresh
        self.entries = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"warning: ignoring corrupt cache {self.path}", file=sys.stderr)
            return {}

    def key(self, message_id: str, context: dict) -> str:
        canonical = json.dumps(
            context, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        return f"{message_id}:{digest}"

    def get(self, message_id: str, context: dict) -> dict | None:
        if self.refresh:
            return None
        return self.entries.get(self.key(message_id, context))

    def put(self, message_id: str, context: dict, verdict: dict) -> None:
        self.entries[self.key(message_id, context)] = verdict
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.entries, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
