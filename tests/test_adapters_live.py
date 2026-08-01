"""Contract tests against the real OpenRouter and Groq APIs.

Deselected by default. The routing pipeline never calls these adapters - it replays
cache/media_text.json - so nothing in the hermetic suite would notice a retired model id, a
changed JSON schema, or a rejected audio format. These tests are what notice.

    python -m pytest -m live -v          # needs OPENROUTER_API_KEY and GROQ_API_KEY

Assertions are about the contract, not the wording: models are free to phrase a transcript
differently between runs, so we pin the tokens the extraction is worthless without.
"""

import pytest

from router.cli import load_env
from router.context import Dataset

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def dataset():
    load_env()
    return Dataset.load("dataset")


def _require(name):
    import os

    if not os.environ.get(name):
        pytest.skip(f"{name} is not set")


def test_the_vision_adapter_reads_text_off_a_real_poster(dataset):
    _require("OPENROUTER_API_KEY")
    from router.openrouter import OpenRouterExtractor

    text = OpenRouterExtractor().text_for("img_010", dataset.media_path("image", "img_010"))

    assert "amazon" in text.lower()


def test_the_vision_adapter_reports_an_image_with_no_legible_text_as_empty(dataset):
    _require("OPENROUTER_API_KEY")
    from router.openrouter import OpenRouterExtractor

    text = OpenRouterExtractor().text_for("img_008", dataset.media_path("image", "img_008"))

    assert text == ""


def test_the_speech_adapter_transcribes_a_real_voice_note(dataset):
    _require("GROQ_API_KEY")
    from router.groq import GroqExtractor

    text = GroqExtractor().text_for("vn_002", dataset.media_path("voice", "vn_002")).lower()

    assert "call" in text


def test_a_missing_media_file_yields_empty_text_without_calling_out(dataset):
    _require("OPENROUTER_API_KEY")
    from router.openrouter import OpenRouterExtractor

    assert OpenRouterExtractor().text_for("img_999", None) == ""


def test_the_live_transcripts_still_agree_with_the_committed_cache(dataset):
    """The cache is what output.csv is built from; drift here invalidates the submission."""
    _require("OPENROUTER_API_KEY")
    from router.media import CachedExtractor, NullExtractor
    from router.openrouter import OpenRouterExtractor

    cached = CachedExtractor(NullExtractor(), "cache/media_text.json")
    path = dataset.media_path("image", "img_011")

    live = OpenRouterExtractor().text_for("img_011", path)
    committed = cached.entries[cached._key("img_011", path)]

    assert "consent" in live.lower()
    assert "consent" in committed.lower()
