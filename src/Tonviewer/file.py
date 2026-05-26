from .INFO.wallet import IN
from .Hash.main import EventResolver
from .Transaction.main import Transactions
from .INFO.nft import NFTClient
from .INFO.fragment import FragmentClient
from .dollers import Dollers
from typing import Optional


class Wallet:
    def __init__(self, wallet: Optional[str]):
        self.wallet = wallet

    def transactions(self, limit: Optional[int] = 1):
        tr = Transactions(self.wallet)
        return tr.get(limit=limit)

    def action(self, action: str, limit: int = 1):
        _f = Transactions(self.wallet)
        return _f.Action(action=action, limit=limit)

    def info(self):
        inf = IN(wallet=self.wallet)
        return inf.balance()


class HashTx:
    def __init__(self, hashtx: Optional[str]):
        self.hashtx = hashtx

    def get(self):
        h = EventResolver(event_address=self.hashtx)
        return h.result()