#!/usr/bin/env bash
# Wire .claude/skills -> .agents/skills so both harnesses see one source of truth.
#
# Why this exists: Git on Windows does not restore symlinks unless core.symlinks
# is true, so a fresh clone lands .claude/skills/<name> as a one-line TEXT FILE
# containing a path. Claude Code then sees no skills at all. This repairs that.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/.agents/skills"
DEST="$ROOT/.claude/skills"

[ -d "$SRC" ] || { echo "error: no .agents/skills at $SRC"; exit 1; }
mkdir -p "$DEST"

# Readable through the path - true for a symlink, a junction, or a plain copy.
works() { [ -r "$1/SKILL.md" ]; }

# Actually a link, not a copy. MSYS silently falls back to copying a directory
# when `ln -s` cannot make a native symlink, and a copy does not receive later
# edits to .agents/. Probe by write-through; nothing else distinguishes the two,
# since a junction reports as a plain directory.
reflects() {
  local skill="$1" marker=".link-probe-$$" rc=1
  touch "$SRC/$skill/$marker" 2>/dev/null || return 1
  [ -e "$DEST/$skill/$marker" ] && rc=0
  rm -f "$SRC/$skill/$marker"
  return $rc
}

link_via_ln() {
  ln -s "../../.agents/skills/$1" "$DEST/$1" 2>/dev/null
}

link_via_junction() {
  command -v cygpath >/dev/null 2>&1 || return 1
  local w_link w_target
  w_link="$(cygpath -w "$DEST/$1")"
  w_target="$(cygpath -w "$SRC/$1")"
  MSYS_NO_PATHCONV=1 cmd /c mklink /J "$w_link" "$w_target" >/dev/null 2>&1
}

created=0; repaired=0; copied=0; ok=0

for skill_path in "$SRC"/*/; do
  [ -d "$skill_path" ] || continue
  skill="$(basename "$skill_path")"
  target="$DEST/$skill"

  if works "$target" && reflects "$skill"; then
    ok=$((ok + 1))
    continue
  fi

  # Clear a broken entry: a symlink, a stray file, or a stale copy. A copy is
  # safe to rm -rf because it has no link semantics. Never rm -rf a junction -
  # on some systems that follows through and deletes the target's contents -
  # which is why the junction attempt comes last and is never cleaned up here.
  if [ -L "$target" ] || [ -f "$target" ]; then
    rm -f "$target"
    repaired=$((repaired + 1))
  elif [ -d "$target" ]; then
    if works "$target"; then
      rm -rf "$target"          # stale copy
      repaired=$((repaired + 1))
    else
      echo "  skip $skill: directory exists but has no SKILL.md - resolve by hand"
      continue
    fi
  else
    created=$((created + 1))
  fi

  if link_via_ln "$skill" && works "$target" && reflects "$skill"; then
    echo "  link $skill (symlink)"
  else
    # ln -s either failed or silently made a copy; clear it and try a junction.
    if [ -L "$target" ] || [ -f "$target" ]; then rm -f "$target"; elif [ -d "$target" ]; then rm -rf "$target"; fi
    if link_via_junction "$skill" && works "$target" && reflects "$skill"; then
      echo "  link $skill (junction)"
    else
      [ -e "$target" ] || cp -r "$SRC/$skill" "$target"
      copied=$((copied + 1))
      echo "  COPY $skill - no link support; edit .agents/ and re-run this script"
    fi
  fi
done

echo
echo "up-to-date: $ok  created: $created  repaired: $repaired  copied: $copied"

if [ "$copied" -gt 0 ]; then
  cat <<'EOF'

Copies were made because this system cannot create links. .agents/ remains the
source of truth - re-run scripts/link-skills.sh after editing a skill. To enable
real symlinks: git config --global core.symlinks true, then re-clone.
EOF
fi

echo
bash "$ROOT/scripts/validate-skills.sh" || exit 1
echo
bash "$ROOT/scripts/skill-token-report.sh"
