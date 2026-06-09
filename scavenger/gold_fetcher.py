"""
THE SCAVENGER — Gold Price Fetcher
Sumber: logammulia.com
"""
import requests
from bs4 import BeautifulSoup
import json
import logging
from datetime import datetime
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [SCAVENGER-GOLD] %(message)s')
log = logging.getLogger(__name__)

def fetch_gold_price() -> dict:
    """Ambil harga emas Antam + hitung change dari kemarin"""
    import json
    from pathlib import Path

    result = {
        "source": "logammulia.com",
        "fetched_at": datetime.now().isoformat(),
        "antam_per_gram": None,
        "buyback_per_gram": None,
        "prev_price": None,
        "change": None,
        "change_pct": None,
        "status": "error",
        "error": None
    }

    # Load harga kemarin dari file lokal
    history_path = Path.home() / "omni-invest/data/gold_history.json"
    prev_price = None
    history = []

    if history_path.exists():
        try:
            with open(history_path) as f:
                history = json.load(f)
            if history:
                prev_price = history[-1].get("price")
        except Exception:
            pass

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    try:
        log.info("Fetching harga emas dari logammulia.com...")
        response = requests.get(
            "https://www.logammulia.com/id/harga-emas-hari-ini",
            headers=headers,
            timeout=15
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 2:
                    text = cols[0].get_text(strip=True)
                    if text.lower().strip() == "1 gr":
                        price_text = cols[1].get_text(strip=True)
                        price_text = price_text.replace("Rp","").replace(".","").replace(",","").strip()
                        if price_text.isdigit():
                            result["antam_per_gram"] = int(price_text)
                            break

        if not result["antam_per_gram"]:
            price_elements = soup.find_all(
                class_=lambda c: c and "price" in c.lower()
            )
            for el in price_elements:
                text = el.get_text(strip=True).replace("Rp","").replace(".","").replace(",","").strip()
                if text.isdigit() and 900000 < int(text) < 5000000:
                    result["antam_per_gram"] = int(text)
                    break

        if result["antam_per_gram"]:
            current = result["antam_per_gram"]
            result["status"] = "success"

            # Hitung change dari harga kemarin
            if prev_price and prev_price != current:
                change = current - prev_price
                change_pct = round((change / prev_price) * 100, 2)
                result["prev_price"] = prev_price
                result["change"] = change
                result["change_pct"] = change_pct
            else:
                result["prev_price"] = prev_price or current
                result["change"] = 0
                result["change_pct"] = 0.0

            # Simpan ke history (max 30 hari)
            today = datetime.now().strftime("%Y-%m-%d")
            # Hindari duplikat hari yang sama
            history = [h for h in history if h.get("date") != today]
            history.append({
                "date": today,
                "price": current
            })
            # Keep max 30 data points
            history = history[-30:]

            history_path.parent.mkdir(parents=True, exist_ok=True)
            with open(history_path, "w") as f:
                json.dump(history, f, indent=2)

            log.info(f"✅ Emas: Rp{current:,}/gram | change: {result['change_pct']}%")
        else:
            result["antam_per_gram"] = 1089000
            result["change_pct"] = 0.0
            result["status"] = "fallback"
            log.warning("⚠️ Scraping gagal, menggunakan harga fallback")

    except Exception as e:
        result["error"] = str(e)
        result["antam_per_gram"] = 1089000
        result["change_pct"] = 0.0
        result["status"] = "fallback"
        log.error(f"❌ Error: {e}")

    return result


if __name__ == "__main__":
    data = fetch_gold_price()
    print(json.dumps(data, indent=2, ensure_ascii=False))
