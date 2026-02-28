from .INFO.wallet import IN
from .Hash.main import EventResolver
from .Transaction.main import Transactions
from typing import Optional
from .main import check_for_update

class Wallet:
    def __init__(self, wallet: Optional[str]) -> None:
        self.wallet = wallet

    def transactions(self, limit: Optional[int]):
        tr = Transactions(self.wallet)
        print(tr.get(limit=limit))
        check_for_update("tonviewer")

    def info(self):
        inf = IN(wallet=self.wallet)
        print(inf.balance())
        check_for_update("tonviewer")


class HashTx:
    def __init__(self, hashtx: Optional[str]) -> None:
        self.hashtx = hashtx

    def get(self):
        h = EventResolver(event_address=self.hashtx)
        print(h.result())
        check_for_update("tonviewer")