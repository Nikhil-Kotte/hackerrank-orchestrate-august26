import re
from difflib import SequenceMatcher

from router.context import Dataset

WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str | None) -> set[str]:
    return set(WORD.findall((text or "").lower()))


def similarity(left: str | None, right: str | None) -> float:
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    ratio = SequenceMatcher(None, (left or "").lower(), (right or "").lower()).ratio()
    return round(0.5 * jaccard + 0.5 * ratio, 6)


def _same_context(message: dict, row: dict) -> bool:
    kind = message["conversation_type"]
    if kind == "business":
        return row["business_id"] == message["business_id"] and message["business_id"]
    if kind == "group":
        return (
            row["group_id"] == message["group_id"]
            and row["sender_user_id"] == message["sender_user_id"]
        )
    return row["sender_user_id"] == message["sender_user_id"] and message["sender_user_id"]


# Same sender/business/group is a strong hint, not a precondition: the recipient's reaction to
# the same content in a neighbouring conversation is still evidence. Recall is flat for any
# weight in 0.05-0.30 and falls at 0.50, so this acts as a tie-break rather than a tuned knob.
CONTEXT_BONUS = 0.15


def analogous_history(dataset: Dataset, message: dict, text: str | None = None) -> list[dict]:
    text = message["message_text"] if text is None else text
    candidates = [
        row
        for row in dataset.history_for(message["user_id"])
        if row["message_id"] != message.get("message_id")
    ]

    def rank(row: dict) -> tuple[float, str]:
        score = similarity(text, row["message_text"])
        if _same_context(message, row):
            score += CONTEXT_BONUS
        return (-score, row["message_id"])

    return sorted(candidates, key=rank)


def has_same_context_history(dataset: Dataset, message: dict) -> bool:
    """Whether any history shares this message's sender/business/group.

    Evidence is withheld entirely when nothing does - `sample_msg_052` has a byte-identical
    prior message and its ground truth is still `none`, so a close text match on its own is
    not what the column is asking for.
    """
    return any(
        row["message_id"] != message.get("message_id") and _same_context(message, row)
        for row in dataset.history_for(message["user_id"])
    )


def wider_history(dataset: Dataset, message: dict) -> list[dict]:
    """Same user and conversation, ignoring the sender - used when the sender is new."""
    kind = message["conversation_type"]
    if kind != "group" or not message["group_id"]:
        return []
    return [
        row
        for row in dataset.history_for(message["user_id"])
        if row["group_id"] == message["group_id"]
        and row["message_id"] != message.get("message_id")
    ]
