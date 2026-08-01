import json

from router.media import ByMediaType, CachedExtractor, StubExtractor


class CountingExtractor:
    def __init__(self, text="fresh"):
        self.text = text
        self.calls = 0

    def text_for(self, media_id, file_path):
        self.calls += 1
        return self.text


def _media_file(tmp_path, contents=b"pixels"):
    path = tmp_path / "img_001.jpg"
    path.write_bytes(contents)
    return path


def test_a_cache_hit_never_reaches_the_inner_extractor(tmp_path):
    media = _media_file(tmp_path)
    inner = CountingExtractor()
    warm = CachedExtractor(inner, tmp_path / "cache.json")
    warm.text_for("img_001", media)

    replay = CachedExtractor(CountingExtractor("should not be used"), tmp_path / "cache.json")
    text = replay.text_for("img_001", media)

    assert text == "fresh"


def test_a_cache_miss_delegates_once_and_persists_the_result(tmp_path):
    media = _media_file(tmp_path)
    inner = CountingExtractor()
    cache_path = tmp_path / "cache.json"
    extractor = CachedExtractor(inner, cache_path)

    extractor.text_for("img_001", media)
    extractor.text_for("img_001", media)

    assert inner.calls == 1
    assert json.loads(cache_path.read_text(encoding="utf-8"))


def test_edited_media_is_re_extracted_because_the_key_includes_the_bytes(tmp_path):
    media = _media_file(tmp_path)
    inner = CountingExtractor()
    extractor = CachedExtractor(inner, tmp_path / "cache.json")
    extractor.text_for("img_001", media)

    media.write_bytes(b"different pixels")
    extractor.text_for("img_001", media)

    assert inner.calls == 2


def test_an_extractor_failure_yields_empty_text_so_every_row_still_emits(tmp_path):
    class Broken:
        def text_for(self, media_id, file_path):
            raise RuntimeError("no api key")

    extractor = CachedExtractor(Broken(), tmp_path / "cache.json")

    assert extractor.text_for("img_001", _media_file(tmp_path)) == ""


def test_audio_goes_to_the_audio_extractor_and_everything_else_to_the_default(tmp_path):
    audio = CountingExtractor("transcript")
    default = CountingExtractor("caption")
    extractor = ByMediaType(audio=audio, default=default)

    assert extractor.text_for("vn_004", tmp_path / "vn_004.mp3") == "transcript"
    assert extractor.text_for("img_002", tmp_path / "img_002.jpg") == "caption"
    assert audio.calls == 1
    assert default.calls == 1


def test_dispatch_falls_back_to_the_default_when_there_is_no_audio_extractor(tmp_path):
    default = CountingExtractor("caption")
    extractor = ByMediaType(audio=None, default=default)

    assert extractor.text_for("vn_004", tmp_path / "vn_004.mp3") == "caption"


def test_the_stub_extractor_serves_the_transcripts_tests_hand_it():
    extractor = StubExtractor({"vn_001": "call me when you reach"})

    assert extractor.text_for("vn_001", None) == "call me when you reach"
    assert extractor.text_for("vn_999", None) == ""
