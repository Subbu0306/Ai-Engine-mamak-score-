PY=.venv/bin/python
PIP=.venv/bin/pip

install:
	python3 -m venv .venv
	$(PIP) install -e '.[dev]'
test:
	$(PY) -m pytest
lint:
	$(PY) -m ruff check .
format-check:
	$(PY) -m ruff format --check .
typecheck:
	$(PY) -m mypy src
quality: lint format-check typecheck test
serve:
	.venv/bin/mamakscore serve
demo:
	$(PY) scripts/create_demo_files.py --output-dir .cache/demo
	.venv/bin/mamakscore evaluate .cache/demo/deck.pdf --financial-model .cache/demo/finance.xlsx
load-test:
	$(PY) scripts/load_test.py --deck .cache/demo/deck.pdf
clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage .cache
