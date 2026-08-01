"""Extract media referenced by sample_messages.csv that is missing from the cache.

Fills only cache misses. Unlike `main.py --refresh-media` this never re-extracts a committed
entry, so the 110-row output stays byte-identical.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import csv

from router.cli import DEFAULT_CACHE, _extractor, load_env
from router.context import Dataset


def main(dataset_dir="dataset", cache_path=DEFAULT_CACHE):
    load_env()
    dataset = Dataset.load(dataset_dir)
    extractor = _extractor(cache_path, refresh=False)

    with open(f"{dataset_dir}/sample_messages.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    seen = set()
    for row in rows:
        media_id = row["media_id"]
        if not media_id or media_id in seen:
            continue
        seen.add(media_id)
        path = dataset.media_path(row["media_type"], media_id)
        key = extractor._key(media_id, path)
        status = "cached" if key in extractor.entries else "extracting"
        text = extractor.text_for(media_id, path)
        print(f"{media_id:<10} {status:<10} {len(text):>5} chars  {text[:70]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
