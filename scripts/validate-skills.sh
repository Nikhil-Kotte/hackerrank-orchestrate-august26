#!/usr/bin/env bash
# Validate skills against the cross-harness contract in .agents/README.md.
# Runs under Git Bash on Windows; no YAML dependency.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="$ROOT/.agents/skills"

# Cross-harness safe keys (codex rejects anything outside this set) plus the
# Claude-Code-only exceptions we knowingly ship. See .agents/README.md.
SAFE_KEYS=" name description license allowed-tools metadata "
CLAUDE_ONLY_KEYS=" disable-model-invocation user-invocable "
ALLOWED_SUBDIRS=" scripts references assets agents "

MAX_DESC_CHARS=350
SHORT_DESC_MIN=25
SHORT_DESC_MAX=64
BODY_WARN_WORDS=2000
BODY_FAIL_WORDS=3000

errors=0
warnings=0

fail() { printf '  [FAIL] %s\n' "$1"; errors=$((errors + 1)); }
warn() { printf '  [WARN] %s\n' "$1"; warnings=$((warnings + 1)); }
pass() { printf '  [ok]   %s\n' "$1"; }

# Print the YAML frontmatter block of $1 (between the first two --- lines).
frontmatter() {
  awk 'NR==1 && $0 ~ /^---[[:space:]]*$/ { inside=1; next }
       inside && $0 ~ /^---[[:space:]]*$/ { exit }
       inside { print }' "$1"
}

# Print the body (everything after the closing --- line).
body() {
  awk 'NR==1 && $0 ~ /^---[[:space:]]*$/ { inside=1; next }
       inside && $0 ~ /^---[[:space:]]*$/ { inside=0; started=1; next }
       started { print }' "$1"
}

# Print the value of top-level key $2 from frontmatter of file $1.
fm_value() {
  frontmatter "$1" | sed -n "s/^$2:[[:space:]]*//p" | head -1
}

[ -d "$SKILLS_DIR" ] || { echo "No skills directory at $SKILLS_DIR"; exit 1; }

for skill_dir in "$SKILLS_DIR"/*/; do
  [ -d "$skill_dir" ] || continue
  skill="$(basename "$skill_dir")"
  md="$skill_dir/SKILL.md"

  printf '\n%s\n' "$skill"

  if [ ! -f "$md" ]; then
    fail "no SKILL.md"
    continue
  fi

  # 1. Required fields, name shape, name/directory agreement.
  name="$(fm_value "$md" name)"
  desc="$(fm_value "$md" description)"

  [ -n "$name" ] || fail "frontmatter missing 'name'"
  [ -n "$desc" ] || fail "frontmatter missing 'description'"

  if [ -n "$name" ]; then
    if ! printf '%s' "$name" | grep -qE '^[a-z0-9]+(-[a-z0-9]+)*$'; then
      fail "name '$name' is not hyphen-case"
    fi
    [ "${#name}" -le 64 ] || fail "name is ${#name} chars (max 64)"
    [ "$name" = "$skill" ] || fail "name '$name' does not match directory '$skill'"
  fi

  # 2. Frontmatter key allowlist.
  while read -r key; do
    [ -n "$key" ] || continue
    if [[ "$SAFE_KEYS" == *" $key "* ]]; then
      continue
    elif [[ "$CLAUDE_ONLY_KEYS" == *" $key "* ]]; then
      continue
    else
      fail "frontmatter key '$key' is outside the cross-harness allowlist (codex rejects it)"
    fi
  done < <(frontmatter "$md" | sed -n 's/^\([a-zA-Z][a-zA-Z0-9_-]*\):.*/\1/p')

  # 3. Gate parity between the two harnesses.
  yaml="$skill_dir/agents/openai.yaml"
  cc_gated=no
  codex_gated=no
  [ "$(fm_value "$md" disable-model-invocation)" = "true" ] && cc_gated=yes
  if [ -f "$yaml" ] && grep -qE '^[[:space:]]*allow_implicit_invocation:[[:space:]]*false' "$yaml"; then
    codex_gated=yes
  fi
  if [ "$cc_gated" != "$codex_gated" ]; then
    fail "gate parity broken: Claude Code gated=$cc_gated, codex gated=$codex_gated (set both or neither)"
  elif [ "$cc_gated" = yes ]; then
    pass "gated in both harnesses"
  fi

  # 4. Description budget, and short_description hard limits.
  if [ -n "$desc" ] && [ "${#desc}" -gt "$MAX_DESC_CHARS" ]; then
    fail "description is ${#desc} chars (budget $MAX_DESC_CHARS)"
  fi
  if [ -f "$yaml" ]; then
    sd="$(sed -n 's/^[[:space:]]*short_description:[[:space:]]*//p' "$yaml" | head -1 | sed 's/^"//; s/"$//')"
    if [ -z "$sd" ]; then
      warn "openai.yaml has no short_description"
    elif [ "${#sd}" -lt "$SHORT_DESC_MIN" ] || [ "${#sd}" -gt "$SHORT_DESC_MAX" ]; then
      fail "short_description is ${#sd} chars (codex requires $SHORT_DESC_MIN-$SHORT_DESC_MAX)"
    fi
  else
    warn "no agents/openai.yaml (skill will not gate or display in codex/Antigravity)"
  fi

  # 5. Directory layout.
  for sub in "$skill_dir"*/; do
    [ -d "$sub" ] || continue
    subname="$(basename "$sub")"
    [[ "$ALLOWED_SUBDIRS" == *" $subname "* ]] || \
      fail "subdirectory '$subname/' is outside {scripts, references, assets, agents}"
  done
  for loose in "$skill_dir"*.md; do
    [ -f "$loose" ] || continue
    [ "$(basename "$loose")" = "SKILL.md" ] || \
      fail "loose markdown '$(basename "$loose")' at skill root - move it into references/"
  done

  # 6. Body word budget.
  words="$(body "$md" | wc -w | tr -d ' ')"
  if [ "$words" -gt "$BODY_FAIL_WORDS" ]; then
    fail "body is $words words (max $BODY_FAIL_WORDS)"
  elif [ "$words" -gt "$BODY_WARN_WORDS" ]; then
    warn "body is $words words (target under $BODY_WARN_WORDS)"
  else
    pass "body is $words words"
  fi

  # 7. Relative links resolve.
  while read -r link; do
    [ -n "$link" ] || continue
    case "$link" in http*|\#*|mailto:*) continue ;; esac
    target="${link%%#*}"
    [ -n "$target" ] || continue
    [ -e "$skill_dir/$target" ] || fail "broken link: $target"
  done < <(grep -oE '\]\([^)]+\)' "$md" | sed 's/^](//; s/)$//')

  # 8. Typographic punctuation banned by AGENTS.md. Matches the raw UTF-8 bytes
  # for the General Punctuation block (dashes, curly quotes, ellipsis) and the
  # middle dot, so accented letters and CJK still pass.
  for doc in "$md" "$skill_dir"references/*.md; do
    [ -f "$doc" ] || continue
    if LC_ALL=C grep -qE $'\xe2\x80[\x90-\xbf]|\xc2\xb7' "$doc"; then
      fail "$(basename "$doc") uses em dashes, curly quotes, or other decorative punctuation (see AGENTS.md)"
    fi
  done

  # 9. Every reference file is reachable from SKILL.md.
  if [ -d "$skill_dir/references" ]; then
    for ref in "$skill_dir"references/*; do
      [ -f "$ref" ] || continue
      refname="$(basename "$ref")"
      grep -q "references/$refname" "$md" || \
        fail "references/$refname is never linked from SKILL.md - it can never load"
    done
  fi
done

printf '\n----------------------------------------\n'
if [ "$errors" -gt 0 ]; then
  printf '%d error(s), %d warning(s)\n' "$errors" "$warnings"
  exit 1
fi
printf 'All skills valid (%d warning(s))\n' "$warnings"
