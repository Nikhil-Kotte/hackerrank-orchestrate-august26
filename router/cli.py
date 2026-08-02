import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Callable

from router.adjudicator import Adjudicator
from router.agent import DEFAULT_TRACES, AgentTraceStore, EvidenceAgent, OpenRouterAgentModel
from router.audit import DEFAULT_AUDIT_LOG, DecisionAuditor
from router.context import Dataset
from router.decisions import DEFAULT_DECISIONS
from router.media import ByMediaType, CachedExtractor, Extractor, NullExtractor
from router.pipeline import OUTPUT_COLUMNS, route_all

DEFAULT_CACHE = "cache/media_text.json"


def load_env(path: Path | str = ".env") -> None:
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


def _adapter(name: str, build: Callable[[], Extractor]) -> Extractor | None:
    try:
        return build()
    except Exception as error:
        print(f"warning: {name} unavailable ({error}); replaying cache", file=sys.stderr)
        return None


def _extractor(cache_path: Path | str, refresh: bool) -> CachedExtractor:
    vision: Extractor | None = None
    audio: Extractor | None = None
    if refresh or os.environ.get("OPENROUTER_API_KEY"):
        def build_vision() -> Extractor:
            from router.openrouter import OpenRouterExtractor

            return OpenRouterExtractor()

        vision = _adapter("OpenRouter", build_vision)
    if refresh or os.environ.get("GROQ_API_KEY"):
        def build_audio() -> Extractor:
            from router.groq import GroqExtractor

            return GroqExtractor()

        audio = _adapter("Groq", build_audio)
    inner = ByMediaType(audio=audio, default=vision or NullExtractor())
    return CachedExtractor(inner, cache_path, refresh=refresh)


def _adjudicator(args: argparse.Namespace) -> Adjudicator | None:
    try:
        return Adjudicator(cache_path=args.decisions, refresh=args.refresh_decisions)
    except Exception as error:
        print(f"warning: adjudicator unavailable ({error}); running rules-only", file=sys.stderr)
        return None


class _LazyAgentModel:
    """Builds the OpenRouter client on the first genuine cache miss.

    A warm trace cache needs no network, so constructing the client up front would make
    ``--agent`` unusable without a key and degrade it silently to rules-only. Deferring the
    construction keeps replay offline while still reporting the failure on a real miss.
    """

    def __init__(self) -> None:
        self._model: OpenRouterAgentModel | None = None
        self._warned = False

    def __call__(self, messages: list[dict], tools: list[dict]) -> list[dict]:
        if self._model is None:
            try:
                self._model = OpenRouterAgentModel()
            except Exception as error:
                # Warn once, then re-raise: the loop records this as an api_error fallback, so
                # the row keeps the rules verdict and the trace says why.
                if not self._warned:
                    print(f"warning: evidence agent unavailable ({error}); "
                          "falling back to the rules verdict on uncached rows", file=sys.stderr)
                    self._warned = True
                raise
        return self._model(messages, tools)


def _agent(args: argparse.Namespace, extractor: Extractor) -> EvidenceAgent | None:
    if args.no_model:
        return None
    store = AgentTraceStore(args.agent_traces, refresh=args.refresh_agent)
    return EvidenceAgent(_LazyAgentModel(), extractor, store)


def write_output(rows: list[dict], path: Path | str) -> None:
    path = Path(path)
    if path.parent != Path(""):
        path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(OUTPUT_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
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
    parser.add_argument(
        "--no-model",
        action="store_true",
        help="force the rules-only path, bypassing any model-in-the-loop stage",
    )
    parser.add_argument(
        "--adjudicate",
        action="store_true",
        help="offer default-branch rows to the adjudicator model (off by default)",
    )
    parser.add_argument(
        "--decisions",
        default=DEFAULT_DECISIONS,
        help="adjudicator verdict cache",
    )
    parser.add_argument(
        "--refresh-decisions",
        action="store_true",
        help="re-run the model instead of replaying the verdict cache",
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help="run the evidence-gathering agent over default-branch rows (off by default)",
    )
    parser.add_argument(
        "--refresh-agent",
        action="store_true",
        help="call the model instead of replaying the agent trace cache",
    )
    parser.add_argument(
        "--agent-traces",
        default=DEFAULT_TRACES,
        help="agent tool-call trace cache",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help=f"write one JSONL trace per decision to {DEFAULT_AUDIT_LOG}",
    )
    args = parser.parse_args(argv)

    load_env()
    dataset = Dataset.load(args.dataset)
    extractor = _extractor(args.cache, args.refresh_media)
    adjudicator = _adjudicator(args) if args.adjudicate and not args.no_model else None
    agent = _agent(args, extractor) if args.agent else None
    audit = DecisionAuditor() if args.audit else None
    rows = route_all(dataset, extractor, adjudicator, audit, agent)
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
