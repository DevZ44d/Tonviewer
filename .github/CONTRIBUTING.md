# Contributing to Tonviewer

Thank you for your interest in contributing! Here's everything you need to get started.

---

## Quick Start

```bash
git clone https://github.com/DevZ44d/Tonviewer.git
cd Tonviewer
make install-dev
```

---

## Workflow

1. **Fork** the repository
2. **Create a branch** — `git checkout -b fix/your-fix` or `feat/your-feature`
3. **Make your changes**
4. **Lint + format** — `make lint && make format`
5. **Push** and open a **Pull Request** against `main`

---

## Code Style

- Formatter: `black` — `make format`
- Linter: `ruff` — `make lint`
- Type hints on all public methods
- Docstrings on all classes and public methods

---

## Commit Messages

Use conventional commits:

```
feat: add jetton balance support
fix: handle Fragment 403 gracefully
docs: update API reference for NFTClient
chore: bump httpx to 0.27.0
```

---

## Reporting Bugs

Open an issue using the **Bug Report** template and include:
- Full traceback
- Python & Tonviewer versions
- Minimal reproducible code

---

## Community

- Telegram Chat: [t.me/PyCodz_Chat](https://t.me/PyCodz_Chat)
- Telegram Channel: [t.me/PyCodz](https://t.me/PyCodz)
