---
name: git-skills
description: Use for any git work in this repo — status, diff, staging, commits, branches, push, undo. Enforces safe git practices and keeps git output token-cheap. Load before running git.
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git show:*), Bash(git branch:*), Bash(git stash list:*)
---

## Current repo state
!`git status --short --branch`

## Token-efficient git (defaults)
- Survey with `git status --short --branch`, not bare `git status`.
- See scope with `git diff --stat HEAD` before any full diff.
- Pull a full diff only per file, on demand: `git diff HEAD -- <path>`. Never dump the whole diff.
- Use `git log --oneline -n <small N>`, not full `git log`. Use `git show --stat <ref>` first.
- Read-only git is pre-approved here — batch several reads in one call, but never re-run a query whose output you already have.
- `git diff HEAD` omits untracked files (`??` in status) — read those files directly instead.

## Safety — hard rules
- Commit or push ONLY when the user explicitly asks. 
- If HEAD is on the default branch (`main`/`master`), create a feature branch BEFORE committing.
- Before committing, inspect the staged diff; refuse to commit secrets, `.env`, keys, tokens, or credentials.
- NEVER run these without an explicit, specific request this session:
  `push --force`/`--force-with-lease`, `reset --hard`, `clean -f`, `checkout`/`restore` that
  discards changes, `branch -D`, `rebase`, `stash drop`/`clear`, or `git rm` of files you didn't
  create.
- Prefer reversible undo: `git revert` over `reset --hard`; a new commit over amending shared history.
- Never bypass hooks/signing (`--no-verify`, `--no-gpg-sign`) unless asked; if a hook fails, fix the cause.
- Before deleting/overwriting a ref or branch, inspect what it points to; if it isn't what was described or you didn't create it, stop and surface that.
- Interactive flags are unsupported (`-i`, `rebase -i`, `add -i`) — don't use them.
- Use the `gh` CLI for GitHub operations (PRs, issues).

## Commit conventions
- Concise imperative subject; body explains "why" when non-obvious.

## Common flows
- Review: `git status --short --branch` → `git diff --stat HEAD` → per-file `git diff HEAD -- <path>` for what matters → summarize + flag risks.
- Commit safely: ensure non-default branch (branch off if needed) → stage intended files
  (`git add <paths>`; avoid `-A` unless intended) → inspect staged diff → commit with trailer.
- Push: confirm intent → `git push -u origin <branch>` (never force unless asked).
- Undo last (unpushed) commit, keep work: `git reset --soft HEAD~1`. For pushed commits use `git revert <sha>`.
