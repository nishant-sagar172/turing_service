# AGENTS.md — Mandatory Instructions for All AI Agents

## Rule

**Before making ANY change to this repository, you MUST read and follow every rule in [CLAUDE.md](CLAUDE.md).**

If you have not read CLAUDE.md, do not proceed. If you cannot comply with the rules in CLAUDE.md, do not make changes.

---

## Checklist Before Every Code Change

1. Read `CLAUDE.md` in full.
2. Clarify the task with the user. Do not assume intent.
3. Confirm scope — what files will be changed and why.
4. If anything existing will be removed or replaced, ask the user first.
5. Make the change.
6. Run `ruff format app/` and `ruff check app/` for any Python changes.
7. Verify the change does not break existing functionality.

---

## Non-Negotiable

- Additive changes only. Do not delete or restructure without explicit approval.
- No assumptions. Ask if unclear.
- No over-engineering. Solve exactly what was asked.
- Follow SOLID principles.
- Pass all linting and formatting checks before considering the work done.

---

## Enforcement

These rules apply to all AI agents: Claude, GitHub Copilot, Cursor, Windsurf, Codex, or any other tool used to contribute to this repository. Human contributors should also follow CLAUDE.md as a style and contribution guide.
