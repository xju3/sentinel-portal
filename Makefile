COMPOSE := docker compose --env-file docker/.env -f docker/docker-compose.yml

.PHONY: setup dev down test lint serve logs-api logs-diagnosis logs-notification logs-persistence rebuild-portal rebuild-admin

setup:
	cd server && uv sync

dev:
	$(COMPOSE) up --build -d --wait

down:
	$(COMPOSE) down

test:
	cd server && uv run --env-file .env pytest -q

lint:
	cd server && uv run ruff check .

serve:
	cd server && uv run --env-file .env --package api python -m uvicorn app.main:app --app-dir api --host 127.0.0.1 --port 3011

logs-api:
	$(COMPOSE) logs -f api

logs-diagnosis:
	$(COMPOSE) logs -f diagnosis

logs-notification:
	$(COMPOSE) logs -f notification

logs-persistence:
	$(COMPOSE) logs -f persistence

rebuild-portal:
	$(COMPOSE) up --build -d portal

rebuild-admin:
	$(COMPOSE) up --build -d admin
