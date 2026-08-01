#!/usr/bin/env bash
# Generate REPO-MAP.md as a stack-aware, evidence-backed repo brief.
# Generic by default: stack detection, entrypoints, tests, and integration
# points are all driven by manifests/conventions for the detected stack, not
# by hardcoded project-specific paths. Repo-specific tuning is optional via
# .repomap.json (see below) rather than being baked into the generator.
#
# Usage: bash repomap-genesis.sh [target-dir] [--top-core N]
set -euo pipefail

TARGET='.'
TOP_CORE=10
while [ $# -gt 0 ]; do
  case "$1" in
    --top-core) TOP_CORE="${2:-10}"; shift 2 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) TARGET="$1"; shift ;;
  esac
done

[ -d "$TARGET" ] || { echo "error: not a directory: $TARGET" >&2; exit 1; }
START_DIR="$(cd "$TARGET" && pwd -P)"
ROOT="$(git -C "$START_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
IS_GIT=yes
if [ -z "$ROOT" ]; then
  ROOT="$START_DIR"
  IS_GIT=no
fi
cd "$ROOT"

OUT="$ROOT/REPO-MAP.md"
CONFIG="$ROOT/.repomap.json"
FILES="$(mktemp)"
STACKS="$(mktemp)"
ENTRY="$(mktemp)"
SECONDARY="$(mktemp)"
CORE="$(mktemp)"
TESTS="$(mktemp)"
INTEGRATIONS="$(mktemp)"
IGNORED="$(mktemp)"
OVERRIDE_NOTES="$(mktemp)"
trap 'rm -f "$FILES" "$STACKS" "$ENTRY" "$SECONDARY" "$CORE" "$TESTS" "$INTEGRATIONS" "$IGNORED" "$OVERRIDE_NOTES" "$FILES.filtered" "$FILES.sorted" "$CORE.stripped"' EXIT

add_unique() {
  local file="$1" value="$2"
  grep -qxF "$value" "$file" 2>/dev/null || printf '%s\n' "$value" >> "$file"
}

pick_first() {
  grep -E "$1" "$FILES" 2>/dev/null | head -n 1 || true
}

pick_all() {
  grep -E "$1" "$FILES" 2>/dev/null || true
}

EXCLUDE_DIRS=(
  .git node_modules bower_components jspm_packages vendor Pods
  .venv venv env ENV __pycache__ .mypy_cache .pytest_cache .ruff_cache .tox .nox .cache
  dist build site coverage htmlcov .next out .nuxt .svelte-kit target bin obj tmp temp
  .idea .vscode .gradle .terraform .serverless
)
EXCLUDE_FILES=(REPO-MAP.md coverage-final.json)

if [ "$IS_GIT" = yes ]; then
  args=(ls-files --cached --others --exclude-standard --)
  for d in "${EXCLUDE_DIRS[@]}"; do
    args+=(":(exclude)$d/**")
    args+=(":(exclude)**/$d/**")
  done
  for f in "${EXCLUDE_FILES[@]}"; do
    args+=(":(exclude)$f")
    args+=(":(exclude)**/$f")
  done
  if [ -f .repomapignore ]; then
    while IFS= read -r pat; do
      case "$pat" in
        ''|'#'*) continue ;;
        */)
          p="${pat%/}"
          args+=(":(exclude)$p/**")
          args+=(":(exclude)**/$p/**")
          ;;
        *)
          args+=(":(exclude)$pat")
          args+=(":(exclude)**/$pat")
          ;;
      esac
    done < .repomapignore
  fi
  git -C "$ROOT" "${args[@]}" > "$FILES"
  ENUM_MODE='git-aware with hard excludes and .repomapignore'
else
  find . -type f 2>/dev/null | sed 's|^\./||' > "$FILES"
  grep -Ev '(^|/)(\.git|node_modules|bower_components|jspm_packages|vendor|Pods|\.venv|venv|env|ENV|__pycache__|\.mypy_cache|\.pytest_cache|\.ruff_cache|\.tox|\.nox|\.cache|dist|build|site|coverage|htmlcov|\.next|out|\.nuxt|\.svelte-kit|target|bin|obj|tmp|temp|\.idea|\.vscode|\.gradle|\.terraform|\.serverless)(/|$)|(^|/)(REPO-MAP\.md|coverage-final\.json)$' "$FILES" > "$FILES.filtered" || true
  mv "$FILES.filtered" "$FILES"
  ENUM_MODE='find fallback with hard excludes'
fi

TOTAL_FILES="$(wc -l < "$FILES" | tr -d ' ')"

# ---------------------------------------------------------------------------
# Stack detection from manifests/configs (generic signals, not project names).
# ---------------------------------------------------------------------------
[ -n "$(pick_first '(^|/)pyproject\.toml$|(^|/)requirements(-dev)?\.txt$|(^|/)setup\.py$|(^|/)Pipfile$|(^|/)poetry\.lock$')" ] && add_unique "$STACKS" 'Python'
[ -n "$(pick_first '(^|/)package\.json$|(^|/)pnpm-lock\.yaml$|(^|/)yarn\.lock$|(^|/)package-lock\.json$|(^|/)tsconfig\.json$')" ] && add_unique "$STACKS" 'Node/TypeScript'
[ -n "$(pick_first '(^|/)go\.mod$')" ] && add_unique "$STACKS" 'Go'
[ -n "$(pick_first '(^|/)Cargo\.toml$')" ] && add_unique "$STACKS" 'Rust'
[ -n "$(pick_first '(^|/)pom\.xml$|(^|/)build\.gradle(\.kts)?$|(^|/)settings\.gradle(\.kts)?$')" ] && add_unique "$STACKS" 'Java/Kotlin'
[ -n "$(pick_first '(^|/).*\.csproj$|(^|/)Directory\.Build\.props$|(^|/)global\.json$')" ] && add_unique "$STACKS" '.NET'
[ -n "$(pick_first '(^|/)Gemfile$|(^|/)Rakefile$')" ] && add_unique "$STACKS" 'Ruby'
[ -n "$(pick_first '(^|/)composer\.json$')" ] && add_unique "$STACKS" 'PHP'
[ -n "$(pick_first '(^|/)Dockerfile$|(^|/)docker-compose\.ya?ml$')" ] && add_unique "$STACKS" 'Containers'

# ---------------------------------------------------------------------------
# Entry points by detected stack. Generic conventions per stack, not tied to
# any one project's folder layout.
# ---------------------------------------------------------------------------
if grep -qxF 'Python' "$STACKS" 2>/dev/null; then
  for pat in \
    '(^|/)main\.py$' \
    '(^|/)app/main\.py$' \
    '(^|/)manage\.py$' \
    '(^|/)wsgi\.py$' \
    '(^|/)asgi\.py$' \
    '(^|/)(__main__|cli)\.py$'
  do
    f="$(pick_first "$pat")"
    [ -n "$f" ] && add_unique "$ENTRY" "$f"
  done
fi

if grep -qxF 'Node/TypeScript' "$STACKS" 2>/dev/null; then
  for pat in \
    '(^|/)src/main\.(ts|tsx|js|jsx)$' \
    '(^|/)src/index\.(ts|tsx|js|jsx)$' \
    '(^|/)index\.(ts|tsx|js|jsx)$' \
    '(^|/)main\.(ts|tsx|js|jsx)$' \
    '(^|/)vite\.config\.(ts|js)$' \
    '(^|/)next\.config\.(js|mjs|ts)$' \
    '(^|/)server\.(ts|js)$'
  do
    f="$(pick_first "$pat")"
    [ -n "$f" ] && add_unique "$ENTRY" "$f"
  done
fi

if grep -qxF 'Go' "$STACKS" 2>/dev/null; then
  for pat in '(^|/)cmd/[^/]+/main\.go$' '(^|/)main\.go$'; do
    f="$(pick_first "$pat")"
    [ -n "$f" ] && add_unique "$ENTRY" "$f"
  done
fi

if grep -qxF 'Rust' "$STACKS" 2>/dev/null; then
  for pat in '(^|/)src/main\.rs$' '(^|/)src/lib\.rs$'; do
    f="$(pick_first "$pat")"
    [ -n "$f" ] && add_unique "$ENTRY" "$f"
  done
fi

if grep -qxF 'Java/Kotlin' "$STACKS" 2>/dev/null; then
  for pat in '(^|/)src/main/.+Application\.(java|kt)$' '(^|/)src/main/.+Main\.(java|kt)$' '(^|/)pom\.xml$' '(^|/)build\.gradle(\.kts)?$'; do
    f="$(pick_first "$pat")"
    [ -n "$f" ] && add_unique "$ENTRY" "$f"
  done
fi

if grep -qxF '.NET' "$STACKS" 2>/dev/null; then
  for pat in '(^|/)Program\.cs$' '(^|/)Startup\.cs$' '(^|/).*\.csproj$'; do
    f="$(pick_first "$pat")"
    [ -n "$f" ] && add_unique "$ENTRY" "$f"
  done
fi

if grep -qxF 'Ruby' "$STACKS" 2>/dev/null; then
  for pat in '(^|/)config/routes\.rb$' '(^|/)config/application\.rb$' '(^|/)Gemfile$' '(^|/)Rakefile$'; do
    f="$(pick_first "$pat")"
    [ -n "$f" ] && add_unique "$ENTRY" "$f"
  done
fi

if grep -qxF 'PHP' "$STACKS" 2>/dev/null; then
  for pat in '(^|/)public/index\.php$' '(^|/)artisan$' '(^|/)composer\.json$'; do
    f="$(pick_first "$pat")"
    [ -n "$f" ] && add_unique "$ENTRY" "$f"
  done
fi

# ---------------------------------------------------------------------------
# Secondary entrypoints / demo surfaces: common runnable-but-not-primary
# patterns across stacks (demos, scripts, notebooks, eval harnesses).
# ---------------------------------------------------------------------------
is_package_marker() {
  case "$1" in
    */__init__.py|*/index.py|*/index.ts|*/index.tsx|*/index.js|*/index.jsx)
      return 0
      ;;
  esac
  return 1
}

for pat in \
  '(^|/)app\.py$' \
  '(^|/)demo\.py$' \
  '(^|/)demo/.+\.py$' \
  '(^|/)examples?/.+\.py$' \
  '(^|/)streamlit_app\.py$' \
  '(^|/)gradio_app\.py$' \
  '(^|/)scripts?/run.*\.(py|sh)$' \
  '(^|/)eval/.+\.py$' \
  '(^|/)notebooks?/.+\.ipynb$'
do
  f="$(pick_first "$pat")"
  if [ -n "$f" ]; then
    is_package_marker "$f" && continue
    already_entry=no
    grep -qxF "$f" "$ENTRY" 2>/dev/null && already_entry=yes
    [ "$already_entry" = no ] && add_unique "$SECONDARY" "$f"
  fi
done

# ---------------------------------------------------------------------------
# Integration points: generic wiring/config files, useful across stacks.
# ---------------------------------------------------------------------------
for pat in \
  '(^|/)docker-compose\.ya?ml$' \
  '(^|/)Dockerfile$' \
  '(^|/)vite\.config\.(ts|js)$' \
  '(^|/)next\.config\.(js|mjs|ts)$' \
  '(^|/)nginx\.conf$' \
  '(^|/)config/routes\.rb$' \
  '(^|/)urls\.py$' \
  '(^|/)router\.(py|ts|js|go)$' \
  '(^|/)api/.*/router\.(py|ts|js)$' \
  '(^|/)openapi\.(ya?ml|json)$' \
  '(^|/)schema\.prisma$' \
  '(^|/)alembic\.ini$' \
  '(^|/)migrations?/'
do
  f="$(pick_first "$pat")"
  [ -n "$f" ] && add_unique "$INTEGRATIONS" "$f"
done

# ---------------------------------------------------------------------------
# Tests: real test-file conventions per language, not tied to one folder
# layout. Co-located tests (e.g. Component.test.tsx next to Component.tsx)
# are matched anywhere, not just inside a tests/ style directory.
# ---------------------------------------------------------------------------
TEST_RE='(^|/)test_[^/]+\.py$|(^|/).+_test\.py$|(^|/).+_test\.go$|(^|/).+\.(spec|test)\.(ts|tsx|js|jsx)$|(^|/).+Spec\.(java|kt)$|(^|/).+Test\.(java|kt)$|(^|/).+_spec\.rb$|(^|/).+Test\.php$'
pick_all "$TEST_RE" | head -n 20 > "$TESTS" || true

# ---------------------------------------------------------------------------
# Core module ranking: evidence-based centrality, excluding boilerplate
# (barrel files, package inits, manifests) unless genuinely central.
# Prefer Python if a working interpreter is available; otherwise fall back
# to a pure awk-based scorer so this section never blocks map generation.
# ---------------------------------------------------------------------------
PYBIN=""
for cand in "python3" "python" "py -3"; do
  bin="${cand%% *}"
  if command -v "$bin" >/dev/null 2>&1; then
    if $cand -c "print(1)" >/dev/null 2>&1; then
      PYBIN="$cand"
      break
    fi
  fi
done

CORE_METHOD=none
if [ -n "$PYBIN" ]; then
  CORE_METHOD=python
  $PYBIN - "$FILES" "$CORE" "$TOP_CORE" <<'PY'
import os, re, sys
from collections import defaultdict, Counter

files_path, out_path, top_n = sys.argv[1], sys.argv[2], int(sys.argv[3])
with open(files_path, "r", encoding="utf-8", errors="ignore") as f:
    files = [line.strip() for line in f if line.strip()]

code_exts = {".py",".ts",".tsx",".js",".jsx",".go",".rs",".java",".kt",".rb",".php",".cs"}
boilerplate_basenames = {"__init__.py","index.ts","index.js","index.tsx","index.jsx"}
manifest_basenames = {
    "package.json","pyproject.toml","requirements.txt","go.mod","Cargo.toml",
    "pom.xml","build.gradle","build.gradle.kts","composer.json","Gemfile"
}
code_files = [p for p in files if os.path.splitext(p)[1].lower() in code_exts]

stem_to_paths = defaultdict(list)
for p in code_files:
    base = os.path.basename(p)
    if base.startswith(".") or base in boilerplate_basenames or base in manifest_basenames:
        continue
    stem_to_paths[os.path.splitext(base)[0]].append(p)

# Only lines that look like real import/require statements are evidence.
# This deliberately excludes comments, docstrings, and prose mentions.
IMPORT_LINE_RE = re.compile(
    r"^\s*(from\s+[\w\.]+\s+import\b"
    r"|import\s+[\w\.]"
    r"|import\b.*from\s+[\'\"]"
    r"|require\(\s*[\'\"]"
    r"|import\s+[\'\"]"
    r"|use\s+[\w\\\\]"
    r"|using\s+[\w\.]+\s*;"
    r")"
)
TOKEN_RE = re.compile(r"[\'\"]?([\w\.\-/\\\\]+)[\'\"]?")

fan_in = defaultdict(set)
for p in code_files:
    try:
        text = open(p, "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        continue
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "//", "*", "/*")):
            continue
        if not IMPORT_LINE_RE.search(s):
            continue
        for tok in TOKEN_RE.findall(s):
            tok = tok.strip("./\\\\")
            if not tok:
                continue
            for seg in re.split(r"[./\\\\]", tok):
                if seg and seg in stem_to_paths:
                    for target in stem_to_paths[seg]:
                        if target != p:
                            fan_in[target].add(p)

used_fallback = False
if fan_in:
    ranked = sorted(fan_in.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    rows = [(path, len(importers)) for path, importers in ranked if len(importers) >= 1]
else:
    # No import-like evidence detected anywhere (unusual repo/style). Fall
    # back to whole-file substring matching, clearly marked as low confidence.
    used_fallback = True
    interesting = [(p, os.path.basename(p), os.path.splitext(os.path.basename(p))[0])
                   for p in code_files
                   if os.path.basename(p) not in boilerplate_basenames
                   and os.path.basename(p) not in manifest_basenames
                   and not os.path.basename(p).startswith(".")]
    score = Counter()
    for p in code_files:
        try:
            text = open(p, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for target, base, stem in interesting:
            if target == p:
                continue
            hits = text.count(base) if base in text else 0
            if hits:
                score[target] += min(hits, 8)
    rows = [(path, sc) for path, sc in
            sorted(score.items(), key=lambda kv: (-kv[1], kv[0])) if sc > 1]

with open(out_path, "w", encoding="utf-8") as out:
    if used_fallback:
        out.write("__FALLBACK_SUBSTRING__\tmarker\n")
    n = 0
    for path, sc in rows:
        out.write(f"{path}\t{sc}\n")
        n += 1
        if n >= top_n:
            break
PY
else
  # Pure bash/awk fallback: score by fan-in (distinct importing files),
  # restricted to import/require-like lines only, not whole-file text.
  # This avoids inflating scores from comments/docs and avoids any flat
  # depth-based baseline that isn't backed by real evidence.
  # Pure bash/awk fallback: score by basename-in-other-files occurrence count.
  # Coarser than the Python pass but keeps the script fully portable.
  CORE_METHOD=awk
  CODE_FILES="$(mktemp)"
  grep -E '\.(py|ts|tsx|js|jsx|go|rs|java|kt|rb|php|cs)$' "$FILES" 2>/dev/null \
    | grep -vE '(^|/)__init__\.py$|(^|/)index\.(ts|js|tsx|jsx)$|(^|/)(package\.json|pyproject\.toml|requirements\.txt|go\.mod|Cargo\.toml|pom\.xml|build\.gradle(\.kts)?|composer\.json|Gemfile)$' > "$CODE_FILES" || true
  IMPORT_LINE_RE='^[[:space:]]*(from[[:space:]]+[A-Za-z0-9_.]+[[:space:]]+import|import[[:space:]]+[A-Za-z0-9_.]|import[[:space:]].*from[[:space:]]+["'"'"']|require\(|import[[:space:]]+["'"'"']|use[[:space:]]+[A-Za-z0-9_\\]|using[[:space:]]+[A-Za-z0-9_.]+[[:space:]]*;)'
  CORE_RAW="$(mktemp)"
  ANY_IMPORT_EVIDENCE=no
  while IFS= read -r target; do
    [ -n "$target" ] || continue
    base="$(basename "$target")"
    stem="${base%.*}"
    fanin=0
    while IFS= read -r src; do
      [ -n "$src" ] || continue
      [ "$src" = "$target" ] && continue
      [ -f "$src" ] || continue
      if grep -E "$IMPORT_LINE_RE" "$src" 2>/dev/null | grep -qF "$stem"; then
        fanin=$((fanin + 1))
        ANY_IMPORT_EVIDENCE=yes
      fi
    done < "$CODE_FILES"
    [ "$fanin" -ge 1 ] && printf '%s\t%s\n' "$target" "$fanin" >> "$CORE_RAW"
  done < "$CODE_FILES"

  if [ "$ANY_IMPORT_EVIDENCE" = yes ]; then
    sort -t "$(printf '\t')" -k2,2nr "$CORE_RAW" 2>/dev/null | head -n "$TOP_CORE" > "$CORE" || true
  else
    # No import-like evidence anywhere; fall back to whole-file substring
    # matching as a last resort, clearly marked as low confidence.
    printf '__FALLBACK_SUBSTRING__\tmarker\n' > "$CORE"
    CORE_RAW2="$(mktemp)"
    while IFS= read -r target; do
      [ -n "$target" ] || continue
      base="$(basename "$target")"
      hits=0
      while IFS= read -r src; do
        [ -n "$src" ] || continue
        [ "$src" = "$target" ] && continue
        [ -f "$src" ] || continue
        c="$(grep -c -F "$base" "$src" 2>/dev/null || true)"
        [ -n "$c" ] || c=0
        hits=$((hits + c))
      done < "$CODE_FILES"
      [ "$hits" -gt 1 ] && printf '%s\t%s\n' "$target" "$hits" >> "$CORE_RAW2"
    done < "$CODE_FILES"
    sort -t "$(printf '\t')" -k2,2nr "$CORE_RAW2" 2>/dev/null | head -n "$TOP_CORE" >> "$CORE" || true
    rm -f "$CORE_RAW2"
  fi
  rm -f "$CODE_FILES" "$CORE_RAW"

fi

# ---------------------------------------------------------------------------
# Optional override: .repomap.json lets a repo maintainer add repo-specific
# hints on top of generic detection, without editing this script. Supported
# keys (all optional):
#   { "entry_points": ["path/to/file"],
#     "secondary_entry_points": ["path/to/file"],
#     "core_modules": ["path/to/file"],
#     "integration_points": ["path/to/file"],
#     "notes": ["free text note appended to Confidence notes"] }
# Paths are added on top of generic findings, not used to replace them.
# ---------------------------------------------------------------------------
OVERRIDE_APPLIED=no
if [ -f "$CONFIG" ] && [ -n "$PYBIN" ]; then
  if $PYBIN - "$CONFIG" "$ENTRY" "$SECONDARY" "$CORE" "$INTEGRATIONS" "$OVERRIDE_NOTES" <<'PY' 2>/dev/null
import json, sys
cfg_path, entry_path, secondary_path, core_path, integ_path, notes_path = sys.argv[1:7]
try:
    with open(cfg_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
except Exception:
    sys.exit(1)

def append_unique(path, values):
    if not values:
        return
    existing = set()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            existing = {line.rstrip('\n') for line in f}
    except FileNotFoundError:
        pass
    with open(path, 'a', encoding='utf-8') as f:
        for v in values:
            if v and v not in existing:
                f.write(v + '\n')
                existing.add(v)

append_unique(entry_path, cfg.get('entry_points', []))
append_unique(secondary_path, cfg.get('secondary_entry_points', []))
append_unique(integ_path, cfg.get('integration_points', []))

core_overrides = cfg.get('core_modules', [])
if core_overrides:
    with open(core_path, 'a', encoding='utf-8') as f:
        for v in core_overrides:
            if v:
                f.write(f"{v}\toverride\n")

notes = cfg.get('notes', [])
if notes:
    with open(notes_path, 'a', encoding='utf-8') as f:
        for n in notes:
            if n:
                f.write(n + '\n')
sys.exit(0)
PY
  then
    OVERRIDE_APPLIED=yes
  fi
fi

CORE_SKIPPED=no
[ "$CORE_METHOD" = none ] && CORE_SKIPPED=yes

# ---------------------------------------------------------------------------
# Ignored/generated areas summary.
# ---------------------------------------------------------------------------
for d in "${EXCLUDE_DIRS[@]}"; do
  add_unique "$IGNORED" "$d/"
done
[ -f .repomapignore ] && add_unique "$IGNORED" '.repomapignore (custom excludes)'
[ -f "$CONFIG" ] && add_unique "$IGNORED" '.repomap.json (optional overrides applied on top of generic detection)'

README_FILE="$(pick_first '(^|/)README(\.md)?$')"
TOTAL_STACKS="$(wc -l < "$STACKS" | tr -d ' ')"
TOTAL_ENTRY="$(wc -l < "$ENTRY" | tr -d ' ')"
TOTAL_SECONDARY="$(wc -l < "$SECONDARY" | tr -d ' ')"
TOTAL_TESTS="$(wc -l < "$TESTS" | tr -d ' ')"
TOTAL_CORE="$(wc -l < "$CORE" | tr -d ' ')"
TOTAL_INT="$(wc -l < "$INTEGRATIONS" | tr -d ' ')"
NOW="$(date +%Y-%m-%d)"

{
  echo '# Repo brief'
  echo
  echo "Generated $NOW by $(basename "$0")."
  echo "Root: $ROOT"
  echo "Enumeration: $ENUM_MODE"
  echo "Candidate files: $TOTAL_FILES"
  echo
  echo '## Overview'
  echo
  if [ -n "$README_FILE" ]; then
    echo "- README anchor: $README_FILE"
  fi
  if [ "$TOTAL_STACKS" -gt 0 ]; then
    echo '- Detected stack profile:'
    sed 's/^/  - /' "$STACKS"
  else
    echo '- Stack confidence: low; no strong manifest/config signals detected.'
  fi
  echo
  if [ "$TOTAL_ENTRY" -gt 0 ]; then
    echo '## Entry points'
    echo
    sed 's/^/- /' "$ENTRY"
    echo
  else
    echo '## Entry points'
    echo
    echo '- No evidence-backed entrypoints detected from current stack rules.'
    echo
  fi
  if [ "$TOTAL_SECONDARY" -gt 0 ]; then
    echo '## Secondary entrypoints / demo surfaces'
    echo
    sed 's/^/- /' "$SECONDARY"
    echo
  fi
  USED_SUBSTRING_FALLBACK=no
  if head -n 1 "$CORE" 2>/dev/null | grep -q '^__FALLBACK_SUBSTRING__'; then
    USED_SUBSTRING_FALLBACK=yes
    tail -n +2 "$CORE" > "$CORE.stripped" 2>/dev/null || true
    mv "$CORE.stripped" "$CORE" 2>/dev/null || true
    TOTAL_CORE="$(wc -l < "$CORE" | tr -d ' ')"
  fi
  if [ "$TOTAL_CORE" -gt 0 ]; then
    if [ "$USED_SUBSTRING_FALLBACK" = yes ]; then
      echo '## Core modules (ranked, low-confidence substring scan)'
    elif [ "$CORE_METHOD" = python ]; then
      echo '## Core modules (ranked, import fan-in scan)'
    else
      echo '## Core modules (ranked, awk import fan-in scan)'
    fi
    echo
    awk -F'\t' '{ if ($2 == "override") printf "- %s (override)\n", $1; else printf "- %s (score %s)\n", $1, $2 }' "$CORE"
    echo
  fi
  if [ "$TOTAL_TESTS" -gt 0 ]; then
    echo '## Tests'
    echo
    sed 's/^/- /' "$TESTS"
    echo
  else
    echo '## Tests'
    echo
    echo '- No meaningful test files detected from common stack-specific patterns.'
    echo
  fi
  if [ "$TOTAL_INT" -gt 0 ]; then
    echo '## Integration points'
    echo
    sed 's/^/- /' "$INTEGRATIONS"
    echo
  fi
  echo '## Ignored paths'
  echo
  sed 's/^/- /' "$IGNORED"
  echo
  echo '## Confidence notes'
  echo
  if [ "$TOTAL_STACKS" -eq 0 ]; then
    echo '- Stack detection confidence is low; review top-level manifests manually.'
  fi
  if [ "$TOTAL_ENTRY" -eq 0 ]; then
    echo '- Entrypoint detection confidence is low; no standard commands or main files matched current stack rules.'
  fi
  if [ "$TOTAL_SECONDARY" -gt 0 ]; then
    echo '- Secondary entrypoints/demo surfaces were detected; treat these as alternate ways to exercise the system, not the primary control path.'
  fi
  if [ "$USED_SUBSTRING_FALLBACK" = yes ]; then
    echo '- Core module ranking fell back to whole-file substring matching because no import/require-style lines were detected anywhere in the repo. This mode can overrate files whose names appear often in comments, docs, or strings; treat these rankings as low confidence and verify manually.'
  elif [ "$CORE_METHOD" = awk ]; then
    echo '- Core module ranking used the awk import fan-in scanner (no working Python interpreter found: tried python3, python, py -3). It counts distinct files that import/require each target, which is coarser than the Python pass but still evidence-based rather than a raw text-match count.'
  elif [ "$TOTAL_CORE" -eq 0 ]; then
    echo '- Core module ranking confidence is low; not enough import/reference signals were detected.'
  fi
  if [ "$OVERRIDE_APPLIED" = yes ]; then
    echo '- Repo-specific overrides from .repomap.json were layered on top of generic detection.'
  fi
  if [ "$TOTAL_STACKS" -gt 0 ] && [ "$TOTAL_ENTRY" -gt 0 ]; then
    echo '- This brief is evidence-backed from manifests/configs, common entrypoint rules, and lightweight reference centrality.'
  fi
  if [ -s "$OVERRIDE_NOTES" ]; then
    sed 's/^/- /' "$OVERRIDE_NOTES"
  fi
  echo '- Detection still relies on common naming conventions; highly nonstandard repo layouts may need manual review to confirm entrypoints and core modules.'
} > "$OUT"

echo "Wrote $OUT"
echo "  $TOTAL_FILES candidate files indexed"
echo "  script: $(basename "$0")"
