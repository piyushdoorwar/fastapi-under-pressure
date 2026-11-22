# SecondLoop: FastAPI Under Pressure companion repo
PY ?= python

.PHONY: seed api partner load test lint

seed:
	$(PY) -m secondloop.seed

api:
	uvicorn secondloop.main:app --port 8000 --no-access-log

partner:
	uvicorn fakes.parcelpath:app --port 8081

load:
	$(PY) tools/load.py --users $(or $(USERS),20) \
		--seconds $(or $(SECONDS),30)

test:
	pytest -q

lint:
	ruff check .
