import csv

import pytest

from router.cli import DEFAULT_CACHE, main, write_output
from router.context import Dataset
from router.media import CachedExtractor, NullExtractor
from router.pipeline import OUTPUT_COLUMNS, route_all

ACTIONS = {"notify", "digest", "mute"}
TYPES = {
    "personal",
    "urgent",
    "event",
    "payment",
    "business_update",
    "promotion",
    "greeting",
    "forward",
    "spam",
    "scam",
    "unknown",
}


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load("dataset")


@pytest.fixture(scope="module")
def emitted(tmp_path_factory, dataset):
    # The shipped configuration: replay the committed cache, never call out. A miss would
    # degrade to empty text; test_cache_coverage is what proves there are none.
    extractor = CachedExtractor(NullExtractor(), DEFAULT_CACHE)
    path = tmp_path_factory.mktemp("out") / "output.csv"
    write_output(route_all(dataset, extractor), path)
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def test_the_header_is_the_required_column_order(emitted):
    fieldnames, _ = emitted

    assert fieldnames == list(OUTPUT_COLUMNS)


def test_predictions_are_one_to_one_with_the_input_messages(emitted, dataset):
    _, rows = emitted

    assert [row["message_id"] for row in rows] == [m["message_id"] for m in dataset.messages]
    assert len(rows) == 110
    assert len({row["message_id"] for row in rows}) == 110


def test_every_action_and_type_is_in_the_allowed_set(emitted):
    _, rows = emitted

    assert {row["action"] for row in rows} <= ACTIONS
    assert {row["message_type"] for row in rows} <= TYPES


def test_every_confidence_parses_into_the_unit_interval(emitted):
    _, rows = emitted

    assert all(0.0 <= float(row["confidence"]) <= 1.0 for row in rows)


def test_every_evidence_id_resolves_or_says_none(emitted, dataset):
    _, rows = emitted

    for row in rows:
        if row["evidence_message_ids"] == "none":
            continue
        for message_id in row["evidence_message_ids"].split(";"):
            assert message_id in dataset.history


def test_no_reason_field_is_empty(emitted):
    _, rows = emitted

    assert all(row["reason"].strip() for row in rows)


def test_the_cli_writes_an_identical_file_on_a_second_run(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    cache = str(tmp_path / "cache.json")

    main(["--output", str(first), "--cache", cache, "--also-write", ""])
    main(["--output", str(second), "--cache", cache, "--also-write", ""])

    assert first.read_bytes() == second.read_bytes()


def test_the_cli_fills_both_output_paths_the_challenge_names(tmp_path):
    primary = tmp_path / "output.csv"
    secondary = tmp_path / "nested" / "output.csv"

    main([
        "--output", str(primary),
        "--also-write", str(secondary),
        "--cache", str(tmp_path / "cache.json"),
    ])

    assert primary.read_bytes() == secondary.read_bytes()
    assert primary.read_text(encoding="utf-8").count("\n") == 111
