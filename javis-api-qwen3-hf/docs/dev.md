## Project Structure

This repository uses a **monorepo architecture**. Each main folder handles a specific domain or feature:

- **app/**  
  Main application code.
  - **main.py**: FastAPI entry point.
  - **api/**: API route definitions (organized by version).
  - **common/**: Shared utilities, schemas, and helpers.
  - **features/**: Each feature (e.g., `chatbot`, `auth`, `users`) is a self-contained module with its own code and dependencies.
      - **api/**: API route definitions for the feature (e.g., REST endpoints, versioning).
      - **configs/**: Configuration files and settings specific to the feature.
      - **constants/**: Constant values, prompts, and mappings used throughout the feature.
      - **enums/**: Enumerations for types, categories, error codes, etc.
      - **models/**: Database models and ORM classes.
      - **repositories/**: Data access layer, handles database queries and persistence.
      - **resources/**: Static files, templates, or other resources required by the feature.
      - **schemas/**: Pydantic models for request/response validation and data structures.
      - **services/**: Business logic, service classes, and core operations for the feature.



- **migrations/**  
  Database migration scripts.

- **env/**  
  Environment configuration files.

- **.pre-commit-config.yaml**  
  Pre-commit hook configuration (see below).

---

## Code Style & Formatting

- All code must pass linting and formatting checks.
- We use [Ruff](https://github.com/charliermarsh/ruff) for linting and formatting.
- **VS Code users:**  
  For easier formatting and to pass Ruff pre-commit checks, install the [Ruff extension for VS Code](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff).

## Commit Messages

- Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/).
- Allowed types: `feat`, `fix`, `chore`, `test`, `custom`.
- Example:
  ```
  feat(chatbot): add intent detection processor
  fix(auth): resolve token expiration bug
  ```

## Pre-commit Hooks

Pre-commit hooks are configured in `.pre-commit-config.yaml`:

- **Ruff**: Enforces code style and formatting.
- **Conventional Commits**: Ensures commit messages follow the required format.



## Pull Requests

- Ensure your branch is up to date with main branch.
- All tests and pre-commit checks must pass.
- Provide a clear description of your changes.

## Environment

- Use the provided `.env` for local development.
- Install dependencies with Poetry:
  ```bash
  poetry install
  ```

## More Details 
For a deeper explanation of each folder and code structure, see [code.md](code.md)