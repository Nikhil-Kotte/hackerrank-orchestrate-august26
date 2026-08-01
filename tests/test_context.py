import pytest

from router.context import Dataset

DATASET_DIR = "dataset"


def test_messages_load_with_multi_line_text_intact():
    dataset = Dataset.load(DATASET_DIR)

    assert len(dataset.messages) == 110
    assert dataset.messages[0]["message_text"].startswith("Important Information\n\nDear Customer,")


def test_history_and_its_paired_event_are_reachable_from_a_user():
    dataset = Dataset.load(DATASET_DIR)

    history = dataset.history_for("u_002")

    assert {row["message_id"] for row in history} >= {"message_0102", "message_0011"}
    assert dataset.event_for("u_011", "message_0001")["message_replied"] == "1"


def test_the_daily_summary_collapses_into_a_per_user_dismissal_ratio():
    dataset = Dataset.load(DATASET_DIR)

    assert dataset.daily_dismiss_ratio("u_041") == pytest.approx(0.79, abs=0.01)
    assert dataset.daily_dismiss_ratio("u_040") == pytest.approx(0.49, abs=0.01)


def test_a_user_with_no_summary_rows_has_no_dismissal_signal():
    dataset = Dataset.load(DATASET_DIR)

    assert dataset.daily_dismiss_ratio("u_does_not_exist") == 0.0
