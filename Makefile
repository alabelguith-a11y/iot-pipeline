.PHONY: install demo test lint etl report up down logs demo-dev kind clean
PY ?= python

install:           ## install python deps
	$(PY) -m pip install -r requirements.txt -r requirements-dev.txt

demo:              ## zero-dependency demo: ZeroMQ + SQLite, ~10 s
	$(PY) scripts/demo_local.py

test:              ## unit + end-to-end ELT tests (no services needed)
	$(PY) -m pytest -q

lint:
	ruff check .

etl:               ## run the ELT once against the current PROFILE
	$(PY) -m iotpipe.etl.runner

report:
	$(PY) -m iotpipe.etl.report

up:                ## full stack: Mosquitto + Kafka + PostgreSQL + bridge + consumer + simulator + ETL loop
	cp -n .env.example .env || true
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f bridge consumer etl

demo-dev: up       ## full stack, then show the report from Postgres
	sleep 45
	docker compose exec etl python -m iotpipe.etl.report

kind:              ## free local Kubernetes (no cloud cost)
	kind create cluster --name iot || true
	docker build -t iot-pipeline:local .
	kind load docker-image iot-pipeline:local --name iot
	kubectl create ns iot --dry-run=client -o yaml | kubectl apply -f -
	kubectl -n iot create secret generic iot-pg --from-literal=POSTGRES_USER=iot --from-literal=POSTGRES_PASSWORD=change-me --from-literal=POSTGRES_DB=iot --dry-run=client -o yaml | kubectl apply -f -
	kubectl -n iot create secret generic iot-db --from-literal=DB_URL=postgresql://iot:change-me@postgres:5432/iot --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -k k8s/infra && kubectl apply -k k8s/base

clean:
	rm -f data/*.db data/*.db-*
