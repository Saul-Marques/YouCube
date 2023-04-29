#!make

run:
	python src/youcube

docker-build:
	docker build -t youcube:latest src/.

pylint:
	pylint src/youcube/*.py

pyspelling:
	pyspelling

cleanup:
ifeq ($(OS), Windows_NT)
	del /s /q src\youcube\data src\data src\youcube\__pycache__ src\__pycache__
else
	rm src/youcube/data src/data src/youcube/__pycache__ src/__pycache__ -Rv || true
endif

install-pylint:
	pip install pylint

install-pyspelling:
	pip install pyspelling

install-requirements:
ifeq ($(OS), Windows_NT)
	pip install -r src\requirements.txt
else
	pip install -r src/requirements.txt
endif
