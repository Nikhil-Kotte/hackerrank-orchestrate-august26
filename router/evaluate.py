import argparse
import csv
from collections import Counter

from router.cli import DEFAULT_CACHE, _extractor, load_env
from router.context import Dataset
from router.pipeline import route_message
from router.rules import CONFIDENCE_BANDS


def _ids(value):
    if not value or value == "none":
        return set()
    return {part.strip() for part in value.split(";") if part.strip()}


def score(predictions, truth):
    by_id = {row["message_id"]: row for row in predictions}
    total = len(truth)
    actions = types = 0
    confusion = Counter()
    evidence_scores = []
    out_of_band = []

    for expected in truth:
        actual = by_id[expected["message_id"]]
        if actual["action"] == expected["action"]:
            actions += 1
        else:
            confusion[(expected["action"], actual["action"])] += 1
        if actual["message_type"] == expected["message_type"]:
            types += 1

        wanted = _ids(expected["evidence_message_ids"])
        got = _ids(actual["evidence_message_ids"])
        if wanted:
            evidence_scores.append(len(wanted & got) / len(wanted))
        elif not got:
            evidence_scores.append(1.0)
        else:
            evidence_scores.append(0.0)

        low, high = CONFIDENCE_BANDS[actual["action"]]
        if not low <= float(actual["confidence"]) <= high:
            out_of_band.append(expected["message_id"])

    return {
        "count": total,
        "action_accuracy": actions / total,
        "type_accuracy": types / total,
        "evidence_recall": sum(evidence_scores) / total,
        "confusion": confusion,
        "out_of_band": out_of_band,
        "action_mix": Counter(by_id[row["message_id"]]["action"] for row in truth),
        "type_mix": Counter(by_id[row["message_id"]]["message_type"] for row in truth),
    }


def evaluate_samples(dataset_dir="dataset", cache_path=DEFAULT_CACHE):
    load_env()
    dataset = Dataset.load(dataset_dir)
    with open(f"{dataset_dir}/sample_messages.csv", newline="", encoding="utf-8") as handle:
        truth = list(csv.DictReader(handle))
    extractor = _extractor(cache_path, refresh=False)
    predictions = [route_message(dataset, row, extractor) for row in truth]
    return predictions, truth, score(predictions, truth)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Score predictions against the solved samples")
    parser.add_argument("--dataset", default="dataset", help="directory holding the CSVs")
    parser.add_argument("--cache", default=DEFAULT_CACHE, help="media extraction cache")
    args = parser.parse_args(argv)

    predictions, truth, report = evaluate_samples(args.dataset, args.cache)
    by_id = {row["message_id"]: row for row in predictions}

    print(f"scored {report['count']} solved sample rows")
    print(f"  action accuracy   {report['action_accuracy']:.3f}")
    print(f"  type accuracy     {report['type_accuracy']:.3f}")
    print(f"  evidence recall   {report['evidence_recall']:.3f}")
    print(f"  predicted actions {dict(report['action_mix'])}")
    print(f"  predicted types   {dict(report['type_mix'])}")
    if report["out_of_band"]:
        print(f"  out of band       {report['out_of_band']}")

    if report["confusion"]:
        print("\nconfusion (expected -> predicted):")
        for (expected, actual), count in sorted(report["confusion"].items()):
            print(f"  {expected:>7} -> {actual:<7} {count}")

    print("\nmisses:")
    for expected in truth:
        actual = by_id[expected["message_id"]]
        if (actual["action"], actual["message_type"]) == (
            expected["action"],
            expected["message_type"],
        ):
            continue
        print(
            f"  {expected['message_id']}"
            f"  want {expected['action']}/{expected['message_type']}"
            f"  got {actual['action']}/{actual['message_type']}"
        )
    return report


if __name__ == "__main__":
    main()
