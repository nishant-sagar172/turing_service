# CLAUDE.md — Rules for AI Agents and Contributors

> **Every AI agent (Claude, Copilot, Cursor, or any other) MUST read and follow these rules before making any change to this codebase. If you cannot follow these rules, do not contribute.**

---

## Core Principles

1. **No assumptions.** Clarify requirements with the user before writing code. If the task is ambiguous, ask — don't guess.
2. **No overthinking.** Solve the problem as stated. Don't add features, abstractions, or "improvements" that weren't requested.
3. **Additive changes only.** Unless it is absolutely necessary, make additive changes. Do not remove, rename, or restructure existing code without explicit user approval.
4. **Ask before dropping.** If any existing code, endpoint, function, or feature is about to be removed or replaced — stop and ask the user explicitly. Never silently delete working code.

---

## Python Backend (FastAPI)

### Formatting & Linting

- **Formatter:** `ruff format` — run before every commit.
- **Linter:** `ruff check` — all code must pass with zero warnings.
- **Type checking:** `mypy` with `disallow_untyped_defs = true` — every function must have type hints.
- Config is in `pyproject.toml`. Do not override or weaken these settings.

```bash
ruff format app/
ruff check app/
mypy app/
```

### Code Standards

- Python 3.12+. Use modern syntax: `str | None` not `Optional[str]`, `dict[str, Any]` not `Dict[str, Any]`.
- Follow SOLID principles:
  - **S** — Each module/function has one responsibility.
  - **O** — Extend behavior through new code, not modifying existing stable code.
  - **L** — Subtypes must be substitutable for their base types.
  - **I** — Keep interfaces small and focused. No god-schemas.
  - **D** — Depend on abstractions (Settings, dependencies), not hardcoded values.
- Use `async/await` for all database and HTTP operations. Never block the event loop.
- Keep functions short. If a function exceeds 40 lines, consider splitting it.
- Use Pydantic schemas for all request/response validation. Never pass raw dicts across boundaries.
- Database queries go in `app/db/` or service modules, never in route handlers directly.
- No bare `except:`. Always catch specific exceptions.
- No `print()` — use `logging`.

### Naming

- Files: `snake_case.py`
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Route handlers: name matches the action (e.g., `create_batch`, `get_client`)

---

## Frontend (Next.js / TypeScript)

### Code Standards

- TypeScript strict mode. No `any` unless absolutely unavoidable.
- Use functional components with hooks. No class components.
- Props must be typed with explicit interfaces, not inline types.
- API calls go through `lib/adminApi.ts` — never call `fetch` directly in components.
- Use `const` by default. Only use `let` when reassignment is necessary.
- Prefer early returns over nested conditionals.
- CSS uses CSS variables defined in the global stylesheet. No hardcoded colors in components.

### Naming

- Files: `PascalCase.tsx` for components, `camelCase.ts` for utilities
- Components: `PascalCase`
- Functions/variables: `camelCase`
- Types/interfaces: `PascalCase`

---

## Version Control & Release Management

### Branching Strategy

- `main` is the production branch. It must always be deployable.
- Feature work goes in feature branches: `feat/<short-description>` (e.g., `feat/webhook-secret-ui`).
- Bug fixes: `fix/<short-description>` (e.g., `fix/batch-pagination`).
- Hotfixes for production: `hotfix/<short-description>`.
- No direct commits to `main` for non-trivial changes — use pull requests.

### Versioning

- This project follows [Semantic Versioning](https://semver.org/) (SemVer): `MAJOR.MINOR.PATCH`.
  - **MAJOR** — breaking API changes (endpoint removed, request/response contract changed).
  - **MINOR** — new features, new endpoints, backward-compatible additions.
  - **PATCH** — bug fixes, formatting, docs, internal refactors with no API impact.
- Version is tracked via git tags: `v1.0.0`, `v1.1.0`, `v1.1.1`, etc.
- Tag a release only after the deploy is verified and healthy.

### Pull Requests

- Every PR must have a clear title and a short description of what changed and why.
- PRs must pass lint (`ruff check`, `ruff format --check`) before merging.
- Review is required for changes touching: auth, database models/migrations, payment, or deployment configs.
- Squash-merge to keep `main` history clean. One commit per PR on `main`.
- Delete the feature branch after merging.

### Git Commits

- Commit messages: short, imperative tense ("Add batch endpoint", "Fix auth redirect").
- No `Co-Authored-By` or signature trailers in commits.
- One logical change per commit. Don't bundle unrelated changes.
- Never force-push to `main`.
- Never commit `.env`, `.env.prod`, API keys, or secrets.

### Database Migrations

- Every schema change must have an Alembic migration.
- Migrations must be backward-compatible — the old code must still work with the new schema during rollout.
- Never edit a migration that has already been applied to production. Create a new one.
- Test migrations locally before pushing: `alembic upgrade head` then `alembic downgrade -1` to verify rollback.

### Deployment

- Deployments are manual — triggered from GitHub Actions (`workflow_dispatch`), not on every push.
- Never deploy untested code. Verify locally or in a review environment first.
- After deploying, verify the health endpoint and spot-check core functionality.
- If a deploy breaks production, rollback first (redeploy the previous tag), debug later.

---

## Architecture Rules

- **Backend routes** live in `app/routers/`. Each router is mounted in `app/main.py`.
- **Schemas** live in `app/schemas/`. One file per domain (clients, batches, calls, admin).
- **Business logic** lives in `app/services/`. Routers call services, not the other way around.
- **Database models** live in `app/db/models.py`. Migrations are managed by Alembic in `alembic/`.
- **Frontend pages** live in `frontend/app/`. API utilities in `frontend/lib/`.
- Do not create new directories or architectural patterns without discussing with the team first.

---

## What NOT To Do

- Do not add dependencies without user approval.
- Do not refactor code that isn't part of the current task.
- Do not write multi-paragraph comments or docstrings. One line max, only when the WHY is non-obvious.
- Do not create README, CHANGELOG, or documentation files unless explicitly asked.
- Do not modify `docker-compose.prod.yml`, `.env.prod`, or deployment configs without explicit approval.
- Do not weaken linter/formatter settings.
- Do not add error handling for scenarios that cannot happen.
- Do not introduce feature flags or backwards-compatibility shims when you can just change the code.

---

## Security

- Never log secrets, API keys, tokens, or passwords — not even partially.
- Validate all external input at system boundaries (user input, API requests, webhook payloads).
- Use parameterized queries. Never build SQL strings with f-strings or concatenation.
- Secrets belong in `.env.prod` on the server, never in code, comments, or commit history.
- If a secret is accidentally committed, rotate it immediately — removing it from history is not enough.
- CORS, auth middleware, and rate limiting must not be weakened without explicit approval.

---

## Dependency Management

- Backend dependencies: `requirements.txt`. Pin exact versions (`package==1.2.3`).
- Frontend dependencies: `package.json` with `package-lock.json`. Always commit the lockfile.
- Do not add new dependencies without user approval. Justify why an existing stdlib or current dependency can't do the job.
- When updating a dependency, test the full stack locally before pushing.
- Prefer well-maintained, widely-used packages. No obscure single-maintainer libraries for critical paths.

---

## Testing

- Write tests for new business logic in `app/services/`. Route handlers are tested through integration tests.
- Tests live alongside the code or in a `tests/` directory mirroring the source structure.
- Test the happy path and the most likely failure mode. Don't test framework behavior.
- Run tests before pushing: `pytest`.
- Never mock the database in integration tests — use a real test database.
- **Never run tests against the production database.** Always use a dedicated test database.
- Never write tests that delete, truncate, or corrupt data. Tests must clean up after themselves using transactions or fixtures — not destructive operations.

---

## Database Safety

- **Never read, modify, delete, or run any query against the database without the user's explicit permission.**
- Never run raw SQL that alters schema, drops tables, truncates, or modifies data outside of Alembic migrations.
- Never write code that bulk-updates or bulk-deletes records without the user reviewing and approving the exact operation.
- Never connect to or interact with the production database for debugging, testing, or exploration unless the user explicitly instructs it.
- If a task requires a database change, describe what will change and wait for approval before executing.
