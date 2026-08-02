"""The evidence-gathering agent loop, tested against stubbed models.

No live calls here. A model is just a callable `(messages, tools) -> list[dict]` where each
entry is `{"name": "...", "arguments": {...}}`; the stub reads `messages` the way a real model
would, so the loop feeding tool results back is part of what is tested.
"""

import csv
import json
from pathlib import Path

import pytest

from router.agent import (
    MAX_ITERATIONS,
    SYSTEM,
    AgentTraceStore,
    EvidenceAgent,
    context_hash,
)
from router.cli import DEFAULT_CACHE, main
from router.context import Dataset
from router.features import build_features
from router.media import CachedExtractor, StubExtractor
from router.pipeline import media_text_for, route_all
from router.rules import decide


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load("dataset")


@pytest.fixture(scope="module")
def extractor():
    return CachedExtractor(StubExtractor({}), DEFAULT_CACHE)


class Model:
    """Counts calls and returns whatever the scripted body returns."""

    def __init__(self, body):
        self.body = body
        self.calls = 0

    def __call__(self, messages, tools):
        self.calls += 1
        return self.body(messages, tools)


def _last_tool_result(messages) -> dict:
    for message in reversed(messages):
        if message.get("role") == "tool":
            return json.loads(message["content"])
    raise AssertionError("no tool result in messages")


def _default_branch_message(dataset, with_media=None):
    """A real row that fell through to the default digest branch."""
    for message in dataset.messages:
        if not decide(build_features(dataset, message, "")).default_branch:
            continue
        has_media = bool(message["media_id"])
        if with_media is True and not has_media:
            continue
        if with_media is False and has_media:
            continue
        return message
    raise AssertionError("no matching default-branch row in dataset")


def _decide(**arguments) -> list[dict]:
    return [{"name": "decide", "arguments": arguments}]


def _run(dataset, extractor, message, model, store):
    features = build_features(dataset, message, "")
    return EvidenceAgent(model, extractor, store).decision_for(dataset, message, features)


def test_a_stub_that_searches_then_decides_is_accepted(dataset, extractor, tmp_path):
    """The loop feeds the tool result back; the stub reads it and decides on the found id."""
    message = _default_branch_message(dataset)
    model = Model(lambda messages, tools: (
        [{"name": "search_history", "arguments": {"query": "order status"}}]
        if len(messages) == 2 else
        _decide(action="digest", reason_key="no_urgency",
                evidence_message_ids=[_last_tool_result(messages)["results"][0]["message_id"]],
                grounding=_last_tool_result(messages)["results"][0]["message_id"])
    ))

    outcome = _run(dataset, extractor, message, model, AgentTraceStore(tmp_path / "t.jsonl"))

    assert outcome.terminal == "decided"
    assert outcome.decision.action == "digest"
    assert outcome.decision.rule == "no_urgency"
    assert outcome.evidence and outcome.evidence != "none"
    assert model.calls == 2
    assert [t["tool"] for t in outcome.trace] == ["search_history", "decide"]


def test_read_media_on_a_row_with_no_media_returns_empty(dataset, extractor, tmp_path):
    message = _default_branch_message(dataset, with_media=False)
    model = Model(lambda messages, tools: (
        [{"name": "read_media", "arguments": {"message_id": message["message_id"]}}]
        if len(messages) == 2 else
        (_decide(action="digest", reason_key="trusted_no_urgency",
                 evidence_message_ids=[], grounding=None)
         if _last_tool_result(messages) == {"text": ""} else
         _decide(action="notify", reason_key="direct_request",
                 evidence_message_ids=[], grounding=None))
    ))

    outcome = _run(dataset, extractor, message, model, AgentTraceStore(tmp_path / "t.jsonl"))

    assert outcome.terminal == "decided"
    assert outcome.evidence == "none"


def test_a_stub_that_never_terminates_falls_back_at_the_cap(dataset, extractor, tmp_path):
    message = _default_branch_message(dataset)
    model = Model(lambda messages, tools: [
        {"name": "search_history", "arguments": {"query": "keep looking"}}
    ])

    outcome = _run(dataset, extractor, message, model, AgentTraceStore(tmp_path / "t.jsonl"))

    assert outcome.terminal == "fallback"
    assert outcome.reason == "iteration_cap"
    assert outcome.decision is None
    assert model.calls == MAX_ITERATIONS


def test_action_mute_is_rejected_by_the_alphabet_and_falls_back(dataset, extractor, tmp_path):
    """Mute is not in the model's output alphabet; there is no validator to compensate."""
    message = _default_branch_message(dataset)
    model = Model(lambda messages, tools: _decide(action="mute", reason_key="marketing_fatigue"))

    outcome = _run(dataset, extractor, message, model, AgentTraceStore(tmp_path / "t.jsonl"))

    assert outcome.terminal == "fallback"
    assert "output alphabet" in outcome.detail
    assert outcome.decision is None
    assert model.calls == 2  # one retry, then fallback


def test_a_reason_key_that_implies_mute_is_rejected(dataset, extractor, tmp_path):
    """marketing_fatigue is a rules mute key; it is not in REASON_ACTIONS at all."""
    message = _default_branch_message(dataset)
    model = Model(lambda messages, tools: _decide(action="digest", reason_key="marketing_fatigue"))

    outcome = _run(dataset, extractor, message, model, AgentTraceStore(tmp_path / "t.jsonl"))

    assert outcome.terminal == "fallback"
    assert "marketing_fatigue" in outcome.detail


def test_a_nonexistent_evidence_id_is_rejected_then_falls_back(dataset, extractor, tmp_path):
    message = _default_branch_message(dataset)
    model = Model(lambda messages, tools: _decide(
        action="digest", reason_key="no_urgency",
        evidence_message_ids=["message_9999"], grounding=None))

    outcome = _run(dataset, extractor, message, model, AgentTraceStore(tmp_path / "t.jsonl"))

    assert outcome.terminal == "fallback"
    assert "message_9999" in outcome.detail


def test_malformed_output_gets_one_retry_then_falls_back(dataset, extractor, tmp_path):
    message = _default_branch_message(dataset)
    model = Model(lambda messages, tools: "not a list of tool calls")

    outcome = _run(dataset, extractor, message, model, AgentTraceStore(tmp_path / "t.jsonl"))

    assert outcome.terminal == "fallback"
    assert outcome.reason == "malformed_output"
    assert model.calls == 2


def test_an_api_error_falls_back_without_retry(dataset, extractor, tmp_path):
    message = _default_branch_message(dataset)
    model = Model(lambda messages, tools: (_ for _ in ()).throw(RuntimeError("provider 500")))

    outcome = _run(dataset, extractor, message, model, AgentTraceStore(tmp_path / "t.jsonl"))

    assert outcome.terminal == "fallback"
    assert outcome.reason == "api_error"
    assert "500" in outcome.detail
    assert model.calls == 1


def test_citing_the_messages_own_id_is_rejected_with_guidance_and_correctable(
    dataset, extractor, tmp_path
):
    """The live run showed the model citing the message's own id as evidence. The rejection
    must tell it to pass an empty list, and the retry must then succeed."""
    message = _default_branch_message(dataset)
    model = Model(lambda messages, tools: (
        _decide(action="digest", reason_key="no_urgency",
                evidence_message_ids=[message["message_id"]], grounding=None)
        if len(messages) == 2 else
        (lambda error: (
            [{"name": "decide", "arguments": {"action": "digest", "reason_key": "no_urgency",
                                              "evidence_message_ids": [], "grounding": None}}]
            if "empty list" in error.get("error", "") else
            [{"name": "decide", "arguments": {"action": "digest", "reason_key": "no_urgency",
                                              "evidence_message_ids": [message["message_id"]],
                                              "grounding": None}}]
        ))(_last_tool_result(messages))
    ))

    outcome = _run(dataset, extractor, message, model, AgentTraceStore(tmp_path / "t.jsonl"))

    assert outcome.terminal == "decided"
    assert outcome.evidence == "none"
    assert model.calls == 2


def test_an_invalid_decision_can_be_corrected_on_the_retry(dataset, extractor, tmp_path):
    """One retry is enough: the error is fed back and the model fixes the evidence."""
    message = _default_branch_message(dataset)
    model = Model(lambda messages, tools: (
        _decide(action="digest", reason_key="no_urgency",
                evidence_message_ids=["message_9999"], grounding=None)
        if len(messages) == 2 else
        _decide(action="digest", reason_key="no_urgency",
                evidence_message_ids=[], grounding=None)
    ))

    outcome = _run(dataset, extractor, message, model, AgentTraceStore(tmp_path / "t.jsonl"))

    assert outcome.terminal == "decided"
    assert outcome.evidence == "none"
    assert model.calls == 2


def test_traces_are_persisted_and_replayed_without_calling_the_model(dataset, extractor, tmp_path):
    message = _default_branch_message(dataset)
    model = Model(lambda messages, tools: _decide(action="digest", reason_key="no_urgency"))

    first = _run(dataset, extractor, message, model, AgentTraceStore(tmp_path / "t.jsonl"))

    def exploding(messages, tools):
        raise AssertionError("replay must not call the model")

    replay = _run(dataset, extractor, message, Model(exploding), AgentTraceStore(tmp_path / "t.jsonl"))

    assert replay.terminal == first.terminal
    assert replay.decision == first.decision
    assert replay.evidence == first.evidence
    persisted = AgentTraceStore(tmp_path / "t.jsonl").load_all()
    assert persisted, "trace file must be written"
    assert all(line["key"].startswith(message["message_id"]) for line in persisted)


def test_agent_does_not_alter_any_default_branch_false_row(dataset, extractor, tmp_path):
    """The gate is default_branch, not the audit block; non-default rows never see the agent."""
    model = Model(lambda messages, tools: _decide(action="digest", reason_key="no_urgency"))
    agent = EvidenceAgent(model, extractor, AgentTraceStore(tmp_path / "t.jsonl"))

    with_agent = route_all(dataset, extractor, agent=agent)
    without = {row["message_id"]: row for row in route_all(dataset, extractor)}
    features_by_id = {
        m["message_id"]: build_features(dataset, m, "")
        for m in dataset.messages
    }

    for row in with_agent:
        if not decide(features_by_id[row["message_id"]]).default_branch:
            assert row == without[row["message_id"]], row["message_id"]


def _gated_rows(dataset, extractor):
    """The rows the agent is actually offered: default_branch with real media text."""
    rows = []
    for message in dataset.messages:
        media_text = media_text_for(dataset, message, extractor)
        features = build_features(dataset, message, media_text)
        if decide(features).default_branch:
            rows.append((message, features))
    return rows


def test_agent_replays_from_a_warm_cache_with_no_api_key(dataset, extractor, tmp_path, monkeypatch):
    """A judge without a key must still see the agent's decisions, not a silent degrade.

    The model is constructed lazily, so a warm cache needs no key at all. Every gated row must
    come from the trace file; falling back to rules-only here is the bug this pins.
    """
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("router.cli.load_env", lambda *a, **k: None)
    traces = tmp_path / "traces.jsonl"
    gated = _gated_rows(dataset, extractor)

    # Warm the cache with a verdict that differs from the rules verdict on every gated row, so
    # a degrade to rules-only cannot masquerade as a successful replay.
    store = AgentTraceStore(traces)
    for message, features in gated:
        store.record(f"{message['message_id']}:{context_hash(message, features)}", [{
            "event": "outcome", "terminal": "decided", "action": "notify",
            "reason_key": "direct_request", "evidence": "none", "grounding": None, "trace": [],
        }])

    out = tmp_path / "output.csv"
    main(["--dataset", "dataset", "--output", str(out), "--also-write", "",
          "--agent", "--agent-traces", str(traces)])

    rows = {r["message_id"]: r for r in csv.DictReader(out.open(encoding="utf-8"))}
    assert len(gated) == 27
    for message, _ in gated:
        assert rows[message["message_id"]]["action"] == "notify", message["message_id"]


def test_a_cache_miss_without_an_api_key_falls_back_and_says_why(
    dataset, extractor, tmp_path, monkeypatch, capsys
):
    """Lazy construction must not swallow the failure: a genuine miss needs a warning."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("router.cli.load_env", lambda *a, **k: None)
    out = tmp_path / "output.csv"

    main(["--dataset", "dataset", "--output", str(out), "--also-write", "",
          "--agent", "--agent-traces", str(tmp_path / "empty.jsonl")])

    assert "OPENROUTER_API_KEY" in capsys.readouterr().err
    golden = {r["message_id"]: r for r in csv.DictReader(
        Path("tests/golden/output_rules_only.csv").open(encoding="utf-8"))}
    rows = {r["message_id"]: r for r in csv.DictReader(out.open(encoding="utf-8"))}
    assert rows == golden


def test_the_prompt_does_not_hand_the_model_the_features_block(dataset, extractor, tmp_path):
    """Run 3 added the features block and search_history stopped firing (3 rows -> 0).

    The self-citation guidance from run 3 is a separate win and must survive.
    """
    assert "features" not in SYSTEM
    assert "empty list" in SYSTEM  # the self-citation guidance
    captured = {}
    model = Model(lambda messages, tools: (
        captured.setdefault("user", messages[1]["content"]),
        _decide(action="digest", reason_key="no_urgency", evidence_message_ids=[]),
    )[1])

    _run(dataset, extractor, _default_branch_message(dataset), model,
         AgentTraceStore(tmp_path / "t.jsonl"))

    assert "features" not in captured["user"]


def test_agent_off_reproduces_the_golden_byte_for_byte(dataset, tmp_path):
    out = tmp_path / "output.csv"
    main(["--dataset", "dataset", "--output", str(out), "--also-write", "", "--no-model"])

    assert out.read_bytes() == Path("tests/golden/output_rules_only.csv").read_bytes()
