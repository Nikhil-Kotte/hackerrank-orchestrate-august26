import json
from pathlib import Path

from router.rules import Decision, Features

DEFAULT_AUDIT_LOG = "cache/decision_log.jsonl"

# Every rule in REASON_BANK, classified into the block that fired. Safety overrides can only
# mute and are never softened; urgency drives notify; suppression and relationship are the
# personalized weights; default is the digest fall-through (and the only rows the optional
# adjudicator may revisit).
RULE_BLOCKS = {
    # safety override
    "routing_instruction": "safety",
    "brand_impersonation": "safety",
    "credential_request": "safety",
    "stranger_credential_request": "safety",
    "fake_support_pressure": "safety",
    "reported_pressure": "safety",
    # direct urgency
    "admin_time_sensitive": "urgency",
    "school_admin_update": "urgency",
    "work_deadline": "urgency",
    "direct_request": "urgency",
    "close_contact_urgent": "urgency",
    "business_order_update": "urgency",
    "business_booking_reminder": "urgency",
    # personalized suppression
    "marketing_fatigue": "suppression",
    "repeated_forwards": "suppression",
    "history_suppression": "suppression",
    "heavy_dismisser_promotion": "suppression",
    # relationship-weighted routing
    "opted_in_promotion": "relationship",
    "known_interest_promotion": "relationship",
    "low_priority_offer": "relationship",
    "business_non_urgent": "relationship",
    "business_informational": "relationship",
    "harmless_greeting": "relationship",
    "group_information": "relationship",
    # weak global prior / default digest
    "unfamiliar_no_risk": "default",
    "trusted_no_urgency": "default",
    "no_urgency": "default",
    "group_muted": "default",
    "do_not_disturb": "default",
}

BLOCKS = ("safety", "urgency", "suppression", "relationship", "default")


class DecisionAuditor:
    """Per-run structured log of every routing decision, the agent's thought process.

    Truncates on construction so one execution yields exactly one trace: a decision log is a
    record of a run, not a ledger. Writes JSONL so it can be tailed or loaded line by line.
    """

    def __init__(self, path: Path | str = DEFAULT_AUDIT_LOG) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def record(
        self, message: dict, features: Features, decision: Decision, evidence: str
    ) -> None:
        entry = {
            "message_id": message["message_id"],
            "conversation_type": message["conversation_type"],
            "action": decision.action,
            "message_type": decision.message_type,
            "rule": decision.rule,
            "block": RULE_BLOCKS[decision.rule],
            "confidence": decision.confidence,
            "evidence_message_ids": evidence,
            "features": {
                "content_kind": features.content_kind,
                "sender_known": features.sender_known,
                "sender_open_rate": features.sender_open_rate,
                "is_time_sensitive": features.is_time_sensitive,
                "is_promotional": features.is_promotional,
                "prior_dismiss_rate": features.prior_dismiss_rate,
                "group_muted_by_user": features.group_muted_by_user,
                "in_do_not_disturb": features.in_do_not_disturb,
                "daily_dismiss_ratio": features.daily_dismiss_ratio,
                "evidence_count": features.evidence_count,
            },
        }
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
