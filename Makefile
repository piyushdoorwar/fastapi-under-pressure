# SecondLoop: FastAPI Under Pressure companion repo
PY ?= python

.PHONY: seed api worker partner mailer idp balancer drills load test lint

seed:
	$(PY) -m secondloop.seed

api:
	$(PY) -m secondloop.serve --port 8000

worker:
	$(PY) -m secondloop.worker

partner:
	uvicorn fakes.parcelpath:app --port 8081

mailer:
	uvicorn fakes.mailer:app --port 8082

idp:
	uvicorn fakes.idp:app --port 8083

# Chapter 16: the drills expect the balancer on 8000
# with the API behind it on 8001 (and 8002 during a
# deploy). Start it with `make balancer`, then
# `$(PY) tools/deploy.py --start`, then a worker.
balancer:
	BALANCER_BACKENDS=http://127.0.0.1:8001,http://127.0.0.1:8002 \
	BALANCER_HEALTH=/readyz \
	uvicorn fakes.balancer:app --port 8000 --no-access-log

drills:
	$(PY) tools/drills.py

load:
	$(PY) tools/load.py --users $(or $(USERS),20) \
		--seconds $(or $(SECONDS),30)

test:
	pytest -q

lint:
	ruff check .
