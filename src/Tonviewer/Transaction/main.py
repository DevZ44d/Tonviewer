import requests
import datetime
import json
import time
from typing import List, Dict, Any, Optional, Iterator
from tonsdk.utils import Address
from ..dollers import Dollers


class Transactions:
    """
    Fetch and filter TON wallet transactions via TonAPI v2 events endpoint.

    Supported action types:
        Sent TON          — TonTransfer (outgoing)
        Received TON      — TonTransfer (incoming)
        NFT Transfer      — NftItemTransfer
        NFT Mint          — NftMint
        NFT Purchase      — NftPurchase
        Transfer Token    — JettonTransfer
        Token Mint        — JettonMint
        Token Burn        — JettonBurn
        Gas Relay         — SmartContractExec / AuctionBid / ContractDeploy
                            JettonSwap / DomainRenew / Staking variants

    Features:
        • Retry logic with exponential back-off (3 attempts)
        • requests.Session for connection reuse
        • Auto-pagination via before_lt cursor
        • Full fee breakdown per action
        • USD equivalent on every TON amount
        • Scam / spam flag surfaced from TonAPI
        • NFT full address + collection name + image URL
        • Jetton symbol, decimals, human-readable amount
        • Auction bid amount + item name
        • Smart contract op-code + TON attached
        • Contract deploy interfaces list
        • Jetton swap in/out summary
        • Domain renew domain name
        • All staking variants with amount
    """

    TON_DECIMALS = 1_000_000_000
    _MAX_PAGE    = 100          # TonAPI hard limit per request
    _RETRIES     = 3
    _BACKOFF     = 1.5          # seconds multiplied on each retry attempt

    _RELAY_TYPES: frozenset = frozenset({
        "AuctionBid", "SmartContractExec", "ContractDeploy",
        "Subscribe", "UnSubscribe",
        "DepositStake", "WithdrawStake", "WithdrawStakeRequest",
        "ElectionsDepositStake", "ElectionsRecoverStake",
        "JettonSwap", "DomainRenew",
    })

    _STAKE_TYPES: frozenset = frozenset({
        "DepositStake", "WithdrawStake", "WithdrawStakeRequest",
        "ElectionsDepositStake", "ElectionsRecoverStake",
    })


    _ACTION_MAP: Dict[str, str] = {
        "send":                 "Sent TON",
        "sent":                 "Sent TON",
        "send ton":             "Sent TON",
        "sent ton":             "Sent TON",
        "receive":              "Received TON",
        "received":             "Received TON",
        "receive ton":          "Received TON",
        "received ton":         "Received TON",
        "nft":                  "NFT Transfer",
        "nft transfer":         "NFT Transfer",
        "nft mint":             "NFT Mint",
        "nft purchase":         "NFT Purchase",
        "transfer token":       "Transfer Token",
        "jetton":               "Transfer Token",
        "token":                "Transfer Token",
        "token mint":           "Token Mint",
        "jetton mint":          "Token Mint",
        "token burn":           "Token Burn",
        "jetton burn":          "Token Burn",
        "gas relay":            "Gas Relay",
        "gas":                  "Gas Relay",
        "relay":                "Gas Relay",
        "swap":                 "Gas Relay",
        "jetton swap":          "Gas Relay",
        "auction":              "Gas Relay",
        "auction bid":          "Gas Relay",
        "deploy":               "Gas Relay",
        "contract deploy":      "Gas Relay",
        "smart contract":       "Gas Relay",
        "stake":                "Gas Relay",
        "deposit stake":        "Gas Relay",
        "withdraw stake":       "Gas Relay",
        "domain":               "Gas Relay",
        "domain renew":         "Gas Relay",
        "subscribe":            "Gas Relay",
        "unsubscribe":          "Gas Relay",
    }

    def __init__(self, wallet: str) -> None:
        self.wallet       = wallet
        self.base_url     = "https://tonapi.io/v2"
        self._dollar_rate = Dollers()._TON_USDT()
        self._session     = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

        # Normalise wallet to raw form (0:hex) for direction detection
        try:
            _w = Address(self.wallet)
            self._wallet_raw = f"0:{_w.hash_part.hex()}"
        except Exception:
            self._wallet_raw = self.wallet.lower()


    @staticmethod
    def _to_uq(addr: str) -> str:
        """Convert any TON address to user-friendly UQ-prefixed form."""
        try:
            return Address(addr).to_string(
                is_user_friendly=True,
                is_url_safe=True,
                is_bounceable=False,
                is_test_only=False,
            )
        except Exception:
            return addr

    @classmethod
    def _name_or_addr(cls, info: Dict) -> str:
        """Return display name if TonAPI provided one, otherwise UQ address."""
        if not info:
            return ""
        name = info.get("name") or ""
        addr = info.get("address") or ""
        return name if name else (cls._to_uq(addr) if addr else "")


    @staticmethod
    def _fmt_time(ts: int) -> str:
        return datetime.datetime.fromtimestamp(ts).strftime("%d %b %I:%M:%S %p")

    @staticmethod
    def _clean_comment(comment: str) -> str:
        if not comment:
            return ""
        if "Ref#" in comment:
            comment = comment.split("Ref#")[0]
        return comment.strip()

    def _ton(self, nano: int) -> float:
        return nano / self.TON_DECIMALS

    def _usd(self, ton: float) -> float:
        return round(ton * self._dollar_rate, 5)

    def _price_str(self, nano: int, sign: str = "") -> str:
        """Format nanoton amount as 'sign0.123 TON ≈ 0.45678 $'."""
        ton = self._ton(nano)
        usd = self._usd(ton)
        return f"{sign}{ton:.3f} TON ≈ {usd:.5f} $"

    def _token_str(self, raw_amount: int, decimals: int, symbol: str) -> str:
        return f"{raw_amount / (10 ** decimals):.6f} {symbol}"


    def _get(self, url: str, params: Optional[Dict] = None) -> Dict:
        last_exc: Exception = RuntimeError("No attempts made")
        for attempt in range(self._RETRIES):
            try:
                r = self._session.get(url, params=params, timeout=15)
                r.raise_for_status()
                return r.json()
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < self._RETRIES - 1:
                    time.sleep(self._BACKOFF * (attempt + 1))
        raise last_exc


    def _parse_nft_purchase(self, a: Dict, ts: int) -> Dict:
        p       = a.get("NftPurchase") or {}
        nft_obj = p.get("nft") or {}
        if isinstance(nft_obj, str): nft_obj = {}
        meta    = nft_obj.get("metadata") or {}
        nano    = int(p.get("amount") or 0)
        rec: Dict[str, Any] = {
            "Action": "NFT Purchase",
            "Time":   self._fmt_time(ts),
            "From":   self._name_or_addr(p.get("seller") or {}),
            "To":     self._name_or_addr(p.get("buyer") or {}),
            "Price":  self._price_str(nano),
            "State":  "Success",
        }
        nft_name = meta.get("name") or ""
        nft_addr = nft_obj.get("address") or ""
        if nft_name: rec["NFT"]         = nft_name
        if nft_addr: rec["NFT Address"] = self._to_uq(nft_addr)
        return rec

    def _parse_nft_mint(self, a: Dict, ts: int) -> Dict:
        mint    = a.get("NftMint") or {}
        nft_obj = mint.get("nft") or {}
        if isinstance(nft_obj, str): nft_obj = {}
        meta    = nft_obj.get("metadata") or {}
        rec: Dict[str, Any] = {
            "Action": "NFT Mint",
            "Time":   self._fmt_time(ts),
            "From":   self._name_or_addr(mint.get("minter") or {}),
            "State":  "Success",
        }
        nft_name = meta.get("name") or ""
        nft_addr = nft_obj.get("address") or ""
        if nft_name: rec["NFT"]         = nft_name
        if nft_addr: rec["NFT Address"] = self._to_uq(nft_addr)
        return rec

    def _parse_nft_transfer(self, a: Dict, actions: List, ts: int) -> Dict:
        nft    = a.get("NftItemTransfer") or {}
        sender = nft.get("sender") or {}
        recip  = nft.get("recipient") or {}

        nft_obj = nft.get("nft") or {}
        if isinstance(nft_obj, str): nft_obj = {}
        meta       = nft_obj.get("metadata") or {}
        collection = nft_obj.get("collection") or {}
        previews   = nft_obj.get("previews") or []

        nft_name   = meta.get("name") or collection.get("name") or ""
        nft_addr   = nft_obj.get("address") or ""
        coll_name  = collection.get("name") or ""
        image      = (
            meta.get("image")
            or meta.get("image_url")
            or (previews[-1].get("url") if previews else None)
        )
        comment    = self._clean_comment(nft.get("comment", ""))

        fee_nano = sum(
            int(a2.get("TonTransfer", {}).get("amount", 0))
            for a2 in actions if a2.get("type") == "TonTransfer"
        )

        rec: Dict[str, Any] = {
            "Action": "NFT Transfer",
            "Time":   self._fmt_time(ts),
            "From":   self._name_or_addr(sender),
            "To":     self._name_or_addr(recip),
            "State":  "Success",
        }
        if nft_name:  rec["NFT"]         = nft_name
        if nft_addr:  rec["NFT Address"] = self._to_uq(nft_addr)
        if coll_name: rec["Collection"]  = coll_name
        if image:     rec["Image"]       = image
        if fee_nano:  rec["Fee"]         = self._price_str(fee_nano, "-")
        if comment:   rec["Comment"]     = comment
        return rec

    def _parse_jetton_transfer(self, a: Dict, actions: List, ts: int) -> Dict:
        jet    = a.get("JettonTransfer") or {}
        sender = jet.get("sender") or {}
        recip  = jet.get("recipient") or {}

        jetton_info = jet.get("jetton") or {}
        if isinstance(jetton_info, str): jetton_info = {}
        symbol      = jetton_info.get("symbol") or "TOKEN"
        decimals    = int(jetton_info.get("decimals") or 9)
        raw_amount  = int(jet.get("amount") or 0)
        comment     = self._clean_comment(jet.get("comment", ""))
        is_enc      = jet.get("encrypted_comment", False)

        gas_nano = sum(
            int(a2.get("TonTransfer", {}).get("amount", 0))
            for a2 in actions if a2.get("type") == "TonTransfer"
        )

        rec: Dict[str, Any] = {
            "Action": "Transfer Token",
            "Time":   self._fmt_time(ts),
            "From":   self._name_or_addr(sender),
            "To":     self._name_or_addr(recip),
            "Amount": self._token_str(raw_amount, decimals, symbol),
            "State":  "Success",
        }
        if gas_nano:  rec["Fee"]     = self._price_str(gas_nano, "-")
        if is_enc:    rec["Comment"] = "[encrypted]"
        elif comment: rec["Comment"] = comment
        return rec

    def _parse_jetton_mint(self, a: Dict, ts: int) -> Dict:
        mint        = a.get("JettonMint") or {}
        jetton_info = mint.get("jetton") or {}
        if isinstance(jetton_info, str): jetton_info = {}
        symbol      = jetton_info.get("symbol") or "TOKEN"
        decimals    = int(jetton_info.get("decimals") or 9)
        raw_amount  = int(mint.get("amount") or 0)
        return {
            "Action": "Token Mint",
            "Time":   self._fmt_time(ts),
            "To":     self._name_or_addr(mint.get("recipient") or {}),
            "Amount": self._token_str(raw_amount, decimals, symbol),
            "State":  "Success",
        }

    def _parse_jetton_burn(self, a: Dict, ts: int) -> Dict:
        burn        = a.get("JettonBurn") or {}
        jetton_info = burn.get("jetton") or {}
        if isinstance(jetton_info, str): jetton_info = {}
        symbol      = jetton_info.get("symbol") or "TOKEN"
        decimals    = int(jetton_info.get("decimals") or 9)
        raw_amount  = int(burn.get("amount") or 0)
        return {
            "Action": "Token Burn",
            "Time":   self._fmt_time(ts),
            "From":   self._name_or_addr(burn.get("sender") or {}),
            "Amount": self._token_str(raw_amount, decimals, symbol),
            "State":  "Success",
        }

    def _parse_ton_transfer(self, a: Dict, ts: int) -> Dict:
        transfer = a.get("TonTransfer") or {}
        sender   = transfer.get("sender") or {}
        recip    = transfer.get("recipient") or {}
        nano     = int(transfer.get("amount") or 0)
        comment  = self._clean_comment(transfer.get("comment", ""))
        is_enc   = transfer.get("encrypted_comment", False)

        recip_raw   = (recip.get("address") or "").lower()
        action_type = "Received TON" if recip_raw == self._wallet_raw else "Sent TON"
        sign        = "+" if action_type == "Received TON" else "-"

        rec: Dict[str, Any] = {
            "Action": action_type,
            "Time":   self._fmt_time(ts),
            "From":   self._name_or_addr(sender),
            "To":     self._name_or_addr(recip),
            "Price":  self._price_str(nano, sign),
            "State":  "Success",
        }
        if is_enc:    rec["Comment"] = "[encrypted]"
        elif comment: rec["Comment"] = comment
        return rec

    def _parse_auction_bid(self, a: Dict, ts: int) -> Dict:
        bid     = a.get("AuctionBid") or {}
        nano    = int(bid.get("amount") or 0)
        nft_obj = bid.get("nft") or {}
        if isinstance(nft_obj, str): nft_obj = {}
        meta    = nft_obj.get("metadata") or {}
        nft_addr = nft_obj.get("address") or ""
        rec: Dict[str, Any] = {
            "Action": "Gas Relay",
            "Sub":    "Auction Bid",
            "Time":   self._fmt_time(ts),
            "From":   self._name_or_addr(bid.get("bidder") or {}),
            "To":     self._name_or_addr(bid.get("auction") or {}),
            "Price":  self._price_str(nano, "-"),
            "State":  "Success",
        }
        nft_name = meta.get("name") or ""
        if nft_name:  rec["Item"]        = nft_name
        if nft_addr:  rec["NFT Address"] = self._to_uq(nft_addr)
        return rec

    def _parse_smart_contract(self, a: Dict, actions: List, ts: int) -> Dict:
        sc      = a.get("SmartContractExec") or {}
        op      = sc.get("operation") or sc.get("op") or ""
        ton_val = int(sc.get("ton_attached") or 0)
        gas_nano = sum(
            int(a2.get("TonTransfer", {}).get("amount", 0))
            for a2 in actions if a2.get("type") == "TonTransfer"
        )
        rec: Dict[str, Any] = {
            "Action": "Gas Relay",
            "Sub":    "Smart Contract",
            "Time":   self._fmt_time(ts),
            "From":   self._name_or_addr(sc.get("executor") or {}),
            "To":     self._name_or_addr(sc.get("contract") or {}),
            "State":  "Success",
        }
        if op:       rec["Op"]  = op
        if ton_val:  rec["TON"] = self._price_str(ton_val, "-")
        if gas_nano: rec["Fee"] = self._price_str(gas_nano, "-")
        return rec

    def _parse_contract_deploy(self, a: Dict, ts: int) -> Dict:
        deploy     = a.get("ContractDeploy") or {}
        interfaces = ", ".join(deploy.get("interfaces") or [])
        rec: Dict[str, Any] = {
            "Action": "Gas Relay",
            "Sub":    "Contract Deploy",
            "Time":   self._fmt_time(ts),
            "From":   self._name_or_addr(deploy.get("deployer") or {}),
            "State":  "Success",
        }
        addr = deploy.get("address") or ""
        if addr:       rec["Contract"]   = self._to_uq(addr)
        if interfaces: rec["Interfaces"] = interfaces
        return rec

    def _parse_jetton_swap(self, a: Dict, ts: int) -> Dict:
        swap    = a.get("JettonSwap") or {}
        ton_in  = int(swap.get("ton_in") or 0)
        ton_out = int(swap.get("ton_out") or 0)

        in_j  = swap.get("jetton_master_in")  or {}
        out_j = swap.get("jetton_master_out") or {}
        if isinstance(in_j,  str): in_j  = {}
        if isinstance(out_j, str): out_j = {}

        raw_in   = int(swap.get("amount_in")  or 0)
        raw_out  = int(swap.get("amount_out") or 0)
        dec_in   = int(in_j.get("decimals")   or 9)
        dec_out  = int(out_j.get("decimals")  or 9)
        sym_in   = in_j.get("symbol")  or "TOKEN"
        sym_out  = out_j.get("symbol") or "TOKEN"

        from_str = self._price_str(ton_in) if ton_in else self._token_str(raw_in, dec_in, sym_in)
        to_str   = self._price_str(ton_out) if ton_out else self._token_str(raw_out, dec_out, sym_out)

        return {
            "Action": "Gas Relay",
            "Sub":    "Jetton Swap",
            "Time":   self._fmt_time(ts),
            "From":   self._name_or_addr(swap.get("user_wallet") or {}),
            "Router": self._name_or_addr(swap.get("router") or {}),
            "Swap":   f"{from_str} → {to_str}",
            "State":  "Success",
        }

    def _parse_domain_renew(self, a: Dict, ts: int) -> Dict:
        renew = a.get("DomainRenew") or {}
        rec: Dict[str, Any] = {
            "Action": "Gas Relay",
            "Sub":    "Domain Renew",
            "Time":   self._fmt_time(ts),
            "From":   self._name_or_addr(renew.get("renewer") or {}),
            "State":  "Success",
        }
        domain = renew.get("domain") or ""
        if domain: rec["Domain"] = domain
        return rec

    def _parse_stake(self, type_: str, a: Dict, ts: int) -> Dict:
        inner  = a.get(type_) or {}
        nano   = int(inner.get("amount") or 0)
        labels = {
            "DepositStake":          ("Stake Deposit",          "-"),
            "WithdrawStake":         ("Stake Withdraw",         "+"),
            "WithdrawStakeRequest":  ("Stake Withdraw Request", "-"),
            "ElectionsDepositStake": ("Elections Deposit",      "-"),
            "ElectionsRecoverStake": ("Elections Recover",      "+"),
        }
        label, sign = labels.get(type_, ("Staking", ""))
        rec: Dict[str, Any] = {
            "Action": "Gas Relay",
            "Sub":    label,
            "Time":   self._fmt_time(ts),
            "From":   self._name_or_addr(
                inner.get("staker") or inner.get("elector") or {}
            ),
            "State":  "Success",
        }
        if nano: rec["Amount"] = self._price_str(nano, sign)
        return rec


    def _parse_event(self, event: Dict) -> Optional[Dict[str, Any]]:
        """
        Convert a raw TonAPI event dict into a unified transaction record.
        Returns None for in-progress, failed, or unsupported events.

        Priority order (most specific first):
            NftPurchase > NftMint > NftItemTransfer >
            JettonSwap > JettonTransfer > JettonMint > JettonBurn >
            TonTransfer >
            AuctionBid > SmartContractExec > ContractDeploy >
            DomainRenew > Staking variants
        """
        if event.get("in_progress"):
            return None

        actions   = event.get("actions") or []
        timestamp = event.get("timestamp") or 0
        event_id  = event.get("event_id") or ""
        is_scam   = bool(event.get("is_scam"))

        def _first(type_: str) -> Optional[Dict]:
            return next((a for a in actions if a.get("type") == type_), None)

        def _ok(a: Optional[Dict]) -> Optional[Dict]:
            return a if (a and a.get("status") == "ok") else None

        parsers = [
            ("NftPurchase",         lambda a: self._parse_nft_purchase(a, timestamp)),
            ("NftMint",             lambda a: self._parse_nft_mint(a, timestamp)),
            ("NftItemTransfer",     lambda a: self._parse_nft_transfer(a, actions, timestamp)),
            ("JettonSwap",          lambda a: self._parse_jetton_swap(a, timestamp)),
            ("JettonTransfer",      lambda a: self._parse_jetton_transfer(a, actions, timestamp)),
            ("JettonMint",          lambda a: self._parse_jetton_mint(a, timestamp)),
            ("JettonBurn",          lambda a: self._parse_jetton_burn(a, timestamp)),
            ("TonTransfer",         lambda a: self._parse_ton_transfer(a, timestamp)),
            ("AuctionBid",          lambda a: self._parse_auction_bid(a, timestamp)),
            ("SmartContractExec",   lambda a: self._parse_smart_contract(a, actions, timestamp)),
            ("ContractDeploy",      lambda a: self._parse_contract_deploy(a, timestamp)),
            ("DomainRenew",         lambda a: self._parse_domain_renew(a, timestamp)),
        ]

        for type_, parser in parsers:
            a = _first(type_)
            # NftItemTransfer can be failed — filter separately
            if type_ == "NftItemTransfer":
                if a and a.get("status") != "ok":
                    return None
                if not a:
                    continue
            else:
                a = _ok(a)
                if a is None:
                    continue
            rec = parser(a)
            rec["Hash"] = event_id
            if is_scam:
                rec["⚠ Scam"] = True
            return rec

        # Staking variants
        for stake_type in self._STAKE_TYPES:
            a = _ok(_first(stake_type))
            if a:
                rec = self._parse_stake(stake_type, a, timestamp)
                rec["Hash"] = event_id
                if is_scam:
                    rec["⚠ Scam"] = True
                return rec

        return None   # unsupported / unknown event


    def _iter_events(self, limit: int) -> Iterator[Dict]:
        """
        Yield raw events from TonAPI, paginating automatically via before_lt.
        Stops when `limit` events have been yielded or no more pages exist.
        """
        fetched:   int           = 0
        before_lt: Optional[int] = None

        while fetched < limit:
            page_size = min(self._MAX_PAGE, limit - fetched)
            params: Dict[str, Any] = {"limit": page_size}
            if before_lt is not None:
                params["before_lt"] = before_lt

            try:
                data = self._get(
                    f"{self.base_url}/accounts/{self.wallet}/events",
                    params,
                )
            except requests.RequestException:
                break

            events = data.get("events") or []
            if not events:
                break

            for ev in events:
                yield ev
                fetched += 1
                if fetched >= limit:
                    return

            before_lt = events[-1].get("lt")
            if not before_lt or len(events) < page_size:
                break

    def get(self, limit: int = 1) -> str:
        """
        Fetch the latest `limit` supported transactions for this wallet.

        Over-fetches raw events (3×) to compensate for skipped / unsupported ones.

        Returns JSON:
            {
                "transactions": [ ... ],
                "total":        int,
                "skipped":      int,
                "dollar_rate":  float
            }
        """
        results: List[Dict[str, Any]] = []
        skipped = 0
        counter = 1

        for event in self._iter_events(limit * 3):
            if len(results) >= limit:
                break
            rec = self._parse_event(event)
            if rec is None:
                skipped += 1
                continue
            rec["#"] = counter
            results.append(rec)
            counter += 1

        return json.dumps({
            "transactions": results,
            "total":        len(results),
            "skipped":      skipped,
            "dollar_rate":  self._dollar_rate,
        }, indent=2, ensure_ascii=False)

    def Action(self, action: str = "Sent TON", limit: int = 1) -> str:
        """
        Fetch the latest `limit` transactions matching `action`.

        Accepts any alias from _ACTION_MAP (e.g. "sent", "nft", "swap", "stake").

        Returns JSON:
            {
                "action":       str,
                "transactions": [ ... ],
                "total":        int,
                "skipped":      int,
                "dollar_rate":  float
            }
        """
        wanted  = self._normalise_action(action)
        results: List[Dict[str, Any]] = []
        skipped = 0
        counter = 1

        for event in self._iter_events(limit * 10):
            if len(results) >= limit:
                break
            rec = self._parse_event(event)
            if rec is None:
                skipped += 1
                continue
            if rec.get("Action") != wanted:
                continue
            rec["#"] = counter
            results.append(rec)
            counter += 1

        return json.dumps({
            "action":       wanted,
            "transactions": results,
            "total":        len(results),
            "skipped":      skipped,
            "dollar_rate":  self._dollar_rate,
        }, indent=2, ensure_ascii=False)

    @classmethod
    def _normalise_action(cls, action: str) -> str:
        return cls._ACTION_MAP.get(action.strip().lower(), action)