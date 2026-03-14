# Variables
IMAGE   := scoring-api
PORT    ?= 8080
MODE    ?= run
PYTHON  := uv run python
PYTEST  := uv run python -m pytest
TESTS   := test.py

.PHONY: all install lint test run \
        docker-build docker-run docker-test \
        compose-up compose-down

all: lint test

install:
	uv sync

lint:
	@echo "Running linter..."
	uv run ruff check .

test:
	@echo "Running tests..."
	$(PYTEST) $(TESTS) -v

run:
	@echo "Starting API server on port $(PORT)..."
	$(PYTHON) api.py --port $(PORT)

docker-build:
	docker build --target $(MODE) -t $(IMAGE)-$(MODE) .

docker-test:
	docker run --rm $(IMAGE)-test

docker-run:
	docker run $(if $(filter run,$(MODE)),-d) --rm -p $(PORT):8080 $(IMAGE)-$(MODE)

compose-up:
	@echo "Starting API + Redis..."
	docker compose up -d --build

compose-down:
	@echo "Stopping services..."
	docker compose down
