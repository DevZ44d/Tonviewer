import requests
import datetime
import json
from typing import List, Dict, Any
from tonsdk.utils import Address
from ..dollers import Dollers


class Transactions:
    """
    Fetch and format TON wallet transactions using TONAPI events.
    """

    TON_DECIMALS = 1_000_000_000
    def __init__(self, wallet: str):
        self.wallet = wallet
        self.base_url = "https://tonapi.io/v2"
        self._dollar_rate = Dollers()._TON_USDT()


    @staticmethod
    def raw_to_UQ(raw: str) -> str:
        try:
            addr = Address(raw)
            return addr.to_string(
                is_user_friendly=True,
                is_url_safe=True,
                is_bounceable=False,
                is_test_only=False
            )
        except Exception:
            return raw


    @staticmethod
    def format_time(timestamp: int) -> str:
        return datetime.datetime.fromtimestamp(
            timestamp
        ).strftime("%d %b %I:%M %p")

    @staticmethod
    def clean_comment(comment: str) -> str:
        if not comment:
            return ""

        if "Ref#" in comment:
            comment = comment.split("Ref#")[0]

        return comment.strip()

    def get(self, limit: int = 1) -> str:

        url = f"{self.base_url}/accounts/{self.wallet}/events?limit={limit}"

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            results: List[Dict[str, Any]] = []
            counter = 1

            for event in data.get("events", []):

                actions = event.get("actions", [])


                ton_transfers = [
                    a for a in actions
                    if a.get("type") == "TonTransfer"
                ]

                if not ton_transfers:
                    continue

                event_time = self.format_time(event["timestamp"])

                for action in ton_transfers:

                    transfer = action["TonTransfer"]

                    amount = int(transfer["amount"]) / self.TON_DECIMALS
                    usd_value = amount * self._dollar_rate

                    sender = self.raw_to_UQ(
                        transfer["sender"]["address"]
                    )
                    recipient = self.raw_to_UQ(
                        transfer["recipient"]["address"]
                    )

                    action_type = (
                        "Received TON"
                        if recipient == self.wallet
                        else "Sent TON"
                    )

                    comment = self.clean_comment(
                        transfer.get("comment", "")
                    )

                    tx: Dict[str, Any] = {
                        "Time": event_time,
                        "Action": action_type,
                        "From": sender,
                        "To": recipient,
                        "Paid For": comment if comment else None,
                        "Price": (
                            f"{'-' if action_type=='Sent TON' else '+'}"
                            f"{amount:.3f} TON ≈ {usd_value:.5f} $"
                        ),
                        "Limit": str(counter)
                    }
                    counter += 1

                    results.append(tx)



            cleaned = [
                {k: v for k, v in tx.items() if v is not None}
                for tx in results
            ]

            skipped = limit - (counter - 1)

            output = {
                "transactions": cleaned,
                "skipped": f"Skipped {skipped} NFT Transactions"
            }

            return json.dumps(output, indent=2, ensure_ascii=False)



        except requests.RequestException:
            return json.dumps(
                {"error": "Failed to fetch transactions"},
                indent=2
            )


