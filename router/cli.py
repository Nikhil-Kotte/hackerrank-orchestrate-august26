import argparse
import csv
import os
import sys
from pathlib import Path

from router.context import Dataset
from router.media import ByMediaType, CachedExtractor, NullExtractor
from router.pipeline import OUTPUT_COLUMNS, route_all

DEFAULT_CACHE = "cache/media_text.json"


def load_env(path=".env"):
    """Populate os.environ from a .env file. The real environment always wins."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _adapter(name, build):
    try:
        return build()
    except Exception as error:
        print(f"warning: {name} unavailable ({error}); replaying cache", file=sys.stderr)
        return None


def _extractor(cache_path, refresh):
    vision = audio = None
    if refresh or os.environ.get("OPENROUTER_API_KEY"):
        def build_vision():
            from router.openrouter import OpenRouterExtractor

            return OpenRouterExtractor()

        vision = _adapter("OpenRouter", build_vision)
    if refresh or os.environ.get("GROQ_API_KEY"):
        def build_audio():
            from router.groq import GroqExtractor

            return GroqExtractor()

        audio = _adapter("Groq", build_audio)
    inner = ByMediaType(audio=audio, default=vision or NullExtractor())
    return CachedExtractor(inner, cache_path, refresh=refresh)


def write_output(rows, path):
    path = Path(path)
    if path.parent != Path(""):
        path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(OUTPUT_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Route WhatsApp messages to notify/digest/mute")
    parser.add_argument("--dataset", default="dataset", help="directory holding the CSVs")
    parser.add_argument("--output", default="output.csv", help="where to write predictions")
    parser.add_argument(
        "--also-write",
        default="dataset/output.csv",
        help="second copy, for the blank template the problem statement ships; '' to skip",
    )
    parser.add_argument("--cache", default=DEFAULT_CACHE, help="media extraction cache")
    parser.add_argument(
        "--refresh-media",
        action="store_true",
        help="re-extract media text through OpenRouter instead of replaying the cache",
    )
    args = parser.parse_args(argv)

    load_env()
    dataset = Dataset.load(args.dataset)
    rows = route_all(dataset, _extractor(args.cache, args.refresh_media))
    write_output(rows, args.output)
    print(f"wrote {len(rows)} rows to {args.output}")
    # problem_statement.md points at dataset/output.csv; the submission checklist names a
    # bare output.csv. Fill both rather than leave a blank template in the package.
    if args.also_write and Path(args.also_write) != Path(args.output):
        write_output(rows, args.also_write)
        print(f"wrote {len(rows)} rows to {args.also_write}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
