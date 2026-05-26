from importlib.metadata import version, PackageNotFoundError
from colorama import Fore, Style
import requests


def help() -> str:
    return f"""
{Fore.RED}Tonviewer{Fore.WHITE} - TON Wallet, NFT & Fragment CLI Tool
Usage:
        {Fore.RED}Tonviewer {Fore.WHITE}-[OPTIONS] "[FOR-OPTION]"

{Fore.YELLOW}Wallet & Transactions:{Fore.WHITE}
  {Fore.RED}-w,  --wallet{Fore.WHITE}              Wallet address (use with -i or -a)
  {Fore.RED}-i,  --info{Fore.WHITE}                Get full wallet info (balance, status, NFT count)
  {Fore.RED}-t,  --transactions{Fore.WHITE}        Fetch latest N transactions for a wallet
  {Fore.RED}-l,  --limit{Fore.WHITE}               Number of transactions / actions to fetch (default: 1)
  {Fore.RED}-a,  --action{Fore.WHITE}              Filter transactions by type:
                             sent | receive | nft | token | gas
  {Fore.RED}-H,  --hashtx{Fore.WHITE}              Resolve a transaction hash → full action breakdown
  {Fore.RED}-p,  --price{Fore.WHITE}               Print live TON/USDT price (Binance)

{Fore.YELLOW}NFT:{Fore.WHITE}
  {Fore.RED}-n,  --nfts{Fore.WHITE}                Fetch all NFTs for @username or wallet address
  {Fore.RED}     --floors{Fore.WHITE}              Also fetch collection floor prices (use with -n)
  {Fore.RED}     --search{Fore.WHITE}              Search NFTs by name / collection (use with -n)
  {Fore.RED}     --detail{Fore.WHITE}              Full metadata for a single NFT contract address
  {Fore.RED}     --bulk{Fore.WHITE}                Bulk NFT fetch for multiple @users / wallets
  {Fore.RED}     --top{Fore.WHITE}                 Show top-N collections by count (use with -n)
  {Fore.RED}     --value{Fore.WHITE}               Estimated floor value by category (use with -n)
  {Fore.RED}     --has{Fore.WHITE}                 Check if a specific NFT name exists (use with -n)
  {Fore.RED}-g,  --gifts{Fore.WHITE}               Show Telegram Gifts only (use with -n)
  {Fore.RED}-u,  --users{Fore.WHITE}               Show Telegram Usernames only (use with -n)
  {Fore.RED}-e,  --etc{Fore.WHITE}                 Show Other / Misc NFTs only (use with -n)

{Fore.YELLOW}Fragment (simple):{Fore.WHITE}
  {Fore.RED}-f,  --fragment{Fore.WHITE}            Look up a single @username on Fragment.com
  {Fore.RED}-fm, --fragment-multi{Fore.WHITE}      Concurrent lookup of multiple @usernames

{Fore.YELLOW}FragmentClient (advanced):{Fore.WHITE}
  {Fore.RED}     --fragment-client{Fore.WHITE}     Advanced single lookup with full metadata
  {Fore.RED}     --fragment-bulk{Fore.WHITE}       Advanced concurrent bulk lookup
  {Fore.RED}     --resolve{Fore.WHITE}             Resolve @username → TON wallet address only
  {Fore.RED}     --fragment-search{Fore.WHITE}     Search Fragment.com for matching usernames

{Fore.YELLOW}Global:{Fore.WHITE}
  {Fore.RED}     --json{Fore.WHITE}                Output raw JSON response on any command
  {Fore.RED}-v,  --version{Fore.WHITE}             Show Tonviewer version and links
  {Fore.RED}-h,  --help{Fore.WHITE}                Show this help message
"""


def versions():
    try:
        pkg_version = version("tonviewer")
    except PackageNotFoundError:
        pkg_version = "unknown"

    return f"""
{Fore.RED}Tonviewer {Fore.WHITE}Version: {Fore.RED}{pkg_version}{Fore.WHITE}
Author: {Fore.RED}PyCodz{Fore.WHITE} .

({Fore.RED}PyPI{Fore.WHITE})      : https://pypi.org/project/Tonviewer .
({Fore.RED}GitHub{Fore.WHITE})    : https://github.com/DevZ44d/Tonviewer.git .
({Fore.RED}Telegram{Fore.WHITE})  : https://t.me/PyCodz .
({Fore.RED}Portfolio{Fore.WHITE}) : https://deep.is-a.dev .
"""


def check_for_update(package_name: str):
    try:
        current_version = version(package_name)
        url = f"https://pypi.org/pypi/{package_name}/json"
        latest_version = requests.get(url).json()["info"]["version"]

        if current_version != latest_version:
            print(f"""{Fore.WHITE}
[{Fore.BLUE}notice{Fore.WHITE}] New release available: {Fore.RED}{current_version}{Fore.WHITE} → {Fore.GREEN}{latest_version}{Fore.WHITE}
[{Fore.BLUE}notice{Fore.WHITE}] Run: {Fore.GREEN}python -m pip install --upgrade {package_name}{Fore.WHITE}
""")
    except Exception:
        pass