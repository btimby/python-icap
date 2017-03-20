#: help - Display callable targets.
.PHONY: help
help:
	@echo "Reference card for usual actions in development environment."
	@echo "Here are available targets:"
	@egrep -o "^#: (.+)" [Mm]akefile  | sed 's/#: /* /'

venv/bin/python3: requirements.txt
	python3 -m virtualenv venv -p python3
	venv/bin/pip install -r requirements.txt

#: venv - Create virtual environment.
venv: venv/bin/python3

#: test - Run unit tests (with coverage).
.PHONY: test
test: venv
	venv/bin/coverage3 run venv/bin/py.test tests/test_*.py

#: lint - Run flake8 linter
.PHONY: lint
lint: venv
	venv/bin/flake8 icap

#: clean - Clean up after targets.
.PHONY: clean
clean:
	rm -rf venv .coverage .cache

