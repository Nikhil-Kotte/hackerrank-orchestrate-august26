Shared rules are in AGENTS.md, loaded alongside this file. Read it if it is not
already in context.

## Antigravity specifics

- Skill gating is not honored here. Every skill under `.agents/skills/` contributes its description to every request whatever its gate says, so keep descriptions short.
- Skills live in `.agents/skills/`, registered by `.agents/skills.json`. Reference material sits in each skill's `references/` and loads only when read.
- Invoke a skill explicitly rather than relying on auto-activation.
