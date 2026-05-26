<<<<<<< HEAD


from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings("ignore")

from colorama import Fore, Style, init as colorama_init
colorama_init(autoreset=True)

from .file import Wallet, HashTx
from .dollers import Dollers
from .main import help as _help_text, versions, check_for_update
from .INFO.nft import NFTClient, NFTResult, NFTItem
from .INFO.fragment import FragmentClient, FragmentResult
from .INFO.GetWallet import Fragment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="Tonviewer",
        description="Tonviewer — TON Wallet, NFT & Fragment CLI",
        add_help=False,
    )

    parser.add_argument("-h", "--help",    action="store_true", help="Display help message")
    parser.add_argument("-v", "--version", action="store_true", help="Show version info")

    parser.add_argument("-w", "--wallet",
        type=str, metavar="ADDR",
        help="Wallet address (use with -i, -a)")
    parser.add_argument("-i", "--info",
        action="store_true",
        help="Get full wallet info — balance, status, last activity, NFT count")
    parser.add_argument("-t", "--transactions",
        type=str, metavar="ADDR",
        help="Fetch N latest transactions for ADDR  (combine with -l)")
    parser.add_argument("-l", "--limit",
        type=int, default=1, metavar="N",
        help="How many transactions/actions to fetch  (default: 1)")
    parser.add_argument("-a", "--action",
        type=str, metavar="TYPE",
        help=("Filter transactions by type.  Accepted aliases:\n"
              "  sent | send | sent ton  →  Sent TON\n"
              "  receive | received ton  →  Received TON\n"
              "  nft | nft transfer      →  NFT Transfer\n"
              "  token | jetton          →  Transfer Token\n"
              "  gas | relay | gas relay →  Gas Relay"))
    parser.add_argument("-H", "--hashtx",
        type=str, metavar="HASH",
        help="Resolve a transaction hash → full action breakdown")

    parser.add_argument("-p", "--price",
        action="store_true",
        help="Print current TON/USDT spot price (Binance)")

    parser.add_argument("-n", "--nfts",
        type=str, metavar="TARGET",
        help="Fetch all NFTs for @username or wallet address")
    parser.add_argument("--floors",
        action="store_true",
        help="Also fetch collection floor prices in TON  (use with -n)")
    parser.add_argument("--search",
        type=str, metavar="QUERY",
        help="Search NFTs by name / collection / description  (use with -n)")
    parser.add_argument("--detail",
        type=str, metavar="NFT_ADDR",
        help="Fetch full metadata for a single NFT contract address")
    parser.add_argument("--bulk",
        nargs="+", metavar="TARGET",
        dest="nft_bulk",
        help="Fetch NFTs for multiple @usernames / wallets concurrently")
    parser.add_argument("--top",
        type=int, metavar="N",
        help="Show top-N collections by count  (use with -n, default: 5)")
    parser.add_argument("--value",
        action="store_true",
        help="Print estimated floor-price value by category  (use with -n)")
    parser.add_argument("--has",
        type=str, metavar="NAME",
        help="Check if an NFT with exactly this name exists  (use with -n)")

    # NFT category filter (mutually exclusive)
    nft_filter = parser.add_mutually_exclusive_group()
    nft_filter.add_argument("-g", "--gifts",
        action="store_true", help="Show Telegram Gifts only  (use with -n)")
    nft_filter.add_argument("-u", "--users",
        action="store_true", help="Show Telegram Usernames only  (use with -n)")
    nft_filter.add_argument("-e", "--etc",
        action="store_true", help="Show Other/Misc NFTs only  (use with -n)")

    parser.add_argument("-f", "--fragment",
        type=str, metavar="USER",
        help="Look up a single @username on Fragment.com (simple)")
    parser.add_argument("-fm", "--fragment-multi",
        nargs="+", metavar="USER",
        dest="fragment_multi",
        help="Look up multiple @usernames concurrently (simple)")

    parser.add_argument("--fragment-client",
        type=str, metavar="USER",
        dest="fragment_client",
        help="Look up @username via the advanced FragmentClient with full metadata")
    parser.add_argument("--fragment-bulk",
        nargs="+", metavar="USER",
        dest="fragment_bulk",
        help="Bulk concurrent lookup via FragmentClient")
    parser.add_argument("--resolve",
        type=str, metavar="USER",
        help="Resolve @username → TON wallet address only (returns None if not found)")
    parser.add_argument("--fragment-search",
        type=str, metavar="QUERY",
        dest="fragment_search",
        help="Search Fragment.com for usernames matching a query string")

    parser.add_argument("--json",
        action="store_true",
        dest="json_output",
        help="Output the raw JSON response instead of the coloured display")

    args, unknown = parser.parse_known_args()
    if unknown:
        for arg in unknown:
            print(
                f"[{Fore.RED}ERROR{Style.RESET_ALL}] Unknown argument: "
                f"{Fore.RED}{arg}{Style.RESET_ALL}. "
                f"Use {Fore.YELLOW}-h{Style.RESET_ALL} for help."
            )
        sys.exit(1)
    return args



def _out(data, *, json_output: bool) -> None:
    """Print data either as raw JSON or as a coloured string."""
    if json_output:
        if isinstance(data, str):
            # Already JSON string → validate + pretty-print
            try:
                print(json.dumps(json.loads(data), indent=2, ensure_ascii=False))
            except json.JSONDecodeError:
                print(data)
        else:
            print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    else:
        if isinstance(data, str):
            print(data)
        else:
            _pretty(data)


def _pretty(obj) -> None:
    """Minimal coloured pretty-print for dicts / lists."""
    if isinstance(obj, list):
        for item in obj:
            _pretty(item)
        return
    if not isinstance(obj, dict):
        print(obj)
        return
    for key, val in obj.items():
        print(f"  {Fore.CYAN}{key:<20}{Style.RESET_ALL}{val}")



def _fmt_nft(item: NFTItem) -> str:
    """One-line coloured representation of an NFTItem."""
    cat_color = {"users": Fore.BLUE, "gifts": Fore.MAGENTA, "etc": Fore.WHITE}.get(
        item.category, Fore.WHITE
    )
    floor = (
        f"  {Fore.GREEN}floor={item.floor_price_ton} TON{Style.RESET_ALL}"
        if item.floor_price_ton
        else ""
    )
    return (
        f"  {Fore.YELLOW}{item.name}{Style.RESET_ALL}"
        f"  {cat_color}({item.collection}){Style.RESET_ALL}"
        f"{floor}"
    )


def _nft_result_to_dict(result: NFTResult) -> dict:
    """Convert NFTResult to a plain JSON-serialisable dict."""
    def item_to_dict(i: NFTItem) -> dict:
        return {
            "address":            i.address,
            "name":               i.name,
            "collection":         i.collection,
            "collection_address": i.collection_address,
            "image_url":          i.image_url,
            "description":        i.description,
            "category":           i.category,
            "floor_price_ton":    i.floor_price_ton,
            "attributes": [
                {"trait_type": a.trait_type, "value": a.value}
                for a in i.attributes
            ],
        }
    return {
        "owner":   result.owner,
        "total":   len(result),
        "users":   [item_to_dict(i) for i in result["users"]],
        "gifts":   [item_to_dict(i) for i in result["gifts"]],
        "etc":     [item_to_dict(i) for i in result["etc"]],
        "summary": {
            "users": len(result["users"]),
            "gifts": len(result["gifts"]),
            "etc":   len(result["etc"]),
        },
    }


async def _cmd_nfts(args: argparse.Namespace) -> None:
    """Handler for -n / --nfts."""
    target = args.nfts
    fetch_floors: bool = args.floors

    async with NFTClient() as client:
        result = await client.get_nfts(target, fetch_floors=fetch_floors)

        if args.has:
            found = result.has(args.has)
            if args.json_output:
                _out({"query": args.has, "found": found, "total_nfts": len(result)},
                     json_output=True)
            else:
                color = Fore.GREEN if found else Fore.RED
                mark  = "✓" if found else "✗"
                print(f"  {color}{mark}{Style.RESET_ALL}  NFT '{args.has}' "
                      f"{'found' if found else 'not found'} in {target}")
            return

        if args.search:
            hits = result.search(args.search)
            if args.json_output:
                _out({"query": args.search, "results": [
                    {"name": i.name, "collection": i.collection,
                     "category": i.category, "floor": i.floor_price_ton}
                    for i in hits
                ]}, json_output=True)
                return
            if not hits:
                print(f"[{Fore.RED}NFT{Style.RESET_ALL}] No results for '{args.search}'")
                return
            print(f"\n[{Fore.GREEN}NFT{Style.RESET_ALL}] "
                  f"{len(hits)} result(s) for '{Fore.YELLOW}{args.search}{Style.RESET_ALL}':\n")
            for item in hits:
                print(_fmt_nft(item))
            return

        if args.value:
            vals = result.value_summary()
            if args.json_output:
                _out(vals, json_output=True)
                return
            print(f"\n[{Fore.GREEN}NFT{Style.RESET_ALL}] Estimated floor value for "
                  f"{Fore.YELLOW}{target}{Style.RESET_ALL}:")
            for k, v in vals.items():
                print(f"  {Fore.CYAN}{k:<10}{Style.RESET_ALL}{v} TON")
            return

        if args.top:
            tops = result.top_collections(args.top)
            if args.json_output:
                _out([{"collection": n, "count": c} for n, c in tops], json_output=True)
                return
            print(f"\n[{Fore.GREEN}NFT{Style.RESET_ALL}] Top-{args.top} collections for "
                  f"{Fore.YELLOW}{target}{Style.RESET_ALL}:\n")
            for name, count in tops:
                print(f"  {Fore.YELLOW}{count:>5}{Style.RESET_ALL}  {name}")
            return

        if result.is_empty:
            if args.json_output:
                _out({"total": 0, "owner": target,
                      "message": "No NFTs found — user may not have a wallet"},
                     json_output=True)
            else:
                print(f"[{Fore.YELLOW}NFT{Style.RESET_ALL}] No NFTs found for "
                      f"{Fore.YELLOW}{target}{Style.RESET_ALL}. "
                      "User may not have a wallet.")
            return

        category: Optional[str] = None
        if args.gifts: category = "gifts"
        elif args.users: category = "users"
        elif args.etc:   category = "etc"

        if category:
            items = result[category]
            if args.json_output:
                _out({"owner": result.owner, "category": category,
                      "count": len(items),
                      "items": [{"name": i.name, "collection": i.collection,
                                 "floor": i.floor_price_ton} for i in items]},
                     json_output=True)
                return
            label = {"users": "Usernames", "gifts": "Gifts", "etc": "Other NFTs"}[category]
            print(f"\n[{Fore.GREEN}NFT{Style.RESET_ALL}] "
                  f"Wallet: {Fore.YELLOW}{result.owner}{Style.RESET_ALL}")
            if not items:
                print(f"[{Fore.YELLOW}NFT{Style.RESET_ALL}] No {label} in this wallet.")
                return
            print(f"\n{Fore.CYAN}{label}{Style.RESET_ALL} ({Fore.GREEN}{len(items)}{Style.RESET_ALL}):\n")
            for item in items:
                print(_fmt_nft(item))
            return

        if args.json_output:
            _out(_nft_result_to_dict(result), json_output=True)
            return

        print(f"\n[{Fore.GREEN}NFT{Style.RESET_ALL}] "
              f"Wallet: {Fore.YELLOW}{result.owner}{Style.RESET_ALL}")
        print(f"\n{result.summary()}\n")
        for cat, label in (("users", "Usernames"), ("gifts", "Gifts"), ("etc", "Other NFTs")):
            items = result[cat]
            if not items:
                continue
            print(f"{Fore.CYAN}{label}{Style.RESET_ALL} ({len(items)}):")
            for item in items:
                print(_fmt_nft(item))
            print()


async def _cmd_nft_detail(args: argparse.Namespace) -> None:
    """Handler for --detail."""
    async with NFTClient() as client:
        item = await client.get_nft_detail(args.detail)
        if item is None:
            if args.json_output:
                _out({"error": f"NFT not found: {args.detail}"}, json_output=True)
            else:
                print(f"[{Fore.RED}NFT{Style.RESET_ALL}] Not found: {args.detail}")
            return

        if args.json_output:
            _out({
                "address":     item.address,
                "name":        item.name,
                "collection":  item.collection,
                "image_url":   item.image_url,
                "description": item.description,
                "category":    item.category,
                "floor":       item.floor_price_ton,
                "attributes":  [{"trait_type": a.trait_type, "value": a.value}
                                 for a in item.attributes],
            }, json_output=True)
        else:
            print(f"\n{Fore.CYAN}── NFT Detail ──{Style.RESET_ALL}")
            print(_fmt_nft(item))
            if item.image_url:
                print(f"  {Fore.CYAN}Image{Style.RESET_ALL}  {item.image_url}")
            if item.description:
                print(f"  {Fore.CYAN}Desc{Style.RESET_ALL}   {item.description[:120]}")
            if item.attributes:
                print(f"  {Fore.CYAN}Traits{Style.RESET_ALL}")
                for attr in item.attributes:
                    print(f"    {Fore.YELLOW}{attr.trait_type}{Style.RESET_ALL}: {attr.value}")


async def _cmd_nft_bulk(args: argparse.Namespace) -> None:
    """Handler for --bulk."""
    targets = args.nft_bulk
    fetch_floors: bool = args.floors

    async with NFTClient() as client:
        bulk: Dict[str, NFTResult] = await client.get_nfts_bulk(
            *targets, fetch_floors=fetch_floors
        )

        if args.json_output:
            _out({
                user: _nft_result_to_dict(res)
                for user, res in bulk.items()
            }, json_output=True)
            return

        for user, res in bulk.items():
            print(
                f"\n  {Fore.YELLOW}{user}{Style.RESET_ALL}  →  "
                f"total={len(res)}  "
                f"users={len(res['users'])}  "
                f"gifts={len(res['gifts'])}  "
                f"etc={len(res['etc'])}"
            )



async def _cmd_fragment_single(args: argparse.Namespace) -> None:
    """Handler for -f / --fragment  (simple scraper)."""
    clean = args.fragment.lstrip("@")

    async with Fragment(user=clean) as client:
        info = await client.get_info()

    if args.json_output:
        _out(info, json_output=True)
    else:
        _print_fragment_simple(info, clean)


async def _cmd_fragment_multi(args: argparse.Namespace) -> None:
    """Handler for -fm / --fragment-multi  (simple scraper, concurrent)."""
    usernames = args.fragment_multi

    async def _one(user: str):
        async with Fragment(user=user.lstrip("@")) as client:
            return user, await client.get_info()

    pairs = await asyncio.gather(*[_one(u) for u in usernames], return_exceptions=True)

    if args.json_output:
        results = []
        for entry in pairs:
            if isinstance(entry, Exception):
                results.append({"error": str(entry)})
            else:
                _, info = entry
                results.append(info)
        _out(results, json_output=True)
        return

    ok = failed = 0
    for entry in pairs:
        if isinstance(entry, Exception):
            print(f"  {Fore.RED}[ERROR]{Style.RESET_ALL} {entry}")
            failed += 1
            continue
        username, info = entry
        _print_fragment_simple(info, username)
        if "error" in info:
            failed += 1
        else:
            ok += 1

    print(f"\n{'─'*52}")
    print(f"[{Fore.GREEN}Fragment{Style.RESET_ALL}] Done — "
          f"{Fore.GREEN}{ok} OK{Style.RESET_ALL}  "
          f"{Fore.RED}{failed} Failed{Style.RESET_ALL}")


def _print_fragment_simple(info: dict, username: str) -> None:
    """Coloured display for Fragment.get_info() results."""
    D = f"{Fore.WHITE}{'─'*52}{Style.RESET_ALL}"
    print(D)
    if "error" in info:
        print(f"  {Fore.RED}✗{Style.RESET_ALL}  @{username.lstrip('@')}"
              f"  →  {Fore.RED}{info['error']}{Style.RESET_ALL}")
        return

    status = info.get("status", "Unknown")
    status_color = {
        "sold": Fore.GREEN, "taken": Fore.GREEN,
        "available": Fore.CYAN, "on sale": Fore.YELLOW,
        "auction": Fore.YELLOW, "unknown": Fore.RED,
    }.get(status.lower(), Fore.WHITE)

    price_d = info.get("price") or {}
    owner   = info.get("owner") or {}
    auction = info.get("auction") or {}

    rows = [
        ("Username",  f"@{info.get('username', username).lstrip('@')}", Fore.YELLOW),
        ("Status",    status,                                            status_color),
    ]
    if price_d.get("display"):
        rows.append(("Price",     price_d["display"],                   Fore.GREEN))
    if owner.get("ton_wallet"):
        rows.append(("Wallet",    owner["ton_wallet"],                  Fore.WHITE))
    if owner.get("tonviewer"):
        rows.append(("Tonviewer", owner["tonviewer"],                   Fore.WHITE))
    if info.get("purchased_at"):
        rows.append(("Purchased", info["purchased_at"],                 Fore.WHITE))
    if auction.get("bids"):
        rows.append(("Bids",      str(auction["bids"]),                 Fore.WHITE))
    if auction.get("auction_ends"):
        rows.append(("Ends At",   auction["auction_ends"],              Fore.WHITE))
    if info.get("fragment_url"):
        rows.append(("Fragment",  info["fragment_url"],                 Fore.WHITE))

    for label, value, color in rows:
        print(f"  {Fore.CYAN}{label:<12}{Style.RESET_ALL}│  {color}{value}{Style.RESET_ALL}")



def _fragment_result_to_dict(r: FragmentResult) -> dict:
    return {
        "username":        r.username,
        "status":          r.status,
        "raw_wallet":      r.raw_wallet,
        "friendly_wallet": r.friendly_wallet,
        "display_wallet":  r.display_wallet,
        "price_ton":       r.price_ton,
        "min_bid":         r.min_bid,
        "auction_end":     r.auction_end,
        "fragment_url":    r.fragment_url,
        "is_sold":         r.is_sold,
        "is_auction":      r.is_auction,
        "is_available":    r.is_available,
        "is_not_found":    r.is_not_found,
        "has_wallet":      r.has_wallet,
        "owner":           r.owner,
    }


def _print_fragment_result(r: FragmentResult) -> None:
    status_color = {
        "sold": Fore.GREEN, "on auction": Fore.YELLOW,
        "available": Fore.CYAN,
    }.get(r.status.lower(), Fore.WHITE)

    D = f"{Fore.WHITE}{'─'*52}{Style.RESET_ALL}"
    print(D)
    print(f"  {Fore.CYAN}Username{Style.RESET_ALL}      @{r.username}")
    print(f"  {Fore.CYAN}Status{Style.RESET_ALL}        {status_color}{r.status}{Style.RESET_ALL}")
    if r.price_ton:
        print(f"  {Fore.CYAN}Price{Style.RESET_ALL}         {Fore.GREEN}{r.price_ton}{Style.RESET_ALL}")
    if r.min_bid:
        print(f"  {Fore.CYAN}Min Bid{Style.RESET_ALL}       {r.min_bid}")
    if r.auction_end:
        print(f"  {Fore.CYAN}Ends At{Style.RESET_ALL}       {r.auction_end}")
    if r.friendly_wallet:
        print(f"  {Fore.CYAN}Wallet{Style.RESET_ALL}        {r.friendly_wallet}")
    if r.fragment_url:
        print(f"  {Fore.CYAN}Fragment{Style.RESET_ALL}      {r.fragment_url}")


async def _cmd_fragment_client(args: argparse.Namespace) -> None:
    """Handler for --fragment-client  (advanced FragmentClient)."""
    async with FragmentClient() as client:
        result = await client.get_username(args.fragment_client)

    if args.json_output:
        _out(_fragment_result_to_dict(result), json_output=True)
    else:
        _print_fragment_result(result)


async def _cmd_fragment_bulk(args: argparse.Namespace) -> None:
    """Handler for --fragment-bulk  (advanced FragmentClient, concurrent)."""
    async with FragmentClient() as client:
        results = await client.get_usernames(*args.fragment_bulk)

    if args.json_output:
        _out([_fragment_result_to_dict(r) for r in results], json_output=True)
        return

    for r in results:
        _print_fragment_result(r)
    print(f"\n[{Fore.GREEN}Fragment{Style.RESET_ALL}] {len(results)} result(s) returned.")


async def _cmd_resolve(args: argparse.Namespace) -> None:
    """Handler for --resolve  (username → wallet, non-raising)."""
    async with FragmentClient() as client:
        wallet = await client.resolve_wallet(args.resolve)

    if args.json_output:
        _out({"username": args.resolve, "wallet": wallet}, json_output=True)
    else:
        if wallet:
            print(f"  {Fore.GREEN}✓{Style.RESET_ALL}  @{args.resolve.lstrip('@')}  →  "
                  f"{Fore.YELLOW}{wallet}{Style.RESET_ALL}")
        else:
            print(f"  {Fore.RED}✗{Style.RESET_ALL}  @{args.resolve.lstrip('@')}  "
                  f"→  wallet not found / username not sold")


async def _cmd_fragment_search(args: argparse.Namespace) -> None:
    """Handler for --fragment-search."""
    async with FragmentClient() as client:
        hits = await client.search(args.fragment_search)

    if args.json_output:
        _out([{"username": h.username, "status": h.status, "price_ton": h.price_ton}
              for h in hits], json_output=True)
        return

    if not hits:
        print(f"[{Fore.YELLOW}Fragment{Style.RESET_ALL}] No results for '{args.fragment_search}'.")
        return

    print(f"\n[{Fore.GREEN}Fragment{Style.RESET_ALL}] "
          f"{len(hits)} result(s) for '{Fore.YELLOW}{args.fragment_search}{Style.RESET_ALL}':\n")
    for h in hits:
        price = f"  {Fore.GREEN}{h.price_ton}{Style.RESET_ALL}" if h.price_ton else ""
        print(f"  {Fore.YELLOW}@{h.username}{Style.RESET_ALL}"
              f"  [{h.status}]{price}")



def run_cli() -> None:
    args = parse_args()

    try:
        if args.help:
            print(_help_text())
            check_for_update("tonviewer")
            sys.exit(0)

        if args.version:
            print(versions())
            check_for_update("tonviewer")
            sys.exit(0)


        if args.price:
            price = Dollers()._TON_USDT()
            if args.json_output:
                _out({"symbol": "TONUSDT", "price": price, "source": "Binance"}, json_output=True)
            else:
                print(f"\n  {Fore.CYAN}TON/USDT{Style.RESET_ALL}  →  "
                      f"{Fore.GREEN}{price}{Style.RESET_ALL}")
            check_for_update("tonviewer")
            sys.exit(0)

        if args.hashtx:
            result = HashTx(hashtx=args.hashtx).get()
            if args.json_output:
                # result is already a JSON string
                print(result)
            else:
                print(result)
            check_for_update("tonviewer")
            sys.exit(0)

        if args.wallet and args.info:
            result = Wallet(wallet=args.wallet).info()
            if args.json_output:
                print(result)
            else:
                print(result)
            check_for_update("tonviewer")
            sys.exit(0)

        if args.wallet and args.action:
            limit = max(args.limit, 1)
            result = Wallet(wallet=args.wallet).action(action=args.action, limit=limit)
            if args.json_output:
                print(result)
            else:
                print(result)
            check_for_update("tonviewer")
            sys.exit(0)

        wallet_addr = args.transactions or args.wallet
        if wallet_addr and not args.info and not args.action:
            limit = max(args.limit, 1)
            result = Wallet(wallet=wallet_addr).transactions(limit=limit)
            if args.json_output:
                print(result)
            else:
                print(result)
            check_for_update("tonviewer")
            sys.exit(0)

        if args.detail:
            asyncio.run(_cmd_nft_detail(args))
            check_for_update("tonviewer")
            sys.exit(0)

        if args.nft_bulk:
            asyncio.run(_cmd_nft_bulk(args))
            check_for_update("tonviewer")
            sys.exit(0)

        if args.nfts:
            asyncio.run(_cmd_nfts(args))
            check_for_update("tonviewer")
            sys.exit(0)

        if args.fragment_search:
            asyncio.run(_cmd_fragment_search(args))
            check_for_update("tonviewer")
            sys.exit(0)

        if args.resolve:
            asyncio.run(_cmd_resolve(args))
            check_for_update("tonviewer")
            sys.exit(0)

        if args.fragment_bulk:
            asyncio.run(_cmd_fragment_bulk(args))
            check_for_update("tonviewer")
            sys.exit(0)

        if args.fragment_client:
            asyncio.run(_cmd_fragment_client(args))
            check_for_update("tonviewer")
            sys.exit(0)

        if args.fragment_multi:
            asyncio.run(_cmd_fragment_multi(args))
            check_for_update("tonviewer")
            sys.exit(0)

        if args.fragment:
            asyncio.run(_cmd_fragment_single(args))
            check_for_update("tonviewer")
            sys.exit(0)

        print(
            f"[{Fore.RED}ERROR{Style.RESET_ALL}] No valid arguments provided. "
            f"Use {Fore.YELLOW}-h{Style.RESET_ALL} for help."
        )
        sys.exit(1)

    except KeyboardInterrupt:
        print(f"\n[{Fore.YELLOW}INFO{Style.RESET_ALL}] Interrupted.")
        sys.exit(0)
    except Exception as exc:
        if args.json_output:
            print(json.dumps({"error": str(exc)}, indent=2))
        else:
            print(f"[{Fore.RED}FATAL{Style.RESET_ALL}] {exc}")
        sys.exit(1)


def console() -> None:
    run_cli()


if __name__ == "__main__":
=======
import argparse
from .file import Wallet, HashTx
from .main import help, versions
from colorama import Fore

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tonviewer is a Python library to fetch wallet info, transactions, and transaction hash data.",
        add_help=False
    )

    parser.add_argument("-w", "--wallet", type=str, help="Wallet address")
    parser.add_argument("-i", "--info", action="store_true", help="Get wallet info")
    parser.add_argument("-t", "--transactions", type=str, help="Wallet address for transactions")
    parser.add_argument("-l", "--limit", type=int, help="Number of transactions to fetch")
    parser.add_argument("-H", "--hashtx", type=str, help="Transaction hash to query")
    parser.add_argument("-h", "--help", action="store_true", help="Display help message")
    parser.add_argument("-v", "--version", action="store_true", help="Display version info")

    args, unknown = parser.parse_known_args()
    if unknown:
        for arg in unknown:
            print(f"[{Fore.RED}ERROR{Fore.WHITE}] No valid arguments provided. Use `{Fore.RED}{arg}{Fore.WHITE}` for help.")
        exit(1)

    return args

def run_cli():
    args = parse_args()

    try:
        # Help / Version
        if args.help:
            print(help())
            return

        if args.version:
            print(versions())
            return

        # Transaction hash
        if args.hashtx:
            HashTx(hashtx=args.hashtx).get()
            return

        # Wallet info
        if args.wallet and args.info:
            Wallet(wallet=args.wallet).info()
            return

        # Transactions
        if args.transactions:
            limit = args.limit if args.limit and args.limit > 0 else None
            Wallet(wallet=args.transactions).transactions(limit)
            return

        # Default error
        print(f"[{Fore.RED}ERROR{Fore.WHITE}] No valid arguments provided. Use `{Fore.RED}-h{Fore.WHITE}` for help.")

    except Exception as e:
        print(f"[FATAL] Unexpected error: {e}")

def console():
    run_cli()

if __name__ == "__main__":
>>>>>>> 5b3efc31ef3ed657ce8ce337dcd5791f8e39f0f5
    console()