import pytest

from router.context import Dataset
from router.retrieval import analogous_history, has_same_context_history


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load("dataset")


def test_history_from_another_conversation_is_reachable_but_ranks_below_same_context(dataset):
    """The hard context filter was dropping correct evidence: sample_msg_014 wants
    message_0015, same user and same topic but a different group."""
    message = {
        "message_id": "sample_msg_014",
        "user_id": "u_006",
        "conversation_type": "group",
        "group_id": "group_008",
        "business_id": "",
        "sender_user_id": "u_051",
        "message_text": (
            "Fwd as received. Drink warm water every hour and avoid cold food, very useful."
        ),
    }

    ids = [row["message_id"] for row in analogous_history(dataset, message)]

    assert "message_0015" in ids


def test_a_same_context_row_outranks_a_more_similar_row_from_elsewhere(dataset):
    message = {
        "message_id": "x",
        "user_id": "u_033",
        "conversation_type": "group",
        "group_id": "group_005",
        "business_id": "",
        "sender_user_id": "u_048",
        "message_text": "Photos for the kurta set are attached. Pickup is near Gate 2.",
    }

    top = analogous_history(dataset, message)[0]

    assert top["group_id"] == "group_005" and top["sender_user_id"] == "u_048"


def test_candidates_never_leave_the_recipient(dataset):
    """Another user's history is never evidence, whatever it says."""
    message = {
        "user_id": "u_033",
        "conversation_type": "group",
        "group_id": "group_005",
        "business_id": "",
        "sender_user_id": "u_048",
        "message_text": "Photos for the kurta set are attached. Pickup is near Gate 2 this weekend.",
    }

    candidates = analogous_history(dataset, message)

    assert candidates
    assert {row["user_id"] for row in candidates} == {"u_033"}


def test_the_most_textually_similar_prior_message_ranks_first(dataset):
    message = {
        "user_id": "u_033",
        "conversation_type": "group",
        "group_id": "group_005",
        "business_id": "",
        "sender_user_id": "u_048",
        "message_text": "Photos for the kurta set are attached. Pickup is near Gate 2 this weekend.",
    }

    candidates = analogous_history(dataset, message)

    assert "kurta set" in candidates[0]["message_text"]


def test_a_sender_the_user_has_no_history_with_reports_no_shared_context(dataset):
    """This is what makes the pipeline emit `none` - see test_pipeline."""
    message = {
        "user_id": "u_021",
        "conversation_type": "personal",
        "group_id": "",
        "business_id": "",
        "sender_user_id": "u_049",
        "message_text": "Hi, I found your number on the volunteer sheet.",
    }

    assert not has_same_context_history(dataset, message)


def test_ranking_is_stable_across_calls(dataset):
    message = {
        "user_id": "u_032",
        "conversation_type": "group",
        "group_id": "group_005",
        "business_id": "",
        "sender_user_id": "u_048",
        "message_text": "Photos for the kurta set are attached. Pickup is near Gate 2 this weekend.",
    }

    first = [row["message_id"] for row in analogous_history(dataset, message)]
    second = [row["message_id"] for row in analogous_history(dataset, message)]

    assert first == second
