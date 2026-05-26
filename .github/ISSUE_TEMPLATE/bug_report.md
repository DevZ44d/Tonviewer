---
name: "\U0001F41B Bug Report"
about: Something is broken or behaving unexpectedly
title: "[BUG] "
labels: ["bug", "needs-triage"]
assignees: DevZ44d
---

## Bug Description

<!-- A clear and concise description of what the bug is. -->

## Steps to Reproduce

```python
# Minimal code that triggers the bug
from Tonviewer import Wallet

wallet = Wallet("UQ...")
print(wallet.info())
```

## Expected Behavior

<!-- What should happen? -->

## Actual Behavior

<!-- What actually happens? Include the full traceback if any. -->

```
Traceback (most recent call last):
  ...
```

## Environment

| Field | Value |
|---|---|
| **OS** | Windows / macOS / Linux |
| **Python version** | `python --version` |
| **Tonviewer version** | `Tonviewer -v` |
| **httpx version** | `pip show httpx` |

## Additional Context

<!-- Screenshots, logs, or any other context. -->
