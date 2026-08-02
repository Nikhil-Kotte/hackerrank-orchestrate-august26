import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from coherence_check import find_incoherent  # noqa: E402

from router.cli import DEFAULT_CACHE  # noqa: E402
from router.context import Dataset  # noqa: E402
from router.media import CachedExtractor, NullExtractor  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dataset():
    return Dataset.load("dataset")


@pytest.fixture(scope="module")
def shipped():
    # output.csv is submitted as a separate artifact and is not part of code.zip, so a
    # reviewer extracting the bundle must get a skip here rather than a collection error.
    path = ROOT / "output.csv"
    if not path.exists():
        pytest.skip("output.csv is submitted separately and is not part of code.zip")
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_the_shipped_output_is_coherent_with_the_build(dataset, shipped):
    extractor = CachedExtractor(NullExtractor(), DEFAULT_CACHE)
    assert find_incoherent(dataset, shipped, extractor) == []
