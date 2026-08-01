# HackerRank Orchestrate

Starter repository for the **HackerRank Orchestrate** 24-hour hackathon.

## Message Notification Router

Build an AI-powered system for WhatsApp that decides which messages deserve immediate attention, which should wait, and which should be muted.

The system must reason over multimodal messages, including text messages, image posters/screenshots, and voice notes.

WhatsApp is noisy. A user can receive family chats, society notices, school updates, co-worker messages, business account promotions, image posters, voice notes, and scams in the same message stream. Treating every message the same creates two bad outcomes: important messages get missed, and unwanted or risky messages interrupt the user.

Read [`problem_statement.md`](./problem_statement.md) for the full task spec, input/output schema, allowed values, and submission format.

---

## Repository Layout

```text
.
├── AGENTS.md                         # Rules for AI coding tools + transcript logging
├── problem_statement.md              # Full challenge statement
├── README.md                         # You are here
└── dataset/
    ├── messages.csv                  # Messages to route
    ├── output.csv                    # Blank submission template
    ├── sample_messages.csv           # Solved examples
    ├── users.csv                     # User notification behavior
    ├── groups.csv                    # Group metadata
    ├── group_members.csv             # User-group relationships
    ├── business_accounts.csv         # Business sender metadata
    ├── user_business_history.csv     # User-business history
    ├── message_history.csv           # Historical messages
    ├── message_events.csv            # User reactions to historical messages
    ├── images.csv                    # Image IDs and media file paths
    ├── voice_notes.csv               # Voice note IDs and media file paths
    ├── daily_notification_summary.csv
    └── media/
        ├── images/
        └── audio/
```

---

## What You Need to Build

For every row in `dataset/messages.csv`, produce one row in `output.csv` with:

| Column | Meaning |
|---|---|
| `message_id` | Incoming message ID |
| `action` | One of `notify`, `digest`, or `mute` |
| `message_type` | Best-fit message category |
| `reason` | Short human-readable explanation |
| `confidence` | Number from `0` to `1` |
| `evidence_message_ids` | Historical message IDs used as evidence; write `none` if there is no useful evidence |

Your system should make personalized decisions using the provided message, user, group, business, media, and historical interaction data.
For image and voice-note messages, `images.csv` and `voice_notes.csv` only provide file paths; your system should inspect the media files themselves.

---

## Suggested Workflow

1. Inspect `dataset/sample_messages.csv` to understand the expected output format.
2. Load `dataset/messages.csv` and all relevant context files.
3. Build your routing system using any approach: LLMs, retrieval, rules, classifiers, agents, or hybrids.
4. Write predictions to `output.csv`.
5. Evaluate your approach on the solved sample rows before submitting.

You may use any language or runtime. Python, JavaScript, and TypeScript are all reasonable choices.

---

## Running This

Python 3.10+ is assumed. Install once:

```bash
pip install -r requirements.txt
```

### Shipped run (no network)

The committed `cache/media_text.json` already holds the OCR and ASR text for every media
message, so the default run is deterministic and calls no API. It writes both `output.csv`
and `dataset/output.csv`:

```bash
python code/main.py
```

`--no-model` forces the same rules-only path explicitly and is what `tests/test_golden.py`
uses to freeze it. The rules-only pipeline achieves 1.000 action accuracy, 1.000 type
accuracy, and 0.750 evidence recall on the 30 solved samples:

```bash
python code/evaluation/main.py
```

### Refreshing media text (network)

To re-extract image posters and voice notes through OpenRouter, set the keys and run with
`--refresh-media`:

```bash
export OPENROUTER_API_KEY=...   # images + voice
export GROQ_API_KEY=...         # voice notes via Whisper (fallback)
python code/main.py --refresh-media
```

### Regression and review tooling

```bash
python -m pytest                              # hermetic suite; no network, no keys
python -m pytest -m live                      # live API contract tests (keys required)
python -m pytest tests/test_golden.py         # byte-identical rules output vs the freeze
python scripts/diff_output.py tests/golden/output_rules_only.csv output.csv   # changed rows
python scripts/coherence_check.py             # shipped output vs the current build
```

`tests/golden/output_rules_only.csv` is the frozen rules-only output. Keep it in sync with
the shipped `output.csv`: regenerate it only when a deliberate rules change is accepted.

### Model-in-the-loop adjudicator (off by default)

An optional second pass offers the default-branch digest rows to a model. It ships **off**:
the default run above is pure rules and never calls an API. The adjudicator is arbitrated
only by the rules' own evidence, `message_type` stays the feature kind, `confidence` is the
reason's calibrated base, and its verdicts are content-hashed into `cache/decisions.json`:

```bash
python code/main.py --adjudicate             # OFF unless you pass this flag
python scripts/adjudication_report.py        # replay the committed verdicts
python scripts/adjudication_report.py --refresh-decisions   # make fresh model calls
python -m pytest tests/test_adjudicator_live.py -m live     # one real call, schema-valid
```

The 51 mute rows are decided by named rules and are never offered to the model, so the
submitted `output.csv` cannot be changed by it.

---

## Requirements

Your solution must:

- be runnable from the terminal
- read the provided files from `dataset/`
- produce a valid `output.csv`
- include one prediction for every `message_id` in `dataset/messages.csv`
- not use organizer-only files or hardcoded labels

If you use API keys or secrets, read them from environment variables. Never hardcode secrets in the repo.

---

## Evaluation

Your `output.csv` will be compared against hidden ground-truth labels.

The scoring will consider:

- correctness of `action`
- correctness of `message_type`
- usefulness and consistency of `reason`
- whether `evidence_message_ids` point to relevant historical messages
- reasonable confidence calibration

Strong systems will combine retrieval, structured metadata, behavioral history, safety checks, OCR/ASR handling, and contextual reasoning.

---

## Chat Transcript Logging

This repo includes an [`AGENTS.md`](./AGENTS.md) file for AI coding tools. It asks compatible tools to append conversation summaries to:

| Platform | Path |
|---|---|
| macOS / Linux | `$HOME/hackerrank_orchestrate_august26/log.txt` |
| Windows | `%USERPROFILE%\hackerrank_orchestrate_august26\log.txt` |

Upload this log as your chat transcript at submission time. Do not paste secrets into the chat.

---

## Submission

Submit the following files as instructed by HackerRank:

1. **Code zip**: full runnable solution, prompts/configs, README, and any evaluation files.
2. **Predictions CSV**: final `output.csv` for all rows in `dataset/messages.csv`.
3. **Chat transcript**: the `log.txt` described above.

Before submitting, confirm:

- `output.csv` has one row per row in `dataset/messages.csv`.
- `output.csv` has the exact required columns in the exact required order.
- Your runnable code and setup instructions are included in `code.zip`.
