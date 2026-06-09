"""
valas_fetcher.py — Fetch kurs mata uang asing ke IDR
Sumber: Yahoo Finance (USDIDR=X, SGDIDR=X, dst)
Simpan ke Firestore market_data/latest.valas + data/market_latest.json
"""

import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")

# Pasangan mata uang yang dipantau → (ticker Yahoo, nama, simbol)
VALAS_PAIRS = {
    "USD": ("USDIDR=X", "US Dollar",        "$"),
    "SGD": ("SGDIDR=X", "Singapore Dollar", "S$"),
    "EUR": ("EURIDR=X", "Euro",             "€"),
    "JPY": ("JPYIDR=X", "Japanese Yen",     "¥"),
}


def fetch_valas_rates() -> dict:
    """
    Fetch kurs semua mata uang ke IDR via Yahoo Finance.
    Return dict siap simpan ke Firestore / JSON.
    """
    rates = {}
    errors = []

    for code, (ticker, nama, simbol) in VALAS_PAIRS.items():
        try:
            data = yf.Ticker(ticker)
            info = data.fast_info

            # Ambil harga terakhir
            current_rate = float(info.last_price)

            # Harga penutupan kemarin untuk hitung change
            hist = data.history(period="2d")
            if len(hist) >= 2:
                prev_close = float(hist["Close"].iloc[-2])
                change_pct = ((current_rate - prev_close) / prev_close) * 100
            elif len(hist) == 1:
                prev_close = float(hist["Close"].iloc[-1])
                change_pct = 0.0
            else:
                prev_close = current_rate
                change_pct = 0.0

            rates[code] = {
                "code":        code,
                "name":        nama,
                "symbol":      simbol,
                "ticker":      ticker,
                "rate":        round(current_rate, 2),   # 1 unit → IDR
                "prev_close":  round(prev_close, 2),
                "change_pct":  round(change_pct, 4),
                "status":      "ok",
                "fetched_at":  datetime.now(WIB).isoformat(),
            }
            print(f"  [VALAS] {code}/IDR = Rp{current_rate:,.2f} ({change_pct:+.2f}%)")

        except Exception as e:
            print(f"  [VALAS] ERROR fetch {code}: {e}")
            errors.append(code)
            rates[code] = {
                "code":       code,
                "name":       nama,
                "symbol":     simbol,
                "ticker":     ticker,
                "rate":       None,
                "change_pct": None,
                "status":     "error",
                "error_msg":  str(e),
                "fetched_at": datetime.now(WIB).isoformat(),
            }

    return {
        "rates":      rates,
        "fetched_at": datetime.now(WIB).isoformat(),
        "errors":     errors,
        "source":     "Yahoo Finance",
    }


# ── Test standalone ──────────────────────────────────────────────────────
if __name__ == "__main__":
    result = fetch_valas_rates()
    print("\n=== HASIL FETCH ===")
    for code, data in result["rates"].items():
        if data["status"] == "ok":
            print(f"  {code}/IDR : Rp{data['rate']:>12,.2f}  ({data['change_pct']:+.4f}%)")
        else:
            print(f"  {code}/IDR : ERROR — {data.get('error_msg')}")