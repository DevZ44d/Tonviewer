import requests
import json
import datetime
from typing import Dict, Any, Optional, List
from tonsdk.utils import Address
from ..dollers import Dollers


class EventResolver:
    TON_DECIMALS = 1_000_000_000

    def __init__(self, *, event_address: str):
        self.event_address = event_address
        self.event_url = f"https://tonapi.io/v2/events/{event_address}"
        self._cached_event: Optional[Dict[str, Any]] = None
        self._doller = Dollers()._TON_USDT()


    def _fetch_event(self) -> Dict[str, Any]:
        if self._cached_event:
            return self._cached_event

        r = requests.get(self.event_url, timeout=10)
        r.raise_for_status()

        self._cached_event = r.json()
        return self._cached_event

    @staticmethod
    def normalize(addr: str, name: Optional[str] = None) -> str:
        if name:
            return name
        try:
            return Address(addr).to_string(
                is_user_friendly=True,
                is_url_safe=True,
                is_bounceable=False,
                is_test_only=False
            )
        except Exception:
            return addr


    @staticmethod
    def format_time(timestamp: int) -> str:
        return datetime.datetime.fromtimestamp(
            timestamp
        ).strftime("%Y-%m-%d %I:%M:%S %p")


    def _parse_ton_transfer(
        self,
        action: Dict[str, Any],
        timestamp: int
    ) -> Dict[str, Any]:

        transfer = action["TonTransfer"]
        accounts = action["simple_preview"]["accounts"]

        amount = int(transfer.get("amount", 0)) / self.TON_DECIMALS
        usd = amount * self._doller

        comment = transfer.get("comment", "")
        paid_for = comment.split("\n")[0].strip() if comment else ""

        return {
            "Time": self.format_time(timestamp),
            "Action": "SUCCESSFUL TON TRANSFER",
            "From": self.normalize(
                accounts[0]["address"],
                accounts[0].get("name")
            ),
            "To": self.normalize(
                accounts[1]["address"],
                accounts[1].get("name")
            ),
            "Paid For": paid_for if paid_for else None,
            "Price": f"−{amount:.3f} TON ≈ {usd:.5f} $",
            "Status": "SUCCESS"
        }

    def _parse_failed_nft_transfer(
            self,
            action: Dict[str, Any],
            timestamp: int
    ) -> Dict[str, Any]:

        preview = action.get("simple_preview", {})
        accounts = preview.get("accounts", [])

        recipient = accounts[0] if len(accounts) > 0 else {}
        sender = accounts[1] if len(accounts) > 1 else {}

        nft_id = action.get("NftItemTransfer", {}).get("nft")

        return {
            "Time": self.format_time(timestamp),
            "Action": "FAILED NFT TRANSFER",
            "From": self.normalize(
                sender.get("address", ""),
                sender.get("name")
            ),
            "To": self.normalize(
                recipient.get("address", ""),
                recipient.get("name")
            ),
            "NFT_ID": nft_id,
            "Value": preview.get("value", "1 NFT"),
            "Status": "FAILED"
        }

    def _parse_nft_transfer(
        self,
        action: Dict[str, Any],
        timestamp: int
    ) -> Dict[str, Any]:

        transfer = action["NftItemTransfer"]
        preview = action.get("simple_preview", {})
        accounts = preview.get("accounts", [])

        sender = accounts[1]
        recipient = accounts[0]

        result = {
            "Time": self.format_time(timestamp),
            "Action": "NFT TRANSFER",
            "From": self.normalize(
                sender["address"],
                sender.get("name")
            ),
            "To": self.normalize(
                recipient["address"],
                recipient.get("name")
            ),
            "NFT_ID": transfer.get("nft"),
            "Value": preview.get("value", "1 NFT"),
            "Status": "SUCCESS"
        }

        comment = transfer.get("comment")
        if comment:
            result["Comment"] = comment

        return result


    def _parse_failed_action(
        self,
        action: Dict[str, Any],
        timestamp: int
    ) -> Dict[str, Any]:

        preview = action.get("simple_preview", {})
        accounts = preview.get("accounts", [])

        bidder = accounts[0] if len(accounts) > 0 else {}
        target = accounts[1] if len(accounts) > 1 else {}

        amount_raw = (
            action.get("AuctionBid", {})
            .get("amount", {})
            .get("value", 0)
        )

        amount = int(amount_raw) / self.TON_DECIMALS
        usd = amount * self._doller

        return {
            "Time": self.format_time(timestamp),
            "Action": "FAILED AUCTION BID",
            "From": self.normalize(
                bidder.get("address", ""),
                bidder.get("name")
            ),
            "To": self.normalize(
                target.get("address", ""),
                target.get("name")
            ),
            "Price": f"{amount:.3f} TON ≈ {usd:.5f} $",
            "Status": "FAILED"
        }


    def _parse_generic_action(
            self,
            action: Dict[str, Any],
            timestamp: int
    ) -> Dict[str, Any]:

        preview = action.get("simple_preview", {})
        accounts = preview.get("accounts", [])

        sender = accounts[0] if len(accounts) > 0 else {}
        receiver = accounts[1] if len(accounts) > 1 else {}

        action_type = action.get("type", "UNKNOWN").upper()
        status = action.get("status", "ok").upper()

        return {
            "Time": self.format_time(timestamp),
            "Action": f"{status} {action_type.replace('_', ' ')}",
            "From": self.normalize(
                sender.get("address", ""),
                sender.get("name")
            ),
            "To": self.normalize(
                receiver.get("address", ""),
                receiver.get("name")
            ),
            "Status": "SUCCESS" if status == "OK" else "FAILED"
        }

    def extract_info(self) -> Dict[str, Any]:
        try:
            data = self._fetch_event()
            timestamp = data.get("timestamp", 0)

            actions = data.get("actions", [])
            if not actions:
                return {"Error": "No actions found"}

            results: List[Dict[str, Any]] = []

            for action in actions:

                status = action.get("status", "ok")

                if "NftItemTransfer" in action:

                    if status == "failed":
                        results.append(
                            self._parse_failed_nft_transfer(
                                action, timestamp
                            )
                        )
                    else:
                        results.append(
                            self._parse_nft_transfer(
                                action, timestamp
                            )
                        )
                    continue

                if "TonTransfer" in action:

                    if status == "failed":
                        results.append(
                            self._parse_generic_action(
                                action, timestamp
                            )
                        )
                    else:
                        results.append(
                            self._parse_ton_transfer(
                                action, timestamp
                            )
                        )
                    continue

                if status == "failed":
                    results.append(
                        self._parse_failed_action(
                            action, timestamp
                        )
                    )
                    continue

                results.append(
                    self._parse_generic_action(
                        action, timestamp
                    )
                )

            cleaned = [
                {k: v for k, v in r.items() if v is not None}
                for r in results
            ]

            return {"actions": cleaned}

        except requests.HTTPError:
            return {
                "Error":
                    "This doesn't look like a valid transaction address. Where'd you get that?"
            }

        except Exception as e:
            return {"Error": f"Parsing error: {e}"}

    def result(self) -> str:
        return json.dumps(
            self.extract_info(),
            indent=2,
            ensure_ascii=False
        )

