from dataclasses import dataclass

CONFIDENCE_BANDS = {
    "notify": (0.85, 0.91),
    "digest": (0.78, 0.84),
    "mute": (0.81, 0.87),
}

# Keyed by the rule variant that fired. Every string except brand_impersonation is
# verbatim from dataset/sample_messages.csv; that one follows the same register.
REASON_BANK = {
    "routing_instruction": (
        "The message tries to instruct the router, but the routing decision should be "
        "based on the actual content and risk.",
        0.85,
    ),
    "credential_request": (
        "The message asks for urgent OTP or account verification through a suspicious flow.",
        0.81,
    ),
    "fake_support_pressure": (
        "The message uses fake support language and account-blocking pressure to push the "
        "user into action.",
        0.87,
    ),
    "stranger_credential_request": (
        "This is the first message from the sender and it asks for sensitive verification "
        "or payment.",
        0.87,
    ),
    "brand_impersonation": (
        "The sender is imitating a known brand from a domain that brand does not own.",
        0.86,
    ),
    "reported_pressure": (
        "The user has reported messages like this one before, and it uses payment pressure "
        "to force an immediate action.",
        0.87,
    ),
    "admin_time_sensitive": (
        "A trusted group admin sent a time-sensitive update that should interrupt the user.",
        0.89,
    ),
    "school_admin_update": (
        "A school admin sent a same-day operational update that the user is likely to need "
        "immediately.",
        0.87,
    ),
    "work_deadline": (
        "The message is from a work context and contains a direct deadline or meeting "
        "dependency.",
        0.85,
    ),
    "direct_request": (
        "The sender directly asks this user for a response or action.",
        0.87,
    ),
    "close_contact_urgent": (
        "A close contact sent a short urgent request that should interrupt the user.",
        0.87,
    ),
    "business_order_update": (
        "A verified business is sending an update that matches the user's recent order "
        "history.",
        0.91,
    ),
    "business_booking_reminder": (
        "A verified business is sending a reminder that matches the user's recent booking "
        "history.",
        0.89,
    ),
    "marketing_fatigue": (
        "The user has opted out of or repeatedly dismissed similar marketing messages.",
        0.81,
    ),
    "repeated_forwards": (
        "The sender has a pattern of repeated forwards or greetings that the user usually "
        "ignores.",
        0.85,
    ),
    "history_suppression": (
        "Similar historical messages were ignored, dismissed, or muted by this user.",
        0.85,
    ),
    "opted_in_promotion": (
        "The message is promotional but matches a topic or business the user has opted into.",
        0.78,
    ),
    "known_interest_promotion": (
        "The message matches the user's known interests but is still low priority.",
        0.84,
    ),
    "low_priority_offer": (
        "The offer is potentially relevant, but it does not need immediate attention.",
        0.84,
    ),
    "group_information": (
        "The message is useful group information, but it is not urgent enough to interrupt "
        "the user.",
        0.84,
    ),
    "harmless_greeting": (
        "The message is a harmless greeting that can be read later.",
        0.82,
    ),
    "business_non_urgent": (
        "A verified business is sending a legitimate but non-urgent update.",
        0.78,
    ),
    "business_informational": (
        "The verified business message is legitimate but does not require immediate attention.",
        0.84,
    ),
    "trusted_no_urgency": (
        "The sender is trusted, but the message has no urgent action or safety relevance.",
        0.82,
    ),
    "unfamiliar_no_risk": (
        "The sender is unfamiliar, but the message does not show urgency, payment pressure, "
        "or safety risk.",
        0.82,
    ),
    "no_urgency": (
        "The message is safe casual chat with no urgent action required.",
        0.80,
    ),
    "do_not_disturb": (
        "The message is worth seeing, but it arrived inside the user's do not disturb "
        "window, so it waits for the digest.",
        0.80,
    ),
    "group_muted": (
        "The user has muted this group, so the update waits for the digest instead of "
        "interrupting.",
        0.80,
    ),
    "heavy_dismisser_promotion": (
        "The user has no history with this sender and dismisses most of the notifications "
        "they receive, so an unsolicited offer is not worth surfacing.",
        0.81,
    ),
}

TRUSTED_OPEN_RATE = 0.6
SUPPRESSION_DISMISS_RATE = 0.5
# Consulted only when there is no sender-specific history to consult instead. Sits in the top
# quartile of per-user dismissal in daily_notification_summary.csv (median 0.36, max 0.73).
HEAVY_DISMISSER_RATIO = 0.45


@dataclass(frozen=True)
class Features:
    content_kind: str = "unknown"
    asks_for_credentials: bool = False
    uses_support_language: bool = False
    contains_routing_instruction: bool = False
    is_reported_pressure: bool = False
    directly_addressed: bool = False
    is_work_context: bool = False
    sender_known: bool = True
    sender_open_rate: float = 0.0
    business_verified: bool = False
    is_brand_impersonation: bool = False
    is_feedback_request: bool = False
    is_promotional: bool = False
    promotions_opted_in: bool = False
    promotions_opted_out: bool = False
    matches_known_interest: bool = False
    has_transactional_relationship: bool = False
    sender_is_group_admin: bool = False
    group_is_high_trust: bool = False
    group_is_school: bool = False
    is_actionable_form: bool = False
    is_time_sensitive: bool = False
    in_do_not_disturb: bool = False
    prior_dismiss_rate: float = 0.0
    prior_muted_after: bool = False
    group_muted_by_user: bool = False
    has_sender_history: bool = False
    daily_dismiss_ratio: float = 0.0
    evidence_count: int = 0


@dataclass(frozen=True)
class Decision:
    action: str
    message_type: str
    rule: str
    reason: str
    confidence: float


# How far calibration may move a decision off its rule's base value. Deliberately tiny: the
# bands are 0.06-0.07 wide and most rule bases sit on a band edge, so anything larger would
# displace almost every rule from the value the samples actually attest.
CALIBRATION_SPAN = 0.02
STRONG_EVIDENCE_ROWS = 3


def _support(features):
    """How well-evidenced this decision is, in [0, 1].

    Two independent things make a decision trustworthy: how much history it rests on, and how
    one-sided that history is. A single dismissal is weaker evidence than five, and a 50/50
    split is weaker than a clean sweep whatever the count.
    """
    volume = min(features.evidence_count, STRONG_EVIDENCE_ROWS) / STRONG_EVIDENCE_ROWS
    # Distance from the coin flip, rescaled to [0, 1].
    behaviour = max(
        abs(features.prior_dismiss_rate - 0.5),
        abs(features.sender_open_rate - 0.5),
    ) * 2
    return 0.5 * volume + 0.5 * behaviour


def _decision(action, message_type, rule, features=None):
    reason, base = REASON_BANK[rule]
    confidence = base
    if features is not None:
        low, high = CONFIDENCE_BANDS[action]
        # Centred on the rule's base, nudged inward only when the base sits on a band edge:
        # business_order_update starts at the 0.91 ceiling, and a rule pinned to the boundary
        # could otherwise only clamp, expressing no uncertainty at all.
        half = CALIBRATION_SPAN / 2
        centre = min(max(base, low + half), high - half)
        confidence = round(centre + CALIBRATION_SPAN * (_support(features) - 0.5), 2)
    return Decision(
        action=action,
        message_type=message_type,
        rule=rule,
        reason=reason,
        confidence=confidence,
    )


def _credential_rule(features):
    if not features.sender_known:
        return "stranger_credential_request"
    if features.uses_support_language:
        return "fake_support_pressure"
    return "credential_request"


def _digest_rule(features):
    if features.is_promotional:
        if features.promotions_opted_in:
            return "opted_in_promotion"
        if features.matches_known_interest:
            return "known_interest_promotion"
        return "low_priority_offer"
    if features.business_verified:
        return "business_non_urgent" if features.is_feedback_request else "business_informational"
    if features.content_kind == "greeting":
        return "harmless_greeting"
    if features.content_kind == "event":
        return "group_information"
    if not features.sender_known:
        return "unfamiliar_no_risk"
    if features.sender_open_rate >= TRUSTED_OPEN_RATE:
        return "trusted_no_urgency"
    return "no_urgency"


def decide(features):
    decision = _route(features)
    if decision.action != "notify":
        return decision
    # A direct mention still gets through: muting a group is a statement about its ambient
    # chatter, not about being addressed by name.
    if features.group_muted_by_user and not features.directly_addressed:
        return _decision("digest", decision.message_type, "group_muted", features)
    # Undemonstrated by the solved samples; see README. Safety mutes are never softened.
    if features.in_do_not_disturb:
        return _decision("digest", decision.message_type, "do_not_disturb", features)
    return decision


def _route(features):
    if features.contains_routing_instruction:
        return _decision("mute", "scam", "routing_instruction", features)
    # Impersonation outranks the generic credential check: naming the domain the brand does
    # not own is the more specific and more useful claim when both fire.
    if features.is_brand_impersonation:
        return _decision("mute", "scam", "brand_impersonation", features)
    if features.asks_for_credentials:
        return _decision("mute", "scam", _credential_rule(features), features)
    # Sender authority does not clear this one: a group admin account posting a QR payment
    # demand the user has already reported is still the pattern they reported.
    if features.is_reported_pressure:
        return _decision("mute", "scam", "reported_pressure", features)
    if features.directly_addressed and features.sender_known:
        rule = "work_deadline" if features.is_work_context else "direct_request"
        return _decision("notify", features.content_kind, rule, features)
    if features.sender_is_group_admin and features.group_is_high_trust and (
        features.is_time_sensitive
        # A consent form from a school admin needs a parent signature by a date printed on
        # the form itself, which OCR of a blank template never yields.
        or (features.group_is_school and features.is_actionable_form)
    ):
        rule = "school_admin_update" if features.group_is_school else "admin_time_sensitive"
        return _decision("notify", features.content_kind, rule, features)
    if (
        features.is_time_sensitive
        and features.sender_known
        and features.sender_open_rate >= TRUSTED_OPEN_RATE
    ):
        rule = "work_deadline" if features.is_work_context else "close_contact_urgent"
        return _decision("notify", features.content_kind, rule, features)
    if features.is_promotional and features.promotions_opted_out:
        return _decision("mute", features.content_kind, "marketing_fatigue", features)
    if features.prior_muted_after or features.prior_dismiss_rate >= SUPPRESSION_DISMISS_RATE:
        if features.is_promotional:
            rule = "marketing_fatigue"
        elif features.content_kind in ("greeting", "forward"):
            rule = "repeated_forwards"
        else:
            rule = "history_suppression"
        return _decision("mute", features.content_kind, rule, features)
    if (
        features.business_verified
        and features.has_transactional_relationship
        and not features.is_promotional
    ):
        rule = (
            "business_booking_reminder"
            if features.content_kind == "event"
            else "business_order_update"
        )
        return _decision("notify", features.content_kind, rule, features)
    # No reaction history with this sender, so the only behavioral prior left is how the user
    # treats notifications overall. Someone who dismisses most of them does not want an
    # unsolicited offer in their digest either.
    if (
        features.is_promotional
        and not features.promotions_opted_in
        and not features.has_sender_history
        and features.daily_dismiss_ratio >= HEAVY_DISMISSER_RATIO
    ):
        return _decision("mute", features.content_kind, "heavy_dismisser_promotion", features)
    return _decision("digest", features.content_kind, _digest_rule(features))
