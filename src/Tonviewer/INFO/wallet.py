import requests
import json
import datetime
from typing import Dict, Any, Optional
from ..dollers import Dollers


class IN:
    """
    A professional wrapper for fetching TON wallet information and balances in USD.

    Attributes:
        wallet (str): INFO address.
    """

    TON_DECIMALS: int = 1_000_000_000

    def __init__(self, *, wallet: str) -> None:
        self.wallet: str = wallet
        self.url: str = f"https://tonapi.io/v2/wallet/{self.wallet}"
        self._dollar_rate: float = Dollers()._TON_USDT()
        self._cached_data: Optional[Dict[str, Any]] = None

    def _fetch_balance(self) -> Optional[Dict[str, Any]]:
        """Fetch wallet data from the API and cache it to reduce repeated requests."""
        if self._cached_data:
            return self._cached_data

        try:
            response = requests.get(self.url)
            response.raise_for_status()
            data = response.json()

            self._cached_data = {
                "name" : data.get("name", ""),
                "balance": data.get("balance", "0"),
                "status": data.get("status", "unknown"),
                "is_wallet": data.get("is_wallet", False),
                "icon": data.get("icon"),
                "nfts_count": data.get("stats", {}).get("nfts_count", 0),
                "last_activity": datetime.datetime.fromtimestamp(
                    data.get("last_activity", 0)
                ).strftime("%Y-%m-%d %I:%M:%S %p")
            }
            return self._cached_data
        except requests.RequestException as e:
            return {"error": """This doesn't look like a valid address. Where'd you get that?"""}

    def _get_ton_balance(self) -> float:
        """Convert raw balance to TON."""
        try:
            raw_balance = float(self._fetch_balance().get("balance", 0))
            return raw_balance / self.TON_DECIMALS
        except Exception:
            return 0.0

    def balance(self) -> str:
        """Return a formatted JSON string with TON balance, USD equivalent, and wallet info."""
        wallet_data = self._fetch_balance()
        if "error" in wallet_data:
            return json.dumps(wallet_data, indent=2, ensure_ascii=False)

        ton_balance = self._get_ton_balance()
        dollar_balance = ton_balance * self._dollar_rate

        info: Dict[str, Any] = {
            #"Name": wallet_data.get("name"),
            "Balance": f"{ton_balance:.8f} TON ≈ ${dollar_balance:.3f}",
            "Status": wallet_data.get("status"),
            "Is INFO": wallet_data.get("is_wallet"),
            "Last Activity": wallet_data.get("last_activity"),
            "NFT Count" : wallet_data.get("nfts_count")
        }

        if wallet_data.get("name"):
            info["Name"] = wallet_data.get("name")

        if wallet_data.get("icon"):
            info["Icon"] = wallet_data.get("icon")

        return json.dumps(info, indent=2, ensure_ascii=False)


