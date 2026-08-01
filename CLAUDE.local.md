@AGENTS.local.md

## Claude Code specifics

- Skills are gated to explicit invocation: `/tdd`, `/grill-me`, `/git-guardrails-claude-code`. They will not fire on their own.
- Settings live in `.claude/settings.json`. `.claude/skills/*` are links to `.agents/skills/*`; edit the latter.
- Run `bash scripts/validate-skills.sh` after changing any skill.