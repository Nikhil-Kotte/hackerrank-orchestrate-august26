"""Report how the adjudicator arbitrates the default-branch rows.

Usage:
    python scripts/adjudication_report.py [--dataset DIR] [--cache FILE]
                                          [--decisions FILE] [--refresh-decisions]

Replays committed verdicts from cache/decisions.json unless --refresh-decisions is given.
The report is decision-level and never writes output.csv - the shipped predictions stay
rules-only. The thing to look for is how many rows the model escalates to notify; the rules
already pin the other 59 to mute, and only default-branch digests are offered here.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from router.adjudicator import Adjudicator, build_adjudication_context  # noqa: E402
from router.cli import DEFAULT_CACHE, _extractor, load_env  # noqa: E402
from router.context import Dataset  # noqa: E402
from router.decisions import DEFAULT_DECISIONS  # noqa: E402
from router.features import build_features  # noqa: E402
from router.pipeline import media_text_for  # noqa: E402
from router.retrieval import analogous_history  # noqa: E402
from router.rules import decide  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description="Adjudication report over default-branch rows")
    parser.add_argument("--dataset", default="dataset", help="directory holding the CSVs")
    parser.add_argument("--cache", default=DEFAULT_CACHE, help="media extraction cache")
    parser.add_argument("--decisions", default=DEFAULT_DECISIONS, help="verdict cache")
    parser.add_argument("--refresh-decisions", action="store_true", help="re-run the model")
    args = parser.parse_args(argv)

    load_env()
    dataset = Dataset.load(args.dataset)
    extractor = _extractor(args.cache, refresh=False)
    adjudicator = Adjudicator(cache_path=args.decisions, refresh=args.refresh_decisions)

    offered = 0
    escalated = []
    reasons = Counter()
    grounded = 0
    for message in dataset.messages:
        media_text = media_text_for(dataset, message, extractor)
        features = build_features(dataset, message, media_text)
        rule_decision = decide(features)
        if not rule_decision.default_branch:
            continue
        offered += 1
        candidates = analogous_history(dataset, message, media_text or message["message_text"])
        context = build_adjudication_context(message, features, media_text, candidates[:3])
        decision, grounding = adjudicator.decision_for(features, context)
        reasons[decision.rule] += 1
        if grounding:
            grounded += 1
        if decision.action != rule_decision.action:
            escalated.append((message["message_id"], decision.rule, decision.confidence))

    print(f"offered to the adjudicator: {offered} default-branch rows")
    print(f"escalated to notify:        {len(escalated)}")
    print(f"grounded on a candidate:    {grounded}")
    print("reason_key mix:")
    for reason, count in reasons.most_common():
        print(f"  {reason:<28} {count}")
    for message_id, rule, confidence in escalated:
        print(f"  escalated {message_id}: {rule} @ {confidence:.2f}")


if __name__ == "__main__":
    sys.exit(main())
