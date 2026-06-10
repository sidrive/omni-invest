"""
THE ANALYST — Business Logic Engine
Kalkulasi P&L, Support/Resistance, Alokasi Aset
"""
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "config" / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ANALYST] %(message)s"
)
log = logging.getLogger(__name__)

# Constants
LOT_SIZE = 100  # 1 lot = 100 lembar saham

# Threshold sinyal valas
VALAS_SELL_THRESHOLD =  2.0   # % kenaikan kurs harian → pertimbangkan konversi
VALAS_BUY_THRESHOLD  = -1.5   # % penurunan kurs harian → peluang beli valas
VALAS_SL_THRESHOLD   = -5.0   # % P&L posisi → stop loss

class Analyst:
    def __init__(self):
        self.portfolio  = self._load_portfolio()
        self.market     = self._load_market()
        self.signals    = []
        self.report     = {}

    def _load_portfolio(self) -> dict:
        """Load portfolio dari Firestore (prioritas) atau file lokal (fallback)"""
        cache_path = Path(__file__).parent.parent / "config" / "portfolio.json"
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore as fs
            if not firebase_admin._apps:
                key_path = os.getenv("FIREBASE_KEY_PATH")
                cred = credentials.Certificate(key_path)
                firebase_admin.initialize_app(cred)
            db = fs.client()
            doc = db.collection("portfolio").document("main").get()
            if doc.exists:
                data = doc.to_dict()
                log.info("✅ Portfolio loaded dari Firestore")
                try:
                    with open(cache_path, "w") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                except Exception as cache_err:
                    log.warning(f"⚠️ Gagal tulis cache portfolio.json: {cache_err}")
                return data
            raise ValueError("Portfolio tidak ada di Firestore")
        except Exception as e:
            log.warning(f"⚠️ Firestore fallback ke file lokal: {e}")
            if not cache_path.exists():
                raise Exception(
                    "Portfolio tidak tersedia. Jalankan pipeline "
                    "saat koneksi Firestore aktif untuk membuat cache lokal."
                )
            with open(cache_path) as f:
                return json.load(f)

    def _load_market(self) -> dict:
        path = Path(os.getenv("DATA_DIR", "~/omni-invest/data")).expanduser()
        path = path / "market_latest.json"
        with open(path) as f:
            return json.load(f)

    # ─────────────────────────────────────────
    # KALKULASI EMAS
    # ─────────────────────────────────────────
    def analyze_gold(self) -> dict:
        log.info("🥇 Analyzing emas...")
        hasil = []
        total_nilai = 0
        total_modal = 0

        market_price = self.market["emas"].get("antam_per_gram", 0)

        for item in self.portfolio["emas"]:
            qty   = item["qty_gram"]
            avg   = item["avg_buy_price"]
            modal = qty * avg
            nilai = qty * market_price
            pl    = nilai - modal
            pl_pct = (pl / modal * 100) if modal > 0 else 0

            total_modal += modal
            total_nilai += nilai

            hasil.append({
                "id"          : item["id"],
                "nama"        : item["nama"],
                "qty_gram"    : qty,
                "avg_buy"     : avg,
                "market_price": market_price,
                "modal"       : modal,
                "nilai_pasar" : nilai,
                "pl"          : round(pl),
                "pl_pct"      : round(pl_pct, 2),
                "signal"      : "HOLD"
            })

            log.info(f"  {item['nama']}: P&L Rp{pl:,.0f} ({pl_pct:.2f}%)")

        return {
            "items"      : hasil,
            "total_modal": total_modal,
            "total_nilai": total_nilai,
            "total_pl"   : total_nilai - total_modal,
            "total_pl_pct": round((total_nilai - total_modal) / total_modal * 100, 2) if total_modal else 0
        }

    # ─────────────────────────────────────────
    # KALKULASI SAHAM + SUPPORT/RESISTANCE
    # ─────────────────────────────────────────
    def analyze_stocks(self) -> dict:
        log.info("📈 Analyzing saham...")
        hasil = []
        total_nilai = 0
        total_modal = 0

        stocks_market = self.market["saham"].get("stocks", {})
        drop_threshold = float(os.getenv("PRICE_DROP_THRESHOLD", 5))

        for item in self.portfolio["saham"]:
            code  = item["id"]
            qty_lembar = item["qty_lot"] * LOT_SIZE
            avg   = item["avg_buy_price"]
            modal = qty_lembar * avg

            market_data  = stocks_market.get(code, {})
            market_price = market_data.get("price") or avg
            change_pct   = market_data.get("change_pct", 0)

            nilai   = qty_lembar * market_price
            pl      = nilai - modal
            pl_pct  = (pl / modal * 100) if modal > 0 else 0

            total_modal += modal
            total_nilai += nilai

            # ── SIGNAL LOGIC ──
            signal = "HOLD"
            signal_reason = ""
            priority = "normal"

            drop_from_avg = ((market_price - avg) / avg * 100) if avg > 0 else 0

            # 1. Cek Support Level
            if market_price <= item.get("support", 0):
                signal = "BUY"
                signal_reason = f"Harga menyentuh Support Rp{item['support']:,}"
                priority = "high"
                self._add_signal("BUY", code, market_price, signal_reason, priority)

            # 2. Cek Average Down (turun dari avg beli)
            elif drop_from_avg <= -drop_threshold:
                signal = "AVG_DOWN"
                signal_reason = f"Harga turun {abs(drop_from_avg):.1f}% dari avg beli Rp{avg:,}"
                priority = "high"
                self._add_signal("AVG_DOWN", code, market_price, signal_reason, priority)

            # 3. Cek Resistance (take profit)
            elif market_price >= item.get("resistance", 999999):
                signal = "SELL"
                signal_reason = f"Harga menyentuh Resistance Rp{item['resistance']:,} — pertimbangkan Take Profit"
                priority = "medium"
                self._add_signal("SELL", code, market_price, signal_reason, priority)

            # 4. Cek Stop Loss
            elif market_price <= item.get("stop_loss", 0):
                signal = "STOPLOSS"
                signal_reason = f"⚠️ Harga di bawah Stop Loss Rp{item['stop_loss']:,}!"
                priority = "critical"
                self._add_signal("STOPLOSS", code, market_price, signal_reason, priority)

            hasil.append({
                "id"           : code,
                "nama"         : item["nama"],
                "qty_lot"      : item["qty_lot"],
                "avg_buy"      : avg,
                "market_price" : market_price,
                "change_pct"   : change_pct,
                "support"      : item.get("support"),
                "resistance"   : item.get("resistance"),
                "stop_loss"    : item.get("stop_loss"),
                "modal"        : modal,
                "nilai_pasar"  : nilai,
                "pl"           : round(pl),
                "pl_pct"       : round(pl_pct, 2),
                "signal"       : signal,
                "signal_reason": signal_reason
            })

            arrow = "▲" if pl >= 0 else "▼"
            log.info(f"  {code}: Rp{market_price:,} | P&L {arrow}Rp{abs(pl):,.0f} ({pl_pct:.2f}%) | {signal}")

        return {
            "items"       : hasil,
            "total_modal" : total_modal,
            "total_nilai" : total_nilai,
            "total_pl"    : total_nilai - total_modal,
            "total_pl_pct": round((total_nilai - total_modal) / total_modal * 100, 2) if total_modal else 0
        }

    # ─────────────────────────────────────────
    # KALKULASI REKSA DANA
    # ─────────────────────────────────────────
    def analyze_reksa(self) -> dict:
        log.info("🏦 Analyzing reksadana...")
        hasil = []
        total_nilai = 0
        total_modal = 0

        reksa_market = self.market["reksadana"].get("reksa_dana", {})

        for item in self.portfolio["reksadana"]:
            fund_id  = item["id"]
            qty_unit = item["qty_unit"]
            avg_nab  = item["avg_buy_nab"]
            modal    = qty_unit * avg_nab

            market_data = reksa_market.get(fund_id, {})
            current_nab = market_data.get("current_nab") or avg_nab
            nilai       = qty_unit * current_nab
            pl          = nilai - modal
            pl_pct      = (pl / modal * 100) if modal > 0 else 0

            total_modal += modal
            total_nilai += nilai

            hasil.append({
                "id"         : fund_id,
                "nama"       : item["nama"],
                "qty_unit"   : qty_unit,
                "avg_nab"    : avg_nab,
                "current_nab": current_nab,
                "modal"      : modal,
                "nilai_pasar": nilai,
                "pl"         : round(pl),
                "pl_pct"     : round(pl_pct, 2),
                "signal"     : "DCA"
            })

            log.info(f"  {fund_id}: NAB {current_nab} | P&L Rp{pl:,.0f} ({pl_pct:.2f}%)")

        return {
            "items"       : hasil,
            "total_modal" : total_modal,
            "total_nilai" : total_nilai,
            "total_pl"    : total_nilai - total_modal,
            "total_pl_pct": round((total_nilai - total_modal) / total_modal * 100, 2) if total_modal else 0
        }

    # ─────────────────────────────────────────
    # KALKULASI VALAS ← TAMBAHAN
    # ─────────────────────────────────────────
    def analyze_valas(self) -> dict:
        log.info("💱 Analyzing valas...")
        hasil = []
        total_nilai = 0
        total_modal = 0

        # Ambil rates dari market_latest.json (sudah diisi valas_fetcher)
        valas_rates = self.market.get("valas", {}).get("rates", {})

        # Ambil posisi valas dari portfolio (default [] jika belum ada)
        portfolio_valas = self.portfolio.get("valas", [])

        if not portfolio_valas:
            log.info("  (Tidak ada posisi valas di portfolio)")
            return {
                "items"       : [],
                "total_modal" : 0,
                "total_nilai" : 0,
                "total_pl"    : 0,
                "total_pl_pct": 0
            }

        for item in portfolio_valas:
            code         = item.get("code", "").upper()
            qty          = float(item.get("qty_unit", 0))
            avg_buy_rate = float(item.get("avg_buy_rate", 0))
            modal        = qty * avg_buy_rate

            rate_data    = valas_rates.get(code, {})
            current_rate = rate_data.get("rate")
            change_pct   = rate_data.get("change_pct", 0.0)
            data_status  = rate_data.get("status", "error")

            # Fallback ke avg_buy_rate jika fetch gagal
            if current_rate is None:
                current_rate = avg_buy_rate

            nilai  = qty * current_rate
            pl     = nilai - modal
            pl_pct = (pl / modal * 100) if modal > 0 else 0

            total_modal += modal
            total_nilai += nilai

            # ── Signal logic ──
            signal        = "HOLD"
            signal_reason = ""
            priority      = "normal"

            if data_status != "ok":
                signal        = "DATA_ERROR"
                priority      = "high"
                signal_reason = f"Gagal fetch kurs {code}"

            elif pl_pct <= VALAS_SL_THRESHOLD:
                signal        = "STOPLOSS"
                priority      = "critical"
                signal_reason = (
                    f"P&L {pl_pct:+.2f}% — kurs {code}/IDR melemah dari "
                    f"Rp{avg_buy_rate:,.0f} → Rp{current_rate:,.0f}"
                )
                self._add_signal("STOPLOSS", f"VALAS {code}", current_rate, signal_reason, priority)

            elif change_pct >= VALAS_SELL_THRESHOLD:
                signal        = "SELL_PARTIAL"
                priority      = "medium"
                signal_reason = (
                    f"Kurs {code}/IDR naik {change_pct:+.2f}% hari ini "
                    f"→ pertimbangkan konversi sebagian ke IDR"
                )
                self._add_signal("SELL_PARTIAL", f"VALAS {code}", current_rate, signal_reason, priority)

            elif change_pct <= VALAS_BUY_THRESHOLD:
                signal        = "BUY"
                priority      = "high"
                signal_reason = (
                    f"Kurs {code}/IDR turun {change_pct:+.2f}% hari ini "
                    f"→ peluang beli valas lebih murah"
                )
                self._add_signal("BUY", f"VALAS {code}", current_rate, signal_reason, priority)

            hasil.append({
                "id"           : item.get("id"),
                "nama"         : item.get("nama"),
                "code"         : code,
                "symbol"       : rate_data.get("symbol", code),
                "qty_unit"     : qty,
                "avg_buy_rate" : avg_buy_rate,
                "current_rate" : current_rate,
                "change_pct"   : round(change_pct, 4),
                "modal"        : round(modal),
                "nilai_pasar"  : round(nilai),
                "pl"           : round(pl),
                "pl_pct"       : round(pl_pct, 2),
                "signal"       : signal,
                "signal_reason": signal_reason,
                "data_status"  : data_status,
            })

            arrow = "▲" if pl >= 0 else "▼"
            log.info(
                f"  {code}/IDR: Rp{current_rate:>10,.2f} ({change_pct:+.2f}%) | "
                f"P&L {arrow}Rp{abs(pl):,.0f} ({pl_pct:.2f}%) | {signal}"
            )

        return {
            "items"       : hasil,
            "total_modal" : total_modal,
            "total_nilai" : total_nilai,
            "total_pl"    : total_nilai - total_modal,
            "total_pl_pct": round((total_nilai - total_modal) / total_modal * 100, 2) if total_modal else 0
        }

    # ─────────────────────────────────────────
    # CEK ALOKASI ASET
    # ─────────────────────────────────────────
    def analyze_allocation(self, gold: dict, stocks: dict, reksa: dict, valas: dict) -> dict:
        log.info("⚖️  Analyzing alokasi aset...")

        # Valas ikut dihitung di total aset
        total_aset = (
            gold["total_nilai"] +
            stocks["total_nilai"] +
            reksa["total_nilai"] +
            valas["total_nilai"]   # ← TAMBAHAN
        )
        if total_aset == 0:
            return {}

        target   = self.portfolio["target_allocation"]
        gold_max = float(os.getenv("GOLD_MAX_ALLOCATION", 30))

        aktual = {
            "emas"      : round(gold["total_nilai"]   / total_aset * 100, 1),
            "saham"     : round(stocks["total_nilai"] / total_aset * 100, 1),
            "reksadana" : round(reksa["total_nilai"]  / total_aset * 100, 1),
            "valas"     : round(valas["total_nilai"]  / total_aset * 100, 1),  # ← TAMBAHAN
        }

        rekomendasi = []

        # Cek emas over-allocation
        if aktual["emas"] > gold_max:
            rekomendasi.append({
                "action": "KURANG",
                "asset" : "Emas",
                "actual": aktual["emas"],
                "target": target["emas"]
            })
            self._add_signal("REBALANCE", "EMAS", 0,
                f"Alokasi emas {aktual['emas']}% > batas {gold_max}%", "medium")

        # Cek saham under-allocation
        if aktual["saham"] < target["saham"] - 5:
            rekomendasi.append({
                "action": "TAMBAH",
                "asset" : "Saham",
                "actual": aktual["saham"],
                "target": target["saham"]
            })

        # Cek reksa dana over/under
        reksa_target = target.get("reksa", target.get("reksadana", 25))
        if aktual["reksadana"] > reksa_target + 5:
            rekomendasi.append({
                "action": "KURANG",
                "asset" : "Reksa Dana",
                "actual": aktual["reksadana"],
                "target": reksa_target
            })
        elif aktual["reksadana"] < reksa_target - 5:
            rekomendasi.append({
                "action": "TAMBAH",
                "asset" : "Reksa Dana",
                "actual": aktual["reksadana"],
                "target": reksa_target
            })

        log.info(
            f"  Alokasi: Emas {aktual['emas']}% | Saham {aktual['saham']}% | "
            f"RD {aktual['reksadana']}% | Valas {aktual['valas']}%"
        )

        return {
            "total_aset" : total_aset,
            "target"     : target,
            "aktual"     : aktual,
            "rekomendasi": rekomendasi
        }

    # ─────────────────────────────────────────
    # HELPER
    # ─────────────────────────────────────────
    def _add_signal(self, tipe: str, aset: str, harga: float, alasan: str, priority: str):
        self.signals.append({
            "type"     : tipe,
            "aset"     : aset,
            "harga"    : harga,
            "alasan"   : alasan,
            "priority" : priority,
            "timestamp": datetime.now().isoformat()
        })

    # ─────────────────────────────────────────
    # MAIN RUN
    # ─────────────────────────────────────────
    def run(self) -> dict:
        log.info("=" * 50)
        log.info("🧮 ANALYST STARTED")
        log.info("=" * 50)

        gold   = self.analyze_gold()
        stocks = self.analyze_stocks()
        reksa  = self.analyze_reksa()
        valas  = self.analyze_valas()                          # ← TAMBAHAN
        alloc  = self.analyze_allocation(gold, stocks, reksa, valas)  # ← update signature

        total_modal = (
            gold["total_modal"] + stocks["total_modal"] +
            reksa["total_modal"] + valas["total_modal"]        # ← TAMBAHAN
        )
        total_nilai = (
            gold["total_nilai"] + stocks["total_nilai"] +
            reksa["total_nilai"] + valas["total_nilai"]        # ← TAMBAHAN
        )
        total_pl = total_nilai - total_modal

        self.report = {
            "analyzed_at"  : datetime.now().isoformat(),
            "summary": {
                "total_modal"  : total_modal,
                "total_nilai"  : total_nilai,
                "total_pl"     : round(total_pl),
                "total_pl_pct" : round(total_pl / total_modal * 100, 2) if total_modal else 0
            },
            "emas"         : gold,
            "saham"        : stocks,
            "reksadana"    : reksa,
            "valas"        : valas,                            # ← TAMBAHAN
            "alokasi"      : alloc,
            "signals"      : self.signals,
            "total_signals": len(self.signals)
        }

        log.info("=" * 50)
        log.info(f"💰 Total Aset  : Rp{total_nilai:,.0f}")
        log.info(f"📊 Total P&L   : Rp{total_pl:,.0f} ({self.report['summary']['total_pl_pct']}%)")
        log.info(f"🚨 Sinyal      : {len(self.signals)} sinyal aktif")
        log.info("=" * 50)

        save_report_to_firestore(self.report)
        return self.report


def save_report_to_firestore(report: dict):
    """Simpan analyst report ke Firestore untuk dashboard"""
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        import os
        if not firebase_admin._apps:
            key_path = os.getenv("FIREBASE_KEY_PATH")
            cred = credentials.Certificate(key_path)
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        db.collection("analyst_report").document("latest").set(report)
        log.info("✅ Analyst report saved to Firestore")
    except Exception as e:
        log.error(f"❌ Firestore report error: {e}")


if __name__ == "__main__":
    analyst = Analyst()
    report  = analyst.run()

    print("\n🚨 SINYAL AKTIF:")
    if report["signals"]:
        for s in report["signals"]:
            print(f"  [{s['priority'].upper()}] {s['type']} {s['aset']} — {s['alasan']}")
    else:
        print("  Tidak ada sinyal saat ini.")

    print(f"\n💰 Total Nilai Aset : Rp{report['summary']['total_nilai']:,.0f}")
    print(f"📈 Floating P&L    : Rp{report['summary']['total_pl']:,.0f} ({report['summary']['total_pl_pct']}%)")

    # Print valas summary
    valas_items = report.get("valas", {}).get("items", [])
    if valas_items:
        print("\n💱 VALAS:")
        for v in valas_items:
            arrow = "▲" if v["pl"] >= 0 else "▼"
            print(f"  {v['code']:<4}: Rp{v['current_rate']:>10,.2f} | "
                  f"P&L {arrow}Rp{abs(v['pl']):>10,.0f} ({v['pl_pct']:+.2f}%) | {v['signal']}")