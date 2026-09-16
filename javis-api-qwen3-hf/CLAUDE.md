# CLAUDE.md

Project conventions for FastAPI development. Keep code minimal, explicit, and consistent.

---

## Core Rules

1. **Imports at the top** of every file. No inline imports inside functions.
2. **No hardcoded values** — use constants, enums, env vars, or config.
3. **Use Enums for fixed types** (status, role, type fields). Never raw strings.
4. **Minimal comments** — only when *why* is non-obvious. Code should be self-explanatory.
5. **Type hints required** on all function signatures and class attributes.
6. **One responsibility per function/module.** Split when it grows.
7. **Follow existing patterns** in `app/` — don't introduce new structures.

---

## FastAPI Best Practices

### Project Structure
- Routes go in `app/<module>/routes/` or `app/api/`
- Business logic in `services/`, not in routes
- Database access in `repositories/` or via SQLAlchemy models
- Pydantic schemas in `schemas/`, separate from ORM models

### Routes
- Follow [claude/endpoint_development.md](claude/endpoint_development.md) for endpoint structure.
- Routes should be thin — call a service, return a response.
- Use dependency injection (`Depends`) for auth, DB session, config.
- HTTP status codes via `status.HTTP_*`, not magic numbers.
- **All responses must be wrapped with `DataResponseAPI`** (see [app/common/schemas/data_response.py](app/common/schemas/data_response.py)) — use `DataResponseAPI.success(...)` for success and `DataResponseAPI.error_response(...)` for errors. Never return raw dicts or models directly.
- For paginated endpoints, follow [claude/paginator.md](claude/paginator.md).

### Error Handling
- Follow [claude/error_handling.md](claude/error_handling.md) — raise typed exceptions with error constants, never inline messages.
- Let the global exception handler format responses; don't catch and re-format in routes.

### Git Commit
- Follow [claude/git_commit.md](claude/git_commit.md) for every commit message.

## General Coding Best Practices

- **Naming**: descriptive, no abbreviations. `user_id` not `uid`.
- **Functions**: short, do one thing, return early to reduce nesting.
- **Constants**: UPPER_SNAKE_CASE, grouped in `constants/`.
- **Enums**: PascalCase class, UPPER_SNAKE values.
- **DRY** — but don't over-abstract. Three similar lines is fine.
- **YAGNI** — don't build for hypothetical future needs.
- **Fail fast** — validate inputs early, raise immediately.
- **Immutable by default** — prefer `tuple`, `frozenset`, Pydantic models.
- **No silent failures** — never bare `except:` or swallow errors.

---

## References

- [claude/git_commit.md](claude/git_commit.md) — commit message convention
- [claude/error_handling.md](claude/error_handling.md) — error handling pattern
- [claude/endpoint_development.md](claude/endpoint_development.md) — endpoint guide
- [claude/paginator.md](claude/paginator.md) — pagination pattern
