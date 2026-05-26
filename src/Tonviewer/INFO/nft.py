"""
nft.py — Async TON NFT fetcher with full metadata & smart categorization.

Key improvements over v1:
  • Graceful handling when @username has no wallet (returns empty NFTResult).
  • Custom exceptions instead of bare ValueError/ConnectionError.
  • Cleaner async lifecycle — no stray gather() calls.
  • Full type hints throughout.
  • Richer NFTResult helpers: filter_by(), top_collections(), value_summary().

Usage:
    async with NFTClient() as client:

        # Fetch all NFTs for a @username (returns empty result if no wallet)
        result = await client.get_nfts("@monk")

        # Category access
        print(result["users"])     # Telegram Usernames
        print(result["gifts"])     # Telegram Gifts
        print(result["etc"])       # Other NFTs

        # Full list
        for nft in result.all:
            print(nft.name, nft.collection, nft.image_url)

        # Grouped by collection
        for coll, items in result.by_collection().items():
            print(coll, "→", len(items))

        # Stats
        print(result.summary())

        # Check if specific NFT exists
        if result.has("Chill Flame #117665"):
            print("Found it!")

        # Bulk — multiple wallets concurrently
        bulk = await client.get_nfts_bulk("@monk", "@doge")
        for user, res in bulk.items():
            print(user, res.summary())
"""

from __future__ import annotations

import asyncio
from .GetWallet import Fragment
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional

import httpx

from .exceptions import (
    AddressResolutionError,
    NFTFetchError,
    UserNotFoundError,
    WalletNotFoundError,
)
from .fragment import FragmentClient, normalize_address

logger = logging.getLogger(__name__)

_TONAPI_BASE = "https://tonapi.io/v2"


_USER_COLLECTIONS: frozenset[str] = frozenset({"telegram usernames", "usernames"})
_GIFT_COLLECTIONS: frozenset[str] = frozenset({
    "telegram gifts", "gifts", "durov", "pepe",
    "holiday", "candle", "loot box", "nft gift",
})
_GIFT_NAME_PATTERNS: frozenset[str] = frozenset({"#"})



@dataclass
class NFTAttribute:
    """A single trait attribute from NFT metadata."""

    trait_type: str
    value:      str

    def __str__(self) -> str:
        return f"{self.trait_type}: {self.value}"


@dataclass
class NFTItem:
    """
    A single NFT with full metadata.

    Attributes:
        address:             Normalised NFT contract address.
        name:                Display name from metadata.
        collection:          Collection name (or "No Collection").
        collection_address:  Normalised collection contract address (or None).
        image_url:           Best available image / preview URL (or None).
        description:         Metadata description text (or None).
        attributes:          List of NFTAttribute trait objects.
        floor_price_ton:     Collection floor price in TON (or None).
        category:            One of "users" | "gifts" | "etc".
    """

    address:            str
    name:               str
    collection:         str
    collection_address: Optional[str]          = None
    image_url:          Optional[str]          = None
    description:        Optional[str]          = None
    attributes:         List[NFTAttribute]     = field(default_factory=list)
    floor_price_ton:    Optional[float]        = None
    category:           Literal["users", "gifts", "etc"] = "etc"

    def has_attribute(self, trait_type: str) -> bool:
        """Return True if any attribute matches trait_type (case-insensitive)."""
        return any(a.trait_type.lower() == trait_type.lower() for a in self.attributes)

    def get_attribute(self, trait_type: str) -> Optional[str]:
        """Return the value of the first matching attribute, or None."""
        for a in self.attributes:
            if a.trait_type.lower() == trait_type.lower():
                return a.value
        return None

    def __str__(self) -> str:
        floor = f"  floor={self.floor_price_ton} TON" if self.floor_price_ton else ""
        return f"[{self.category}] {self.name}  ({self.collection}){floor}"

    def __repr__(self) -> str:
        return f"NFTItem(name={self.name!r}, collection={self.collection!r}, category={self.category!r})"



class NFTResult:
    """
    Smart container for a wallet's NFT portfolio.

    Indexing / category access:
        result["users"]   → List[NFTItem]  — Telegram Usernames
        result["gifts"]   → List[NFTItem]  — Telegram Gifts
        result["etc"]     → List[NFTItem]  — Other NFTs
        result.all        → List[NFTItem]  — Everything

    Main methods:
        by_collection()   → Dict[str, List[NFTItem]]
        search(query)     → List[NFTItem]
        filter_by(fn)     → List[NFTItem]
        has(name)         → bool
        top_collections(n)→ List[tuple[str, int]]
        names             → List[str]
        summary()         → str
    """

    def __init__(self, items: List[NFTItem], owner: Optional[str] = None) -> None:
        self._items = items
        self._owner = owner
        self._cats: Dict[str, List[NFTItem]] = self._categorize()


    def __getitem__(self, key: str) -> List[NFTItem]:
        if key in self._cats:
            return self._cats[key]
        raise KeyError(f"Unknown category {key!r}. Valid keys: {list(self._cats)}")

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    def __repr__(self) -> str:
        owner = f", owner={self._owner!r}" if self._owner else ""
        return (
            f"NFTResult(total={len(self)}, "
            f"users={len(self['users'])}, "
            f"gifts={len(self['gifts'])}, "
            f"etc={len(self['etc'])}"
            f"{owner})"
        )


    @property
    def all(self) -> List[NFTItem]:
        """All NFTs regardless of category."""
        return list(self._items)

    @property
    def names(self) -> List[str]:
        """Flat list of all NFT names."""
        return [n.name for n in self._items]

    @property
    def owner(self) -> Optional[str]:
        """The wallet address this result belongs to, if known."""
        return self._owner

    @property
    def is_empty(self) -> bool:
        """True when the wallet holds no NFTs."""
        return not self._items


    def by_collection(self) -> Dict[str, List[NFTItem]]:
        """
        Group all NFTs by collection name, sorted by size (largest first).

        Returns:
            Ordered dict mapping collection name → list of NFTItems.
        """
        groups: Dict[str, List[NFTItem]] = {}
        for item in self._items:
            groups.setdefault(item.collection, []).append(item)
        return dict(sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True))

    def search(self, query: str) -> List[NFTItem]:
        """
        Case-insensitive search across name, collection, and description.

        Args:
            query: Substring to search for.

        Returns:
            All matching NFTItem objects.
        """
        q = query.lower()
        return [
            item for item in self._items
            if q in item.name.lower()
            or q in item.collection.lower()
            or (item.description and q in item.description.lower())
        ]

    def filter_by(self, predicate: Callable[[NFTItem], bool]) -> List[NFTItem]:
        """
            Filter NFTs using an arbitrary callable.

            Example:
                result.filter_by(lambda n: n.floor_price_ton and n.floor_price_ton > 10)

            Args:
                predicate: A function that takes an NFTItem and returns bool.

            Returns:
                List of NFTItems for which predicate returns True.
        """
        return [item for item in self._items if predicate(item)]

    def has(self, name: str, *, exact: bool = True) -> bool:
        """
            Check whether an NFT with the given name exists in the result.

            Args:
                name:  NFT name to look for.
                exact: If True (default), require an exact match.
                       If False, do a case-insensitive substring search.

            Returns:
                True if found, False otherwise.
        """
        if exact:
            return name in self.names
        return bool(self.search(name))

    def top_collections(self, n: int = 5) -> List[tuple[str, int]]:
        """
            Return the top-N collections by NFT count.

            Args:
                n: Number of collections to return (default 5).

            Returns:
                List of (collection_name, count) tuples.
        """
        return [(k, len(v)) for k, v in list(self.by_collection().items())[:n]]

    def value_summary(self) -> Dict[str, float]:
        """
            Aggregate floor prices by category.

            Returns a dict with keys "users", "gifts", "etc", "total"
            representing estimated minimum portfolio value in TON.
            Note: floor × count is a rough lower bound, not an exact valuation.
        """
        out: Dict[str, float] = {"users": 0.0, "gifts": 0.0, "etc": 0.0, "total": 0.0}
        for cat in ("users", "gifts", "etc"):
            total = sum(
                item.floor_price_ton
                for item in self._cats[cat]
                if item.floor_price_ton
            )
            out[cat] = round(total, 4)
        out["total"] = round(sum(out[c] for c in ("users", "gifts", "etc")), 4)
        return out

    def summary(self) -> str:
        """Return a human-readable portfolio summary string."""
        lines = [
            f"Total NFTs : {len(self)}",
            f"  Users    : {len(self['users'])}",
            f"  Gifts    : {len(self['gifts'])}",
            f"  Other    : {len(self['etc'])}",
            f"Collections: {len(self.by_collection())}",
        ]
        for coll, count in self.top_collections(5):
            lines.append(f"  • {coll}: {count}")
        vals = self.value_summary()
        if vals["total"] > 0:
            lines.append(f"Est. floor value: {vals['total']} TON")
        return "\n".join(lines)


    def _categorize(self) -> Dict[str, List[NFTItem]]:
        cats: Dict[str, List[NFTItem]] = {"users": [], "gifts": [], "etc": []}
        for item in self._items:
            coll = item.collection.lower()

            if item.name.startswith("@") or any(kw in coll for kw in _USER_COLLECTIONS):
                item.category = "users"
                cats["users"].append(item)
            elif (
                any(p in item.name for p in _GIFT_NAME_PATTERNS)
                or any(kw in coll for kw in _GIFT_COLLECTIONS)
            ):
                item.category = "gifts"
                cats["gifts"].append(item)
            else:
                item.category = "etc"
                cats["etc"].append(item)
        return cats



class NFTClient:
    """
        Async TON NFT client.

        Fetches ALL NFTs (paginated) for a @username or wallet address,
        enriches them with collection floor prices, and categorizes them.

        Handles gracefully:
          • @username not on Fragment  → returns empty NFTResult
          • @username has no wallet    → returns empty NFTResult
          • TonAPI pagination errors   → partial results with warning logged
          • Floor-price fetch errors   → item.floor_price_ton remains None

        Args:
            tonapi_key: Optional TonAPI bearer token for higher rate limits.

        Usage:
            async with NFTClient() as client:
                result = await client.get_nfts("@monk")
                print(result.summary())
    """

    _PAGE_SIZE = 1000   # TonAPI maximum items per request

    def __init__(self, tonapi_key: Optional[str] = None) -> None:
        self._tonapi_key  = tonapi_key
        self._http:       Optional[httpx.AsyncClient] = None
        self._fragment:   Optional[FragmentClient]    = None

    async def __aenter__(self) -> "NFTClient":
        headers: Dict[str, str] = {
            "Accept":     "application/json",
            "User-Agent": "TonNFTClient/2.1",
        }
        if self._tonapi_key:
            headers["Authorization"] = f"Bearer {self._tonapi_key}"

        self._http     = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers=headers,
        )
        self._fragment = await FragmentClient().__aenter__()
        return self

    async def __aexit__(self, *_) -> None:
        tasks = []
        if self._http:
            tasks.append(self._http.aclose())
        if self._fragment:
            tasks.append(self._fragment.__aexit__(None, None, None))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


    async def get_nfts(
        self,
        user_or_wallet: str,
        *,
        fetch_floors: bool = True,
    ) -> NFTResult:
        """
            Fetch ALL NFTs for a @username or raw TON wallet address.

            If the username is not on Fragment or has no wallet, an empty
            NFTResult is returned (no exception is raised).

            Args:
                user_or_wallet: Telegram @username or raw TON wallet address.
                fetch_floors:   When True, fetch collection floor prices from
                                TonAPI and attach them to each NFTItem.

            Returns:
                NFTResult containing all found NFTs, or an empty NFTResult.

            Raises:
                NFTFetchError: If TonAPI returns a non-recoverable error during
                               pagination (partial results may already be available).
        """
        try:
            address = await self._resolve(user_or_wallet)
        except AddressResolutionError as exc:
            logger.info(f"[NFTClient] {exc} — returning empty result.")
            return NFTResult([], owner=user_or_wallet)

        raw   = await self._fetch_all_nfts(address)
        items = self._parse_items(raw)

        if fetch_floors and items:
            await self._enrich_floors(items)

        return NFTResult(items, owner=address)

    async def get_nft_detail(self, nft_address: str) -> Optional[NFTItem]:
        """
            Fetch full detail for a single NFT by its contract address.

            Args:
                nft_address: Raw or normalised TON NFT address.

            Returns:
                NFTItem if successful, None if the request fails.
        """
        try:
            r = await self._http.get(f"{_TONAPI_BASE}/nfts/{nft_address}")
            r.raise_for_status()
            return self._parse_one(r.json())
        except Exception as exc:
            logger.error(f"[TonAPI] NFT detail fetch failed for {nft_address!r}: {exc}")
            return None

    async def get_nfts_bulk(
        self,
        *users_or_wallets: str,
        fetch_floors: bool = False,
    ) -> Dict[str, NFTResult]:
        """
            Fetch NFTs for multiple @usernames / wallets concurrently.

            Skips entries that fail (with a logged warning) so other results
            are not affected.

            Args:
                *users_or_wallets: Any mix of @usernames and wallet addresses.
                fetch_floors:      Fetch collection floor prices (default False
                                   to keep bulk calls fast).

            Returns:
                Dict mapping the original identifier → NFTResult.
                Missing / failed entries are omitted from the dict.
        """
        results = await asyncio.gather(
            *[self.get_nfts(u, fetch_floors=fetch_floors) for u in users_or_wallets],
            return_exceptions=True,
        )
        output: Dict[str, NFTResult] = {}
        for u, r in zip(users_or_wallets, results):
            if isinstance(r, NFTResult):
                output[u] = r
            else:
                logger.warning(f"[NFTClient] bulk — skipping {u!r}: {r}")
        return output

    async def _resolve(self, user_or_wallet: str) -> str:
        """
            Resolve @username → wallet address.

            - If username is Available / Auction / Unknown → AddressResolutionError
            - If username is Sold/Taken → return owner wallet (UQ format)
            - If raw wallet address passed → return as-is
        """
        if not user_or_wallet.startswith("@"):
            return user_or_wallet  # already a raw address

        scraper = Fragment(user_or_wallet)
        info = await scraper.get_info()

        # Username doesn't exist or is not sold/owned by anyone
        if "error" in info:
            raise AddressResolutionError(
                user_or_wallet,
                f"Username not on Fragment or is taken/unavailable: {info['error']}"
            )

        status = info.get("status", "Unknown").lower()
        valid_statuses = {"sold", "taken"}  # only these have a real owner wallet

        if status not in valid_statuses:
            raise AddressResolutionError(
                user_or_wallet,
                f"Username @{user_or_wallet.lstrip('@')} is '{info['status']}' "
                f"— no owner wallet to fetch NFTs for."
            )

        wallet = info.get("owner", {}).get("ton_wallet")
        if not wallet:
            raise AddressResolutionError(
                user_or_wallet,
                f"Username '{user_or_wallet}' is {info['status']} but wallet address not found."
            )

        logger.info(
            f"[Fragment] {user_or_wallet} → {wallet} (status: {info['status']})"
        )
        return wallet


    async def _fetch_all_nfts(self, address: str) -> List[Dict[str, Any]]:
        """Paginate through all NFTs for a wallet address."""
        all_items: List[Dict[str, Any]] = []
        offset = 0

        while True:
            try:
                r = await self._http.get(
                    f"{_TONAPI_BASE}/accounts/{address}/nfts",
                    params={"limit": self._PAGE_SIZE, "offset": offset},
                )
                r.raise_for_status()
                batch = r.json().get("nft_items", [])
                all_items.extend(batch)

                if len(batch) < self._PAGE_SIZE:
                    break   # reached the last page
                offset += self._PAGE_SIZE
                logger.debug(f"[NFT] Paginated — {offset} items fetched so far…")

            except httpx.HTTPStatusError as exc:
                raise NFTFetchError(address, offset=offset, cause=exc) from exc
            except Exception as exc:
                logger.error(f"[TonAPI] NFT page fetch failed (offset={offset}): {exc}")
                break   # return partial results rather than raising

        logger.debug(f"[NFT] Total fetched for {address!r}: {len(all_items)}")
        return all_items


    async def _enrich_floors(self, items: List[NFTItem]) -> None:
        """Fetch floor prices for all unique collections concurrently."""
        # Build mapping: collection_address → list of its NFTItems
        coll_map: Dict[str, List[NFTItem]] = {}
        for item in items:
            if item.collection_address:
                coll_map.setdefault(item.collection_address, []).append(item)

        if not coll_map:
            return

        floors = await asyncio.gather(
            *[self._fetch_floor(addr) for addr in coll_map],
            return_exceptions=True,
        )

        for coll_addr, floor_price in zip(coll_map, floors):
            if isinstance(floor_price, (int, float)) and floor_price > 0:
                for item in coll_map[coll_addr]:
                    item.floor_price_ton = floor_price

    async def _fetch_floor(self, collection_address: str) -> Optional[float]:
        """Fetch the floor price (in TON) for a single collection."""
        try:
            r = await self._http.get(
                f"{_TONAPI_BASE}/nfts/collections/{collection_address}",
            )
            r.raise_for_status()
            data  = r.json()
            floor = data.get("floor_price")
            if floor:
                return float(floor) / 1_000_000_000
            return None
        except Exception:
            return None


    def _parse_items(self, raw: List[Dict[str, Any]]) -> List[NFTItem]:
        parsed: List[NFTItem] = []
        for item in raw:
            try:
                parsed.append(self._parse_one(item))
            except Exception as exc:
                logger.debug(f"[NFT] Skipping malformed item: {exc}")
        return parsed

    @staticmethod
    def _parse_one(item: Dict[str, Any]) -> NFTItem:
        metadata   = item.get("metadata") or {}
        collection = item.get("collection") or {}
        coll_name  = collection.get("name") or "No Collection"
        coll_addr  = collection.get("address")

        # Best available image URL
        previews  = item.get("previews") or []
        image_url = (
            metadata.get("image")
            or metadata.get("image_url")
            or (previews[-1].get("url") if previews else None)
        )

        # Trait attributes
        raw_attrs  = metadata.get("attributes") or []
        attributes = [
            NFTAttribute(
                trait_type=str(a.get("trait_type", "")),
                value     =str(a.get("value", "")),
            )
            for a in raw_attrs
            if isinstance(a, dict)
        ]

        return NFTItem(
            address            = normalize_address(item.get("address", "")),
            name               = metadata.get("name") or item.get("address", "Unnamed NFT"),
            collection         = coll_name,
            collection_address = normalize_address(coll_addr) if coll_addr else None,
            image_url          = image_url,
            description        = metadata.get("description") or None,
            attributes         = attributes,
        )


"""
async def main() -> None:
    #logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async with NFTClient() as client:

        # ── Test 1: username with no wallet ────────────────────────────────
        #print("=== Test: @username with no wallet ===")
        #result = await client.get_nfts("@DevGit", fetch_floors=False)
        #print(f"Result: {result!r}")
        #print(f"Empty : {result.is_empty}")
        #print()

        result = await client.get_nfts(user_or_wallet="@ddddi", fetch_floors=True)
        hits = result.search("chill flame")
        for item in hits:
            print(item.name)

        #if result["users"]:
            #print([n.name for n in result["users"]])

        #if result.has("@dream"):
            #print("✓ found")
        #else:
            #print("✗ not found")

        #nft = await client.get_nft_detail(nft_address="EQB4cq9KQlNNz4RYY4cpuJiGElOjqIr6LiEo6CNPgokfP9R2")
        #print(nft.name)

        #print("\nTop 5 collections:")
        #for name, count in result.top_collections(5):
            #print(f"  {name}: {count}")

        #print()

        # ── Test 3: bulk ───────────────────────────────────────────────────
        #print("=== Test: bulk fetch ===")
        #bulk = await client.get_nfts_bulk("@ddddi", "@sakoi", "@z5zzz", "@DevGit", "@zzgsersehrs")
        #for user, res in bulk.items():
            #print(f"  {user}: {res!r}")


if __name__ == "__main__":
    asyncio.run(main())
"""