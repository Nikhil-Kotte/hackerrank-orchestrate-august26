from router.features import build_features
from router.retrieval import analogous_history, has_same_context_history
from router.rules import decide

OUTPUT_COLUMNS = (
    "message_id",
    "action",
    "message_type",
    "reason",
    "confidence",
    "evidence_message_ids",
)

def media_text_for(dataset, message, extractor):
    media_id = message["media_id"]
    if not media_id:
        return ""
    return extractor.text_for(media_id, dataset.media_path(message["media_type"], media_id))


def _evidence(candidates, decision, has_context=True):
    # Withheld when nothing shares the sender/business/group, even if a textually close row
    # exists elsewhere: sample_msg_052 has a byte-identical prior message and wants `none`.
    if not candidates or not has_context:
        return "none"
    if decision.rule in ("history_suppression", "marketing_fatigue", "repeated_forwards"):
        wanted = candidates[:2]
    else:
        wanted = candidates[:1]
    return ";".join(row["message_id"] for row in wanted)


def route_message(dataset, message, extractor):
    media_text = media_text_for(dataset, message, extractor)
    text = " ".join(part for part in (message["message_text"], media_text) if part)
    features = build_features(dataset, message, media_text)
    decision = decide(features)
    candidates = analogous_history(dataset, message, text)

    return {
        "message_id": message["message_id"],
        "action": decision.action,
        "message_type": decision.message_type,
        "reason": decision.reason,
        "confidence": f"{decision.confidence:.2f}",
        "evidence_message_ids": _evidence(
            candidates, decision, has_same_context_history(dataset, message)
        ),
    }


def route_all(dataset, extractor):
    return [route_message(dataset, message, extractor) for message in dataset.messages]
