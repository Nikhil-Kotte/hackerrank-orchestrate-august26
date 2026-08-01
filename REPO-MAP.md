# Repo brief

Generated 2026-08-01 by repo-map.sh.
Root: C:/Users/Nkroc/OneDrive/Desktop/College/hackerrank-orchestrate-august26
Enumeration: git-aware with hard excludes and .repomapignore
Candidate files: 85

## Overview

- README anchor: README.md
- Detected stack profile:
  - Python

## Entry points

- code/evaluation/main.py
- router/cli.py
- code/main.py

## Core modules (ranked, import fan-in scan)

- router/context.py (score 7)
- router/media.py (score 5)
- router/pipeline.py (score 4)
- router/rules.py (score 4)
- router/retrieval.py (score 3)
- code/evaluation/main.py (score 2)
- code/main.py (score 2)
- router/cli.py (score 2)
- router/evaluate.py (score 2)
- router/features.py (score 2)

## Tests

- tests/test_context.py
- tests/test_contract.py
- tests/test_evaluate.py
- tests/test_features.py
- tests/test_media.py
- tests/test_pipeline.py
- tests/test_retrieval.py
- tests/test_rules.py

## Ignored paths

- .git/
- node_modules/
- bower_components/
- jspm_packages/
- vendor/
- Pods/
- .venv/
- venv/
- env/
- ENV/
- __pycache__/
- .mypy_cache/
- .pytest_cache/
- .ruff_cache/
- .tox/
- .nox/
- .cache/
- dist/
- build/
- site/
- coverage/
- htmlcov/
- .next/
- out/
- .nuxt/
- .svelte-kit/
- target/
- bin/
- obj/
- tmp/
- temp/
- .idea/
- .vscode/
- .gradle/
- .terraform/
- .serverless/
- .repomap.json (optional overrides applied on top of generic detection)

## Confidence notes

- Repo-specific overrides from .repomap.json were layered on top of generic detection.
- This brief is evidence-backed from manifests/configs, common entrypoint rules, and lightweight reference centrality.
- Primary entry point is code/main.py. The generic scan also lists code/evaluation/main.py under Entry points because it matches main.py first in sort order; that file is the sample scorer, not the router.
- The importable package is router/, not code/. A code/ package would shadow the stdlib code module that pdb imports, which breaks pytest at collection time. code/main.py is a thin entry-point shim kept for the AGENTS.md section 6.4 convention.
- Predictions are written to dataset/output.csv, one row per message_id in dataset/messages.csv (110 rows). Columns are fixed: message_id,action,message_type,reason,confidence,evidence_message_ids.
- dataset/ is organizer-provided input and is not modified by the solution apart from output.csv.
- Detection still relies on common naming conventions; highly nonstandard repo layouts may need manual review to confirm entrypoints and core modules.
