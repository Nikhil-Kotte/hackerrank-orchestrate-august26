"""Contract test against the real OpenRouter API for the adjudicator.

Deselected by default. The hermetic suite never builds an Adjudicator, so it would not notice
a retired model id, a changed schema, or a rejected reason key. This test is what notices.

    python -m pytest -m live -v          # needs OPENROUTER_API_KEY
"""

import pytest

from router.adjudicator import REASON_ACTIONS, Adjudicator, build_adjudication_context
from router.cli import DEFAULT_CACHE, _extractor, load_env
from router.context import Dataset
from router.features import build_features
from router.pipeline import media_text_for
from router.retrieval import analogous_history
from router.rules import decide

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def dataset():
    load_env()
    return Dataset.load("dataset")


def _require(name):
    import os

    if not os.environ.get(name):
        pytest.skip(f"{name} is not set")


def test_the_adjudicator_returns_a_schema_valid_verdict_on_a_real_call(dataset, tmp_path):
    _require("OPENROUTER_API_KEY")
    extractor = _extractor(DEFAULT_CACHE, refresh=False)
    adjudicator = Adjudicator(cache_path=tmp_path / "decisions.json", refresh=True)

    message = next(
        m
        for m in dataset.messages
        if decide(build_features(dataset, m, media_text_for(dataset, m, extractor))).default_branch
    )
    media_text = media_text_for(dataset, message, extractor)
    features = build_features(dataset, message, media_text)
    candidates = analogous_history(dataset, message, media_text or message["message_text"])[:3]
    context = build_adjudication_context(message, features, media_text, candidates)

    decision, grounding = adjudicator.decision_for(features, context)

    assert decision.action in ("notify", "digest")
    assert decision.rule in REASON_ACTIONS
    assert REASON_ACTIONS[decision.rule] == decision.action
    if grounding is not None:
        assert grounding in {row["message_id"] for row in candidates}
