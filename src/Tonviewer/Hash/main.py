<<<<<<< HEAD
import requests
import datetime
import json
import time
from typing import Dict, Any, Optional, List
from tonsdk.utils import Address
from ..dollers import Dollers


class EventResolver:
    """
    Resolve a TON transaction hash (event_id) → full structured action breakdown.

    Supports all known TonAPI v2 action types:
        TonTransfer          — Sent / Received TON with USD equivalent
        NftItemTransfer      — NFT transfer with name, collection, image, fee
        NftPurchase          — NFT marketplace sale with buyer/seller/price
        NftMint              — NFT mint with minter and NFT address
        JettonTransfer       — Token transfer with symbol, amount, gas fee
        JettonMint           — Token mint with recipient and amount
        JettonBurn           — Token burn with sender and amount
        JettonSwap           — DEX swap with in/out assets fully labelled
        AuctionBid           — Auction bid with item name and bid amount
        SmartContractExec    — Contract call with op-code and TON attached
        ContractDeploy       — Deploy with contract address and interfaces
        DomainRenew          — TON DNS renewal with domain name
        Subscribe            — Subscription with beneficiary and amount
        UnSubscribe          — Unsubscription event
        DepositStake         — Stake deposit amount
        WithdrawStake        — Stake withdrawal amount
        WithdrawStakeRequest — Pending withdrawal request
        ElectionsDepositStake  — Validator election deposit
        ElectionsRecoverStake  — Validator stake recovery
        Unknown / fallback   — simple_preview fields surfaced

    Features:
        • Retry with exponential back-off (3 attempts)
        • requests.Session for connection reuse
        • Event-level metadata: event_id, timestamp, fee, in_progress, is_scam
        • Per-action: status, type, all addresses as UQ-friendly, USD values
        • None / empty fields stripped from output automatically
    """

    TON_DECIMALS = 1_000_000_000
    _RETRIES     = 3
    _BACKOFF     = 1.5

    _STAKE_LABELS: Dict[str, tuple] = {
        "DepositStake":           ("Stake Deposit",          "-"),
        "WithdrawStake":          ("Stake Withdraw",         "+"),
        "WithdrawStakeRequest":   ("Stake Withdraw Request", "-"),
        "ElectionsDepositStake":  ("Elections Deposit",      "-"),
        "ElectionsRecoverStake":  ("Elections Recover",      "+"),
    }

    def __init__(self, *, event_address: str) -> None:
        self.event_address = event_address
        self._url          = f"https://tonapi.io/v2/events/{event_address}"
        self._cached:      Optional[Dict[str, Any]] = None
        self._rate         = Dollers()._TON_USDT()
        self._session      = requests.Session()
        self._session.headers.update({"Accept": "application/json"})


    def _fetch(self) -> Dict[str, Any]:
        if self._cached is not None:
            return self._cached
        last: Exception = RuntimeError("No attempts")
        for attempt in range(self._RETRIES):
            try:
                r = self._session.get(self._url, timeout=15)
                r.raise_for_status()
                self._cached = r.json()
                return self._cached
            except requests.RequestException as exc:
                last = exc
                if attempt < self._RETRIES - 1:
                    time.sleep(self._BACKOFF * (attempt + 1))
        raise last


    @staticmethod
    def _uq(addr: str) -> str:
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
    def _label(cls, info: Dict) -> str:
        """Return display name if available, otherwise UQ address."""
        if not info:
            return ""
        name = info.get("name") or ""
        addr = info.get("address") or ""
        return name if name else (cls._uq(addr) if addr else "")


    @staticmethod
    def _fmt_time(ts: int) -> str:
        return datetime.datetime.fromtimestamp(ts).strftime(
            "%Y-%m-%d %I:%M:%S %p"
        )

    def _ton(self, nano: int) -> float:
        return nano / self.TON_DECIMALS

    def _usd(self, ton: float) -> float:
        return round(ton * self._rate, 5)

    def _price(self, nano: int, sign: str = "") -> str:
        ton = self._ton(nano)
        return f"{sign}{ton:.3f} TON ≈ {self._usd(ton):.5f} $"

    def _token_amount(self, raw: int, decimals: int, symbol: str) -> str:
        return f"{raw / (10 ** decimals):.6f} {symbol}"

    @staticmethod
    def _status(action: Dict) -> str:
        return "SUCCESS" if action.get("status") == "ok" else "FAILED"


    def _ton_transfer(self, a: Dict, ts: int) -> Dict:
        t       = a.get("TonTransfer") or {}
        sender  = t.get("sender") or {}
        recip   = t.get("recipient") or {}
        nano    = int(t.get("amount") or 0)
        comment = (t.get("comment") or "").strip()
        is_enc  = t.get("encrypted_comment", False)

        recip_raw = (recip.get("address") or "").lower()
        direction = "Received TON" if "received" in recip_raw else "Sent TON"
        sign      = "+" if direction == "Received TON" else "-"

        rec: Dict[str, Any] = {
            "Type":   direction,
            "Status": self._status(a),
            "Time":   self._fmt_time(ts),
            "From":   self._label(sender),
            "To":     self._label(recip),
            "Amount": self._price(nano, sign),
        }
        if is_enc:        rec["Comment"] = "[encrypted]"
        elif comment:     rec["Comment"] = comment
        return rec

    def _nft_transfer(self, a: Dict, actions: List, ts: int) -> Dict:
        n       = a.get("NftItemTransfer") or {}
        sender  = n.get("sender") or {}
        recip   = n.get("recipient") or {}
        comment = (n.get("comment") or "").strip()
        is_enc  = n.get("encrypted_comment", False)

        nft_obj    = n.get("nft") or {}
        if isinstance(nft_obj, str): nft_obj = {}
        meta       = nft_obj.get("metadata") or {}
        collection = nft_obj.get("collection") or {}
        previews   = nft_obj.get("previews") or []
        nft_addr   = nft_obj.get("address") or ""

        nft_name   = meta.get("name") or collection.get("name") or ""
        coll_name  = collection.get("name") or ""
        image      = (
            meta.get("image")
            or meta.get("image_url")
            or (previews[-1].get("url") if previews else None)
        )
        fee_nano = sum(
            int(a2.get("TonTransfer", {}).get("amount", 0))
            for a2 in actions if a2.get("type") == "TonTransfer"
        )

        rec: Dict[str, Any] = {
            "Type":   "NFT Transfer",
            "Status": self._status(a),
            "Time":   self._fmt_time(ts),
            "From":   self._label(sender),
            "To":     self._label(recip),
        }
        if nft_name:   rec["NFT"]        = nft_name
        if nft_addr:   rec["NFT Address"]= self._uq(nft_addr)
        if coll_name:  rec["Collection"] = coll_name
        if image:      rec["Image"]      = image
        if fee_nano:   rec["Fee"]        = self._price(fee_nano, "-")
        if is_enc:     rec["Comment"]    = "[encrypted]"
        elif comment:  rec["Comment"]    = comment
        return rec

    def _nft_purchase(self, a: Dict, ts: int) -> Dict:
        p       = a.get("NftPurchase") or {}
        nft_obj = p.get("nft") or {}
        if isinstance(nft_obj, str): nft_obj = {}
        meta    = nft_obj.get("metadata") or {}
        nano    = int(p.get("amount") or 0)
        nft_addr = nft_obj.get("address") or ""

        rec: Dict[str, Any] = {
            "Type":   "NFT Purchase",
            "Status": self._status(a),
            "Time":   self._fmt_time(ts),
            "Seller": self._label(p.get("seller") or {}),
            "Buyer":  self._label(p.get("buyer") or {}),
            "Price":  self._price(nano),
        }
        nft_name = meta.get("name") or ""
        if nft_name:  rec["NFT"]         = nft_name
        if nft_addr:  rec["NFT Address"] = self._uq(nft_addr)
        return rec

    def _nft_mint(self, a: Dict, ts: int) -> Dict:
        m       = a.get("NftMint") or {}
        nft_obj = m.get("nft") or {}
        if isinstance(nft_obj, str): nft_obj = {}
        meta    = nft_obj.get("metadata") or {}
        nft_addr = nft_obj.get("address") or ""

        rec: Dict[str, Any] = {
            "Type":   "NFT Mint",
            "Status": self._status(a),
            "Time":   self._fmt_time(ts),
            "Minter": self._label(m.get("minter") or {}),
        }
        nft_name = meta.get("name") or ""
        if nft_name:  rec["NFT"]         = nft_name
        if nft_addr:  rec["NFT Address"] = self._uq(nft_addr)
        return rec

    def _jetton_transfer(self, a: Dict, actions: List, ts: int) -> Dict:
        j       = a.get("JettonTransfer") or {}
        sender  = j.get("sender") or {}
        recip   = j.get("recipient") or {}
        comment = (j.get("comment") or "").strip()
        is_enc  = j.get("encrypted_comment", False)

        jinfo    = j.get("jetton") or {}
        if isinstance(jinfo, str): jinfo = {}
        symbol   = jinfo.get("symbol") or "TOKEN"
        decimals = int(jinfo.get("decimals") or 9)
        raw_amt  = int(j.get("amount") or 0)

        gas_nano = sum(
            int(a2.get("TonTransfer", {}).get("amount", 0))
            for a2 in actions if a2.get("type") == "TonTransfer"
        )

        rec: Dict[str, Any] = {
            "Type":   "Token Transfer",
            "Status": self._status(a),
            "Time":   self._fmt_time(ts),
            "From":   self._label(sender),
            "To":     self._label(recip),
            "Amount": self._token_amount(raw_amt, decimals, symbol),
        }
        if gas_nano:   rec["Fee"]     = self._price(gas_nano, "-")
        if is_enc:     rec["Comment"] = "[encrypted]"
        elif comment:  rec["Comment"] = comment
        return rec

    def _jetton_mint(self, a: Dict, ts: int) -> Dict:
        m     = a.get("JettonMint") or {}
        jinfo = m.get("jetton") or {}
        if isinstance(jinfo, str): jinfo = {}
        symbol   = jinfo.get("symbol") or "TOKEN"
        decimals = int(jinfo.get("decimals") or 9)
        raw_amt  = int(m.get("amount") or 0)
        return {
            "Type":   "Token Mint",
            "Status": self._status(a),
            "Time":   self._fmt_time(ts),
            "To":     self._label(m.get("recipient") or {}),
            "Amount": self._token_amount(raw_amt, decimals, symbol),
        }

    def _jetton_burn(self, a: Dict, ts: int) -> Dict:
        b     = a.get("JettonBurn") or {}
        jinfo = b.get("jetton") or {}
        if isinstance(jinfo, str): jinfo = {}
        symbol   = jinfo.get("symbol") or "TOKEN"
        decimals = int(jinfo.get("decimals") or 9)
        raw_amt  = int(b.get("amount") or 0)
        return {
            "Type":   "Token Burn",
            "Status": self._status(a),
            "Time":   self._fmt_time(ts),
            "From":   self._label(b.get("sender") or {}),
            "Amount": self._token_amount(raw_amt, decimals, symbol),
        }

    def _jetton_swap(self, a: Dict, ts: int) -> Dict:
        s       = a.get("JettonSwap") or {}
        ton_in  = int(s.get("ton_in")  or 0)
        ton_out = int(s.get("ton_out") or 0)

        in_j  = s.get("jetton_master_in")  or {}
        out_j = s.get("jetton_master_out") or {}
        if isinstance(in_j,  str): in_j  = {}
        if isinstance(out_j, str): out_j = {}

        raw_in   = int(s.get("amount_in")  or 0)
        raw_out  = int(s.get("amount_out") or 0)
        dec_in   = int(in_j.get("decimals")  or 9)
        dec_out  = int(out_j.get("decimals") or 9)
        sym_in   = in_j.get("symbol")  or "TOKEN"
        sym_out  = out_j.get("symbol") or "TOKEN"

        from_str = self._price(ton_in)  if ton_in  else self._token_amount(raw_in,  dec_in,  sym_in)
        to_str   = self._price(ton_out) if ton_out else self._token_amount(raw_out, dec_out, sym_out)

        return {
            "Type":   "Jetton Swap",
            "Status": self._status(a),
            "Time":   self._fmt_time(ts),
            "Trader": self._label(s.get("user_wallet") or {}),
            "Router": self._label(s.get("router") or {}),
            "In":     from_str,
            "Out":    to_str,
        }

    def _auction_bid(self, a: Dict, ts: int) -> Dict:
        b       = a.get("AuctionBid") or {}
        nano    = int(b.get("amount") or 0)
        nft_obj = b.get("nft") or {}
        if isinstance(nft_obj, str): nft_obj = {}
        meta    = nft_obj.get("metadata") or {}
        nft_addr = nft_obj.get("address") or ""

        rec: Dict[str, Any] = {
            "Type":    "Auction Bid",
            "Status":  self._status(a),
            "Time":    self._fmt_time(ts),
            "Bidder":  self._label(b.get("bidder") or {}),
            "Auction": self._label(b.get("auction") or {}),
            "Bid":     self._price(nano, "-"),
        }
        nft_name = meta.get("name") or ""
        if nft_name:  rec["Item"]        = nft_name
        if nft_addr:  rec["NFT Address"] = self._uq(nft_addr)
        return rec

    def _smart_contract(self, a: Dict, actions: List, ts: int) -> Dict:
        sc      = a.get("SmartContractExec") or {}
        op      = sc.get("operation") or sc.get("op") or ""
        ton_att = int(sc.get("ton_attached") or 0)
        gas_nano = sum(
            int(a2.get("TonTransfer", {}).get("amount", 0))
            for a2 in actions if a2.get("type") == "TonTransfer"
        )
        rec: Dict[str, Any] = {
            "Type":     "Smart Contract",
            "Status":   self._status(a),
            "Time":     self._fmt_time(ts),
            "Executor": self._label(sc.get("executor") or {}),
            "Contract": self._label(sc.get("contract") or {}),
        }
        if op:       rec["Op"]  = op
        if ton_att:  rec["TON"] = self._price(ton_att, "-")
        if gas_nano: rec["Fee"] = self._price(gas_nano, "-")
        return rec

    def _contract_deploy(self, a: Dict, ts: int) -> Dict:
        d          = a.get("ContractDeploy") or {}
        interfaces = ", ".join(d.get("interfaces") or [])
        addr       = d.get("address") or ""
        rec: Dict[str, Any] = {
            "Type":     "Contract Deploy",
            "Status":   self._status(a),
            "Time":     self._fmt_time(ts),
            "Deployer": self._label(d.get("deployer") or {}),
        }
        if addr:        rec["Contract"]   = self._uq(addr)
        if interfaces:  rec["Interfaces"] = interfaces
        return rec

    def _domain_renew(self, a: Dict, ts: int) -> Dict:
        r      = a.get("DomainRenew") or {}
        domain = r.get("domain") or ""
        rec: Dict[str, Any] = {
            "Type":    "Domain Renew",
            "Status":  self._status(a),
            "Time":    self._fmt_time(ts),
            "Renewer": self._label(r.get("renewer") or {}),
        }
        if domain: rec["Domain"] = domain
        return rec

    def _subscribe(self, a: Dict, ts: int) -> Dict:
        s    = a.get("Subscribe") or {}
        nano = int(s.get("amount") or 0)
        rec: Dict[str, Any] = {
            "Type":        "Subscribe",
            "Status":      self._status(a),
            "Time":        self._fmt_time(ts),
            "Subscriber":  self._label(s.get("subscriber") or {}),
            "Beneficiary": self._label(s.get("beneficiary") or {}),
        }
        if nano: rec["Amount"] = self._price(nano, "-")
        return rec

    def _unsubscribe(self, a: Dict, ts: int) -> Dict:
        s = a.get("UnSubscribe") or {}
        return {
            "Type":        "Unsubscribe",
            "Status":      self._status(a),
            "Time":        self._fmt_time(ts),
            "Subscriber":  self._label(s.get("subscriber") or {}),
            "Beneficiary": self._label(s.get("beneficiary") or {}),
        }

    def _stake(self, type_: str, a: Dict, ts: int) -> Dict:
        inner      = a.get(type_) or {}
        nano       = int(inner.get("amount") or 0)
        label, sign = self._STAKE_LABELS.get(type_, ("Staking", ""))
        rec: Dict[str, Any] = {
            "Type":   label,
            "Status": self._status(a),
            "Time":   self._fmt_time(ts),
            "From":   self._label(
                inner.get("staker") or inner.get("elector") or {}
            ),
        }
        if nano: rec["Amount"] = self._price(nano, sign)
        return rec

    def _fallback(self, a: Dict, ts: int) -> Dict:
        """Surface simple_preview fields for unknown action types."""
        preview  = a.get("simple_preview") or {}
        accounts = preview.get("accounts") or []
        sender   = accounts[0] if len(accounts) > 0 else {}
        recip    = accounts[1] if len(accounts) > 1 else {}
        rec: Dict[str, Any] = {
            "Type":   a.get("type") or "Unknown",
            "Status": self._status(a),
            "Time":   self._fmt_time(ts),
            "From":   self._label(sender),
            "To":     self._label(recip),
        }
        val  = preview.get("value") or ""
        desc = preview.get("description") or ""
        if val:  rec["Value"]       = val
        if desc: rec["Description"] = desc
        return rec


    def _resolve_action(self, a: Dict, actions: List, ts: int) -> Dict:
        t = a.get("type") or ""

        dispatch = {
            "TonTransfer":       lambda: self._ton_transfer(a, ts),
            "NftItemTransfer":   lambda: self._nft_transfer(a, actions, ts),
            "NftPurchase":       lambda: self._nft_purchase(a, ts),
            "NftMint":           lambda: self._nft_mint(a, ts),
            "JettonTransfer":    lambda: self._jetton_transfer(a, actions, ts),
            "JettonMint":        lambda: self._jetton_mint(a, ts),
            "JettonBurn":        lambda: self._jetton_burn(a, ts),
            "JettonSwap":        lambda: self._jetton_swap(a, ts),
            "AuctionBid":        lambda: self._auction_bid(a, ts),
            "SmartContractExec": lambda: self._smart_contract(a, actions, ts),
            "ContractDeploy":    lambda: self._contract_deploy(a, ts),
            "DomainRenew":       lambda: self._domain_renew(a, ts),
            "Subscribe":         lambda: self._subscribe(a, ts),
            "UnSubscribe":       lambda: self._unsubscribe(a, ts),
        }

        if t in dispatch:
            return dispatch[t]()

        if t in self._STAKE_LABELS:
            return self._stake(t, a, ts)

        return self._fallback(a, ts)

    def extract_info(self) -> Dict[str, Any]:
        try:
            data      = self._fetch()
            timestamp = data.get("timestamp") or 0
            actions   = data.get("actions")   or []
            event_id  = data.get("event_id")  or self.event_address
            is_scam   = bool(data.get("is_scam"))
            fee_nano  = int((data.get("extra") or {}).get("fees_collected") or 0)

            if not actions:
                return {"error": "No actions found for this event"}

            parsed: List[Dict[str, Any]] = []
            for a in actions:
                rec = self._resolve_action(a, actions, timestamp)
                # Strip None / empty string values
                rec = {k: v for k, v in rec.items() if v is not None and v != ""}
                parsed.append(rec)

            output: Dict[str, Any] = {
                "event_id":    event_id,
                "timestamp":   self._fmt_time(timestamp),
                "action_count": len(parsed),
                "actions":     parsed,
            }
            if fee_nano:  output["network_fee"] = self._price(fee_nano, "-")
            if is_scam:   output["⚠ scam"]      = True

            return output

        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else "?"
            return {"error": f"HTTP {code} — invalid or unknown transaction hash"}

        except requests.RequestException as exc:
            return {"error": f"Network error: {exc}"}

        except Exception as exc:
            return {"error": f"Parsing error: {exc}"}

    def result(self) -> str:
        return json.dumps(
            self.extract_info(),
            indent=2,
            ensure_ascii=False,
        )
=======
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

>>>>>>> 5b3efc31ef3ed657ce8ce337dcd5791f8e39f0f5
