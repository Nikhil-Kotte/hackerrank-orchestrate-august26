import re
import unicodedata

from router.context import Dataset
from router.retrieval import _same_context, analogous_history, wider_history
from router.rules import Features

# Every regex bank below is Latin and ASCII, so a trigger spelled with a lookalike from another
# script slips past all of them. OCR produces these by accident (the poster cache already holds
# a Greek kappa and eta inside otherwise-Latin words) and an attacker can produce them on
# purpose. NFKC folds compatibility forms such as fullwidth digits, but leaves both homoglyphs
# and zero-width characters alone, so those two are handled explicitly.
CONFUSABLES = str.maketrans(
    {
        # Cyrillic
        "А": "A", "В": "B", "Е": "E", "З": "3", "І": "I", "Ј": "J", "К": "K", "М": "M",
        "Н": "H", "О": "O", "Р": "P", "С": "C", "Ѕ": "S", "Т": "T", "У": "Y", "Х": "X",
        "а": "a", "е": "e", "і": "i", "ј": "j", "о": "o", "р": "p", "с": "c", "ѕ": "s",
        "у": "y", "х": "x",
        # Greek
        "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M",
        "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
        "α": "a", "ο": "o", "ρ": "p", "ν": "v",
    }
)


def normalize(text: str) -> str:
    """Fold a message to the alphabet the pattern banks are written in.

    Applied to the lowercased matching text only. Retrieval and the `@mention` scan keep the
    raw string, so evidence selection is unaffected by the fold.
    """
    folded = unicodedata.normalize("NFKC", text).translate(CONFUSABLES)
    return "".join(char for char in folded if unicodedata.category(char) != "Cf")


HIGH_TRUST_GROUPS = {
    "family",
    "extended_family",
    "school_group",
    "coworker",
    "society",
    "caregiving",
    "safety",
    "college_faculty",
    "college_students",
    "dance_class",
}

CREDENTIAL_PATTERNS = [
    r"\botp\b",
    r"\bone[- ]time (pass|code)",
    r"\bpass ?word\b",
    r"\bpin\b",
    r"\bcvv\b",
    r"login code",
    r"verification code",
    r"\b6[- ]digit\b",
    r"verify (your |the )?(account|identity|kyc|wallet|admin)",
    r"confirm (your |the )?(password|otp|identity|card|account)",
    r"re-?verify",
    r"complete (your )?kyc",
    r"complete (pending |the |your )?(account check|verification)",
    r"verify through (this |the )?link",
    r"shar(e|ing) your (account|card|bank) (number|details)",
]

# A brand warning users about OTP fraud, or a courier saying it will not ask, is not asking.
CREDENTIAL_DISCLAIMERS = [
    r"never ask",
    r"never asks",
    r"do not share",
    r"don't share",
    r"we will never",
    r"beware of",
    r"no (payment or otp|otp or payment|otp|payment) is (required|needed)",
    r"(otp|payment|password|pin) is not (required|needed)",
]

PRESSURE_PATTERNS = [
    r"will be blocked",
    r"may be (temporarily )?blocked",
    r"account (will )?(be )?(suspend|deactivat|clos)",
    r"expire[sd]? today",
    r"within \d+ (hours?|minutes?)",
    r"service (may |will )?stops?\b",
    r"last warning",
    r"immediately or",
    r"unless you (login|log in|verify|confirm|complete|pay)",
    r"to avoid (permanent |account )?(lock|closure|block|restriction)",
    r"will be restricted",
    r"window closes",
]

ROUTING_INSTRUCTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|earlier)",
    r"ignore (the )?(sender|safety|risk|spam)",
    r"disregard (all |any )?(previous|prior|the above)",
    r"mark (this |it )?(message )?(as )?(notify|urgent|important|high priority)",
    r"classify (this |it )?(as|to) ",
    r"route (this|it) (message )?(to|as) ",
    r"you are (an? )?(ai|assistant|router|model)",
    # `moderator` but not a bare `admin`: school and society groups post real "Admin note:"
    # messages, and muting those would cost more than the injection shape is worth.
    r"(system|assistant|moderator)[ :_-]*(prompt|note|instruction)",
    r"(note|metadata|instruction)s? for (the )?(notification )?router",
    r"routing (override|instruction)",
    r"(admin|routing|rules?|filter)[ _-]*override",
    r"override (the )?(routing|rules|filter)",
    # Asserting a routing decision the user never made is an instruction wearing a memory.
    r"(approved|authoris|authoriz)\w* (the )?routing",
    r"\b(action|confidence|user_priority|verified_business)\s*=",
    r"do not (mute|filter|classify) this",
]

PAYMENT_PATTERNS = [
    r"\bpay now\b",
    r"pay (rs|inr|₹|\$)",
    r"transfer (rs|inr|₹|\$|the )",
    r"send (the )?(money|payment|amount)",
    r"pending (charge|due|payment)",
    r"outstanding (amount|due)",
    r"\bupi\b",
    r"payment link",
    r"token amount",
    r"booking amount",
    r"(processing|reactivation|clearance) fee",
    r"scan (the |this )?qr",
]

PROMO_PATTERNS = [
    r"\d+\s?%\s?off",
    # Not a bare \boffer\b: "offer letter" is a job document, not a promotion (msg_060).
    r"\boffers?\b(?!\s+(letter|of admission|of employment))",
    r"\bdiscount\b",
    r"\bsale\b",
    r"\bcoupon\b",
    r"\bdeal\b",
    r"limited (time|period|stock)",
    r"reply stop",
    r"unsubscribe",
    r"shop now",
    r"buy now",
    r"\bcashback\b",
    r"tap below to (shop|claim)",
    r"\bselling\b",
    r"per person",
]

# A marketplace group post offering an item is a promotion for the reader.
MARKETPLACE_PATTERNS = [
    r"\bpickup\b",
    r"\bsize [a-z]\b",
    r"\bstill available\b",
    r"\bdm if\b",
    r"\bprice is\b",
    r"\bworn once\b",
]

GREETING_PATTERNS = [
    r"^good (morning|evening|night|afternoon)",
    r"stay (positive|blessed|safe)",
    r"good vibes",
    r"blessings",
    r"hope today is",
    r"happy (sunday|monday|new|birthday|festival)",
]

TIME_PRESSURE_PATTERNS = [
    r"\bimmediately\b",
    r"\basap\b",
    r"right away",
    r"\burgent",
    r"in \d+ (mins?|minutes?|hours?)",
    r"\d+ mins? (max|early|late)",
    r"before (eod|end of day|the deadline)",
    r"\bdue (before|by|today)\b",
    r"timing (has )?changed",
    r"changed to \d",
    # A same-day change to a standing arrangement, as in sample_msg_002.
    r"\b(today|tonight)'?s?\b[^.]{0,80}\binstead of\b",
    r"(cannot|can not|can't) wait",
    r"heads[- ]?up",
    r"\bescalation\b",
    r"\bincident\b",
    r"\bdeadline\b",
    r"come online now",
    r"call (me )?(back )?now",
    r"need (quick |urgent )?help",
    r"\bstuck\b",
]

# "closes at 5 PM", "by 6 PM", "till 7:30 pm" - a wall-clock cutoff. On its own this is just a
# schedule, so it only counts as pressure when SAME_DAY_PATTERN also fires: a deadline three
# weeks out is not an interruption. msg_062's "fire alarm test tomorrow 9 AM" stays digest.
CLOCK_DEADLINE_PATTERNS = [
    r"\b(clos(e|es|ing)|start(s|ing)?|end(s|ing)?|shut(s)?|lock(s)?)\s+(at|by|before)\s+\d{1,2}",
    r"\b(by|before|till|until)\s+\d{1,2}(:\d{2})?\s*(am|pm|noon)\b",
]

SAME_DAY_PATTERN = r"\b(today|tonight|this (evening|afternoon|morning))\b"

# Romanized Hindi carries the same urgency the English bank already catches, and 9 of the 110
# messages use it while 0 of the 30 solved samples do - so nothing else tests this.
#
# These are added to the urgency and de-escalation banks ONLY. Nothing here may reach
# PRESSURE_PATTERNS or CREDENTIAL_PATTERNS: "band ho jayega" means "will close", and mapping it
# onto "will be blocked" would turn a society gate notice into a scam signal. Safety already
# handles Hinglish correctly because \botp\b is language-agnostic.
HINGLISH_TIME_PRESSURE_PATTERNS = [
    r"\bjaldi\b(?!\s+nahi)",
    r"\bturant\b",
    r"\babhi\b",
    r"\b\d+\s*min(ute)?s?\s+me\b",
    r"\b\d+\s*baje\s+tak\b",
    r"nikalna padega",
    r"hata do",
    r"le aao",
    r"kar dena",
]

HINGLISH_DEESCALATION_PATTERNS = [
    r"koi urgency nahi",
    r"koi jaldi nahi",
    r"jaldi nahi hai",
    r"kal dekh lenge",
]

# Senders who explicitly de-escalate are not asking to be let through.
DEESCALATION_PATTERNS = [
    r"nothing urgent",
    r"not urgent",
    r"no rush",
    r"no pressure",
    r"nothing dramatic",
    r"whenever you get time",
    r"no need to (reply|respond)",
    r"when you get \d+ mins?",
]

# A form a parent has to sign and return. OCR of a blank template carries no date or time,
# so the urgency has to come from the artifact itself (img_011 / sample_msg_046).
FORM_PATTERNS = [
    r"consent form",
    r"permission slip",
    r"has permission to participate",
    r"signature of parent",
    r"field trip",
    r"\bcircular\b",
    r"registration form",
    r"form is open",
]

EVENT_PATTERNS = [
    r"\bmeeting\b",
    r"\bappointment\b",
    r"\bschedule[ds]?\b",
    r"\brsvp\b",
    r"\bregistration\b",
    r"\bcircular\b",
    r"\bconsent\b",
    r"\bassembly\b",
    r"form is open",
    r"\bbooking\b",
    r"\bclass\b",
    r"\breminder\b",
    r"\bbus\b",
    r"\btrip\b",
    r"\bevent\b",
    r"\bprescription\b",
]

# Words that make a business message about a real transaction rather than marketing.
TRANSACTION_PATTERNS = [
    r"\border\b",
    r"\bdeliver",
    r"\bshipment\b",
    r"\bappointment\b",
    r"\bbooking\b",
    r"\bpayment\b",
    r"\bclaim\b",
    r"\bprescription\b",
    r"\brefill\b",
    r"\breservation\b",
    r"\bride\b",
    r"\bbill\b",
    r"\bstatement\b",
]

TRANSACTIONAL_RELATIONSHIP_TOKENS = (
    "order",
    "delivery",
    "booking",
    "payment",
    "appointment",
    "account",
    "bill",
    "refill",
    "claim",
    "purchase",
    "reservation",
    "ride",
    "prescription",
    "membership",
)

NON_RELATIONSHIP_TOKENS = ("opted_out", "ignored", "search", "interest", "watchlist")

# A commercial signal in the message's own words. Used to decide whether an attached poster
# is allowed to make the row promotional - see COMMERCIAL_PATTERNS use in build_features.
COMMERCIAL_PATTERNS = [
    r"\bpay\b",
    r"\brs\.?\s*\d",
    r"\bprice\b",
    r"\bsqft\b",
    r"\btoken\b",
    r"\bsale\b",
    r"\bselling\b",
    r"\bplots?\b",
]

SUPPORT_LANGUAGE_PATTERNS = [
    r"\bsupport (alert|team|desk)\b",
    r"\bcustomer support\b",
    r"\bhelpdesk\b",
    r"\bservice team\b",
]

WORK_CONTEXT_PATTERNS = [
    r"\bprod\b",
    r"\bproduction\b",
    r"\bdeploy",
    r"\bclient\b",
    r"\bsprint\b",
    r"\bescalation\b",
    r"\bincident\b",
    r"\bticket\b",
    r"\balert threshold\b",
    r"\bretry count\b",
    r"\breview\b",
    r"\bqueue numbers\b",
    r"\beod\b",
]

FEEDBACK_PATTERNS = [
    r"\bfeedback\b",
    r"\bsurvey\b",
    r"\brate (your|us)\b",
    r"your experience\b",
]

INTEREST_TOKENS = ("interest", "search", "watchlist", "style", "subscription")

YOUNG_DOMAIN_DAYS = 120
LOW_TRUST_REPORTS = 10
# At this many hops the message was blasted at a list, so an @mention inside it is not a
# request aimed at the recipient.
MASS_FORWARD_COUNT = 3


def _matches(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _flag(row: dict | None, column: str) -> bool:
    return bool(row) and row.get(column) == "1"


def _int(row: dict | None, column: str, default: int = 0) -> int:
    if not row:
        return default
    try:
        return int(row[column])
    except (KeyError, TypeError, ValueError):
        return default


def _reaction_history(dataset: Dataset, message: dict, candidates: list[dict]) -> dict:
    events = [dataset.event_for(message["user_id"], row["message_id"]) for row in candidates]
    events = [event for event in events if event]
    if not events:
        return {}
    total = len(events)
    return {
        "open_rate": sum(_int(e, "message_opened") for e in events) / total,
        "reply_rate": sum(_int(e, "message_replied") for e in events) / total,
        "dismiss_rate": sum(_int(e, "notification_dismissed") for e in events) / total,
        "muted_after": any(_flag(e, "muted_after_message") for e in events),
        "reported": any(_flag(e, "message_reported") for e in events),
    }


def _is_impersonation(business: dict | None) -> bool:
    if not business or _flag(business, "verified"):
        return False
    official = business["official_domain"].strip()
    used = business["domain_used_by_sender"].strip()
    if not official or not used or official == used:
        return False
    return _int(business, "domain_used_by_sender_age_days") < YOUNG_DOMAIN_DAYS


def _is_low_trust_business(business: dict | None) -> bool:
    if not business or _flag(business, "verified"):
        return False
    return (
        _int(business, "user_reports_30d") >= LOW_TRUST_REPORTS
        or _int(business, "account_age_days") < YOUNG_DOMAIN_DAYS
    )


def _has_relationship(business_history: dict | None) -> bool:
    if not business_history:
        return False
    reason = business_history["why_user_knows_account"]
    if any(token in reason for token in NON_RELATIONSHIP_TOKENS):
        return False
    return any(token in reason for token in TRANSACTIONAL_RELATIONSHIP_TOKENS)


def _in_do_not_disturb(user: dict | None, created_at: str) -> bool:
    window = (user or {}).get("do_not_disturb_window", "")
    if "-" not in window or " " not in created_at:
        return False
    start, end = (part.strip() for part in window.split("-", 1))
    clock = created_at.split(" ", 1)[1][:5]
    if start <= end:
        return start <= clock < end
    return clock >= start or clock < end


def _matches_interest(business_history: dict | None, group_type: str, reactions: dict) -> bool:
    if business_history and any(
        token in business_history["why_user_knows_account"] for token in INTEREST_TOKENS
    ):
        return True
    return group_type == "marketplace" and reactions.get("open_rate", 0.0) >= 0.6


def _content_kind(text: str, message: dict, context: dict) -> str:
    if context["is_scam"]:
        return "scam"
    if _matches(GREETING_PATTERNS, text):
        return "greeting"
    if context["is_promotional"]:
        return "spam" if context["low_trust_business"] else "promotion"
    if context["forwarded"] >= MASS_FORWARD_COUNT and message["conversation_type"] != "business":
        return "forward"
    if _matches(PAYMENT_PATTERNS, text) and message["conversation_type"] != "business":
        return "payment"
    if message["conversation_type"] == "business":
        # An account with a fresh domain and a pile of reports is spam whether or not the
        # copy happens to use offer vocabulary - a cold-call robocall carries none.
        if context["low_trust_business"]:
            return "spam"
        return "event" if _matches(EVENT_PATTERNS, text) else "business_update"
    if _matches(EVENT_PATTERNS, text):
        return "event"
    # `urgent` is a claim about the sender as well as the clock: a stranger's lost-property
    # note has a real cutoff but is not an emergency.
    if context["is_time_sensitive"] and context["sender_known"]:
        return "urgent"
    if message["conversation_type"] == "personal" and not context["sender_known"]:
        return "unknown"
    if message["sender_user_id"]:
        return "personal"
    return "unknown"


def _behavioural_signals(
    dataset: Dataset, message: dict, text: str, sender_membership: dict | None
) -> dict:
    # Retrieval ranks the whole user pool so evidence can cite a neighbouring conversation,
    # but behavior is only evidence about the sender it was measured on: reaction rates and
    # sender_known stay on the strict same-context rows.
    candidates = analogous_history(dataset, message, text)
    same_context = [row for row in candidates if _same_context(message, row)]
    reactions = _reaction_history(dataset, message, same_context[:5])
    if not reactions:
        reactions = _reaction_history(dataset, message, wider_history(dataset, message))
    return {
        "reactions": reactions,
        "sender_known": bool(same_context)
        or bool(message["sender_user_id"] and sender_membership),
        "has_sender_history": bool(reactions),
        "evidence_count": len(same_context),
    }


def _risk_signals(
    lowered: str, message: dict, business: dict | None, group_type: str, reactions: dict
) -> dict:
    asks_for_credentials = _matches(CREDENTIAL_PATTERNS, lowered) and not _matches(
        CREDENTIAL_DISCLAIMERS, lowered
    )
    under_pressure = _matches(PRESSURE_PATTERNS, lowered)
    impersonation = _is_impersonation(business)
    reported_pressure = under_pressure and reactions.get("reported", False)
    low_trust = _is_low_trust_business(business)
    # An attached poster may establish "this is an ad" only when the message has no words of
    # its own (voice notes, image-only) or its own words are already commercial. Otherwise the
    # attachment is context: msg_060 is a faculty deadline shipping an IIT flyer that "offers
    # opportunity", and msg_064 is a refund scam shipping a cinema poster. Both read as
    # promotions off the OCR alone. msg_074, a real land-plot pitch, keeps its poster because
    # its own text quotes a price.
    own_text = (message["message_text"] or "").lower()
    promo_text = (
        lowered
        if not own_text.strip() or _matches(COMMERCIAL_PATTERNS, own_text)
        else own_text
    )
    is_promotional = not asks_for_credentials and (
        _matches(PROMO_PATTERNS, promo_text)
        or (group_type == "marketplace" and _matches(MARKETPLACE_PATTERNS, promo_text))
    )
    return {
        "asks_for_credentials": asks_for_credentials,
        "uses_support_language": _matches(SUPPORT_LANGUAGE_PATTERNS, lowered)
        and under_pressure,
        "contains_routing_instruction": _matches(ROUTING_INSTRUCTION_PATTERNS, lowered),
        "is_reported_pressure": reported_pressure,
        "is_promotional": is_promotional,
        "is_scam": asks_for_credentials or impersonation or reported_pressure,
        "low_trust_business": low_trust,
        "is_brand_impersonation": impersonation,
        "is_feedback_request": _matches(FEEDBACK_PATTERNS, lowered),
    }


def _urgency_signals(
    lowered: str, text: str, user_id: str, message: dict, forwarded: int, group_type: str
) -> dict:
    same_day_deadline = _matches(CLOCK_DEADLINE_PATTERNS, lowered) and re.search(
        SAME_DAY_PATTERN, lowered
    )
    is_time_sensitive = (
        _matches(TIME_PRESSURE_PATTERNS, lowered)
        or _matches(HINGLISH_TIME_PRESSURE_PATTERNS, lowered)
        or bool(same_day_deadline)
    ) and not _matches(
        DEESCALATION_PATTERNS + HINGLISH_DEESCALATION_PATTERNS, lowered
    )
    directly_addressed = forwarded < MASS_FORWARD_COUNT and (
        bool(re.search(rf"@{re.escape(user_id)}\b", text))
        or (
            message["conversation_type"] == "personal"
            and _matches(
                [
                    r"can you\b",
                    r"could you\b",
                    r"\bplease\b",
                    r"call me\b",
                    r"let me know\b",
                    r"are you (still|free|around)\b",
                    r"need (quick |your )?help",
                ],
                lowered,
            )
        )
    )
    return {
        "directly_addressed": directly_addressed,
        "is_work_context": _matches(WORK_CONTEXT_PATTERNS, lowered)
        and (group_type == "coworker" or message["conversation_type"] == "personal"),
        "is_actionable_form": _matches(FORM_PATTERNS, lowered),
        "is_time_sensitive": is_time_sensitive,
    }


def _relationship_signals(
    dataset: Dataset,
    message: dict,
    business: dict | None,
    business_history: dict | None,
    membership: dict | None,
    sender_membership: dict | None,
    group_type: str,
    reactions: dict,
    lowered: str,
) -> dict:
    opted_out = bool(business_history) and (
        bool(business_history["promotions_opted_out_at"])
        or (
            business_history["allows_promotions"] == "0"
            and _int(business_history, "messages_dismissed_30d")
            > _int(business_history, "messages_opened_30d")
        )
    )
    return {
        "business_verified": _flag(business, "verified"),
        "promotions_opted_in": bool(business_history)
        and business_history["allows_promotions"] == "1"
        and not opted_out,
        "promotions_opted_out": opted_out,
        "matches_known_interest": _matches_interest(business_history, group_type, reactions),
        "has_transactional_relationship": _has_relationship(business_history)
        and _matches(TRANSACTION_PATTERNS, lowered),
        "sender_is_group_admin": bool(sender_membership)
        and sender_membership["role"] == "admin",
        "group_is_high_trust": group_type in HIGH_TRUST_GROUPS,
        "group_is_school": group_type == "school_group",
        "in_do_not_disturb": _in_do_not_disturb(
            dataset.users.get(message["user_id"]), message["created_at"]
        ),
        "group_muted_by_user": _flag(membership, "group_muted_by_user"),
    }


def build_features(dataset: Dataset, message: dict, media_text: str = "") -> Features:
    text = " ".join(part for part in (message["message_text"], media_text) if part)
    lowered = normalize(text).lower()
    user_id = message["user_id"]
    forwarded = int(message["forwarded_count"] or 0)

    business = dataset.businesses.get(message["business_id"])
    business_history = dataset.business_history_for(user_id, message["business_id"])
    membership = dataset.membership_for(user_id, message["group_id"])
    group = dataset.groups.get(message["group_id"])
    sender_membership = dataset.membership_for(message["sender_user_id"], message["group_id"])
    group_type = group["group_type"] if group else ""

    behavioural = _behavioural_signals(dataset, message, text, sender_membership)
    risk = _risk_signals(lowered, message, business, group_type, behavioural["reactions"])
    urgency = _urgency_signals(lowered, text, user_id, message, forwarded, group_type)
    relationship = _relationship_signals(
        dataset,
        message,
        business,
        business_history,
        membership,
        sender_membership,
        group_type,
        behavioural["reactions"],
        lowered,
    )

    context = {
        "is_scam": risk["is_scam"],
        "is_promotional": risk["is_promotional"],
        "is_time_sensitive": urgency["is_time_sensitive"],
        "forwarded": forwarded,
        "sender_known": behavioural["sender_known"],
        "low_trust_business": risk["low_trust_business"],
    }

    return Features(
        content_kind=_content_kind(lowered, message, context),
        asks_for_credentials=risk["asks_for_credentials"],
        uses_support_language=risk["uses_support_language"],
        contains_routing_instruction=risk["contains_routing_instruction"],
        is_reported_pressure=risk["is_reported_pressure"],
        directly_addressed=urgency["directly_addressed"],
        is_work_context=urgency["is_work_context"],
        sender_known=behavioural["sender_known"],
        sender_open_rate=behavioural["reactions"].get("open_rate", 0.0),
        business_verified=relationship["business_verified"],
        is_brand_impersonation=risk["is_brand_impersonation"],
        is_feedback_request=risk["is_feedback_request"],
        is_promotional=risk["is_promotional"],
        promotions_opted_in=relationship["promotions_opted_in"],
        promotions_opted_out=relationship["promotions_opted_out"],
        matches_known_interest=relationship["matches_known_interest"],
        has_transactional_relationship=relationship["has_transactional_relationship"],
        sender_is_group_admin=relationship["sender_is_group_admin"],
        group_is_high_trust=relationship["group_is_high_trust"],
        group_is_school=relationship["group_is_school"],
        is_actionable_form=urgency["is_actionable_form"],
        is_time_sensitive=urgency["is_time_sensitive"],
        in_do_not_disturb=relationship["in_do_not_disturb"],
        prior_dismiss_rate=behavioural["reactions"].get("dismiss_rate", 0.0),
        prior_muted_after=behavioural["reactions"].get("muted_after", False),
        group_muted_by_user=relationship["group_muted_by_user"],
        has_sender_history=behavioural["has_sender_history"],
        daily_dismiss_ratio=dataset.daily_dismiss_ratio(user_id),
        evidence_count=behavioural["evidence_count"],
    )
