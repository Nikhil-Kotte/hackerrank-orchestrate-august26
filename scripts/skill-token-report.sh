#!/usr/bin/env bash
# Report the always-on context cost of every discoverable skill.
# Every skill's name + description is sent on EVERY request unless it is gated.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTEXT_TOKENS=200000

# Per-skill description cap actually in force (Claude Code default is 1536).
CAP=1536
settings="$ROOT/.claude/settings.json"
if [ -f "$settings" ]; then
  found="$(grep -oE '"skillListingMaxDescChars"[[:space:]]*:[[:space:]]*[0-9]+' "$settings" | grep -oE '[0-9]+$' || true)"
  [ -n "$found" ] && CAP="$found"
fi

fm_value() {
  awk 'NR==1 && $0 ~ /^---[[:space:]]*$/ { inside=1; next }
       inside && $0 ~ /^---[[:space:]]*$/ { exit }
       inside { print }' "$1" | sed -n "s/^$2:[[:space:]]*//p" | head -1
}

scan() { # $1 = directory to search for */SKILL.md
  [ -d "$1" ] || return 0
  find "$1" -name SKILL.md -type f 2>/dev/null
}

rows=""
total_chars=0
gated_chars=0

while read -r md; do
  [ -n "$md" ] || continue
  name="$(fm_value "$md" name)"
  [ -n "$name" ] || name="$(basename "$(dirname "$md")")"
  desc="$(fm_value "$md" description)"

  # Truncation the harness would apply.
  eff_desc_chars=${#desc}
  [ "$eff_desc_chars" -gt "$CAP" ] && eff_desc_chars="$CAP"
  chars=$((${#name} + eff_desc_chars))

  gate="-"
  [ "$(fm_value "$md" disable-model-invocation)" = "true" ] && gate="gated"
  yaml="$(dirname "$md")/agents/openai.yaml"
  [ -f "$yaml" ] && grep -qE 'allow_implicit_invocation:[[:space:]]*false' "$yaml" && gate="gated"

  flag=""
  [ "${#desc}" -gt "$CAP" ] && flag=" (truncated from ${#desc})"

  total_chars=$((total_chars + chars))
  [ "$gate" = "gated" ] && gated_chars=$((gated_chars + chars))

  rows+="$(printf '%7d %6d  %-6s %s%s' "$((chars / 4))" "$chars" "$gate" "$name" "$flag")"$'\n'
done < <(scan "$ROOT/.agents/skills"; scan "$HOME/.claude/skills"; scan "$HOME/.claude/plugins/cache")

printf 'Skill listing cost - sent on every request (cap: %s chars/skill)\n\n' "$CAP"
printf ' TOKENS  CHARS  GATE   SKILL\n'
printf '%s' "$rows" | sort -rn

ungated_chars=$((total_chars - gated_chars))
printf '\n----------------------------------------\n'
printf 'Total          %6d chars  ~%5d tokens\n' "$total_chars" "$((total_chars / 4))"
printf 'Gated (free)   %6d chars  ~%5d tokens\n' "$gated_chars" "$((gated_chars / 4))"
printf 'Ungated cost   %6d chars  ~%5d tokens  (%s%% of a %sk window)\n' \
  "$ungated_chars" "$((ungated_chars / 4))" \
  "$(awk -v t="$((ungated_chars / 4))" -v c="$CONTEXT_TOKENS" 'BEGIN{printf "%.3f", t*100/c}')" \
  "$((CONTEXT_TOKENS / 1000))"

printf '\nGated skills cost nothing in Claude Code and codex; they stay invocable as /name.\n'
printf 'Antigravity honors no gate - there, every row above is always loaded.\n'
