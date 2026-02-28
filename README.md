<p align="center">
  <img align="center" width="350" src="https://github.com/user-attachments/assets/779356f9-84af-4247-83f0-32be2229c569" />
</p>


<p align="center">

<a href="https://pypi.org/project/Tonviewer/">
    <img src="https://img.shields.io/pypi/v/Tonviewer?color=blue&logo=pypi&logoColor=blue">
  </a>

  <a href="https://t.me/Pycodz">
    <img src="https://img.shields.io/badge/Telegram-Channel-blue.svg?logo=telegram">
  </a>
  
  <a href="https://t.me/DevZ44d" target="_blank">
    <img alt="Telegram Owner" src="https://img.shields.io/badge/Telegram-Owner-blue.svg?logo=telegram" />
  </a>
</p>

<p align="center">

  <a href="https://pepy.tech/projects/Tonviewer/">
    <img src="https://static.pepy.tech/personalized-badge/tonviewer?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=blue&left_text=downloads">
  </a>

  <a href="https://pepy.tech/projects/Tonviewer/">
    <img src="https://img.shields.io/badge/license-MIT-blue.svg">
  </a>
</p>

#### 🚀 Quick Start
```python
from Tonviewer import Wallet, HashTx


def main():
    # Replace with your wallet address
    wallet = Wallet("wallet_address_here")

    # Get wallet info (balance + TON details)
    wallet.info()

    # Example: Get last 3 transactions (default limit = 1)
    wallet.transactions(limit=3)


def get_transaction_by_hash():
    # Pass a transaction hash
    tx = HashTx(
        hashtx="b4566294bb20e0c22c57109f1128b903d4446d12710b3926b48c42cfc60dd097"
    )

    tx.get()  # Prints and returns dict


if __name__ == "__main__":
    main()
    get_transaction_by_hash()
```

### Installation and Development 🚀

- Via Git:
```shell
pip install  git+https://github.com/DevZ44d/Tonviewer.git
```

- Via PyPi:
```shell
pip install Tonviewer -U
```
### Tonviewer

- **_Tonviewer_** is a Python library that allows you to fetch real-time data.

- It enables users to view wallet **balances** and **live coin information** and get **transactions** of Wallet with ease, making it perfect for TON developers, analysts, and bot creators.

### ✨ Features

- 🧾  **Real-time** TON wallet balance fetching.
- 🔎 **Transaction by Hash** → Simply pass a transaction hash, it grabs the page via Selenium.
- 📄 **Parse Raw HTML** → Already have the page source? Pass it directly.
- 🟢 **Successful TX** → Extracts `Time`, `Action`, `From`, `To`, `Paid For`, `Price`, `Status`, `Comment`.
- 🔴 **Failed TX** → Extracts only the essentials (`Time`, `Action`, `From`, `To`, `Comment`, `Status`).
- ⚠️ **Invalid Hash** → Clean error message when the transaction address is not valid.
- 🧾 **Auto JSON Print** → Prints a formatted JSON result **and** returns it as a Python `dict`.


### Using in Terminal 🚀
```shell
Tonviewer -[OPTIONS] "[Wallet]"
```

### Usage 📚
```text
Tonviewer -[OPTIONS] "[FOR-OPTION]"

Options
    -w, --wallet                    Prints balance of wallet .
    -i, --info                      Get wallet info
    -t, --transactions              Get transactions of Wallet . 
    -l, --limit                     Number of times to get transactions .
    -H, --hashtx                    Pass a transaction hash
    -h, --help                      Display help message .
    -v, --version                   Show Version Of Libarary and info .
```

### 🚀 Usage (_Class Terminal_)
- 🔹Get wallet info:

```shell
Tonviewer -w "UQBaCsVw45KDyL8a_JIJeu2VlJazKnz9KBqBirRjKbnuZobG" -i
```

- 🔹Get transactions of Wallet:
```shell
Tonviewer -t "UQBaCsVw45KDyL8a_JIJeu2VlJazKnz9KBqBirRjKbnuZobG" -l 3
```

- 📦 Pass a transaction hash:
```shell
Tonviewer -H "d04cf57cf372e51704c8c34f8008df397c0a4f1b33bb4008b95e95ce0ba3fbdc"
```

### 📦 Example format response of `Wallet` Method:
```json
{
  "Balance": "0.73280244 TON ≈ $0.949",
  "Status": "active",
  "Is Wallet": true,
  "Last Activity": "2026-02-20 01:34:21 AM",
  "NFT Count": 344,
  "Name": "ddddi.t.me",
  "Icon": "https://cache.tonapi.io/imgproxy/wVVaalJBHOeiyU0Tf_bqX1QQjbvEl5oFOS8OvwIV5Do/rs:fill:200:200:1/g:no/aHR0cHM6Ly90Lm1lL2kvdXNlcnBpYy8zMjAvZGRkZGkuanBn.webp"
}
```
### 📦 Example format response of `Transactions` Method ,
```json
{
  "transactions": [
    {
      "Time": "24 Jan 01:14 AM",
      "Action": "Sent TON",
      "From": "UQBAZ3qWaaoIC8Pq5ELnz2ofYoGN_E3mhzxhE-8EWTpMYgyc",
      "To": "UQCFJEP4WZ_mpdo0_kMEmsTgvrMHG7K_tWY16pQhKHwoOtFz",
      "Paid For": "245 Telegram Stars",
      "Price": "-2.401 TON ≈ 2.98432 $",
      "Limit": "1"
    }
  ],
  "skipped": "Skipped 0 NFT Transactions"
}
```

### 📦 Example Output of `HashTx` Method (`NFT`,`BID`,`TON`,`AUCTION`) .

### ✅ Successful Transaction :
```json
{
  "actions": [
    {
      "Time": "2024-01-28 08:37:32 PM",
      "Action": "SUCCESSFUL TON TRANSFER",
      "From": "UQC7Ptcp7G1IhS2t__alZVlPQF7TtXk7XgsLf-wCBbHMboYF",
      "To": "UQAh_cfG6nAD8EazS3dED8mtQo3bmeGn6nMM8TAZ-9h50k1D",
      "Price": "−19.994 TON ≈ 24.95213 $",
      "Status": "SUCCESS"
    }
  ]
}
```

### ❌ Failed Transaction:
```json
{
  "actions": [
    {
      "Time": "2024-01-28 08:37:32 PM",
      "Action": "FAILED AUCTION BID",
      "From": "UQAh_cfG6nAD8EazS3dED8mtQo3bmeGn6nMM8TAZ-9h50k1D",
      "To": "UQC7Ptcp7G1IhS2t__alZVlPQF7TtXk7XgsLf-wCBbHMboYF",
      "Price": "20.000 TON ≈ 24.96000 $",
      "Status": "FAILED"
    }
  ]
}
```

### ⚠️ Invalid Hash:
```json
{
  "Error": "This doesn't look like a valid transaction address. Where'd you get that?"
}
```

### 💬 Help & Support .
- Follow updates via the **[Telegram Channel](https://t.me/Pycodz)**.
- For general questions and help, join our **[Telegram chat](https://t.me/PyCodz_Chat)**.


