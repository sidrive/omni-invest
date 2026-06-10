# OMNI-INVEST SENTINEL — BACKEND CONTEXT

> Dokumen ini adalah referensi lengkap untuk AI assistant (Claude) saat membantu development backend Python Omni-Invest.
> Last updated: 2026-06-10

---

## 🎯 GAMBARAN SISTEM

Pipeline investasi otomatis yang berjalan di STB Armbian S905x. Tiga fase berurutan:

```
Scavenger → Analyst → Messenger
```

- **Scavenger** — fetch harga pasar dari berbagai sumber (scraping + API)
- **Analyst** — kalkulasi P&L, sinyal beli/jual, analisis alokasi aset
- **Messenger** — kirim push notification via FCM jika ada sinyal aktif

**Flask server** (`serve_setup.py`) menyajikan REST API untuk dashboard Vue.js sekaligus meng-host file dist statis di port 4500.

---

## 🏗️ ARSITEKTUR & ENVIRONMENT

```
STB Armbian S905x — IP 192.168.192.81
├── Port 4500           → Flask server (PM2: omni-dashboard)
├── Python env          → /home/sidrive/omni-invest/venv/
├── Project dir         → /home/sidrive/omni-invest/
└── Dashboard dist      → /home/sidrive/omni-invest-dashboard/dist/

Cron schedule : 0 9-16 * * 1-5   (weekdays jam 09–16 WIB)
Process manager: PM2 (Flask) + Cron (pipeline)
```

**Stack:**

| Komponen | Teknologi |
|---|---|
| Web framework | Flask + Flask-CORS |
| Database | Firebase Firestore |
| Push notification | FCM V1 |
| Data pasar | Yahoo Finance (`yfinance`), Bibit API, scraping logammulia.com |
| Scheduler | Cron (pipeline otomatis) |

---

## 📁 STRUKTUR FILE

```
omni-invest/
├── main.py                          ← Orchestrator: Scavenger → Analyst → Messenger
├── serve_setup.py                   ← Flask server + semua API endpoints
├── config/
│   ├── .env                         ← IGNORED di git
│   ├── firebase-key.json            ← IGNORED di git
│   ├── portfolio.json               ← IGNORED di git (cache lokal, auto-dibuat dari Firestore)
│   ├── reksa_mapping.json           ← IGNORED di git (auto-dibuat saat POST /api/portfolio)
│   ├── portfolio.example.json       ← Template struktur, ikut di git
│   └── reksa_mapping.example.json  ← Template struktur, ikut di git
├── scavenger/
│   ├── runner.py                    ← Koordinator fetch semua aset
│   ├── gold_fetcher.py              ← Scraping logammulia.com
│   ├── stock_fetcher.py             ← Yahoo Finance (WATCHLIST = array string ["KODE.JK"])
│   ├── reksa_fetcher.py             ← Bibit API, baca REKSA_MAPPING dari reksa_mapping.json
│   └── valas_fetcher.py             ← Yahoo Finance (USDIDR=X, SGDIDR=X, EURIDR=X, JPYIDR=X)
├── analyst/
│   └── engine.py                    ← Kalkulasi P&L, sinyal S/R, alokasi
├── messenger/
│   └── fcm_sender.py                ← FCM V1 push notification
├── data/                            ← IGNORED di git (semua runtime)
│   ├── market_latest.json
│   └── gold_history.json
└── logs/                            ← IGNORED di git
    ├── sentinel.log
    └── cron.log
```

---

## 🔌 API ENDPOINTS

Semua endpoint didefinisikan di `serve_setup.py`. Base URL: `http://192.168.192.81:4500`

| Method | Endpoint | Fungsi |
|---|---|---|
| GET | `/api/portfolio` | Ambil portfolio dari Firestore |
| POST | `/api/portfolio` | Simpan ke Firestore + tulis cache `portfolio.json` + sync `reksa_mapping.json` |
| GET | `/api/market` | Data market terbaru dari Firestore |
| GET | `/api/report` | Analyst report + sinyal dari Firestore |
| GET | `/api/transactions` | Riwayat transaksi (limit 50, descending) |
| POST | `/api/transactions` | Tambah transaksi baru |
| POST | `/api/run` | Trigger pipeline manual |
| GET | `/api/gold-history` | Baca `data/gold_history.json` |
| GET | `/api/watchlist` | Baca dari Firestore `config/watchlist` |
| POST | `/api/watchlist` | Simpan watchlist + update `WATCHLIST` di `stock_fetcher.py` |
| POST | `/api/validate-ticker` | Validasi ticker saham via Yahoo Finance |

### Struktur Response

Semua endpoint mengembalikan format `{"status": "ok"|"error", "data": ..., "message": ...}`.

```python
# GET /api/portfolio → data
{
  "emas":      [{ "id", "nama", "qty_gram", "avg_buy_price", "catatan" }],
  "saham":     [{ "id", "nama", "qty_lot", "avg_buy_price", "support", "resistance", "stop_loss", "catatan" }],
  "reksadana": [{ "id", "nama", "qty_unit", "avg_buy_nab", "rd_code", "catatan" }],
  "valas":     [{ "id", "code", "nama", "qty_unit", "avg_buy_rate", "catatan" }],
  "target_allocation": { "emas": int, "saham": int, "reksa": int }  # key "reksa"!
}

# GET /api/market → data
{
  "fetched_at": "ISO string",
  "emas":      { "antam_per_gram", "price", "change_pct" },
  "saham":     { "stocks": { "BBCA.JK": { "price", "change_pct" } } },
  "reksadana": {
    "reksa_dana": { "KODE_INTERNAL": { "current_nab", "nama", "jenis", "nav_date", "source" } },
    "summary":    { "total", "ok", "failed", "cached" }
  },
  "valas": { "rates": { "USD": { "rate", "change_pct", "status", "symbol" } } }
}

# GET /api/report → data
{
  "analyzed_at": "ISO string",
  "summary":    { "total_modal", "total_nilai", "total_pl", "total_pl_pct" },
  "emas":       { "items": [...], "total_modal", "total_nilai", "total_pl", "total_pl_pct" },
  "saham":      { "items": [...], "total_modal", "total_nilai", "total_pl", "total_pl_pct" },
  "reksadana":  { "items": [...], "total_modal", "total_nilai", "total_pl", "total_pl_pct" },
  "valas":      { "items": [...], "total_modal", "total_nilai", "total_pl", "total_pl_pct" },
  "alokasi": {
    "total_aset": number,
    "target":     { "emas", "saham", "reksa" },           # key "reksa" di target
    "aktual":     { "emas", "saham", "reksadana", "valas" },  # key "reksadana" di aktual
    "rekomendasi": [{ "action", "asset", "actual", "target" }]  # ARRAY OBJECT, bukan string!
  },
  "signals":       [{ "type", "aset", "harga", "alasan", "priority", "timestamp" }],
  "total_signals": int
}
```

---

## 🗄️ FIRESTORE COLLECTIONS

| Collection | Document | Isi |
|---|---|---|
| `market_data` | `latest` | Harga emas, saham, reksadana, valas — di-update tiap Scavenger |
| `analyst_report` | `latest` | P&L, sinyal, alokasi — di-update tiap pipeline selesai |
| `portfolio` | `main` | Data aset user — single source of truth |
| `transactions` | auto-id | Riwayat transaksi, di-query order by `tanggal` DESC limit 50 |
| `config` | `watchlist` | Daftar saham dipantau: `{ "saham": [...], "reksa": [...] }` |

---

## 💰 ASET YANG DIDUKUNG

### 🥇 Emas

- **Source:** Scraping `logammulia.com`
- **Field harga:** `antam_per_gram` (harga per gram, bukan per batang)
- **Kalkulasi modal:** `qty_gram × avg_buy_price`
- **`avg_buy_price`** = harga **per gram** (Rp/gram) — **BUKAN total modal yang dikeluarkan**
- **Pitfall scraping:** Gunakan `==` bukan `in` untuk match nama row di tabel HTML — substring menyebabkan false-positive

### 📈 Saham

- **Source:** Yahoo Finance via `yfinance`
- **Ticker format:** `BBCA.JK`, `BBRI.JK` (suffix `.JK` wajib untuk saham IDX)
- **`WATCHLIST`** di `stock_fetcher.py` = **array string** `["BBCA.JK", ...]` — **BUKAN array dict**
- **Kalkulasi modal:** `qty_lot × 100 × avg_buy_price` (1 lot = 100 lembar, `LOT_SIZE = 100`)

### 🏦 Reksa Dana

- **Source:** Bibit API
  - Primary: scraping HTML `bibit.id/reksadana/<rd_code>/<slug>` via `__NEXT_DATA__` → NAV per unit yang akurat
  - Fallback: `api.bibit.id/products/<rd_code>/simulations?range=120` → `data[-1]` (NAB bukan per unit)
- **`rd_code` format:** `RD562`, `RD424` — dari URL `bibit.id/reksadana/RD562/nama-reksa`
- **`REKSA_MAPPING`** dibaca dari `config/reksa_mapping.json` — **BUKAN hardcoded di reksa_fetcher.py**
- **Sumber mapping:** di-generate otomatis dari data portfolio saat `POST /api/portfolio`
- **Kalkulasi modal:** `qty_unit × avg_buy_nab`
- **Field NAB di market data:** `current_nab` (bukan `nab`)

### 💱 Valas

- **Source:** Yahoo Finance
- **Tickers:** `USDIDR=X`, `SGDIDR=X`, `EURIDR=X`, `JPYIDR=X`
- **Mata uang didukung:** USD, SGD, EUR, JPY
- **`avg_buy_rate`** = kurs IDR saat beli — **BUKAN total modal dalam IDR**
- **JPY:** `qty_unit` tanpa desimal (bilangan bulat)
- **Signal valas:** `BUY` | `HOLD` | `SELL_PARTIAL` | `STOPLOSS` | `DATA_ERROR`

---

## 🧮 ANALYST ENGINE (`analyst/engine.py`)

### Kalkulasi P&L

```python
# Saham
modal  = qty_lot × 100 × avg_buy_price   # LOT_SIZE = 100
nilai  = qty_lot × 100 × market_price

# Emas
modal  = qty_gram × avg_buy_price        # avg_buy_price = harga Rp/gram
nilai  = qty_gram × market_price

# Reksa Dana
modal  = qty_unit × avg_buy_nab
nilai  = qty_unit × current_nab          # current_nab dari market_latest.json

# Valas
modal  = qty_unit × avg_buy_rate
nilai  = qty_unit × current_rate

# Semua aset:
pl     = nilai - modal
pl_pct = (pl / modal) × 100
```

### Signal Logic

| Signal | Kondisi | Priority | Aset |
|---|---|---|---|
| `BUY` | `market_price <= support` | high | Saham |
| `AVG_DOWN` | harga turun ≥ `PRICE_DROP_THRESHOLD`% dari avg buy | high | Saham |
| `SELL` | `market_price >= resistance` | medium | Saham |
| `STOPLOSS` | `market_price <= stop_loss` | critical | Saham |
| `REBALANCE` | alokasi emas > `GOLD_MAX_ALLOCATION`% | medium | Emas |
| `DCA` | selalu (reksa dana tidak punya level S/R) | normal | Reksa Dana |
| `BUY` | kurs harian turun ≤ `VALAS_BUY_THRESHOLD` (−1.5%) | high | Valas |
| `SELL_PARTIAL` | kurs harian naik ≥ `VALAS_SELL_THRESHOLD` (+2.0%) | medium | Valas |
| `STOPLOSS` | P&L posisi ≤ `VALAS_SL_THRESHOLD` (−5.0%) | critical | Valas |
| `DATA_ERROR` | gagal fetch kurs dari Yahoo Finance | high | Valas |

### Rekomendasi Alokasi

```python
# Threshold (target diambil dari portfolio.target_allocation di Firestore)
# key di target_allocation = "reksa" (BUKAN "reksadana")

Emas  : aktual > GOLD_MAX_ALLOCATION  → action: "KURANG"
Saham : aktual < target.saham - 5    → action: "TAMBAH"
Reksa : aktual > target.reksa + 5    → action: "KURANG"
Reksa : aktual < target.reksa - 5    → action: "TAMBAH"

# Format rekomendasi — ARRAY OBJECT, bukan string:
{ "action": "KURANG"|"TAMBAH", "asset": "Emas"|"Saham"|"Reksa Dana",
  "actual": float, "target": float }
```

### Data Loading

```python
# _load_portfolio() — urutan prioritas:
# 1. Firestore  → berhasil → tulis cache portfolio.json → return data
# 2. Fallback   → baca config/portfolio.json (cache lokal)
# 3. Keduanya gagal → Exception dengan pesan jelas, pipeline berhenti

# _load_market() — baca file lokal:
path = Path(os.getenv("DATA_DIR", "~/omni-invest/data")).expanduser() / "market_latest.json"
# File ini ditulis Scavenger sebelum Analyst dijalankan
```

---

## 🔄 ALUR PIPELINE (`main.py`)

```python
def run():
    # Phase 1: Scavenger
    market_data = run_scavenger()
    # → fetch semua harga → simpan ke data/market_latest.json + Firestore market_data/latest

    # Phase 2: Analyst
    analyst = Analyst()
    report  = analyst.run()
    # → baca portfolio + market data → kalkulasi P&L & sinyal → simpan ke Firestore analyst_report/latest

    # Phase 3: Messenger
    if report["signals"]:
        send_signals(report["signals"])   # kirim FCM tiap sinyal aktif
    if datetime.now().hour == 16:
        send_daily_summary(report)        # summary harian hanya jam 16:00
```

**Cara trigger pipeline:**
- `POST /api/run` — via API (dari dashboard)
- `python3 main.py` — langsung di terminal STB

---

## 🔧 FUNGSI HELPER DI `serve_setup.py`

### `_sync_reksa_mapping(reksa_list)`

Dipanggil otomatis setiap `POST /api/portfolio`. Menulis `config/reksa_mapping.json` berdasarkan daftar reksadana di portfolio.

```python
# Input : reksa_list dari portfolio["reksadana"]
#         Setiap item butuh field: rd_code, id, nama
# Output: config/reksa_mapping.json diperbarui (merge, tidak overwrite semua)
# Dibaca: reksa_fetcher.py saat fetch NAB, tidak lagi hardcoded di .py

# Format reksa_mapping.json:
{
  "KODE_INTERNAL": {
    "rd_code": "RD562",
    "slug": "bri-indeks-syariah",
    "nama_display": "BRI Indeks Syariah",
    "jenis": "unknown"
  }
}
```

### `_update_stock_fetcher(saham_list)`

Dipanggil saat `POST /api/watchlist`. Menulis ulang variabel `WATCHLIST` di `stock_fetcher.py` via regex replace.

```python
# Input : saham_list dari watchlist["saham"], setiap item butuh field: kode
# Output: WATCHLIST = ["BBCA.JK", "BBRI.JK", ...] di stock_fetcher.py
# Penting: hasil harus array string, BUKAN array dict
```

### `save_portfolio()` — Urutan Operasi

```python
# 1. Firestore .set(data)  → UTAMA, fatal jika gagal (return 500)
# 2. Tulis portfolio.json  → best effort, gagal hanya log warning (Firestore sudah aman)
# 3. _sync_reksa_mapping() → sinkronisasi reksa_mapping.json dari data portfolio baru
```

### `get_db()`

Lazy-init Firebase Admin SDK. Memeriksa `firebase_admin._apps` terlebih dulu agar tidak double-initialize.

---

## ⚙️ ENVIRONMENT VARIABLES (`config/.env`)

| Variable | Contoh Nilai | Keterangan |
|---|---|---|
| `FIREBASE_KEY_PATH` | `/home/sidrive/omni-invest/config/firebase-key.json` | Path ke service account key |
| `DATA_DIR` | `/home/sidrive/omni-invest/data` | Direktori `market_latest.json` & `gold_history.json` |
| `LOG_DIR` | `/home/sidrive/omni-invest/logs` | Direktori log files |
| `PRICE_DROP_THRESHOLD` | `5` | % penurunan dari avg buy untuk trigger AVG_DOWN |
| `GOLD_MAX_ALLOCATION` | `30` | % maks alokasi emas sebelum trigger REBALANCE |

---

## 🐛 KNOWN ISSUES & WORKAROUND

### Firestore 504 Deadline Exceeded

- **Sebab:** IPv6-related issue pada STB Armbian S905x (sudah di-disable via `sysctl`, masih kadang terjadi)
- **Workaround:** `_load_portfolio()` di `engine.py` fallback ke `config/portfolio.json`
- **Cache selalu fresh:** Setiap kali Firestore berhasil diakses, cache langsung diperbarui

### Report Tidak Terupdate Setelah Edit Portfolio

- `/api/report` membaca hasil pipeline terakhir dari Firestore — bukan real-time
- Perubahan portfolio tidak otomatis men-trigger pipeline
- **Solusi:** Jalankan `POST /api/run` atau `python3 main.py` setelah edit portfolio

### SPA Routing — Route Order di Flask

`serve_spa()` menangkap semua path yang tidak cocok. Route `/api/*` **harus** didefinisikan lebih dulu dalam `serve_setup.py` karena Flask mencocokkan route secara urutan — catch-all `/<path:path>` selalu paling bawah.

---

## 🚀 CARA MENJALANKAN

```bash
# Aktivasi venv
cd /home/sidrive/omni-invest
source venv/bin/activate

# Jalankan pipeline sekali (manual)
python3 main.py

# Test import modul
python3 -c "from scavenger.reksa_fetcher import fetch_all_reksa; print('OK')"
python3 -c "from analyst.engine import Analyst; print('OK')"
python3 -c "from scavenger.runner import run_scavenger; print('OK')"

# Monitor log realtime
tail -f logs/sentinel.log
tail -f logs/cron.log

# PM2 — Flask server
pm2 status
pm2 restart omni-dashboard
pm2 logs omni-dashboard --lines 30
```

---

## 📋 ATURAN PENTING UNTUK AI

1. **Jangan hardcode path** — gunakan `Path(__file__).parent` untuk path relatif, atau `os.getenv()` untuk path dari environment
2. **Selalu `try/except`** di semua fungsi yang akses Firestore atau file I/O
3. **Jangan modifikasi `.py` file dari runtime** — semua data dinamis masuk ke `.json`
4. **`WATCHLIST`** di `stock_fetcher.py` = array string `["KODE.JK"]` — **BUKAN array dict**
5. **`avg_buy_price` emas** = harga per gram (Rp/gram) — **BUKAN total modal**
6. **`rd_code`** format `"RD562"` — diambil dari URL `bibit.id/reksadana/RD562/nama-reksa`
7. **`alokasi.rekomendasi`** = array object `{action, asset, actual, target}` — **BUKAN array string**
8. **`target_allocation`** di Firestore/portfolio menggunakan key `"reksa"` (bukan `"reksadana"`)
9. **`savePortfolio` payload** harus include **semua key**: `emas`, `saham`, `reksadana`, `valas`, `target_allocation` — key yang hilang akan di-overwrite kosong di Firestore
10. **`config/portfolio.json` dan `reksa_mapping.json`** tidak boleh di-commit ke git — sudah ada di `.gitignore`
11. **Firestore = single source of truth** — jangan tulis data langsung ke `portfolio.json`, selalu via `POST /api/portfolio`
12. **`current_nab`** adalah nama field NAB reksa dana di market data — bukan `nab`
13. **JPY qty** = bilangan bulat tanpa desimal; valas lain boleh 2 desimal
14. **`avg_buy_rate` valas** = kurs IDR saat beli, bukan total modal dalam IDR
15. **Flask SPA catch-all** — route `/<path:path>` harus selalu **paling bawah** di `serve_setup.py`

---

## 📦 DEPENDENCIES UTAMA (`requirements.txt`)

| Package | Versi | Kegunaan |
|---|---|---|
| `firebase-admin` | 7.4.0 | Firestore client + FCM |
| `google-cloud-firestore` | 2.27.0 | Firestore SDK |
| `yfinance` | 1.3.0 | Harga saham & kurs valas |
| `requests` | 2.33.1 | HTTP ke Bibit API & logammulia |
| `beautifulsoup4` | 4.14.3 | Parsing HTML scraping emas |
| `lxml` | 6.1.0 | HTML parser backend untuk BeautifulSoup |
| `python-dotenv` | 1.2.2 | Load `config/.env` |
| `flask` | — | Web framework API + SPA host |
| `flask-cors` | — | CORS untuk request dari Vue dev server |

---

_Last updated: 2026-06-10_
_Stack: Python Flask + Firebase Firestore + FCM_
_Server: Armbian S905x STB — IP: 192.168.192.81, Port: 4500_
_Pipeline: Scavenger (fetch) → Analyst (kalkulasi) → Messenger (FCM)_
_Aset: Emas, Saham (IDX), Reksa Dana (Bibit), Valas (USD/SGD/EUR/JPY)_
