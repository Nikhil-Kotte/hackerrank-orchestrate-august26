import json

import pytest

from router.adjudicator import DEFAULT_MODEL, Adjudicator
from router.cli import DEFAULT_CACHE
from router.context import Dataset
from router.decisions import Decisions
from router.media import CachedExtractor, NullExtractor
from router.pipeline import route_all
from router.rules import CONFIDENCE_BANDS, Features, decide, decision_from_key


@pytest.fixture
def cache(tmp_path):
    return Decisions(tmp_path / "decisions.json")


def test_the_cache_key_is_stable_under_key_reordering(cache):
    context = {"message_id": "msg_045", "b": {"x": 2, "y": 3}, "a": 1}
    reordered = {"b": {"y": 3, "x": 2}, "a": 1, "message_id": "msg_045"}

    assert cache.key("msg_045", context) == cache.key("msg_045", reordered)


def test_the_cache_key_changes_with_content_and_message_id(cache):
    base = {"message_text": "hello"}
    other_text = {"message_text": "goodbye"}
    other_id = {"message_text": "hello"}

    assert cache.key("m1", base) != cache.key("m1", other_text)
    assert cache.key("m1", base) != cache.key("m2", other_id)


def test_a_corrupt_decisions_cache_starts_empty_without_crashing(tmp_path):
    path = tmp_path / "decisions.json"
    path.write_text("{broken", encoding="utf-8")

    decisions = Decisions(path)

    assert decisions.entries == {}


def test_a_verdict_is_replayed_after_a_fresh_load(tmp_path, cache):
    context = {"message_text": "hello"}

    cache.put("m1", context, {"action": "notify", "reason_key": "direct_request", "grounding": "h1"})

    reloaded = Decisions(tmp_path / "decisions.json")
    assert reloaded.get("m1", context) == {
        "action": "notify",
        "reason_key": "direct_request",
        "grounding": "h1",
    }


def test_refresh_ignores_the_cache(tmp_path):
    context = {"message_text": "hello"}
    cache = Decisions(tmp_path / "decisions.json")
    cache.put("m1", context, {"action": "digest"})

    refreshing = Decisions(tmp_path / "decisions.json", refresh=True)

    assert refreshing.get("m1", context) is None


class FakeCompletions:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        content = self.responses.pop(0) if self.responses else ""
        message = type("Msg", (), {"content": content})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


class RaisingCompletions:
    def create(self, **kwargs):
        raise AssertionError("the model must not be called")


def make_adjudicator(tmp_path, client):
    adjudicator = Adjudicator.__new__(Adjudicator)
    adjudicator.model = DEFAULT_MODEL
    adjudicator.client = client
    adjudicator.decisions = Decisions(tmp_path / "decisions.json")
    return adjudicator


def _context(**overrides):
    context = {
        "message_id": "msg_045",
        "message_text": "hello",
        "conversation_type": "personal",
        "forwarded_count": 0,
        "candidates": ["h_01"],
        "candidate_evidence": [{"message_id": "h_01", "message_text": "previous chat"}],
        "sender_known": True,
        "sender_open_rate": 0.0,
    }
    context.update(overrides)
    return context


def test_a_missing_key_is_refused_up_front(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        Adjudicator()


def test_a_valid_verdict_is_mapped_into_a_band_compliant_decision(tmp_path):
    features = Features()
    completions = FakeCompletions(
        json.dumps({"action": "notify", "reason_key": "direct_request", "grounding": "h_01"})
    )
    adjudicator = make_adjudicator(tmp_path, type("C", (), {"chat": type("Chat", (), {"completions": completions})()})())

    decision, grounding = adjudicator.decision_for(features, _context())

    assert decision.action == "notify"
    assert decision.message_type == features.content_kind
    assert decision.rule == "direct_request"
    assert grounding == "h_01"
    low, high = CONFIDENCE_BANDS["notify"]
    assert low <= decision.confidence <= high
    assert completions.calls == 1


def test_grounding_may_be_null(tmp_path):
    completions = FakeCompletions(
        json.dumps({"action": "digest", "reason_key": "no_urgency", "grounding": None})
    )
    adjudicator = make_adjudicator(tmp_path, type("C", (), {"chat": type("Chat", (), {"completions": completions})()})())

    decision, grounding = adjudicator.decision_for(Features(), _context())

    assert decision.action == "digest"
    assert grounding is None


def test_an_invalid_action_falls_back_to_the_rule(tmp_path):
    completions = FakeCompletions(json.dumps({"action": "mute", "reason_key": "no_urgency"}))
    adjudicator = make_adjudicator(tmp_path, type("C", (), {"chat": type("Chat", (), {"completions": completions})()})())

    decision, grounding = adjudicator.decision_for(Features(), _context())

    assert decision == decide(Features())
    assert grounding is None
    assert completions.calls == 2


def test_a_reason_key_outside_the_bank_is_rejected(tmp_path):
    completions = FakeCompletions(
        json.dumps({"action": "digest", "reason_key": "not_a_real_key"})
    )
    adjudicator = make_adjudicator(tmp_path, type("C", (), {"chat": type("Chat", (), {"completions": completions})()})())

    decision, _ = adjudicator.decision_for(Features(), _context())

    assert decision == decide(Features())


def test_a_reason_key_that_implies_the_wrong_action_is_rejected(tmp_path):
    # direct_request implies notify; the model claimed digest.
    completions = FakeCompletions(
        json.dumps({"action": "digest", "reason_key": "direct_request"})
    )
    adjudicator = make_adjudicator(tmp_path, type("C", (), {"chat": type("Chat", (), {"completions": completions})()})())

    decision, _ = adjudicator.decision_for(Features(), _context())

    assert decision == decide(Features())


def test_a_grounding_outside_the_candidates_is_rejected(tmp_path):
    completions = FakeCompletions(
        json.dumps({"action": "digest", "reason_key": "no_urgency", "grounding": "h_999"})
    )
    adjudicator = make_adjudicator(tmp_path, type("C", (), {"chat": type("Chat", (), {"completions": completions})()})())

    decision, _ = adjudicator.decision_for(Features(), _context())

    assert decision == decide(Features())


def test_cached_verdicts_are_replayed_without_calling_the_model(tmp_path):
    adjudicator = make_adjudicator(
        tmp_path, type("C", (), {"chat": type("Chat", (), {"completions": RaisingCompletions()})()})()
    )
    context = _context()
    adjudicator.decisions.put(
        "msg_045", context, {"action": "notify", "reason_key": "direct_request", "grounding": "h_01"}
    )

    decision, grounding = adjudicator.decision_for(Features(), context)

    assert decision.action == "notify"
    assert grounding == "h_01"


class FlipToNotify:
    """Hostile stub: if the model could reach a mute row it would flip it to notify."""

    def decision_for(self, features, context):
        return decision_from_key(features, "notify", "direct_request"), None


class RecordingAdjudicator:
    def __init__(self):
        self.seen = []

    def decision_for(self, features, context):
        self.seen.append(context["message_id"])
        return decision_from_key(features, "digest", "no_urgency"), None


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load("dataset")


@pytest.fixture(scope="module")
def extractor():
    return CachedExtractor(NullExtractor(), DEFAULT_CACHE)


def test_the_51_row_mute_set_is_unchanged_even_under_a_hostile_model(dataset, extractor):
    baseline = {row["message_id"]: row["action"] for row in route_all(dataset, extractor)}
    flipped = {
        row["message_id"]: row["action"]
        for row in route_all(dataset, extractor, FlipToNotify())
    }
    mute_ids = {mid for mid, action in baseline.items() if action == "mute"}

    assert len(mute_ids) == 51
    for mid in mute_ids:
        assert flipped[mid] == "mute"


def test_the_adjudicator_is_never_consulted_on_a_mute_row(dataset, extractor):
    recorder = RecordingAdjudicator()
    routed = route_all(dataset, extractor, recorder)
    mute_ids = {row["message_id"] for row in routed if row["action"] == "mute"}

    assert not (mute_ids & set(recorder.seen))


def test_the_default_run_needs_no_adjudicator(dataset, extractor):
    routed = route_all(dataset, extractor)

    assert len(routed) == 110
    assert all("default_branch" not in row for row in routed)
