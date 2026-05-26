<<<<<<< HEAD
import requests

class Dollers:
    def __init__(self):
        self.url_binance: str = "https://api.binance.com/api/v3/ticker/price"

    def _TON_USDT(self):
        try:
            params = {"symbol": "TONUSDT"}
            res = requests.get(self.url_binance, params=params)
            return float(res.json()["price"])
        except ConnectionResetError as e:
=======
import requests

class Dollers:
    def __init__(self):
        self.url_binance: str = "https://api.binance.com/api/v3/ticker/price"

    def _TON_USDT(self):
        try:
            params = {"symbol": "TONUSDT"}
            res = requests.get(self.url_binance, params=params)
            return float(res.json()["price"])
        except ConnectionResetError as e:
>>>>>>> 5b3efc31ef3ed657ce8ce337dcd5791f8e39f0f5
            return e