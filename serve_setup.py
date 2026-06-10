"""Omni-Invest Dashboard Server + API"""
from flask import Flask, send_from_directory, request, jsonify
from flask_cors import CORS
import json, os, sys, threading, time
from pathlib import Path

app = Flask(__name__)
CORS(app)
BASE = "/home/sidrive/omni-invest-dashboard/dist"

# Load env & Firebase
from dotenv import load_dotenv
load_dotenv("/home/sidrive/omni-invest/config/.env")

import firebase_admin
from firebase_admin import credentials, firestore

PROJECT_DIR = os.environ.get("PROJECT_DIR", "/home/sidrive/omni-invest")
LOCAL_PORTFOLIO_PATH = os.path.join(PROJECT_DIR, "config", "portfolio.json")

_pipeline_last_run = 0
_pipeline_running  = False
PIPELINE_COOLDOWN  = 300

def get_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate(os.getenv("FIREBASE_KEY_PATH"))
        firebase_admin.initialize_app(cred)
    return firestore.client()

def _load_portfolio_local() -> dict | None:
    """Baca portfolio dari local JSON — primary source of truth."""
    try:
        if os.path.exists(LOCAL_PORTFOLIO_PATH):
            with open(LOCAL_PORTFOLIO_PATH, "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"[WARN] Gagal baca portfolio lokal: {e}")
    return None

def _save_portfolio_local(portfolio: dict) -> bool:
    """Tulis portfolio ke local JSON — synchronous, source of truth."""
    try:
        os.makedirs(os.path.dirname(LOCAL_PORTFOLIO_PATH), exist_ok=True)
        with open(LOCAL_PORTFOLIO_PATH, "w") as f:
            json.dump(portfolio, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ERROR] Gagal simpan portfolio lokal: {e}")
        return False

def _sync_firestore_async(portfolio: dict):
    """Sync portfolio ke Firestore di background — non-blocking, best effort."""
    def _write():
        try:
            db = get_db()
            db.collection("portfolio").document("main").set(portfolio)
            print("[INFO] Firestore portfolio sync OK")
        except Exception as e:
            print(f"[WARN] Firestore sync gagal (non-critical): {e}")
    threading.Thread(target=_write, daemon=True).start()

def _trigger_pipeline_async():
    """Jalankan pipeline di background setelah transaksi, dengan cooldown 5 menit."""
    global _pipeline_last_run, _pipeline_running

    now = time.time()
    if _pipeline_running:
        print("[INFO] Pipeline sedang berjalan, skip auto-trigger")
        return
    if now - _pipeline_last_run < PIPELINE_COOLDOWN:
        sisa = int(PIPELINE_COOLDOWN - (now - _pipeline_last_run))
        print(f"[INFO] Pipeline cooldown aktif, skip auto-trigger ({sisa}s lagi)")
        return

    def _run():
        global _pipeline_last_run, _pipeline_running
        _pipeline_running = True
        _pipeline_last_run = time.time()
        try:
            print("[INFO] Auto-trigger pipeline setelah transaksi...")
            sys.path.insert(0, PROJECT_DIR)
            from main import run
            run()
            print("[INFO] Auto-trigger pipeline selesai")
        except Exception as e:
            print(f"[WARN] Auto-trigger pipeline error: {e}")
        finally:
            _pipeline_running = False

    threading.Thread(target=_run, daemon=True).start()

# ── API: GET PORTFOLIO ──
@app.route("/api/portfolio", methods=["GET"])
def get_portfolio():
    try:
        # Primary: baca dari local JSON
        data = _load_portfolio_local()
        if data:
            return jsonify({"status": "ok", "data": data})
        # Fallback: baca dari Firestore jika local tidak ada
        db = get_db()
        doc = db.collection("portfolio").document("main").get()
        if doc.exists:
            return jsonify({"status": "ok", "data": doc.to_dict()})
        return jsonify({"status": "error", "message": "Portfolio tidak ditemukan"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ── API: SAVE PORTFOLIO ──
@app.route("/api/portfolio", methods=["POST"])
def save_portfolio():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "Data kosong"}), 400
        # Tulis ke local JSON (synchronous)
        ok = _save_portfolio_local(data)
        if not ok:
            return jsonify({"status": "error", "message": "Gagal simpan portfolio lokal"}), 500
        # Sync ke Firestore (async, non-blocking)
        _sync_firestore_async(data)
        # Sync reksa_mapping dari data portfolio baru
        reksa_list = data.get("reksadana", [])
        _sync_reksa_mapping(reksa_list)
        # Auto-trigger pipeline agar analyst report terupdate
        _trigger_pipeline_async()
        return jsonify({"status": "ok", "message": "Portfolio disimpan. Analyst report sedang diperbarui..."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

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
            "timestamp", direction=firestore.Query.DESCENDING
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

        jenis_aset = data.get("jenis_aset", "")
        kode       = data.get("kode", "")
        aksi       = data.get("aksi", "").upper()
        qty        = float(data.get("qty", 0))
        harga      = float(data.get("harga", 0))

        if not all([jenis_aset, kode, aksi, qty, harga]):
            return jsonify({"status":"error", "message":"Field tidak lengkap"}), 400

        db = get_db()

        # Update portfolio dulu — jika gagal, transaksi tidak disimpan
        ok, msg = _update_portfolio_after_transaction(db, jenis_aset, kode, aksi, qty, harga)
        if not ok:
            return jsonify({"status":"error", "message": msg}), 400

        from datetime import datetime, timezone
        if not data.get("timestamp"):
            data["timestamp"] = datetime.now(timezone.utc).isoformat()
        if not data.get("total"):
            data["total"] = round(qty * harga, 4)
        db.collection("transactions").add(data)

        # Auto-trigger pipeline di background (dengan cooldown)
        _trigger_pipeline_async()

        return jsonify({"status": "ok", "message": f"Transaksi {aksi} {kode} berhasil disimpan. Analyst report sedang diperbarui..."})
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

def _update_portfolio_after_transaction(db, jenis_aset, kode, aksi, qty, harga):
    """Update portfolio lokal setelah transaksi BUY/SELL — tidak pernah baca Firestore."""
    field_map = {
        "saham": {"qty": "qty_lot",   "avg": "avg_buy_price", "list": "saham"},
        "reksa": {"qty": "qty_unit",  "avg": "avg_buy_nab",   "list": "reksadana"},
        "emas":  {"qty": "qty_gram",  "avg": "avg_buy_price", "list": "emas"},
        "valas": {"qty": "qty_unit",  "avg": "avg_buy_rate",  "list": "valas"},
    }
    if jenis_aset not in field_map:
        return False, f"Jenis aset tidak dikenal: {jenis_aset}"

    fields    = field_map[jenis_aset]
    qty_field = fields["qty"]
    avg_field = fields["avg"]
    list_key  = fields["list"]

    # Baca dari local JSON — tidak pernah baca Firestore
    portfolio = _load_portfolio_local()
    if portfolio is None:
        return False, "File portfolio.json tidak ditemukan. Simpan portfolio dulu via Settings."

    asset_list = portfolio.get(list_key, [])

    def match_asset(a):
        if jenis_aset == "valas":
            return a.get("code", "").upper() == kode.upper()
        return a.get("id", "").upper() == kode.upper()

    idx = next((i for i, a in enumerate(asset_list) if match_asset(a)), None)
    if idx is None:
        return False, f"Aset '{kode}' tidak ditemukan di portfolio. Tambah dulu via Settings."

    asset   = asset_list[idx]
    old_qty = float(asset.get(qty_field, 0) or 0)
    old_avg = float(asset.get(avg_field, 0) or 0)

    if aksi == "BUY":
        new_qty = old_qty + qty
        new_avg = harga if old_qty == 0 else (old_qty * old_avg + qty * harga) / new_qty
        if jenis_aset == "saham":
            new_qty = round(new_qty)
            new_avg = round(new_avg, 0)
        elif jenis_aset == "valas":
            new_qty = round(new_qty, 2)
            new_avg = round(new_avg, 4)
        else:
            new_qty = round(new_qty, 4)
            new_avg = round(new_avg, 2)
        asset[qty_field] = new_qty
        asset[avg_field] = new_avg
        asset.pop("status", None)

    elif aksi == "SELL":
        if qty > old_qty:
            return False, f"Qty jual ({qty}) melebihi qty tersedia ({old_qty})"
        new_qty = round(old_qty - qty, 0 if jenis_aset == "saham" else 4)
        asset[qty_field] = new_qty
        if new_qty == 0:
            asset["status"] = "CLOSED"
        else:
            asset.pop("status", None)
    else:
        return False, f"Aksi tidak dikenal: {aksi}"

    asset_list[idx] = asset
    portfolio[list_key] = asset_list

    # Tulis ke local JSON (synchronous)
    ok = _save_portfolio_local(portfolio)
    if not ok:
        return False, "Gagal menyimpan portfolio lokal"

    # Sync ke Firestore (async, non-blocking)
    _sync_firestore_async(portfolio)

    if jenis_aset == "reksa":
        try:
            _sync_reksa_mapping(portfolio.get("reksadana", []))
        except Exception:
            pass

    return True, "Portfolio berhasil diupdate"


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

    threading.Thread(target=warmup, daemon=True).start()

    app.run(host="0.0.0.0", port=4500, debug=False)