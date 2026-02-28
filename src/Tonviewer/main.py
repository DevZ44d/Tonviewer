from importlib.metadata import version, PackageNotFoundError
from colorama import Fore
import requests

def help() -> str:
    return f"""
{Fore.RED}Tonviewer{Fore.WHITE} - TON Wallet & Crypto Info CLI Tool
Usage:
        {Fore.RED}Tonviewer {Fore.WHITE}-[OPTIONS] "[FOR-OPTION]"
Options:
  {Fore.RED}-w, --wallet{Fore.WHITE}          Print wallet balance.
  {Fore.RED}-i, --info{Fore.WHITE}            Get wallet info.
  {Fore.RED}-t, --transactions{Fore.WHITE}    Get wallet transactions.
  {Fore.RED}-l, --limit{Fore.WHITE}           Number of transactions to fetch.
  {Fore.RED}-H, --hashtx{Fore.WHITE}          Pass a transaction hash.
  {Fore.RED}-v, --version{Fore.WHITE}         Show Tonviewer version.
  {Fore.RED}-h, --help{Fore.WHITE}            Show this help message.
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
[{Fore.BLUE}notice{Fore.WHITE}] Run: {Fore.GREEN}pip install -U {package_name}{Fore.WHITE}
""")
    except Exception:
        pass
