<div align="center">

# `Fragment`

**Async Python scraper for Fragment.com — TON username intelligence in one context manager.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Async](https://img.shields.io/badge/Async-httpx-orange?style=flat-square)](https://www.python-httpx.org/)
[![Scraper](https://img.shields.io/badge/Target-fragment.com-0088cc?style=flat-square)](https://fragment.com)

</div>

---

## Overview

`Fragment` is a production-ready async scraper class that retrieves username ownership, sale prices, auction state, and owner wallet data from [fragment.com](https://fragment.com) — the official TON blockchain username marketplace.

It is designed as an **async context manager** for clean connection lifecycle management, with built-in exponential back-off retries, Cloudflare-aware headers, and structured JSON output.

---

## Requirements

```bash
pip install httpx beautifulsoup4 tonsdk
```

| Package | Purpose |
|---|---|
| `httpx` | Async HTTP client with connection pooling |
| `beautifulsoup4` | HTML parsing |
| `tonsdk` | TON address normalization (UQ format) |

---

## Quick Start

```python
import asyncio
from fragment import Fragment

async def main():
    async with Fragment(user="ccccce") as client:
        result = await client.get_info()
        print(result)

asyncio.run(main())
```

> ⚠️ **Always use `async with`.** Calling `get_info()` outside a context manager raises `RuntimeError`.

---

## API Reference

### `Fragment(user, timeout, retries)`

```python
Fragment(
    user: str,          # Username with or without "@"  →  "ccccce" or "@ccccce"
    timeout: float = 30.0,  # Per-request timeout in seconds
    retries: int   = 3,     # Max retry attempts on network failures
)
```

**Context manager methods:**

| Method | Returns | Description |
|---|---|---|
| `async get_info()` | `Dict` | Full structured data for the username |

---

## Return Schema

`get_info()` always returns a `dict`. On success:

```json
{
  "username":     "@ccccce",
  "fragment_url": "https://fragment.com/username/ccccce",
  "status":       "Sold",
  "price": {
    "display":  "1 500 TON",
    "value":    1500.0,
    "currency": "TON"
  },
  "owner": {
    "ton_wallet": "UQAh_cfG6nAD8EazS3dED8mtQo3bmeGn6nMM8TAZ-9h50k1D",
    "display":    "UQAh_cfG...",
    "tonviewer":  "https://tonviewer.com/UQAh_cfG6nAD8EazS3dED8mtQo3bmeGn6nMM8TAZ-9h50k1D"
  },
  "purchased_at": "14 Mar 2024 at 7:59 PM",
  "auction": {
    "bids":         12,
    "auction_ends": "2024-04-01 18:00 UTC",
    "min_bid":      "200 TON"
  },
  "metadata": {
    "collection": "Telegram Usernames",
    "note":       "Owned since March 2024"
  }
}
```

On error:

```json
{
  "error": "User not found in fragment (Taken)"
}
```

---

## Status Values

| `status` | Meaning |
|---|---|
| `"Sold"` | Username has a confirmed owner |
| `"On Sale"` | Listed at a fixed price |
| `"Auction"` | Active auction — bidding open |
| `"Available"` | Not yet claimed |
| `"Taken"` | Registered on TON but not listed |
| `"Unknown"` | Could not determine from page |

---

## Field Reference

<details>
<summary><strong>price</strong></summary>

| Key | Type | Description |
|---|---|---|
| `display` | `str \| None` | Raw price string as shown on Fragment (e.g. `"1 500 TON"`) |
| `value` | `float \| None` | Numeric extracted value for calculations |
| `currency` | `str \| None` | Always `"TON"` when present |

`price` is `null` for usernames with no listed price.

</details>

<details>
<summary><strong>owner</strong></summary>

| Key | Type | Description |
|---|---|---|
| `ton_wallet` | `str \| None` | UQ-formatted wallet address |
| `display` | `str \| None` | Display text scraped from the page link |
| `tonviewer` | `str \| None` | Direct Tonviewer.com link for the wallet |

`ton_wallet` is always normalized to **UQ** (user-friendly, non-bounceable, URL-safe) format via `tonsdk`.

</details>

<details>
<summary><strong>auction</strong></summary>

| Key | Type | Description |
|---|---|---|
| `bids` | `int` | Number of bids placed |
| `auction_ends` | `str` | Formatted deadline — `"YYYY-MM-DD HH:MM UTC"` |
| `min_bid` | `str` | Minimum / next required bid string |

This key is **omitted** if no auction data is found on the page.

</details>

<details>
<summary><strong>purchased_at</strong></summary>

A human-readable timestamp of the last sale/purchase, converted to 12-hour AM/PM format.

Example: `"14 Mar 2024 at 7:59 PM"`

Omitted when not available on the page.

</details>

---

## Error Handling

The scraper catches all expected failure modes internally and returns a structured `{"error": "..."}` dict instead of raising, **except** for `RuntimeError` (used outside context manager) which always propagates.

```python
async with Fragment(user="unknownxyz999") as client:
    result = await client.get_info()

    if "error" in result:
        print(f"Failed: {result['error']}")
    else:
        print(result["status"])
```

| Condition | Behavior |
|---|---|
| HTTP 403 (Cloudflare) | Returns `{"error": "Access denied — Cloudflare or IP block."}` |
| HTTP 404 | Returns `{"error": "User not found in fragment (Taken)"}` |
| Username not on Fragment | Returns `{"error": "User not found in fragment (Taken)"}` |
| Network timeout / failure | Retries up to `retries` times with exponential back-off, then returns `{"error": ...}` |
| Used outside `async with` | Raises `RuntimeError` immediately |

---

## Retry Strategy

On network failures (not 403/404), the client retries automatically:

```
Attempt 1  → fail → wait 2s
Attempt 2  → fail → wait 4s
Attempt 3  → fail → return {"error": ...}
```

Customize via constructor:

```python
async with Fragment(user="ccccce", retries=5, timeout=15.0) as client:
    ...
```

---

## Examples

**Check if a username is available:**
```python
async with Fragment(user="mytargetname") as client:
    data = await client.get_info()
    if data.get("status") == "Available":
        print("Username is free to register!")
```

**Get owner wallet:**
```python
async with Fragment(user="durov") as client:
    data = await client.get_info()
    wallet = data.get("owner", {}).get("ton_wallet")
    print(wallet)   # UQA...
```

**Bulk lookup with `asyncio.gather`:**
```python
async def bulk_check(usernames: list[str]):
    async def fetch(user):
        async with Fragment(user=user) as client:
            return await client.get_info()

    results = await asyncio.gather(*[fetch(u) for u in usernames])
    for r in results:
        print(r["username"], "→", r.get("status", r.get("error")))

asyncio.run(bulk_check(["monk", "doge", "cool", "ton", "hello"]))
```

**Extract auction floor bid:**
```python
async with Fragment(user="premium") as client:
    data = await client.get_info()
    auction = data.get("auction", {})
    print(f"Min bid : {auction.get('min_bid', 'N/A')}")
    print(f"Ends at : {auction.get('auction_ends', 'N/A')}")
    print(f"# Bids  : {auction.get('bids', 0)}")
```

---

## Security Notes

- **No credentials required.** The scraper uses public, unauthenticated Fragment pages.
- **Browser-like headers** are sent on every request to reduce Cloudflare detection.
- **No data is persisted.** All results live only in memory for the lifetime of the context manager.
- **IP blocks.** High-volume scraping from a single IP (especially datacenter IPs) will trigger Cloudflare 403s. Use a residential proxy for production deployments.

---

## Troubleshooting

<details>
<summary><strong>Always getting 403</strong></summary>

Fragment.com uses Cloudflare bot protection. This typically affects datacenter IPs (VPS, cloud servers). Solutions:

- Use a residential proxy
- Add a `Cookie` header from a real browser session
- Reduce request frequency

</details>

<details>
<summary><strong>owner.ton_wallet is always None</strong></summary>

Fragment's page structure may have changed. The scraper looks for `<a>` tags linking to `tonviewer.com` or `tonscan.org`. If neither is present in the HTML, the wallet cannot be extracted. Open an issue with the username.

</details>

<details>
<summary><strong>RuntimeError: Fragment must be used as an async context manager</strong></summary>

You called `get_info()` without entering the context manager:

```python
# ❌ Wrong
client = Fragment(user="ccccce")
await client.get_info()

# ✅ Correct
async with Fragment(user="ccccce") as client:
    await client.get_info()
```

</details>

<details>
<summary><strong>purchased_at is missing</strong></summary>

This field is only populated when a `<time>` tag or a "Purchased / Sold / Last sale" text pattern is found in the page. It is silently omitted when unavailable — this is expected behaviour, not a bug.

</details>

---

## License

MIT © 2025
