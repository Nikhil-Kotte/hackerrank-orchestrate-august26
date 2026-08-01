import sys

import pytest

from router.groq import DEFAULT_MODEL, GroqExtractor


class FakeTranscriptions:
    def __init__(self, text):
        self.text = text
        self.seen = None

    def create(self, **kwargs):
        self.seen = kwargs
        return type("Result", (), {"text": self.text})()


class FakeClient:
    def __init__(self, text):
        self.audio = type("Audio", (), {"transcriptions": FakeTranscriptions(text)})()


def test_a_missing_key_is_refused_up_front(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        GroqExtractor()


def test_the_key_check_precedes_the_openai_import(monkeypatch):
    # A clean-room without the openai package must still fail with the key error,
    # not a ModuleNotFoundError from `from openai import OpenAI`.
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "openai", None)

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        GroqExtractor()


def test_the_transcript_is_returned_stripped(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    clip = tmp_path / "vn_004.mp3"
    clip.write_bytes(b"audio")
    extractor = GroqExtractor.__new__(GroqExtractor)
    extractor.model = DEFAULT_MODEL
    extractor.client = FakeClient("  reaching in ten minutes  ")

    assert extractor.text_for("vn_004", clip) == "reaching in ten minutes"


def test_no_decoding_prompt_is_sent_because_whisper_echoes_it(tmp_path):
    clip = tmp_path / "vn_007.mp3"
    clip.write_bytes(b"audio")
    extractor = GroqExtractor.__new__(GroqExtractor)
    extractor.model = DEFAULT_MODEL
    extractor.client = FakeClient("hello")

    extractor.text_for("vn_007", clip)

    assert "prompt" not in extractor.client.audio.transcriptions.seen


def test_a_missing_file_yields_empty_text_without_calling_the_api(tmp_path):
    extractor = GroqExtractor.__new__(GroqExtractor)
    extractor.model = DEFAULT_MODEL
    extractor.client = FakeClient("never used")

    assert extractor.text_for("vn_999", tmp_path / "absent.mp3") == ""
    assert extractor.client.audio.transcriptions.seen is None
