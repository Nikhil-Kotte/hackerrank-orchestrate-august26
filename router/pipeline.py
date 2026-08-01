from router.adjudicator import Adjudicator, build_adjudication_context
from router.context import Dataset
from router.features import build_features
from router.media import Extractor
from router.retrieval import analogous_history, has_same_context_history
from router.rules import Decision, decide

OUTPUT_COLUMNS = (
    "message_id",
    "action",
    "message_type",
    "reason",
    "confidence",
    "evidence_message_ids",
)

def media_text_for(dataset: Dataset, message: dict, extractor: Extractor) -> str:
    media_id = message["media_id"]
    if not media_id:
        return ""
    return extractor.text_for(media_id, dataset.media_path(message["media_type"], media_id))


def _evidence(candidates: list[dict], decision: Decision, has_context: bool = True) -> str:
    # Withheld when nothing shares the sender/business/group, even if a textually close row
    # exists elsewhere: sample_msg_052 has a byte-identical prior message and wants `none`.
    if not candidates or not has_context:
        return "none"
    if decision.rule in ("history_suppression", "marketing_fatigue", "repeated_forwards"):
        wanted = candidates[:2]
    else:
        wanted = candidates[:1]
    return ";".join(row["message_id"] for row in wanted)


def route_message(
    dataset: Dataset,
    message: dict,
    extractor: Extractor,
    adjudicator: Adjudicator | None = None,
) -> dict:
    media_text = media_text_for(dataset, message, extractor)
    text = " ".join(part for part in (message["message_text"], media_text) if part)
    features = build_features(dataset, message, media_text)
    decision = decide(features)
    candidates = analogous_history(dataset, message, text)

    has_context = has_same_context_history(dataset, message)
    # Only a row that fell through to the default digest branch is offered to the model. Safety
    # and suppression mutes are decided by named rules and never reach it, so the 51-row mute
    # set cannot be changed by the model. The model's grounding is honoured as evidence only
    # when same-context history exists, matching the rules' own evidence policy.
    if adjudicator is not None and decision.default_branch:
        context = build_adjudication_context(message, features, media_text, candidates[:3])
        decision, grounding = adjudicator.decision_for(features, context)
        evidence = grounding if (grounding and has_context) else _evidence(candidates, decision, has_context)
    else:
        evidence = _evidence(candidates, decision, has_context)

    return {
        "message_id": message["message_id"],
        "action": decision.action,
        "message_type": decision.message_type,
        "reason": decision.reason,
        "confidence": f"{decision.confidence:.2f}",
        "evidence_message_ids": evidence,
    }


def route_all(
    dataset: Dataset, extractor: Extractor, adjudicator: Adjudicator | None = None
) -> list[dict]:
    return [
        route_message(dataset, message, extractor, adjudicator)
        for message in dataset.messages
    ]
