---
name: best-coding-practices
description: Clean-code checklist for this FastAPI/Python service. Load before writing or editing routers, services, schemas, or models.
---

Apply to all Python code in turing_service. Skip any rule the surrounding file's style already contradicts. Avoid  Overexplaining and unnecessay thinking. Make only Necessary changes.

**Structure**
- Routers stay thin: validate via Pydantic, delegate to `app/services/*`, return schemas. No business logic in handlers.
- No extra comments. Only short useful comments
- Every store/query function takes and filters by `client_id` — no bypassing tenant scoping.
- Pydantic v2 for all request/response shapes; add real constraints (`ge`, `min_length`, etc.) instead of trusting upstream/caller input.

**Style**
- No comments except a one-line non-obvious "why" (workaround, invariant). Never restate what the code says.
- Type hints everywhere; no bare `Any` unless the payload is genuinely opaque passthrough.
- No dead code, unused imports, commented-out blocks, or speculative abstractions/error handling for cases that can't occur.
- f-strings over `.format`/`%`; `pathlib` over `os.path`; async SQLAlchemy only.

**Before finishing**
- Run `ruff check .` and `mypy .`; fix anything you introduced.
- Re-read the diff — remove anything added "just in case."
