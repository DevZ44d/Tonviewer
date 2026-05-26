import httpx
import asyncio
from bs4 import BeautifulSoup
import json
import re
from typing import Dict, Optional
from tonsdk.utils import Address
from datetime import datetime

def _to_uq(addr: str) -> Optional[str]:
    if not addr:
        return None
    try:
        a = Address(addr)
        return a.to_string(is_user_friendly=True, is_url_safe=True,
                           is_bounceable=False, is_test_only=False)
    except Exception:
        return addr


def _name_or_addr(info: Dict) -> Optional[str]:
    if not info:
        return None
    name = info.get("name", "")
    return name if name else _to_uq(info.get("address", ""))


def _extract_number(text: str) -> Optional[float]:
    clean = re.sub(r"[^\d.]", "", text.replace(",", ".").replace(" ", ""))
    try:
        return float(clean)
    except ValueError:
        return None


class Fragment:
    BASE_URL = "https://fragment.com"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://fragment.com/",
        "DNT": "1",
    }

    def __init__(self, user: str, timeout: float = 30.0, retries: int = 3):
        self.username = user.lstrip("@").lower().strip()
        self.url      = f"{self.BASE_URL}/username/{self.username}"
        self.timeout  = timeout
        self.retries  = retries
        self._client: Optional[httpx.AsyncClient] = None


    async def __aenter__(self) -> "Fragment":
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers=self._HEADERS,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _fetch(self) -> str:
        client = self._client
        if client is None:
            raise RuntimeError(
                "Fragment must be used as an async context manager: "
                "`async with Fragment(user=...) as f:`"
            )

        last_exc: Exception = RuntimeError("No attempts made")
        for attempt in range(1, self.retries + 1):
            try:
                resp = await client.get(self.url)
                if resp.status_code == 403:
                    raise PermissionError("Access denied — Cloudflare or IP block.")
                if resp.status_code == 404:
                    raise LookupError("Page not found (404).")
                if resp.status_code != 200:
                    raise ConnectionError(f"Unexpected HTTP status: {resp.status_code}")
                return resp.text
            except (PermissionError, LookupError):
                raise
            except Exception as e:
                last_exc = e
                if attempt < self.retries:
                    await asyncio.sleep(2 ** attempt)   # exponential back-off

        raise last_exc

    def _parse_status(self, soup: BeautifulSoup) -> str:
        tag = soup.find("span", class_=re.compile(r"tm-section-header-status"))
        if tag:
            return tag.get_text(strip=True)
        for word in ("Sold", "Available", "Taken", "On Sale", "Auction"):
            if word.lower() in soup.text.lower():
                return word
        return "Unknown"

    def _parse_price(self, soup: BeautifulSoup) -> Optional[str]:
        for cls in ("tm-section-header-domain-price", "tm-value", "table-cell-value"):
            tag = soup.find("div", class_=cls) or soup.find("span", class_=cls)
            if tag:
                return tag.get_text(separator=" ").strip()
        return None

    def _parse_wallet(self, soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
        links = soup.find_all("a", href=re.compile(r"tonviewer\.com|tonscan\.org"))
        for link in links:
            href    = str(link.get("href", ""))
            display = link.get_text(strip=True) or None
            m = re.search(
                r"/([EUeu][Qq][a-zA-Z0-9_-]{46}|[a-zA-Z0-9_-]{44,48})", href
            )
            if m:
                uq = _to_uq(m.group(1))
                return display or uq, uq
        return None, None

    def _parse_auction_info(self, soup: BeautifulSoup) -> Dict:
        info: Dict = {}
        bid_tag = soup.find(string=re.compile(r"\d+\s+bid", re.I))
        if bid_tag:
            m = re.search(r"(\d+)", bid_tag)
            if m:
                info["bids"] = int(m.group(1))
        timer = soup.find(attrs={"data-deadline": True})
        if timer:
            try:
                ts = int(timer["data-deadline"])
                info["auction_ends"] = datetime.utcfromtimestamp(ts).strftime(
                    "%Y-%m-%d %H:%M UTC"
                )
            except (ValueError, TypeError):
                pass
        min_bid = soup.find("div", class_=re.compile(r"min.?bid|next.?bid", re.I))
        if min_bid:
            info["min_bid"] = min_bid.get_text(separator=" ").strip()
        return info

    def _parse_owner_info(self, soup: BeautifulSoup) -> Dict:
        info: Dict = {}
        col = soup.find(
            "div", class_=re.compile(r"nft.?collection|username.?collection", re.I)
        )
        if col:
            info["collection"] = col.get_text(strip=True)
        since = soup.find(string=re.compile(r"since|owned|last.?sale", re.I))
        if since:
            info["note"] = since.strip()
        return info

    def _parse_purchased_at(self, soup: BeautifulSoup) -> Optional[str]:
        time_tag = soup.find("time")
        raw = time_tag.get_text(strip=True) if time_tag else None
        if not raw:
            m = re.search(
                r"(Purchased|Sold|Last sale)[^\d]*(\d{1,2}\s+\w+\s+\d{4})\s+at\s+(\d{2}:\d{2})",
                soup.get_text(" ", strip=True),
                re.I,
            )
            if m:
                raw = f"{m.group(2)} at {m.group(3)}"
        if not raw:
            return None

        def to_12h(match):
            h, mn = int(match.group(1)), match.group(2)
            return f"{h % 12 or 12}:{mn} {'AM' if h < 12 else 'PM'}"

        return re.sub(r"\b(\d{2}):(\d{2})\b", to_12h, raw)


    async def get_info(self) -> dict[str, str] | dict[str, str] | dict[str, str] | dict[str, str] | dict[
        str, str] | str:
        try:
            html = await self._fetch()
        except PermissionError as e:
            return {"error": str(e)}
        except LookupError:
            return {"error": "User not found in fragment (Taken)"}
        except ConnectionError as e:
            return {"error": str(e)}
        except RuntimeError:
            raise
        except Exception as e:
            return {"error": f"Unexpected error: {e}"}

        soup = BeautifulSoup(html, "html.parser")

        page_text = soup.get_text(" ", strip=True)
        is_not_found = (
            "Buy and Sell Usernames" in page_text
            and not soup.find("span", class_=re.compile(r"tm-section-header-status"))
            and not soup.find("div",  class_=re.compile(r"tm-section-header"))
        )
        if is_not_found:
            return {"error": "User not found in fragment (Taken)"}

        status                    = self._parse_status(soup)
        price_raw                 = self._parse_price(soup)
        display_wallet, uq_wallet = self._parse_wallet(soup)
        auction_info              = self._parse_auction_info(soup)
        owner_info                = self._parse_owner_info(soup)
        price_value               = _extract_number(price_raw) if price_raw else None

        result: Dict = {
            "username":     f"@{self.username}",
            "fragment_url": self.url,
            "status":       status,
            "price": {
                "display":  price_raw,
                "value":    price_value,
                "currency": "TON" if price_raw else None,
            } if price_raw else None,
            "owner": {
                "ton_wallet": uq_wallet,
                "display":    display_wallet,
                "tonviewer":  f"https://tonviewer.com/{uq_wallet}" if uq_wallet else None,
            },
        }

        if auction_info:
            result["auction"] = auction_info
        if owner_info:
            result["metadata"] = owner_info

        purchased_at = self._parse_purchased_at(soup)
        if purchased_at:
            result["purchased_at"] = purchased_at

        return result

"""
async def main():
    async with Fragment(user="ccccce") as client:
        result = await client.get_info()
        print(json.dumps(result, indent=2, ensure_ascii=False))

async def bulk_check(usernames: list[str]):
    async def fetch(user):
        async with Fragment(user=user) as client:
            return await client.get_info()

    results = await asyncio.gather(*[fetch(u) for u in usernames])
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(bulk_check(["monk", "doge", "cool", "ton", "hello", "ddddi", "DevGit"]))
    #asyncio.run(main())
"""