"""Print only the rows that changed between two prediction CSVs.

Usage:
    python scripts/diff_output.py OLD NEW [--dataset DIR]

OLD is usually tests/golden/output_rules_only.csv and NEW the current output.csv.
For each changed row it shows the fired rule (from the current build) and every
column that moved. Exits 1 when rows changed, 0 when the files match.
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

COLUMNS = ("action", "message_type", "reason", "confidence", "evidence_message_ids")


def _rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return {row["message_id"]: row for row in csv.DictReader(handle)}


_state = {}


def _rule_for(dataset_dir, message_id):
    if not _state:
        from router.context import Dataset
        from router.media import CachedExtractor, NullExtractor

        dataset = Dataset.load(dataset_dir)
        _state["by_id"] = {m["message_id"]: m for m in dataset.messages}
        _state["extractor"] = CachedExtractor(NullExtractor(), "cache/media_text.json")
        _state["dataset"] = dataset
    msg = _state["by_id"].get(message_id)
    if msg is None:
        return "?"
    try:
        from router.features import build_features
        from router.rules import decide

        media = msg["media_id"]
        media_text = (
            _state["extractor"].text_for(
                media, _state["dataset"].media_path(msg["media_type"], media)
            )
            if media
            else ""
        )
        return decide(build_features(_state["dataset"], msg, media_text)).rule
    except Exception:
        return "?"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Print rows that changed between two prediction CSVs"
    )
    parser.add_argument("old", help="old predictions CSV (usually the golden file)")
    parser.add_argument("new", help="new predictions CSV")
    parser.add_argument("--dataset", default="dataset", help="dataset dir to derive rules")
    args = parser.parse_args(argv)

    old, new = _rows(args.old), _rows(args.new)
    changed = 0
    for message_id, row in new.items():
        if message_id not in old:
            print(f"{message_id}: added")
            changed += 1
            continue
        prev = old[message_id]
        diffs = [column for column in COLUMNS if prev[column] != row[column]]
        if not diffs:
            continue
        changed += 1
        print(f"{message_id} ({_rule_for(args.dataset, message_id)}):")
        for column in diffs:
            print(f"  {column}: {prev[column]!r} -> {row[column]!r}")
    print(f"\n{changed} changed row(s)")
    return 0 if changed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
