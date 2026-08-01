"""Flag output.csv rows whose shipped decision disagrees with the current build.

Usage:
    python scripts/coherence_check.py [--dataset DIR] [--output FILE]

Each shipped cell is re-derived with the current build (same cache replay as the real
run) and compared field by field. Exits 1 when any cell disagrees, 0 when the file is
coherent with the build.
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from router.cli import DEFAULT_CACHE
from router.context import Dataset
from router.media import CachedExtractor, NullExtractor
from router.pipeline import route_message

FIELDS = ("action", "message_type", "reason", "confidence", "evidence_message_ids")


def find_incoherent(dataset, rows, extractor):
    """Return (message_id, field, shipped, build) for every disagreeing cell."""
    by_id = {row["message_id"]: row for row in rows}
    findings = []
    for message in dataset.messages:
        shipped = by_id[message["message_id"]]
        actual = route_message(dataset, message, extractor)
        for field in FIELDS:
            if shipped[field] != actual[field]:
                findings.append((message["message_id"], field, shipped[field], actual[field]))
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check output.csv against the current build")
    parser.add_argument("--dataset", default="dataset", help="directory holding the CSVs")
    parser.add_argument("--output", default="output.csv", help="predictions file to check")
    parser.add_argument("--cache", default=DEFAULT_CACHE, help="media extraction cache")
    args = parser.parse_args(argv)

    dataset = Dataset.load(args.dataset)
    with open(args.output, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    extractor = CachedExtractor(NullExtractor(), args.cache)
    findings = find_incoherent(dataset, rows, extractor)
    for message_id, field, shipped, actual in findings:
        print(f"{message_id} {field}: shipped={shipped!r} build={actual!r}")
    print(f"{len(findings)} incoherent cell(s)")
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
