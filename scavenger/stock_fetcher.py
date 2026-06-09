"""
THE SCAVENGER — Stock Price Fetcher
Sumber: Yahoo Finance via requests (TLS fix untuk Armbian)
"""
import requests
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [SCAVENGER-STOCK] %(message)s')
log = logging.getLogger(__name__)

WATCHLIST = [
    "BBCA.JK",
    "TLKM.JK",
]

def fetch_stock_prices(tickers: list = None) -> dict:
    if tickers is None:
        tickers = WATCHLIST

    result = {
        "source": "yahoo_finance",
        "fetched_at": datetime.now().isoformat(),
        "stocks": {},
        "status": "success",
        "errors": []
    }

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
    })

    log.info(f"Fetching {len(tickers)} saham...")

    for ticker_symbol in tickers:
        code = ticker_symbol.replace(".JK", "")
        try:
            url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker_symbol}"
            params = {"interval": "1d", "range": "2d"}

            resp = session.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()

            meta = data["chart"]["result"][0]["meta"]
            current_price = meta.get("regularMarketPrice") or meta.get("previousClose")
            prev_close = meta.get("previousClose") or meta.get("chartPreviousClose")

            if not current_price:
                raise ValueError("Harga tidak tersedia")

            change = current_price - prev_close
            change_pct = (change / prev_close) * 100 if prev_close else 0

            result["stocks"][code] = {
                "ticker": ticker_symbol,
                "price": round(current_price),
                "prev_close": round(prev_close) if prev_close else None,
                "change": round(change),
                "change_pct": round(change_pct, 2),
                "currency": "IDR"
            }

            arrow = "▲" if change >= 0 else "▼"
            log.info(f"✅ {code}: Rp{round(current_price):,} {arrow}{change_pct:.2f}%")

        except Exception as e:
            result["stocks"][code] = {
                "ticker": ticker_symbol,
                "price": None,
                "status": "error",
                "error": str(e)
            }
            result["errors"].append(f"{code}: {e}")
            log.error(f"❌ {code}: {e}")

    if result["errors"]:
        result["status"] = "partial"

    return result

if __name__ == "__main__":
    data = fetch_stock_prices()
    print(json.dumps(data, indent=2, ensure_ascii=False))
