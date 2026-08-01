"""Print what each prediction actually rests on, so a reason can be checked against evidence.

Read-only. Changes no labels. Reason and type both derive from the fired rule, so they cannot
disagree with each other; what can be wrong is a reason asserting a fact the feature that fired
does not establish. That is what this dumps.

    python scripts/audit_reasons.py                 # every notify row
    python scripts/audit_reasons.py --rule business_order_update
    python scripts/audit_reasons.py --type payment urgent event
    python scripts/audit_reasons.py --all
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse

from router.cli import DEFAULT_CACHE, load_env
from router.context import Dataset
from router.features import build_features
from router.media import CachedExtractor, NullExtractor
from router.pipeline import media_text_for
from router.retrieval import analogous_history
from router.rules import decide


def _collapse(text, limit):
    flat = " ".join((text or "").split())
    return flat[:limit] + ("..." if len(flat) > limit else "")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="dataset")
    parser.add_argument("--cache", default=DEFAULT_CACHE)
    parser.add_argument("--rule", nargs="*", help="only these fired rules")
    parser.add_argument("--type", nargs="*", help="only these message types")
    parser.add_argument("--action", nargs="*", default=["notify"], help="default: notify")
    parser.add_argument("--all", action="store_true", help="every row")
    args = parser.parse_args(argv)

    load_env()
    dataset = Dataset.load(args.dataset)
    extractor = CachedExtractor(NullExtractor(), args.cache)

    shown = 0
    for message in dataset.messages:
        media_text = media_text_for(dataset, message, extractor)
        features = build_features(dataset, message, media_text)
        decision = decide(features)

        if not args.all:
            if args.rule and decision.rule not in args.rule:
                continue
            if args.type and decision.message_type not in args.type:
                continue
            if not args.rule and not args.type and decision.action not in args.action:
                continue

        shown += 1
        text = " ".join(p for p in (message["message_text"], media_text) if p)
        candidates = analogous_history(dataset, message, text)
        business = dataset.businesses.get(message["business_id"])
        history = dataset.business_history_for(message["user_id"], message["business_id"])

        print("=" * 78)
        print(f"{message['message_id']}  {decision.action}/{decision.message_type}"
              f"  rule={decision.rule}  conf={decision.confidence}")
        print(f"  reason   {decision.reason}")
        print(f"  source   {_collapse(message['message_text'], 150)!r}")
        if media_text:
            print(f"  media    {_collapse(media_text, 150)!r}")
        print(f"  context  conv={message['conversation_type']}"
              f" group={message['group_id'] or '-'}"
              f" sender={message['sender_user_id'] or '-'}"
              f" at={message['created_at']}")
        if business:
            print(f"  business {business['display_name']} verified={business['verified']}"
                  f" reports30d={business['user_reports_30d']}"
                  f" domain={business['domain_used_by_sender'] or '-'}"
                  f" ({business['domain_used_by_sender_age_days']}d)")
        if history:
            print(f"  relation why_user_knows_account={history['why_user_knows_account']!r}"
                  f" opened30d={history['messages_opened_30d']}"
                  f" dismissed30d={history['messages_dismissed_30d']}")
        print(f"  behavior open={features.sender_open_rate:.2f}"
              f" dismiss={features.prior_dismiss_rate:.2f}"
              f" muted_after={features.prior_muted_after}"
              f" has_history={features.has_sender_history}"
              f" daily_dismiss={features.daily_dismiss_ratio:.2f}")
        for row in candidates[:2]:
            print(f"  evidence {row['message_id']}  {_collapse(row['message_text'], 110)!r}")
        if not candidates:
            print("  evidence none")

    print("=" * 78)
    print(f"{shown} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
