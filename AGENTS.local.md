# Working agreement

Loads on every request. Kept short on purpose.

## Context

- Read REPO-MAP.md before exploring the tree, if it exists.
- Search before reading. Grep for the lines, then read only around them.
- Read large files with an offset and limit. Never read a file whole to answer a narrow question.
- Batch independent tool calls into one message; they run in parallel.
- Do not re-read a file you just wrote or edited. The edit already confirmed it.
- Do not spawn subagents unless asked. A subagent starts cold and re-derives context that already exists here.

## Output

- Return code first. Explanation after, only if non-obvious.
- No inline prose. Comments only where the logic is unclear.
- No boilerplate unless explicitly requested.

## Code

- Simplest working solution. No over-engineering.
- No abstractions for single-use operations.
- No speculative features or "you might also want".
- Read the file before modifying it. Never edit blind.
- No docstrings or type annotations on code not being changed.
- No error handling for scenarios that cannot happen.
- Three similar lines beat a premature abstraction.

## Review

- State the bug. Show the fix. Stop.
- Nothing beyond the scope of the review.
- No compliments on the code before or after.

## Debugging

- Never speculate about a bug without reading the relevant code first.
- State what you found, where, and the fix. One pass.
- If the cause is unclear, say so. Do not guess.

## Formatting

- No em dashes, smart quotes, or decorative Unicode symbols.
- Plain hyphens and straight quotes only.
- Natural language characters (accented letters, CJK) are fine when the content requires them.
- Code output must be copy-paste safe.
