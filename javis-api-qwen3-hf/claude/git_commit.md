# Git Commit Convention

## Types

- `feat` — new feature
- `fix` — bug fix
- `docs` — documentation
- `refactor` — code change without feature/fix
- `test` — tests
- `chore` — tooling, deps, config

## Format

```
<type>(<scope>): <subject>
```

## Rules

- Subject in imperative mood ("add", not "added")
- No period at the end
- Max 72 characters
- One logical change per commit

## Example

```
feat(auth): add JWT refresh token
fix(api): handle null user response
docs: update git commit convention
```
