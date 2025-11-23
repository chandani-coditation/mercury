.PHONY: help install test lint format type-check docker-up docker-down docker-logs clean

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	pip install -r requirements.txt

test: ## Run tests with coverage
	pytest tests/ -v --cov=ai_service --cov=ingestion --cov=retrieval --cov-report=html --cov-report=term-missing

lint: ## Run flake8 linter
	flake8 ai_service/ ingestion/ retrieval/ --max-line-length=100

format: ## Format code with black
	black ai_service/ ingestion/ retrieval/ tests/

type-check: ## Run mypy type checking
	mypy ai_service/ --ignore-missing-imports

docker-up: ## Start Docker services
	docker-compose up -d

docker-down: ## Stop Docker services
	docker-compose down

docker-logs: ## View Docker logs
	docker-compose logs -f ai-service

docker-build: ## Rebuild Docker images
	docker-compose build --no-cache

clean: ## Clean temporary files
	find . -type d -name __pycache__ -exec rm -r {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -r {} +
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage

all: format lint type-check test ## Run all checks (format, lint, type-check, test)

