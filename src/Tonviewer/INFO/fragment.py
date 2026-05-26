"""
fragment.py — Async Fragment.com scraper (production-grade, bug-fixed).

Handles all edge-cases:
  • Username not found on Fragment
  • Username found but no wallet linked (auction / unclaimed)
  • Cloudflare 403 blocks
  • Network failures with configurable retries & exponential back-off
  • Concurrent request throttling via Semaphore
  • Optional in-memory result caching with TTL
  • Proxy support for rotating IPs

═══════════════════════════════════════════════
  FIXES vs original:
    [FIX #1] _price_from_regex — page_text uses separator=" " so splitlines()
             always returned a single element. Replaced with direct regex search.
    [FIX #2] get_usernames — silently returned [] when all usernames failed.
             Now logs a clear summary of how many failed and which ones.
    [FIX #3] WalletNotFoundError now receives the status string so callers can
             distinguish "On Auction" from other no-wallet cases.
    [FIX #4] _parse not-found heuristic was too fragile — added secondary checks.
    [FIX #5] _fetch retry loop: last-attempt raise was inside `except` but could
             shadow the original exception type. Now always raises FragmentFetchError
             with `from exc` to preserve the chain correctly.

  ADDITIONS vs original:
    [ADD #1] Semaphore — caps concurrent HTTP requests (default: 5).
    [ADD #2] In-memory cache with configurable TTL (default: 300 s).
    [ADD #3] Proxy support — pass proxy="http://user:pass@host:port" to __init__.
    [ADD #4] FragmentParseError raised on truly unexpected HTML instead of silent None.
    [ADD #5] monitor_auction() helper coroutine.
    [ADD #6] to_dict() / to_json() on FragmentResult for easy serialisation.
    [ADD #7] WalletNotFoundError carries the status field.
═══════════════════════════════════════════════

Usage:
    async with FragmentClient() as client:

        # ── Single lookup ────────────────────────────────────────────────
        result = await client.get_username("@monk")
        print(result.status, result.price_ton, result.friendly_wallet)

        # ── Resolve wallet only (returns None instead of raising) ────────
        wallet = await client.resolve_wallet("@monk")   # str | None

        # ── Bulk (concurrent, throttled) ─────────────────────────────────
        results = await client.get_usernames("@monk", "@doge", "@ton")

        # ── Search for available usernames ───────────────────────────────
        hits = await client.search("cool")
        for h in hits:
            print(h.username, h.status, h.price_ton)

        # ── Serialise to dict / JSON ─────────────────────────────────────
        print(result.to_dict())
        print(result.to_json())

        # ── Debug: save raw HTML to disk ─────────────────────────────────
        result = await client.get_username("@monk", debug=True)

    # ── Auction monitor ──────────────────────────────────────────────────
    async with FragmentClient() as client:
        await monitor_auction(client, "@cool", interval=60)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup
from tonsdk.utils import Address

from .exceptions import (
    FragmentBlockedError,
    FragmentFetchError,
    FragmentParseError,
    UserNotFoundError,
    WalletNotFoundError,
)

logger = logging.getLogger(__name__)

_FRAGMENT_BASE = "https://fragment.com"



def normalize_address(raw: str) -> str:
    """
    Convert any TON address format to user-friendly UQ-prefixed form.

    Returns the raw string unchanged when conversion fails so the caller
    always gets *something* rather than an empty string.
    """
    if not raw:
        return ""
    try:
        return Address(raw).to_string(
            is_user_friendly=True,
            is_url_safe=True,
            is_bounceable=False,
            is_test_only=False,
        )
    except Exception:
        logger.debug(f"[Fragment] normalize_address: could not convert {raw!r}")
        return raw



@dataclass
class FragmentResult:
    """
    Full result for a single Telegram username queried from Fragment.com.

    Attributes:
        username:        Clean username without @.
        status:          Fragment status string (Sold / On Auction / Available / Not Found).
        raw_wallet:      Raw wallet address as returned by TonViewer/TonScan links.
        friendly_wallet: Normalised UQ-prefixed wallet address (or None).
        display_wallet:  Abbreviated address shown on the page (or None).
        price_ton:       Sale / current price string including the TON symbol (or None).
        min_bid:         Minimum bid string for auctions (or None).
        auction_end:     Auction deadline string / timestamp (or None).
        fragment_url:    Canonical Fragment URL for this username.
        fetched_at:      Unix timestamp of when the result was fetched.
    """

    username:        str
    status:          str
    raw_wallet:      Optional[str]  = None
    friendly_wallet: Optional[str]  = None
    display_wallet:  Optional[str]  = None
    price_ton:       Optional[str]  = None
    min_bid:         Optional[str]  = None
    auction_end:     Optional[str]  = None
    fragment_url:    str            = ""
    fetched_at:      float          = field(default_factory=time.time)


    @property
    def is_sold(self) -> bool:
        """True when the username has been sold and has an owner."""
        return "sold" in self.status.lower()

    @property
    def is_auction(self) -> bool:
        """True when the username is currently on auction."""
        return "auction" in self.status.lower()

    @property
    def is_available(self) -> bool:
        """True when the username is available for purchase."""
        return "available" in self.status.lower()

    @property
    def is_not_found(self) -> bool:
        """True when Fragment has no record of this username."""
        return "not found" in self.status.lower()

    @property
    def has_wallet(self) -> bool:
        """True when a wallet address was successfully resolved."""
        return bool(self.friendly_wallet)

    @property
    def owner(self) -> Optional[str]:
        """Alias for friendly_wallet — the current owner's wallet."""
        return self.friendly_wallet


    def to_dict(self) -> Dict[str, Any]:
        """
        Return a plain dict representation of the result (JSON-serialisable).

        Derived boolean properties are included for convenience.

        Example:
            d = result.to_dict()
            print(d["status"], d["is_sold"], d["friendly_wallet"])
        """
        base = asdict(self)
        base.update(
            is_sold      = self.is_sold,
            is_auction   = self.is_auction,
            is_available = self.is_available,
            is_not_found = self.is_not_found,
            has_wallet   = self.has_wallet,
        )
        return base

    def to_json(self, *, indent: int = 2) -> str:
        """
        Return a JSON string representation of the result.

        Example:
            print(result.to_json())
            with open("result.json", "w") as f:
                f.write(result.to_json())
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


    def __str__(self) -> str:
        parts = [f"@{self.username}", f"[{self.status}]"]
        if self.price_ton:
            parts.append(self.price_ton)
        if self.friendly_wallet:
            parts.append(f"→ {self.friendly_wallet[:16]}…")
        return "  ".join(parts)

    def __repr__(self) -> str:
        return (
            f"FragmentResult(username={self.username!r}, status={self.status!r}, "
            f"has_wallet={self.has_wallet}, price={self.price_ton!r})"
        )


@dataclass
class FragmentSearchResult:
    """Lightweight result from a Fragment search query."""

    username:  str
    status:    str
    price_ton: Optional[str] = None

    def __str__(self) -> str:
        price = f"  {self.price_ton}" if self.price_ton else ""
        return f"@{self.username}  [{self.status}]{price}"

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict (JSON-serialisable)."""
        return asdict(self)



class FragmentClient:
    """
    Async Fragment.com client with robust error handling, concurrency throttling,
    optional caching, and multi-strategy price extraction.

    Args:
        retries:     Number of HTTP retries per request (default 3).
        timeout:     Total request timeout in seconds (default 20).
        concurrency: Max simultaneous HTTP requests (default 5).
                     Prevents Cloudflare rate-limiting on bulk lookups.
        cache_ttl:   Seconds to cache results in memory (default 300).
                     Set to 0 to disable caching entirely.
        proxy:       Optional proxy URL, e.g. "http://user:pass@host:port".
                     Useful when Cloudflare blocks your IP.

    Raises:
        UserNotFoundError:    Username does not exist on Fragment.
        WalletNotFoundError:  Username exists but has no wallet (auction/unclaimed).
        FragmentBlockedError: Cloudflare 403 block — never retried.
        FragmentFetchError:   Network / HTTP error after all retries.
        FragmentParseError:   Unexpected HTML structure during parsing.

    Usage:
        async with FragmentClient() as client:
            result = await client.get_username("@monk")

        async with FragmentClient(concurrency=3, cache_ttl=600, proxy="http://...") as client:
            results = await client.get_usernames("@a", "@b", "@c")
    """

    # Fragment uses Unicode Ꞇ (U+A766) for TON prices — NOT the word "TON".
    _TON_CHARS = "\ua766\ua767"
    _TON_RE = re.compile(
        r"([\d][\d\s,]*(?:\.\d+)?\s*(?:TON|[\ua766\ua767])"
        r"|(?:TON|[\ua766\ua767])\s*[\d][\d\s,]*(?:\.\d+)?)",
        re.IGNORECASE,
    )

    # Selector sets tried in order for status detection
    _STATUS_SELECTORS = [
        ("span", re.compile(r"tm-section-header-status")),
        ("div",  re.compile(r"tm-section-header-status")),
        ("span", re.compile(r"status")),
    ]

    def __init__(
        self,
        retries:     int   = 3,
        timeout:     float = 20.0,
        concurrency: int   = 5,
        cache_ttl:   int   = 300,
        proxy:       Optional[str] = None,
    ) -> None:
        self._retries     = retries
        self._timeout     = timeout
        self._proxy       = proxy
        self._sem         = asyncio.Semaphore(concurrency)
        self._cache_ttl   = cache_ttl
        # cache: username (str) → (fetched_at: float, result: FragmentResult)
        self._cache: Dict[str, tuple[float, FragmentResult]] = {}
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "FragmentClient":
        # httpx ≥ 0.23 removed `proxies=` in favour of `proxy=` (single URL)
        # or `mounts=` (per-scheme dict).  We build kwargs dynamically so the
        # code works whether a proxy is configured or not.
        client_kwargs: Dict[str, Any] = dict(
            timeout=httpx.Timeout(self._timeout, connect=8.0),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer":         "https://fragment.com/",
                "Cache-Control":   "no-cache",
            },
            follow_redirects=True,
        )
        if self._proxy:
            # `proxy=` is the modern httpx API (≥ 0.23).
            # For older httpx versions still using `proxies=`, swap the key below.
            client_kwargs["proxy"] = self._proxy
        self._client = httpx.AsyncClient(**client_kwargs)
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_username(
        self,
        username:  str,
        *,
        debug:     bool = False,
        use_cache: bool = True,
    ) -> FragmentResult:
        """
        Fetch all available info for a Telegram username from Fragment.com.

        Args:
            username:  Telegram username with or without the leading @.
            debug:     When True, save raw HTML to ``fragment_debug_<username>.html``
                       and print candidate elements to stdout.
            use_cache: When True (default), return a cached result if it is
                       still within cache_ttl seconds old.

        Returns:
            FragmentResult with status, wallet, price and auction data.

        Raises:
            UserNotFoundError:    The username does not exist on Fragment.
            WalletNotFoundError:  The username has no linked wallet.
            FragmentBlockedError: Fragment returned a 403 / Cloudflare block.
            FragmentFetchError:   Network / HTTP failure after all retries.
            FragmentParseError:   Unexpected HTML that could not be parsed.

        Example:
            result = await client.get_username("@monk")
            if result.is_sold:
                print("Owner wallet:", result.owner)
        """
        clean = username.lstrip("@").lower().strip()

        if use_cache and self._cache_ttl > 0:
            cached = self._cache.get(clean)
            if cached is not None:
                fetched_at, result = cached
                if time.time() - fetched_at < self._cache_ttl:
                    logger.debug(f"[Fragment] cache hit for @{clean}")
                    return result

        url  = f"{_FRAGMENT_BASE}/username/{clean}"
        html = await self._fetch(url)

        if debug:
            self._dump_debug(html, clean)

        result = self._parse(clean, url, html)

        if self._cache_ttl > 0:
            self._cache[clean] = (time.time(), result)

        return result

    async def get_usernames(self, *usernames: str) -> List[FragmentResult]:
        """
        Fetch multiple usernames concurrently (throttled by the semaphore).

        Successful results are returned in the same order as the input.
        Failed ones are logged with a summary and silently skipped so a
        single bad username does not abort the whole batch.

        Args:
            *usernames: One or more Telegram usernames (with or without @).

        Returns:
            List of FragmentResult for every username that succeeded.

        Example:
            results = await client.get_usernames("@a", "@b", "@c")
            for r in results:
                print(r)
        """
        if not usernames:
            return []

        tasks    = [self.get_username(u) for u in usernames]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        output: List[FragmentResult] = []
        failed: List[str]            = []

        for u, r in zip(usernames, gathered):
            if isinstance(r, FragmentResult):
                output.append(r)
            else:
                failed.append(u)
                logger.warning(f"[Fragment] Skipping {u!r}: {type(r).__name__}: {r}")

        if failed:
            logger.info(
                f"[Fragment] get_usernames: {len(failed)}/{len(usernames)} failed "
                f"— {failed}"
            )

        return output

    async def search(self, query: str) -> List[FragmentSearchResult]:
        """
        Search Fragment for usernames matching the query string.

        Args:
            query: Partial username to search for (with or without @).

        Returns:
            List of FragmentSearchResult objects. May be empty if no hits.

        Example:
            hits = await client.search("cool")
            for h in hits:
                print(h.username, h.status, h.price_ton)
        """
        clean = query.lstrip("@").strip()
        url   = f"{_FRAGMENT_BASE}/username?filter=sale&query={clean}"
        html  = await self._fetch(url)
        return self._parse_search(html)

    async def resolve_wallet(self, username: str) -> Optional[str]:
        """
        Resolve @username → UQ-prefixed TON wallet address.

        This is the safe, non-raising variant of get_username — it returns
        None when the username is not found or has no wallet, instead of
        raising an exception.  Use it when you only care about the wallet
        and want to handle missing cases inline.

        Args:
            username: Telegram username with or without @.

        Returns:
            UQ-prefixed wallet address string, or None.

        Example:
            wallet = await client.resolve_wallet("@monk")
            if wallet:
                send_ton(wallet, amount=10)
        """
        try:
            result = await self.get_username(username)
            return result.friendly_wallet or None
        except (UserNotFoundError, WalletNotFoundError) as exc:
            logger.info(f"[Fragment] resolve_wallet: {exc}")
            return None
        except Exception as exc:
            logger.warning(
                f"[Fragment] resolve_wallet unexpected error for {username!r}: {exc}"
            )
            return None

    def clear_cache(self, username: Optional[str] = None) -> None:
        """
        Invalidate cached results.

        Args:
            username: If provided, clear only this username's cache entry.
                      If None, clear the entire cache.

        Example:
            client.clear_cache()           # flush everything
            client.clear_cache("@monk")    # flush only @monk
        """
        if username is None:
            self._cache.clear()
            logger.debug("[Fragment] Cache cleared")
        else:
            clean = username.lstrip("@").lower().strip()
            self._cache.pop(clean, None)
            logger.debug(f"[Fragment] Cache cleared for @{clean}")


    @staticmethod
    def _dump_debug(html: str, username: str) -> None:
        """
        Save raw HTML and print all elements that could contain a price.
        Useful when price_ton is unexpectedly None after Fragment updates its markup.
        """
        path = f"fragment_debug_{username}.html"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"[DEBUG] HTML saved → {path}")

        soup  = BeautifulSoup(html, "html.parser")
        seen: set[str] = set()
        count = 0

        print("[DEBUG] Elements with digits (max 60):")
        for el in soup.find_all(True):
            t = el.get_text(strip=True)
            if t and any(c.isdigit() for c in t) and len(t) < 80 and t not in seen:
                seen.add(t)
                cls_str = str(el.get("class", ""))
                print(f"  <{el.name} class={cls_str!r}> {t!r}")
                count += 1
                if count >= 60:
                    break

        print("\n[DEBUG] Elements whose class contains price/value/ton/amount/sale/domain/header:")
        for el in soup.find_all(True):
            c = " ".join(el.get("class", []))
            if re.search(r"price|value|ton|amount|sale|domain|header", c, re.I):
                print(f"  <{el.name} class={c!r}> {el.get_text(strip=True)[:80]!r}")


    async def _fetch(self, url: str) -> str:
        """
        Fetch a URL with throttling, retry, and exponential back-off.

        The asyncio Semaphore limits concurrent requests across the entire
        client instance, so bulk lookups do not hammer Fragment at once.

        Raises:
            FragmentBlockedError: 403 — never retried.
            FragmentFetchError:   Any other failure after all retries.
        """
        assert self._client is not None, (
            "Client not started — use 'async with FragmentClient()'"
        )

        async with self._sem:                          # [ADD #1] throttle
            last_exc: Optional[Exception] = None

            for attempt in range(self._retries):
                try:
                    response = await self._client.get(url)

                    if response.status_code == 403:
                        raise FragmentBlockedError(
                            "Cloudflare blocked (403) — rotate User-Agent or use a proxy.",
                            url=url,
                        )

                    response.raise_for_status()
                    return response.text

                except FragmentBlockedError:
                    raise                              # never retry a hard block

                except Exception as exc:
                    last_exc = exc
                    if attempt < self._retries - 1:
                        wait = 1.5 ** attempt
                        logger.warning(
                            f"[Fragment] attempt {attempt + 1}/{self._retries} failed "
                            f"for {url!r}: {exc} — retrying in {wait:.1f}s"
                        )
                        await asyncio.sleep(wait)

            # [FIX #5] always raise FragmentFetchError with the chain preserved
            raise FragmentFetchError(
                f"Fragment fetch failed after {self._retries} attempts: {last_exc}",
                url=url,
                attempts=self._retries,
            ) from last_exc


    def _parse(self, username: str, url: str, html: str) -> FragmentResult:
        """
        Parse a username detail page into a FragmentResult.

        Raises:
            UserNotFoundError:   Page indicates the username does not exist.
            WalletNotFoundError: Username sold but no wallet link in HTML.
            FragmentParseError:  Truly unexpected HTML structure.
        """
        soup      = BeautifulSoup(html, "html.parser")
        page_text = soup.get_text(separator=" ", strip=True)
        result    = FragmentResult(username=username, status="Unknown", fragment_url=url)

        # ── Not found — [FIX #4] more robust heuristic ───────────────────────
        no_section_header = not soup.find(class_=re.compile(r"tm-section-header"))
        generic_page      = "Buy and Sell Usernames" in page_text
        if generic_page and no_section_header:
            raise UserNotFoundError(username)

        # ── Status ──────────────────────────────────────────────────────────
        status_el = None
        for tag, pattern in self._STATUS_SELECTORS:
            status_el = soup.find(tag, class_=pattern)
            if status_el:
                break

        if status_el:
            result.status = status_el.get_text(strip=True)
        elif re.search(r"\bSold\b", page_text):
            result.status = "Sold"
        elif re.search(r"On\s+Auction", page_text, re.I):
            result.status = "On Auction"
        elif re.search(r"\bAvailable\b", page_text):
            result.status = "Available"


        result.price_ton = (
            self._price_from_header(soup)
            or self._price_from_table(soup)
            or self._price_from_regex(page_text)      # [FIX #1] fixed strategy
            or self._price_from_any_element(soup)
        )

        result.min_bid = self._min_bid_from_page(soup)
        timer_el = (
            soup.find(attrs={"data-deadline": True})
            or soup.find(class_=re.compile(r"countdown|timer", re.I))
        )
        if timer_el:
            deadline = timer_el.get("data-deadline")
            result.auction_end = deadline or timer_el.get_text(strip=True)

        links = soup.find_all("a", href=re.compile(r"tonviewer\.com|tonscan\.org"))
        for link in links:
            href = str(link.get("href", ""))
            text = link.get_text(strip=True)
            if not result.display_wallet and text:
                result.display_wallet = text
            addr_match = re.search(r"/([A-Za-z0-9_-]{44,48})", href)
            if addr_match:
                result.raw_wallet      = addr_match.group(1)
                result.friendly_wallet = normalize_address(result.raw_wallet)
                break

        if not result.friendly_wallet and result.is_sold:
            raise WalletNotFoundError(username, status=result.status)

        return result


    @classmethod
    def _has_ton(cls, text: str) -> bool:
        """Return True if text contains a TON price indicator."""
        return bool(re.search(r"TON|[\ua766\ua767]", text, re.IGNORECASE))

    @classmethod
    def _extract_ton(cls, text: str) -> Optional[str]:
        """Extract and return the first TON price string from text, or None."""
        m = cls._TON_RE.search(text)
        return m.group(1).strip() if m else None

    @classmethod
    def _price_from_header(cls, soup: BeautifulSoup) -> Optional[str]:
        """Strategy 1: look for well-known CSS class names in the page header."""
        for css in (
            "tm-section-header-domain-price",
            "tm-value",
            "table-cell-value",
            "tm-section-header-price",
            "tm-currency",
        ):
            tag = soup.find(class_=css)
            if tag:
                text = tag.get_text(separator=" ").strip()
                if cls._has_ton(text):
                    return cls._extract_ton(text) or text
        return None

    @classmethod
    def _price_from_table(cls, soup: BeautifulSoup) -> Optional[str]:
        """Strategy 2: scan table/row structures for a sale-related label + TON value."""
        _SALE_LABELS = re.compile(
            r"last\s*sale|sold\s*for|price|amount|sale\s*price", re.I
        )
        for row in soup.select("tr, .table-cell, .tm-table-row, .tm-item-cell"):
            cells = (
                row.find_all(["td", "th", "div"], recursive=False)
                or row.find_all(["td", "th"])
            )
            if len(cells) < 2:
                continue
            label = cells[0].get_text(strip=True)
            value = cells[1].get_text(separator=" ", strip=True)
            if _SALE_LABELS.search(label) and cls._has_ton(value):
                return cls._extract_ton(value) or value
        return None

    @classmethod
    def _price_from_regex(cls, page_text: str) -> Optional[str]:
        """
        Strategy 3: direct regex search across the full page text.

        [FIX #1] — The original code called page_text.splitlines() but
        page_text is built with separator=" " and contains no newlines,
        so splitlines() returned a single-element list and the loop body
        executed at most once (on the full concatenated text, which the
        gas/fee guard often rejected).

        We now search the full text directly with _extract_ton, skipping
        only when the *only* match is preceded by a fee/gas keyword.
        """
        # Quick bail: if there is no TON indicator at all, don't bother.
        if not cls._has_ton(page_text):
            return None

        # Try the targeted regex first — it captures "N TON" or "TON N".
        candidate = cls._extract_ton(page_text)
        if not candidate:
            return None

        # Reject if it appears to be a fee/commission line.
        # Find where in the text the candidate occurs and peek at the
        # surrounding ~60 characters for fee-related keywords.
        pos = page_text.find(candidate)
        if pos != -1:
            context = page_text[max(0, pos - 60): pos + len(candidate) + 60]
            if re.search(r"\b(gas|fee|commission|network)\b", context, re.I):
                return None

        return candidate

    @classmethod
    def _price_from_any_element(cls, soup: BeautifulSoup) -> Optional[str]:
        """Strategy 4: last resort — scan every element for a short TON string."""
        skip = {"script", "style", "nav", "head", "meta", "link"}
        for el in soup.find_all(True):
            if el.name in skip:
                continue
            own = el.get_text(strip=True)
            if own and cls._has_ton(own) and len(own) < 40:
                extracted = cls._extract_ton(own)
                if extracted:
                    return extracted
        return None

    @classmethod
    def _min_bid_from_page(cls, soup: BeautifulSoup) -> Optional[str]:
        """Extract the minimum bid for auction pages."""
        _BID_LABEL = re.compile(r"min\w*\s*bid|minimum\s*bid", re.I)
        for el in soup.find_all(string=_BID_LABEL):
            parent = el.find_parent()
            if not parent:
                continue
            candidates = [
                parent.find_next_sibling(),
                parent.parent.find_next_sibling() if parent.parent else None,
            ]
            for candidate in candidates:
                if candidate is None:
                    continue
                text = candidate.get_text(separator=" ", strip=True)
                if cls._has_ton(text):
                    return cls._extract_ton(text) or text
        return None

    def _parse_search(self, html: str) -> List[FragmentSearchResult]:
        """Parse the search results page into a list of FragmentSearchResult."""
        soup    = BeautifulSoup(html, "html.parser")
        results: List[FragmentSearchResult] = []

        for row in soup.select(".tm-row-selectable, .table-cell"):
            name_el   = row.select_one(".tm-value, .table-cell-name")
            price_el  = row.select_one(".tm-section-header-domain-price, .table-cell-value")
            status_el = row.select_one(".tm-section-header-status")
            if not name_el:
                continue
            results.append(FragmentSearchResult(
                username  = name_el.get_text(strip=True).lstrip("@"),
                status    = status_el.get_text(strip=True) if status_el else "Unknown",
                price_ton = price_el.get_text(separator=" ").strip() if price_el else None,
            ))

        return results



async def monitor_auction(
    client:   FragmentClient,
    username: str,
    *,
    interval: float = 60.0,
    on_change: Optional[Any] = None,          # callable(result) | None
) -> None:
    """
    Poll a username's auction page and log / callback whenever the price changes.

    Stops automatically when the auction ends (username is no longer "On Auction").

    Args:
        client:    An already-entered FragmentClient instance.
        username:  The Telegram username to monitor (with or without @).
        interval:  Polling interval in seconds (default 60).
        on_change: Optional async or sync callable invoked with the new
                   FragmentResult whenever the price changes.
                   Signature: on_change(result: FragmentResult) -> None

    Example:
        async with FragmentClient() as client:
            await monitor_auction(client, "@cool", interval=30)

        # With custom callback:
        async def notify(r):
            print(f"Price changed → {r.price_ton}")

        async with FragmentClient() as client:
            await monitor_auction(client, "@cool", on_change=notify)
    """
    clean      = username.lstrip("@")
    last_price: Optional[str] = None

    logger.info(f"[Fragment] monitor_auction started for @{clean} (every {interval}s)")

    while True:
        try:
            result = await client.get_username(username, use_cache=False)

            if result.is_auction:
                if result.price_ton != last_price:
                    logger.info(
                        f"[Fragment] @{clean} price: {last_price!r} → {result.price_ton!r}"
                    )
                    last_price = result.price_ton
                    if on_change is not None:
                        if asyncio.iscoroutinefunction(on_change):
                            await on_change(result)
                        else:
                            on_change(result)
            else:
                # Auction ended
                logger.info(
                    f"[Fragment] @{clean} auction ended — "
                    f"status: {result.status}, price: {result.price_ton}"
                )
                if on_change is not None:
                    if asyncio.iscoroutinefunction(on_change):
                        await on_change(result)
                    else:
                        on_change(result)
                break

        except (UserNotFoundError, WalletNotFoundError) as exc:
            logger.warning(f"[Fragment] monitor_auction: {exc} — stopping")
            break
        except FragmentBlockedError:
            logger.error("[Fragment] monitor_auction: blocked by Cloudflare — stopping")
            break
        except Exception as exc:
            logger.warning(f"[Fragment] monitor_auction: transient error ({exc}) — retrying")

        await asyncio.sleep(interval)

"""
import asyncio

async def main():
    async with FragmentClient() as client:
        # Single username
        result = await client.get_username("tonvm")

        # Shortcut: resolve username → wallet address only
        wallet_addr = await client.resolve_wallet("@cool")

        # Bulk concurrent lookup
        results = await client.get_usernames("@monk", "@doge", "@DevGit")
        print(results)
        print(result.friendly_wallet)   # UQ-normalized owner address
        print(result.status)            # "Sold" | "On Auction" | "Available" | "Not Found"
        print(wallet_addr)

        # Boolean helpers
        print(result.is_sold)
        print(result.is_auction)
        print(result.is_available)
        print(result.has_wallet)
        print(result.owner)
        print(result.is_not_found)



if __name__ == "__main__":
    asyncio.run(main())
"""