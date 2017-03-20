
venv/bin/python3: requirements.txt
	python3 -m virtualenv venv -p python3
	venv/bin/pip install -r requirements.txt

venv: venv/bin/python3

test: venv
	venv/bin/coverage3 run venv/bin/py.test tests/test_*.py

lint: venv
	venv/bin/flake8 icap

clean:
	rm -rf venv .coverage

doc:
	make -C docs html
