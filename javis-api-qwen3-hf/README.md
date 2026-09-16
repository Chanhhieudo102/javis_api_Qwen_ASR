# BE - FastAPI Backend

A FastAPI backend project with clean architecture.

## Project Structure

```
be/
├── app/
│   ├── agent/                  # Common Agent Layer (Single Provider, Fallbacks, Tracing)
│   │   ├── clients/            # ChatModel Protocol & RunnableChatModel wrapper
│   │   ├── constants/          # Graph & model constants
│   │   ├── enums/              # ModelPurpose enums
│   │   ├── schemas/            # ModelProfile schemas
│   │   ├── utils/              # Chat request & traced run name utils
│   │   └── models.py           # Provider registry for chat models
│   ├── voice2text/             # Speech-to-Text & Transcript Analysis
│   │   ├── api/v2/             # Realtime WebSocket & Transcript API
│   │   ├── graphs/             # LangGraph Feature Graphs
│   │   │   └── transcript_analysis/ # Clean, punctuate, summarize, action items
│   │   ├── schemas/            # Schemas for ASR & analysis
│   │   └── services/           # Service layer
│   ├── api/                    # API routes
│   │   └── v1/
│   │       └── routes.py
│   ├── common/                 # Shared utilities (db, i18n, configs, exceptions)
│   ├── auth/                   # Authentication feature
│   ├── users/                  # Users feature
│   └── main.py
├── tests/                      # Unit tests (including test_agent_graphs.py)
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── alembic.ini
```

## Setup

### 1. Install Dependencies

```bash
# Install poetry if not installed
pip install poetry

# Install dependencies
poetry install
```

### 2. Setup Environment

```bash
# Copy environment file
cp .env.example .env

# Edit .env with your configuration
```

### 3. Setup Pre-commit

```bash
# Install pre-commit hooks
poetry run pre-commit install
```

### 4. Database Setup

```bash
# Start PostgreSQL with Docker
docker-compose up -d db

# Run migrations
poetry run alembic upgrade head
```

### 5. Run Application

```bash
# Development mode
poetry run uvicorn app.main:app --reload

# Or with Docker
docker-compose up
```

## Development

### Create Migration

```bash
poetry run alembic revision --autogenerate -m "description"
```

### Run Tests

```bash
poetry run pytest
```

### Lint & Format

```bash
# Lint
poetry run ruff check .

# Format
poetry run ruff format .

# Fix lint issues
poetry run ruff check --fix .
```

## Makefile Commands

```bash
make help              # Show all available commands
make install           # Install dependencies
make dev               # Run development server
make test              # Run tests
make lint              # Lint code
make format            # Format code
make migrate           # Run migrations
make migrate-new       # Create new migration
make docker-up-dev     # Start docker (development)
make docker-down-dev   # Stop docker (development)
make clean             # Clean cache files
```

## API Documentation

- Swagger UI: http://localhost:8000/api/v1/docs
- ReDoc: http://localhost:8000/api/v1/redoc
