import csv
from collections import defaultdict
from pathlib import Path

TABLES = [
    "messages",
    "users",
    "groups",
    "group_members",
    "business_accounts",
    "user_business_history",
    "message_history",
    "message_events",
    "images",
    "voice_notes",
    "daily_notification_summary",
]


def _read(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class Dataset:
    def __init__(self, tables: dict, root: Path) -> None:
        self.root = Path(root)
        self.messages = tables["messages"]
        self.users = {row["user_id"]: row for row in tables["users"]}
        self.groups = {row["group_id"]: row for row in tables["groups"]}
        self.businesses = {row["business_id"]: row for row in tables["business_accounts"]}
        self.images = {row["image_id"]: row["file_path"] for row in tables["images"]}
        self.voice_notes = {
            row["voice_note_id"]: row["file_path"] for row in tables["voice_notes"]
        }

        self.history = {row["message_id"]: row for row in tables["message_history"]}

        self._history_by_user = defaultdict(list)
        for row in tables["message_history"]:
            self._history_by_user[row["user_id"]].append(row)

        self._events = {
            (row["user_id"], row["message_id"]): row for row in tables["message_events"]
        }
        self._membership = {
            (row["user_id"], row["group_id"]): row for row in tables["group_members"]
        }
        self._business_history = {
            (row["user_id"], row["business_id"]): row
            for row in tables["user_business_history"]
        }

        self._daily_totals = defaultdict(lambda: [0, 0])
        for row in tables["daily_notification_summary"]:
            totals = self._daily_totals[row["user_id"]]
            totals[0] += int(row["notifications_sent"] or 0)
            totals[1] += int(row["notifications_dismissed"] or 0)

    @classmethod
    def load(cls, root: Path | str) -> "Dataset":
        root = Path(root)
        return cls({name: _read(root / f"{name}.csv") for name in TABLES}, root)

    def history_for(self, user_id: str) -> list[dict]:
        return self._history_by_user.get(user_id, [])

    def event_for(self, user_id: str, message_id: str) -> dict | None:
        return self._events.get((user_id, message_id))

    def membership_for(self, user_id: str, group_id: str) -> dict | None:
        return self._membership.get((user_id, group_id))

    def business_history_for(self, user_id: str, business_id: str) -> dict | None:
        return self._business_history.get((user_id, business_id))

    def daily_dismiss_ratio(self, user_id: str) -> float:
        """Share of all notifications this user dismissed, across the whole summary window."""
        sent, dismissed = self._daily_totals.get(user_id, (0, 0))
        return dismissed / sent if sent else 0.0

    def media_path(self, media_type: str, media_id: str) -> Path | None:
        if media_type == "image":
            relative = self.images.get(media_id)
        elif media_type == "voice":
            relative = self.voice_notes.get(media_id)
        else:
            relative = None
        if not relative:
            return None
        return self.root / relative
