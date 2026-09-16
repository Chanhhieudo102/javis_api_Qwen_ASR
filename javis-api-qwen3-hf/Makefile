.PHONY: install dev run test lint format migrate migrate-new docker-up docker-down clean

# Install dependencies
install:
	poetry install

# Run development server
dev:
	poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run production server
run:
	poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# Run tests
test:
	poetry run pytest -v

# Run tests with coverage
test-cov:
	poetry run pytest -v --cov=app --cov-report=html

# Lint code
lint:
	poetry run ruff check .

# Format code
format:
	poetry run ruff format .
	poetry run ruff check --fix .

# Run database migrations
migrate:
	poetry run alembic upgrade head

# Create new migration
migrate-new:
	@read -p "Migration message: " msg; \
	poetry run alembic revision --autogenerate -m "$$msg"

# Rollback last migration
migrate-down:
	poetry run alembic downgrade -1

# Start docker containers
docker-up:
	docker-compose up -d

# Start docker containers (development)
docker-up-dev:
	docker-compose -f docker-compose.dev.yml up -d

# Stop docker containers
docker-down:
	docker-compose down

# Stop docker containers (development)
docker-down-dev:
	docker-compose -f docker-compose.dev.yml down

# Build docker image
docker-build:
	docker-compose build

# View docker logs
docker-logs:
	docker-compose logs -f

# Setup pre-commit hooks
pre-commit-install:
	poetry run pre-commit install

# Run pre-commit on all files
pre-commit-run:
	poetry run pre-commit run --all-files

# Clean up cache files
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true

# Show help
help:
	@echo "Available commands:"
	@echo "  install          - Install dependencies"
	@echo "  dev              - Run development server"
	@echo "  run              - Run production server"
	@echo "  test             - Run tests"
	@echo "  test-cov         - Run tests with coverage"
	@echo "  lint             - Lint code with ruff"
	@echo "  format           - Format code with ruff"
	@echo "  migrate          - Run database migrations"
	@echo "  migrate-new      - Create new migration"
	@echo "  migrate-down     - Rollback last migration"
	@echo "  docker-up        - Start docker containers"
	@echo "  docker-up-dev    - Start docker containers (development)"
	@echo "  docker-down      - Stop docker containers"
	@echo "  docker-down-dev  - Stop docker containers (development)"
	@echo "  docker-build     - Build docker image"
	@echo "  docker-logs      - View docker logs"
	@echo "  pre-commit-install - Setup pre-commit hooks"
	@echo "  pre-commit-run   - Run pre-commit on all files"
	@echo "  clean            - Clean up cache files"
