import pytest

from router.rules import CONFIDENCE_BANDS, Features, decide


def test_credential_harvesting_is_muted_even_when_the_user_trusts_the_sender():
    features = Features(
        asks_for_credentials=True,
        sender_open_rate=0.9,
    )

    decision = decide(features)

    assert (decision.action, decision.message_type) == ("mute", "scam")


def test_a_pattern_this_user_dismissed_and_muted_is_suppressed():
    features = Features(
        content_kind="promotion",
        prior_dismiss_rate=1.0,
        prior_muted_after=True,
    )

    decision = decide(features)

    assert (decision.action, decision.message_type) == ("mute", "promotion")


def test_a_direct_mention_interrupts_even_in_a_group_the_user_muted():
    features = Features(
        content_kind="urgent",
        directly_addressed=True,
        group_muted_by_user=True,
        prior_dismiss_rate=0.8,
    )

    decision = decide(features)

    assert (decision.action, decision.message_type) == ("notify", "urgent")


def test_a_direct_question_from_an_unfamiliar_sender_does_not_interrupt():
    features = Features(
        content_kind="unknown",
        directly_addressed=True,
        sender_known=False,
    )

    decision = decide(features)

    assert (decision.action, decision.message_type) == ("digest", "unknown")


def test_a_brand_message_sent_from_a_domain_the_brand_does_not_own_is_muted():
    features = Features(
        content_kind="business_update",
        is_brand_impersonation=True,
    )

    decision = decide(features)

    assert (decision.action, decision.message_type) == ("mute", "scam")


def test_a_credential_request_reuses_the_canonical_scam_reason():
    features = Features(asks_for_credentials=True)

    decision = decide(features)

    assert decision.reason == (
        "The message asks for urgent OTP or account verification through a suspicious flow."
    )


@pytest.mark.parametrize(
    "features",
    [
        Features(asks_for_credentials=True),
        Features(contains_routing_instruction=True),
        Features(is_brand_impersonation=True),
        Features(directly_addressed=True),
        Features(directly_addressed=True, sender_known=False),
        Features(is_promotional=True, promotions_opted_out=True),
        Features(prior_muted_after=True),
        Features(business_verified=True, has_transactional_relationship=True),
        Features(sender_is_group_admin=True, group_is_high_trust=True, is_time_sensitive=True),
        Features(),
    ],
)
def test_confidence_stays_inside_the_band_observed_for_its_action(features):
    decision = decide(features)

    low, high = CONFIDENCE_BANDS[decision.action]
    assert low <= decision.confidence <= high


@pytest.mark.parametrize(
    "features,expected",
    [
        (
            Features(
                content_kind="event",
                sender_is_group_admin=True,
                group_is_high_trust=True,
                group_is_school=True,
                is_time_sensitive=True,
            ),
            "A school admin sent a same-day operational update that the user is likely to "
            "need immediately.",
        ),
        (
            Features(content_kind="urgent", directly_addressed=True, is_work_context=True),
            "The message is from a work context and contains a direct deadline or meeting "
            "dependency.",
        ),
        (
            Features(
                content_kind="event",
                business_verified=True,
                has_transactional_relationship=True,
            ),
            "A verified business is sending a reminder that matches the user's recent "
            "booking history.",
        ),
        (
            Features(content_kind="greeting", prior_dismiss_rate=1.0),
            "The sender has a pattern of repeated forwards or greetings that the user "
            "usually ignores.",
        ),
        (
            Features(content_kind="promotion", is_promotional=True, prior_dismiss_rate=1.0),
            "The user has opted out of or repeatedly dismissed similar marketing messages.",
        ),
        (
            Features(content_kind="scam", asks_for_credentials=True, uses_support_language=True),
            "The message uses fake support language and account-blocking pressure to push "
            "the user into action.",
        ),
        (
            Features(content_kind="promotion", is_promotional=True, promotions_opted_in=True),
            "The message is promotional but matches a topic or business the user has opted "
            "into.",
        ),
        (
            Features(content_kind="event"),
            "The message is useful group information, but it is not urgent enough to "
            "interrupt the user.",
        ),
        (
            Features(content_kind="greeting"),
            "The message is a harmless greeting that can be read later.",
        ),
        (
            Features(content_kind="unknown", sender_known=False),
            "The sender is unfamiliar, but the message does not show urgency, payment "
            "pressure, or safety risk.",
        ),
        (
            Features(content_kind="personal", sender_open_rate=1.0),
            "The sender is trusted, but the message has no urgent action or safety relevance.",
        ),
    ],
)
def test_the_reason_names_the_signal_that_actually_fired(features, expected):
    assert decide(features).reason == expected


def test_a_notify_that_lands_in_the_do_not_disturb_window_waits_instead():
    features = Features(
        content_kind="personal",
        directly_addressed=True,
        in_do_not_disturb=True,
    )

    decision = decide(features)

    assert decision.action == "digest"
    assert "do not disturb" in decision.reason


def test_do_not_disturb_never_softens_a_safety_decision():
    features = Features(
        content_kind="scam",
        asks_for_credentials=True,
        in_do_not_disturb=True,
    )

    assert decide(features).action == "mute"


def test_a_promotion_from_a_business_the_user_opted_out_of_is_muted():
    features = Features(
        content_kind="promotion",
        is_promotional=True,
        promotions_opted_out=True,
        prior_dismiss_rate=0.0,
    )

    decision = decide(features)

    assert (decision.action, decision.message_type) == ("mute", "promotion")


def test_a_verified_business_update_on_an_account_the_user_actually_transacts_with_notifies():
    features = Features(
        content_kind="business_update",
        business_verified=True,
        has_transactional_relationship=True,
    )

    decision = decide(features)

    assert (decision.action, decision.message_type) == ("notify", "business_update")


def test_a_time_sensitive_admin_update_in_a_high_trust_group_notifies():
    features = Features(
        content_kind="event",
        sender_is_group_admin=True,
        group_is_high_trust=True,
        is_time_sensitive=True,
    )

    decision = decide(features)

    assert (decision.action, decision.message_type) == ("notify", "event")


def test_a_school_admin_posting_a_consent_form_notifies_without_explicit_urgency():
    features = Features(
        content_kind="event",
        sender_is_group_admin=True,
        group_is_high_trust=True,
        group_is_school=True,
        is_actionable_form=True,
    )

    decision = decide(features)

    assert (decision.action, decision.rule) == ("notify", "school_admin_update")


def test_an_actionable_form_outside_a_school_group_does_not_notify_on_its_own():
    features = Features(
        content_kind="event",
        sender_is_group_admin=True,
        group_is_high_trust=True,
        is_actionable_form=True,
    )

    assert decide(features).action == "digest"


def test_unanimous_suppression_history_is_more_confident_than_a_split_one():
    """Confidence is uncertainty, not decoration: five dismissals out-rank a coin flip."""
    unanimous = Features(
        content_kind="promotion", prior_dismiss_rate=1.0, prior_muted_after=True,
        evidence_count=5,
    )
    borderline = Features(
        content_kind="promotion", prior_dismiss_rate=0.5, prior_muted_after=True,
        evidence_count=1,
    )

    assert decide(unanimous).confidence > decide(borderline).confidence


def test_a_transaction_match_is_more_confident_when_the_user_always_opens_the_sender():
    engaged = Features(
        content_kind="business_update", business_verified=True,
        has_transactional_relationship=True, sender_open_rate=1.0, evidence_count=4,
    )
    thin = Features(
        content_kind="business_update", business_verified=True,
        has_transactional_relationship=True, sender_open_rate=0.2, evidence_count=1,
    )

    assert decide(engaged).confidence > decide(thin).confidence


def test_calibration_never_escapes_the_band_for_its_action():
    extremes = [
        Features(content_kind="promotion", prior_dismiss_rate=1.0, prior_muted_after=True,
                 evidence_count=99),
        Features(content_kind="promotion", prior_dismiss_rate=0.5, evidence_count=0),
        Features(content_kind="business_update", business_verified=True,
                 has_transactional_relationship=True, sender_open_rate=1.0, evidence_count=99),
        Features(asks_for_credentials=True, evidence_count=99),
        Features(content_kind="personal", evidence_count=0),
    ]

    for features in extremes:
        decision = decide(features)
        low, high = CONFIDENCE_BANDS[decision.action]
        assert low <= decision.confidence <= high, decision.rule


def test_confidence_is_a_pure_function_of_the_features():
    features = Features(content_kind="promotion", prior_dismiss_rate=0.8, evidence_count=3)

    assert decide(features).confidence == decide(features).confidence


def test_impersonation_outranks_the_generic_credential_reason_when_both_fire():
    features = Features(
        content_kind="scam",
        asks_for_credentials=True,
        is_brand_impersonation=True,
    )

    decision = decide(features)

    assert (decision.action, decision.rule) == ("mute", "brand_impersonation")


def test_admin_authority_does_not_clear_a_pattern_the_user_already_reported():
    features = Features(
        content_kind="scam",
        is_reported_pressure=True,
        sender_is_group_admin=True,
        group_is_high_trust=True,
        is_time_sensitive=True,
        sender_open_rate=0.9,
    )

    decision = decide(features)

    assert (decision.action, decision.message_type) == ("mute", "scam")
    assert decision.rule == "reported_pressure"


def test_a_muted_group_downgrades_an_admin_update_that_is_not_addressed_to_the_user():
    features = Features(
        content_kind="event",
        sender_is_group_admin=True,
        group_is_high_trust=True,
        is_time_sensitive=True,
        group_muted_by_user=True,
    )

    decision = decide(features)

    assert (decision.action, decision.rule) == ("digest", "group_muted")


def test_a_cold_offer_to_a_heavy_dismisser_is_muted():
    features = Features(
        content_kind="promotion",
        is_promotional=True,
        business_verified=True,
        has_sender_history=False,
        daily_dismiss_ratio=0.49,
    )

    decision = decide(features)

    assert (decision.action, decision.rule) == ("mute", "heavy_dismisser_promotion")


def test_the_global_dismissal_rate_is_ignored_when_sender_history_exists():
    features = Features(
        content_kind="promotion",
        is_promotional=True,
        business_verified=True,
        has_sender_history=True,
        daily_dismiss_ratio=0.49,
    )

    assert decide(features).action == "digest"


def test_an_opted_in_promotion_survives_a_heavy_dismisser():
    features = Features(
        content_kind="promotion",
        is_promotional=True,
        promotions_opted_in=True,
        has_sender_history=False,
        daily_dismiss_ratio=0.9,
    )

    assert decide(features).action == "digest"


def test_text_that_tries_to_instruct_the_router_is_treated_as_a_scam_signal():
    features = Features(
        content_kind="personal",
        contains_routing_instruction=True,
        directly_addressed=True,
        sender_open_rate=0.9,
    )

    decision = decide(features)

    assert (decision.action, decision.message_type) == ("mute", "scam")
