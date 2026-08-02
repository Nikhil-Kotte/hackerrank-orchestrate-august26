import json

import pytest

from router.audit import BLOCKS, RULE_BLOCKS, DecisionAuditor
from router.cli import DEFAULT_CACHE
from router.context import Dataset
from router.media import CachedExtractor, NullExtractor
from router.pipeline import route_all
from router.rules import REASON_BANK

FIELDS = (
    "message_id",
    "action",
    "message_type",
    "rule",
    "block",
    "confidence",
    "evidence_message_ids",
    "features",
)


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load("dataset")


@pytest.fixture(scope="module")
def extractor():
    return CachedExtractor(NullExtractor(), DEFAULT_CACHE)


def test_every_rule_in_the_reason_bank_maps_to_a_block():
    assert set(RULE_BLOCKS) == set(REASON_BANK)


def test_the_audit_log_has_one_record_per_message(dataset, extractor, tmp_path):
    path = tmp_path / "decision_log.jsonl"
    route_all(dataset, extractor, audit=DecisionAuditor(path))

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 110
    for line in lines:
        record = json.loads(line)
        assert record["block"] in BLOCKS
        assert record["rule"] in REASON_BANK
        for field in FIELDS:
            assert field in record


def test_the_default_run_writes_no_audit_log(dataset, extractor, tmp_path):
    target = tmp_path / "decision_log.jsonl"
    route_all(dataset, extractor)

    assert not target.exists()
