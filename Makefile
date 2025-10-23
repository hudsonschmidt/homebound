.PHONY: venv install run lint type test format clean

venv:
	python3 -m venv .venv

install:
	. .venv/bin/activate && pip install --upgrade pip wheel setuptools && \
	pip install -e "backend[dev]"

run:
	. .venv/bin/activate && uvicorn app.main:app --reload

lint:
	. .venv/bin/activate && ruff check .

type:
	. .venv/bin/activate && mypy backend

test:
	. .venv/bin/activate && pytest -q

format:
	. .venv/bin/activate && ruff check --select I --fix . && ruff format .

clean:
	rm -rf .mypy_cache .pytest_cache .ruff_cache build dist
	find . -name '__pycache__' -type d -exec rm -rf {} +
