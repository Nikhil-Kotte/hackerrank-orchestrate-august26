"""The committed cache must cover every media file the router or the scorer will touch.

A miss degrades silently to empty text (CachedExtractor.text_for swallows the failure), which
is how the sample scorer ran for a while against hand-written transcripts instead of real
extraction. This is the test that catches it.
"""

import csv

import pytest

from router.cli import DEFAULT_CACHE
from router.context import Dataset
from router.media import CachedExtractor, NullExtractor


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load("dataset")


@pytest.fixture(scope="module")
def cache():
    return CachedExtractor(NullExtractor(), DEFAULT_CACHE)


def _media_rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row["media_id"]]


def _missing(dataset, cache, rows):
    missing = []
    for row in rows:
        path = dataset.media_path(row["media_type"], row["media_id"])
        if cache._key(row["media_id"], path) not in cache.entries:
            missing.append(row["media_id"])
    return sorted(set(missing))


def test_every_message_media_id_is_cached(dataset, cache):
    assert _missing(dataset, cache, _media_rows("dataset/messages.csv")) == []


def test_every_sample_media_id_is_cached(dataset, cache):
    assert _missing(dataset, cache, _media_rows("dataset/sample_messages.csv")) == []


def test_every_media_file_referenced_by_a_message_exists_on_disk(dataset):
    rows = _media_rows("dataset/messages.csv") + _media_rows("dataset/sample_messages.csv")

    for row in rows:
        path = dataset.media_path(row["media_type"], row["media_id"])
        assert path is not None and path.exists(), row["media_id"]


def test_the_cache_key_pins_the_file_contents(dataset, cache):
    path = dataset.media_path("image", "img_010")

    assert cache._key("img_010", path).startswith("img_010:")
    assert cache._key("img_010", path) != cache._key("img_010", None)
