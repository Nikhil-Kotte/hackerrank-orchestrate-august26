"""The solved samples' `evidence_message_ids` column is a generator artifact.

It is a running counter over `message_history.csv`, advanced once per emitted id and not at
all by a `none` row, rather than a semantically retrieved reference. These tests pin that
claim so it is executable rather than a paragraph in SOLUTION.md. Nothing here feeds the
router: we deliberately do not fit the sequence (see SOLUTION.md, "Evidence recall").
"""

import csv
import itertools
import re
from pathlib import Path

import pytest

from router.retrieval import similarity

ROOT = Path(__file__).resolve().parents[1]


def _index(message_id: str) -> int:
    return int(re.sub(r"\D", "", message_id))


def _rows(name: str) -> list[dict]:
    with open(ROOT / "dataset" / name, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def samples() -> list[dict]:
    return _rows("sample_messages.csv")


@pytest.fixture(scope="module")
def history() -> dict[str, dict]:
    return {row["message_id"]: row for row in _rows("message_history.csv")}


def _emitted(row: dict) -> list[int]:
    value = row["evidence_message_ids"]
    if not value or value == "none":
        return []
    return [_index(part) for part in value.split(";")]


def _runs(indices: list[int]) -> list[tuple[int, int]]:
    """Maximal spans of consecutive sample indices actually present in the file."""
    spans = []
    for _, group in itertools.groupby(enumerate(indices), lambda pair: pair[1] - pair[0]):
        block = [value for _, value in group]
        spans.append((block[0], block[-1]))
    return spans


def test_the_samples_arrive_as_three_contiguous_runs(samples):
    assert _runs([_index(row["message_id"]) for row in samples]) == [(1, 15), (19, 20), (41, 53)]


def test_graded_evidence_is_a_consecutive_block_within_each_contiguous_sample_run(samples):
    """The signature of a counter: no gaps, no reuse, no reordering inside a run."""
    by_index = {_index(row["message_id"]): _emitted(row) for row in samples}

    for low, high in _runs(sorted(by_index)):
        emitted = [i for index in range(low, high + 1) for i in by_index.get(index, [])]
        assert emitted == list(range(emitted[0], emitted[0] + len(emitted))), (low, high)


def test_graded_evidence_ascends_strictly_across_every_sample(samples):
    emitted = [i for row in samples for i in _emitted(row)]

    assert emitted == sorted(set(emitted))


def test_a_none_row_does_not_advance_the_counter(samples):
    """sample_msg_049 and sample_msg_052 emit nothing, and the block closes over them."""
    by_index = {_index(row["message_id"]): _emitted(row) for row in samples}

    assert by_index[49] == [] and by_index[52] == []
    assert by_index[48] == [53] and by_index[50] == [54]
    assert by_index[51] == [55] and by_index[53] == [56]


def test_graded_evidence_never_reaches_past_the_opening_stretch_of_the_history_file(
    samples, history
):
    """A semantic retriever over 412 rows would not confine itself to the first 56."""
    emitted = [i for row in samples for i in _emitted(row)]

    assert max(emitted) == 56
    assert len(history) == 412


def test_the_graded_evidence_for_sample_msg_044_is_the_less_similar_of_two_same_context_rows(
    samples, history
):
    """Our answer is textually near-verbatim; the graded answer is a different item entirely,
    and both share the user, group and sender. Similarity is not what the column encodes."""
    sample = next(row for row in samples if row["message_id"] == "sample_msg_044")
    ours = history["message_0401"]
    graded = history["message_0049"]

    assert (sample["user_id"], sample["group_id"], sample["sender_user_id"]) == (
        (ours["user_id"], ours["group_id"], ours["sender_user_id"])
    ) == ((graded["user_id"], graded["group_id"], graded["sender_user_id"]))
    assert similarity(sample["message_text"], ours["message_text"]) > 3 * similarity(
        sample["message_text"], graded["message_text"]
    )
