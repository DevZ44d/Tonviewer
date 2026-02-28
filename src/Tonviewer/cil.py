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
    console()