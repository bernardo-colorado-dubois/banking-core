SHELL := /bin/bash
.DEFAULT_GOAL := help

.PHONY: help up down build restart logs front-logs ps shell psql create-admin

help: ## Lista los comandos
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-14s %s\n", $$1, $$2}'

up: ## Construye y levanta la app, el frontend y PostgreSQL
	docker compose up -d --build

down: ## Detiene los contenedores (los datos se conservan en el volumen)
	docker compose down

build: ## Reconstruye la imagen de la app (tras cambiar requirements.txt)
	docker compose build app

restart: ## Reinicia la app
	docker compose restart app

logs: ## Sigue los logs de la app
	docker compose logs -f app

front-logs: ## Sigue los logs del frontend
	docker compose logs -f frontend

ps: ## Estado de los contenedores
	docker compose ps

shell: ## Abre una shell en el contenedor de la app
	docker compose exec app bash

psql: ## Abre psql en la base
	docker compose exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

create-admin: ## DESTRUCTIVO: borra y recrea el esquema, siembra RBAC y el primer admin
	@read -p "Esto borra todas las tablas. ¿Continuar? [y/N] " ans && [ "$$ans" = y ]
	docker compose exec app python create_admin.py
