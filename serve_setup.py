"""Omni-Invest Dashboard Server + API"""
from flask import Flask, send_from_directory, request, jsonify
from flask_cors import CORS
import json, os, sys
from pathlib import Path

app = Flask(__name__)
CORS(app)
BASE = "/home/sidrive/omni-invest-dashboard/dist"

# Load env & Firebase
from dotenv import load_dotenv
load_dotenv("/home/sidrive/omni-invest/config/.env")

import firebase_admin
from firebase_admin import credentials, firestore

def get_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate(os.getenv("FIREBASE_KEY_PATH"))
        firebase_admin.initialize_app(cred)
    return firestore.client()

# ── API: GET PORTFOLIO ──
@app.route("/api/portfolio", methods=["GET"])
def get_portfolio():
    try:
        db = get_db()
        doc = db.collection("portfolio").document("main").get()
        if doc.exists:
            return jsonify({"status":"ok", "data": doc.to_dict()})
        return jsonify({"status":"error", "message":"Portfolio tidak ditemukan"}), 404
    except Exception as e:
        return jsonify({"status":"error", "message":str(e)}), 500

# ── API: SAVE PORTFOLIO ──
@app.route("/api/portfolio", methods=["POST"])
def save_portfolio():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status":"error", "message":"Data kosong"}), 400
        db = get_db()
        db.collection("portfolio").document("main").set(data)
    except Exception as e:
        return jsonify({"status":"error", "message":str(e)}), 500

    try:
        with open("/home/sidrive/omni-invest/config/portfolio.json", "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        app.logger.warning(f"Cache lokal gagal ditulis: {e}")

    # Sync REKSA_MAPPING dari portfolio
    reksa_list = data.get("reksadana", [])
    _sync_reksa_mapping(reksa_list)
    return jsonify({"status":"ok", "message":"Portfolio berhasil disimpan"})

# ── API: GET MARKET DATA ──
@app.route("/api/market", methods=["GET"])
def get_market():
    try:
        db = get_db()
        doc = db.collection("market_data").document("latest").get()
        if doc.exists:
            return jsonify({"status":"ok", "data": doc.to_dict()})
        return jsonify({"status":"error", "message":"Data market tidak ditemukan"}), 404
    except Exception as e:
        return jsonify({"status":"error", "message":str(e)}), 500

# ── API: GET ANALYST REPORT ──
@app.route("/api/report", methods=["GET"])
def get_report():
    try:
        db = get_db()
        doc = db.collection("analyst_report").document("latest").get()
        if doc.exists:
            return jsonify({"status":"ok", "data": doc.to_dict()})
        return jsonify({"status":"error", "message":"Report tidak ditemukan"}), 404
    except Exception as e:
        return jsonify({"status":"error", "message":str(e)}), 500

# ── API: GET TRANSACTIONS ──
@app.route("/api/transactions", methods=["GET"])
def get_transactions():
    try:
        db = get_db()
        docs = db.collection("transactions").order_by(
            "tanggal", direction=firestore.Query.DESCENDING
        ).limit(50).stream()
        txs = [{"id": d.id, **d.to_dict()} for d in docs]
        return jsonify({"status":"ok", "data": txs})
    except Exception as e:
        return jsonify({"status":"error", "message":str(e)}), 500

# ── API: SAVE TRANSACTION ──
@app.route("/api/transactions", methods=["POST"])
def save_transaction():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status":"error", "message":"Data kosong"}), 400
        db = get_db()
        db.collection("transactions").add(data)
        return jsonify({"status":"ok", "message":"Transaksi disimpan"})
    except Exception as e:
        return jsonify({"status":"error", "message":str(e)}), 500

# ── API: RUN PIPELINE ──
@app.route("/api/run", methods=["POST"])
def run_pipeline():
    try:
        sys.path.insert(0, "/home/sidrive/omni-invest")
        from main import run
        run()
        return jsonify({"status":"ok", "message":"Pipeline selesai"})
    except Exception as e:
        return jsonify({"status":"error", "message":str(e)}), 500
      
# ── API: GET WATCHLIST ──
@app.route("/api/watchlist", methods=["GET"])
def get_watchlist():
    try:
        import json
        # Baca langsung dari file scavenger
        stock_path = "/home/sidrive/omni-invest/scavenger/stock_fetcher.py"
        reksa_path = "/home/sidrive/omni-invest/scavenger/reksa_fetcher.py"

        # Load watchlist dari Firestore (lebih reliable)
        db = get_db()
        doc = db.collection("config").document("watchlist").get()
        if doc.exists:
            return jsonify({"status": "ok", "data": doc.to_dict()})

        # Fallback default
        return jsonify({"status": "ok", "data": {
            "saham": ["BBCA.JK", "BBRI.JK", "TLKM.JK"],
            "reksa": []
        }})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ── API: SAVE WATCHLIST ──
@app.route("/api/watchlist", methods=["POST"])
def save_watchlist():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "Data kosong"}), 400

        db = get_db()
        db.collection("config").document("watchlist").set(data)

        # Update file stock_fetcher.py
        saham_list = data.get("saham", [])
        _update_stock_fetcher(saham_list)

        return jsonify({"status": "ok", "message": "Watchlist berhasil disimpan"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ── API: VALIDATE TICKER ──
@app.route("/api/validate-ticker", methods=["POST"])
def validate_ticker():
    try:
        data = request.get_json()
        ticker = data.get("ticker", "").upper()
        if not ticker.endswith(".JK"):
            ticker += ".JK"

        import requests as req
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = req.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        result = r.json()

        meta = result["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice")
        name  = meta.get("longName") or meta.get("shortName") or ticker

        return jsonify({
            "status"  : "ok",
            "valid"   : True,
            "ticker"  : ticker,
            "name"    : name,
            "price"   : price
        })
    except Exception as e:
        return jsonify({
            "status" : "ok",
            "valid"  : False,
            "message": f"Ticker tidak valid: {str(e)}"
        })

def _update_stock_fetcher(saham_list: list):
    """Update WATCHLIST di stock_fetcher.py"""
    path = "/home/sidrive/omni-invest/scavenger/stock_fetcher.py"
    with open(path, "r") as f:
        content = f.read()

    # Buat string baru untuk WATCHLIST
    items = ',\n    '.join([f'"{s["kode"]}"' for s in saham_list if s.get("kode")])
    new_watchlist = f'WATCHLIST = [\n    {items},\n]'

    # Replace baris WATCHLIST yang lama
    import re
    content = re.sub(
        r'WATCHLIST\s*=\s*\[.*?\]',
        new_watchlist,
        content,
        flags=re.DOTALL
    )

    with open(path, "w") as f:
        f.write(content)

def _sync_reksa_mapping(reksa_list: list):
    """Sync REKSA_MAPPING ke config/reksa_mapping.json dari data portfolio"""
    import re
    path = Path("/home/sidrive/omni-invest/config/reksa_mapping.json")

    existing = {}
    if path.exists():
        with open(path) as f:
            existing = json.load(f)

    for r in reksa_list:
        rd_code = r.get("rd_code", "").strip().upper()
        kode_id = r.get("id", "").strip().upper()
        nama    = r.get("nama", "").strip()
        if not rd_code or not kode_id:
            continue
        slug = nama.lower()
        slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
        existing[kode_id] = {
            "rd_code":      rd_code,
            "slug":         slug,
            "nama_display": nama,
            "jenis":        "unknown"
        }

    with open(path, "w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    app.logger.info(f"[reksa] REKSA_MAPPING synced: {len(existing)} entri → reksa_mapping.json")

# ── API: GOLD HISTORY ──
@app.route("/api/gold-history", methods=["GET"])
def get_gold_history():
    try:
        import json
        from pathlib import Path
        history_path = Path("/home/sidrive/omni-invest/data/gold_history.json")
        if history_path.exists():
            with open(history_path) as f:
                history = json.load(f)
            return jsonify({"status": "ok", "data": history})
        return jsonify({"status": "ok", "data": []})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ── STATIC FILES & SPA FALLBACK ──
# PENTING: route ini harus paling bawah, setelah semua /api/* routes
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    # Jangan tangkap /api/* di sini
    if path.startswith("api/"):
        return jsonify({"status":"error", "message":"Not found"}), 404

    # Cek apakah file statis ada (js, css, png, dll)
    full_path = os.path.join(BASE, path)
    if path and os.path.isfile(full_path):
        return send_from_directory(BASE, path)

    # Semua route Vue (/, /portfolio, /alerts, dll) → index.html
    return send_from_directory(BASE, "index.html")


if __name__ == "__main__":
    print("🌐 Dashboard : http://192.168.192.81:4500")
    print("🔌 API Base  : http://192.168.192.81:4500/api/")

    # Pre-warm Firebase saat server start
    def warmup():
        import time
        time.sleep(2)
        try:
            db = get_db()
            db.collection("market_data").document("latest").get()
            print("✅ Firebase pre-warmed!")
        except Exception as e:
            print(f"⚠️  Warmup warning: {e}")

    import threading
    threading.Thread(target=warmup, daemon=True).start()

    app.run(host="0.0.0.0", port=4500, debug=False)