import csv

import pytest

from router.context import Dataset
from router.cli import DEFAULT_CACHE
from router.media import CachedExtractor, NullExtractor
from router.pipeline import OUTPUT_COLUMNS, route_all, route_message

@pytest.fixture(scope="module")
def transcripts():
    """The committed extractions, not hand-written stand-ins.

    An earlier revision hardcoded invented transcripts here and in the scorer, which is how
    the sample score drifted away from what the shipped pipeline produces.
    """
    return CachedExtractor(NullExtractor(), DEFAULT_CACHE)


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load("dataset")


@pytest.fixture(scope="module")
def samples():
    with open("dataset/sample_messages.csv", newline="", encoding="utf-8") as handle:
        return {row["message_id"]: row for row in csv.DictReader(handle)}


def test_a_routed_row_carries_exactly_the_output_columns(dataset, samples, transcripts):
    row = route_message(dataset, samples["sample_msg_001"], transcripts)

    assert list(row) == list(OUTPUT_COLUMNS)


def test_identical_messages_split_on_the_recipients_reaction_history(dataset, samples, transcripts):
    engaged = route_message(dataset, samples["sample_msg_044"], transcripts)
    fatigued = route_message(dataset, samples["sample_msg_045"], transcripts)

    assert engaged["action"] == "digest"
    assert fatigued["action"] == "mute"


def test_evidence_ids_resolve_to_real_history_rows(dataset, samples, transcripts):
    row = route_message(dataset, samples["sample_msg_045"], transcripts)

    for message_id in row["evidence_message_ids"].split(";"):
        assert message_id in dataset.history


def test_suppression_evidence_points_at_history_the_user_actually_dismissed(dataset, samples, transcripts):
    row = _route(dataset, samples, transcripts, "sample_msg_045")

    for message_id in row["evidence_message_ids"].split(";"):
        event = dataset.event_for("u_033", message_id)
        assert event["notification_dismissed"] == "1" or event["muted_after_message"] == "1"


def test_a_message_with_no_comparable_history_reports_none(dataset, samples, transcripts):
    row = route_message(dataset, samples["sample_msg_049"], transcripts)

    assert row["evidence_message_ids"] == "none"


def test_every_message_in_the_dataset_gets_exactly_one_row(dataset, transcripts):
    rows = route_all(dataset, transcripts)

    assert len(rows) == len(dataset.messages)
    assert [row["message_id"] for row in rows] == [
        message["message_id"] for message in dataset.messages
    ]


def test_routing_the_whole_dataset_twice_gives_identical_rows(dataset, transcripts):
    assert route_all(dataset, transcripts) == route_all(dataset, transcripts)


def _route(dataset, samples, transcripts, message_id):
    return route_message(dataset, samples[message_id], transcripts)


@pytest.mark.parametrize(
    "message_id,expected_type,why",
    [
        ("sample_msg_002", "event", "a school admin's scheduling change is an event"),
        ("sample_msg_005", "event", "a business reminder tied to a booking is an event"),
        ("sample_msg_006", "personal", "an unhurried ask in a friends group is personal"),
        ("sample_msg_013", "greeting", "a forwarded blessing is still a greeting"),
        ("sample_msg_043", "spam", "marketing from an unverified reported account is spam"),
        ("sample_msg_044", "promotion", "a marketplace sale post is a promotion"),
        ("sample_msg_049", "unknown", "a stranger in a personal chat is uncategorised"),
    ],
)
def test_message_type_follows_the_conversation_context(
    dataset, samples, transcripts, message_id, expected_type, why
):
    assert _route(dataset, samples, transcripts, message_id)["message_type"] == expected_type, why


def test_a_brand_advisory_that_mentions_otp_only_to_warn_is_not_a_credential_request(dataset, samples, transcripts):
    row = _route(dataset, samples, transcripts, "sample_msg_048")

    assert (row["action"], row["message_type"]) == ("digest", "business_update")


def test_a_feedback_request_from_a_business_the_user_transacts_with_still_waits(dataset, samples, transcripts):
    assert _route(dataset, samples, transcripts, "sample_msg_011")["action"] == "digest"


def test_a_personal_note_that_explicitly_defers_contact_does_not_interrupt(dataset, samples, transcripts):
    assert _route(dataset, samples, transcripts, "sample_msg_050")["action"] == "digest"


def test_an_urgent_ask_from_a_close_contact_interrupts_without_an_at_mention(dataset, samples, transcripts):
    assert _route(dataset, samples, transcripts, "sample_msg_042")["action"] == "notify"
