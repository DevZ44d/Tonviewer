<div align="center">

# `NFTClient`

**Async TON NFT portfolio fetcher — full metadata, floor prices, and smart categorization in one context manager.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Async](https://img.shields.io/badge/Async-httpx-orange?style=flat-square)](https://www.python-httpx.org/)
[![TON](https://img.shields.io/badge/Blockchain-TON-0088cc?style=flat-square)](https://ton.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

</div>

---

## Overview

`NFTClient` is a production-ready async client that fetches the **complete NFT portfolio** of any TON wallet or Telegram `@username`. It handles:

- Automatic `@username → wallet` resolution via **Fragment.com**
- Full **pagination** through TonAPI (1 000 items/page)
- Concurrent **floor price enrichment** per collection
- Smart **categorization** into Usernames / Gifts / Other
- Graceful degradation — missing wallets, rate limits, and parse errors never crash the caller

---

## Requirements

```bash
pip install httpx
```

| Package | Purpose |
|---|---|
| `httpx` | Async HTTP client |
| `beautifulsoup4` | Fragment scraper (via `Fragment` / `FragmentClient`) |
| `tonsdk` | TON address normalization |

Internal dependencies from the same project:

| Module | Role |
|---|---|
| `fragment.py` → `FragmentClient`, `normalize_address` | Resolve `@username` → wallet |
| `GetWallet.py` → `Fragment` | Single-username Fragment scraper |
| `exceptions.py` | Custom exception hierarchy |

---

## Quick Start

```python
import asyncio
from nft import NFTClient

async def main():
    async with NFTClient() as client:
        result = await client.get_nfts("@monk")
        print(result.summary())

asyncio.run(main())
```

---

## API Reference

### `NFTClient(tonapi_key=None)`

```python
NFTClient(
    tonapi_key: Optional[str] = None   # TonAPI bearer token for higher rate limits
)
```

Must be used as an **async context manager**. On enter, it opens one shared `httpx.AsyncClient` and one `FragmentClient`. Both are closed cleanly on exit.

---

### Methods

#### `get_nfts(user_or_wallet, *, fetch_floors=True) → NFTResult`

Fetch **all** NFTs for a `@username` or raw wallet address.

```python
result = await client.get_nfts("@monk")
result = await client.get_nfts("UQDYzZmfsrGzhObKJUw4gzdeIxEai3jAFbiGKGwxvxHinf4K")
result = await client.get_nfts("@newuser", fetch_floors=False)   # skip floor prices
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `user_or_wallet` | `str` | — | Telegram `@username` or TON wallet address |
| `fetch_floors` | `bool` | `True` | Fetch collection floor prices from TonAPI |

**Returns:** `NFTResult` — never raises for missing wallets or unavailable usernames (returns empty result instead).

**Raises:** `NFTFetchError` — only on non-recoverable TonAPI pagination errors.

---

#### `get_nft_detail(nft_address) → Optional[NFTItem]`

Fetch full metadata for a single NFT by its contract address.

```python
nft = await client.get_nft_detail("UQDf9WIWEA8Sk5Fkr4dTG4-o1p0EN0qlb1as2JVB20MDd0_i")
if nft:
    print(nft.name, nft.collection, nft.image_url)
```

Returns `None` on any failure (logged, not raised).

---

#### `get_nfts_bulk(*users_or_wallets, fetch_floors=False) → Dict[str, NFTResult]`

Fetch NFTs for multiple wallets / usernames **concurrently**.

```python
bulk = await client.get_nfts_bulk("@monk", "@doge", "@sakoi", fetch_floors=True)
for user, result in bulk.items():
    print(user, "→", result.summary())
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `*users_or_wallets` | `str` | — | Any mix of `@usernames` and wallet addresses |
| `fetch_floors` | `bool` | `False` | Floor prices (default off to keep bulk fast) |

Failed entries are **skipped silently** (logged as warnings) — the rest of the dict is unaffected.

---

## `NFTResult` — Portfolio Container

The object returned by all fetch methods. Supports direct indexing, iteration, search, and filtering.

### Category Access

```python
result["users"]   # List[NFTItem] — Telegram Usernames
result["gifts"]   # List[NFTItem] — Telegram Gifts
result["etc"]     # List[NFTItem] — All other NFTs
result.all        # List[NFTItem] — Everything flat
```

### Properties

| Property | Type | Description |
|---|---|---|
| `.all` | `List[NFTItem]` | All NFTs in a flat list |
| `.names` | `List[str]` | All NFT display names |
| `.owner` | `Optional[str]` | Wallet address this result belongs to |
| `.is_empty` | `bool` | `True` when wallet holds no NFTs |

### Methods

| Method | Returns | Description |
|---|---|---|
| `by_collection()` | `Dict[str, List[NFTItem]]` | Grouped by collection, sorted by size |
| `search(query)` | `List[NFTItem]` | Case-insensitive search across name, collection, description |
| `filter_by(fn)` | `List[NFTItem]` | Filter with any callable predicate |
| `has(name, exact=True)` | `bool` | Check if an NFT name exists |
| `top_collections(n=5)` | `List[tuple[str, int]]` | Top-N collections by count |
| `value_summary()` | `Dict[str, float]` | Estimated floor value in TON per category |
| `summary()` | `str` | Human-readable portfolio stats block |

### `len()` and iteration

```python
print(len(result))       # total NFT count
for nft in result:       # iterates over all NFTs
    print(nft.name)
```

---

## `NFTItem` — Single NFT

```python
@dataclass
class NFTItem:
    address:            str                        # Normalized contract address
    name:               str                        # Display name from metadata
    collection:         str                        # Collection name (or "No Collection")
    collection_address: Optional[str]              # Collection contract address
    image_url:          Optional[str]              # Best available image / preview URL
    description:        Optional[str]              # Metadata description
    attributes:         List[NFTAttribute]         # Trait list
    floor_price_ton:    Optional[float]            # Collection floor in TON
    category:           "users" | "gifts" | "etc"  # Assigned category
```

**Attribute helpers:**

```python
nft.has_attribute("Background")            # bool
nft.get_attribute("Rarity")                # Optional[str]
```

---

## Categorization Rules

| Category | Rule |
|---|---|
| `users` | Name starts with `@` **or** collection name contains `"telegram usernames"` / `"usernames"` |
| `gifts` | Name contains `#` **or** collection matches: `"telegram gifts"`, `"gifts"`, `"durov"`, `"pepe"`, `"holiday"`, `"candle"`, `"loot box"`, `"nft gift"` |
| `etc` | Everything else |

---

## Address Resolution

When a `@username` is passed, `NFTClient` resolves it via the `Fragment` scraper:

| Fragment Status | Behavior |
|---|---|
| `Sold` / `Taken` | Extracts owner wallet → proceeds to fetch NFTs |
| `Available` / `On Auction` | Raises `AddressResolutionError` → returns **empty** `NFTResult` |
| Error / Not Found | Raises `AddressResolutionError` → returns **empty** `NFTResult` |

Raw wallet addresses bypass Fragment entirely.

---

## Exceptions

All custom exceptions are importable from `exceptions.py`:

| Exception | When raised |
|---|---|
| `AddressResolutionError` | `@username` cannot be resolved to a wallet (caught internally → empty result) |
| `NFTFetchError` | TonAPI pagination fails with a non-recoverable HTTP error |
| `UserNotFoundError` | Username not found on Fragment |
| `WalletNotFoundError` | Fragment page has no owner wallet link |

---

## Examples

**Iterate by category:**
```python
async with NFTClient() as client:
    result = await client.get_nfts("@ddddi")

    print(f"Usernames : {len(result['users'])}")
    print(f"Gifts     : {len(result['gifts'])}")
    print(f"Other     : {len(result['etc'])}")
```

**Search across portfolio:**
```python
async with NFTClient() as client:
    result = await client.get_nfts("@monk")
    matches = result.search("flame")
    for nft in matches:
        print(nft.name, "→", nft.collection)
```

**Custom filter — NFTs with floor price > 10 TON:**
```python
async with NFTClient() as client:
    result = await client.get_nfts("@monk", fetch_floors=True)
    valuable = result.filter_by(lambda n: n.floor_price_ton and n.floor_price_ton > 10)
    print(f"High-value NFTs: {len(valuable)}")
```

**Check for specific NFT:**
```python
async with NFTClient() as client:
    result = await client.get_nfts("@monk")
    if result.has("@dream"):
        print("Found!")
    if result.has("flame", exact=False):   # substring match
        print("Partial match found")
```

**Portfolio value breakdown:**
```python
async with NFTClient() as client:
    result = await client.get_nfts("@monk", fetch_floors=True)
    vals = result.value_summary()
    print(f"Usernames : {vals['users']} TON")
    print(f"Gifts     : {vals['gifts']} TON")
    print(f"Other     : {vals['etc']} TON")
    print(f"Total     : {vals['total']} TON")
```

**Single NFT detail:**
```python
async with NFTClient() as client:
    nft = await client.get_nft_detail("UQDf9WIWEA8Sk5Fkr4dTG4-o1p0EN0qlb1as2JVB20MDd0_i")
    if nft:
        print(nft.name)
        print(nft.image_url)
        for attr in nft.attributes:
            print(f"  {attr.trait_type}: {attr.value}")
```

**Bulk with floors:**
```python
async with NFTClient() as client:
    bulk = await client.get_nfts_bulk(
        "@monk", "@doge", "@sakoi",
        fetch_floors=True,
    )
    for user, result in bulk.items():
        vals = result.value_summary()
        print(f"{user:15s} → {len(result):4d} NFTs | ~{vals['total']} TON")
```

**Authenticated client (higher rate limits):**
```python
async with NFTClient(tonapi_key="your_tonapi_key_here") as client:
    result = await client.get_nfts("@monk")
    print(result.summary())
```

---

## Performance Notes

- **Pagination** — fetches in batches of 1 000 (TonAPI max). A wallet with 5 000 NFTs requires 5 sequential requests.
- **Floor enrichment** — all unique collection floor prices are fetched **concurrently** via `asyncio.gather`. For 50 unique collections this is one round-trip, not 50.
- **Bulk fetches** — `get_nfts_bulk()` fires all wallet fetches concurrently. Use `fetch_floors=False` (default) for fastest results when floor prices aren't needed.
- **Shared connection pool** — the single `httpx.AsyncClient` is reused across all requests inside the context manager. Do not create a new `NFTClient` per call in a loop.

---

## Troubleshooting

<details>
<summary><strong>Empty result for a @username I know has NFTs</strong></summary>

Fragment may show the username as `"Available"` or `"Auction"` — both indicate no current owner wallet. Verify with:

```python
from GetWallet import Fragment

async with Fragment(user="yourname") as f:
    info = await f.get_info()
    print(info["status"], info.get("owner"))
```

If status is not `"Sold"` or `"Taken"`, there is no wallet to fetch NFTs for.

</details>

<details>
<summary><strong>NFTFetchError on large wallets</strong></summary>

TonAPI may throttle heavily loaded wallets. Use an authenticated key:

```python
async with NFTClient(tonapi_key="your_key") as client:
    ...
```

Get a free key at [tonconsole.com](https://tonconsole.com).

</details>

<details>
<summary><strong>floor_price_ton is always None</strong></summary>

Floor prices require `fetch_floors=True` (default) and a valid `collection_address` on the NFT. NFTs with no collection (`"No Collection"`) will never have a floor price.

</details>

<details>
<summary><strong>NFT appears in wrong category</strong></summary>

Categorization is based on collection name keywords and NFT name prefixes. To add a new collection keyword, extend `_USER_COLLECTIONS` or `_GIFT_COLLECTIONS` at the top of `nft.py`.

</details>

---

## License

MIT © 2025
