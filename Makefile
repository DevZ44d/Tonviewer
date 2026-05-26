# ─────────────────────────────────────────────────────────────────────────────
#  Tonviewer — Makefile
#  Convenience targets for development, testing, and publishing.
#
#  Usage:
#    make install          Install in editable mode (development)
#    make install-dev      Install + dev dependencies
#    make lint             Run ruff linter
#    make format           Auto-format with black
#    make build            Build source + wheel distributions
#    make publish          Upload to PyPI (requires TWINE_PASSWORD or .pypirc)
#    make publish-test     Upload to TestPyPI first
#    make docker-build     Build Docker image
#    make docker-run       Run Docker container (interactive)
#    make docker-compose   Start via docker-compose
#    make clean            Remove build artefacts and caches
#    make check-update     Check if a newer version exists on PyPI
# ─────────────────────────────────────────────────────────────────────────────

PYTHON  ?= python3
PIP     ?= $(PYTHON) -m pip
PACKAGE := Tonviewer
IMAGE   := tonviewer
VERSION := $(shell $(PYTHON) -c \
	"from importlib.metadata import version; print(version('$(PACKAGE)'))" \
	2>/dev/null || echo "dev")

.DEFAULT_GOAL := help

# ── help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo ""
	@echo "  Tonviewer $(VERSION) — available targets"
	@echo ""
	@echo "  Setup"
	@echo "    make install          Install package in editable mode"
	@echo "    make install-dev      Install package + dev dependencies"
	@echo ""
	@echo "  Code Quality"
	@echo "    make lint             Lint with ruff"
	@echo "    make format           Format with black"
	@echo ""
	@echo "  Build & Publish"
	@echo "    make build            Build sdist + wheel"
	@echo "    make publish          Upload to PyPI"
	@echo "    make publish-test     Upload to TestPyPI"
	@echo "    make check-update     Check latest version on PyPI"
	@echo ""
	@echo "  Docker"
	@echo "    make docker-build     Build Docker image"
	@echo "    make docker-run       Run container (shows --help)"
	@echo "    make docker-compose   Start via docker-compose"
	@echo ""
	@echo "  Maintenance"
	@echo "    make clean            Remove build artefacts and caches"
	@echo ""

# ── install ───────────────────────────────────────────────────────────────────

.PHONY: install
install:
	$(PIP) install -e .
	$(PIP) install httpx beautifulsoup4
	@echo ""
	@echo "  ✔ Tonviewer installed — run: Tonviewer --help"

.PHONY: install-dev
install-dev:
	$(PIP) install -e .
	$(PIP) install httpx beautifulsoup4 ruff black build twine
	@echo ""
	@echo "  ✔ Dev environment ready"

# ── code quality ──────────────────────────────────────────────────────────────

.PHONY: lint
lint:
	$(PYTHON) -m ruff check src/

.PHONY: format
format:
	$(PYTHON) -m black src/

# ── build ─────────────────────────────────────────────────────────────────────

.PHONY: build
build: clean
	$(PYTHON) -m build
	@echo ""
	@echo "  ✔ Built dist/"
	@ls -lh dist/

# ── publish ───────────────────────────────────────────────────────────────────

.PHONY: publish
publish: build
	$(PYTHON) -m twine upload dist/*
	@echo ""
	@echo "  ✔ Published Tonviewer $(VERSION) → PyPI"

.PHONY: publish-test
publish-test: build
	$(PYTHON) -m twine upload --repository testpypi dist/*
	@echo ""
	@echo "  ✔ Published Tonviewer $(VERSION) → TestPyPI"

.PHONY: check-update
check-update:
	@echo "  Local  version : $(VERSION)"
	@echo "  PyPI   version : $$($(PYTHON) -c \
		"import urllib.request, json; \
		d=json.loads(urllib.request.urlopen('https://pypi.org/pypi/Tonviewer/json').read()); \
		print(d['info']['version'])")"

# ── docker ────────────────────────────────────────────────────────────────────

.PHONY: docker-build
docker-build:
	docker build \
		-t $(IMAGE):$(VERSION) \
		-t $(IMAGE):latest \
		.
	@echo ""
	@echo "  ✔ Image built → $(IMAGE):$(VERSION)"

.PHONY: docker-run
docker-run:
	docker run --rm -it $(IMAGE):latest --help

.PHONY: docker-compose
docker-compose:
	docker compose run --rm tonviewer --help

# ── wallet shortcuts (Docker) ─────────────────────────────────────────────────
# Usage:  make wallet-info ADDR="UQ..."
#         make wallet-tx   ADDR="UQ..." LIMIT=5
#         make tx-hash     HASH="abc123..."

.PHONY: wallet-info
wallet-info:
	docker compose run --rm tonviewer -w "$(ADDR)" -i

.PHONY: wallet-tx
wallet-tx:
	docker compose run --rm tonviewer -t "$(ADDR)" -l $(or $(LIMIT),5)

.PHONY: tx-hash
tx-hash:
	docker compose run --rm tonviewer -H "$(HASH)"

# ── clean ─────────────────────────────────────────────────────────────────────

.PHONY: clean
clean:
	rm -rf dist/ build/ *.egg-info src/*.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	@echo "  ✔ Clean"
