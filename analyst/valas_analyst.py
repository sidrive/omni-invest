"""
valas_analyst.py — Kalkulasi P&L dan signal untuk aset valas
Dipanggil dari analyst/engine.py setelah fetch market data selesai.

Logika:
  modal_idr  = qty_unit × avg_buy_rate
  nilai_idr  = qty_unit × current_rate
  P&L        = nilai_idr - modal_idr
  P&L%       = (P&L / modal_idr) × 100

Signal:
  HOLD_STRONG  → change_pct < -1.5%  (kurs melemah vs IDR, peluang beli lebih)
  SELL_PARTIAL → change_pct > +2.0%  (kurs menguat, pertimbangkan konversi)
  HOLD         → kondisi normal
"""

from datetime import datetime
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")

# ── Threshold signal ──────────────────────────────────────────────────────
SIGNAL_SELL_THRESHOLD    =  2.0   # % kenaikan kurs → pertimbangkan jual/konversi
SIGNAL_BUY_THRESHOLD     = -1.5   # % penurunan kurs → peluang beli valas
STOPLOSS_PL_THRESHOLD    = -5.0   # % P&L aset → warning stop loss
BUY_THRESHOLD            = SIGNAL_BUY_THRESHOLD


def analyze_valas(portfolio_valas: list, valas_rates: dict) -> dict:
    """
    Hitung P&L dan sinyal untuk semua posisi valas di portfolio.

    Args:
        portfolio_valas : list aset valas dari portfolio.main.valas
                          Format per item:
                          {
                            "id": "usd_01",
                            "nama": "USD Tabungan",
                            "code": "USD",           ← kode mata uang
                            "qty_unit": 500.0,        ← jumlah unit yang dipegang
                            "avg_buy_rate": 15800.0,  ← kurs rata-rata beli (IDR/unit)
                            "catatan": "..."
                          }
        valas_rates     : dict dari valas_fetcher.run() → result["rates"]

    Returns:
        dict hasil analisis lengkap
    """
    items        = []
    total_modal  = 0.0
    total_nilai  = 0.0
    signals      = []

    for aset in portfolio_valas:
        code         = aset.get("code", "").upper()
        qty          = float(aset.get("qty_unit", 0))
        avg_buy_rate = float(aset.get("avg_buy_rate", 0))

        # Ambil data kurs terkini
        rate_data    = valas_rates.get(code, {})
        current_rate = rate_data.get("rate")
        change_pct   = rate_data.get("change_pct")
        status       = rate_data.get("status", "error")

        # Safe display values — untuk f-string dan round(), jangan ubah current_rate asli
        display_rate       = current_rate if current_rate is not None else 0.0
        display_change_pct = change_pct   if change_pct   is not None else 0.0

        # Kalkulasi
        modal_idr  = qty * avg_buy_rate
        nilai_idr  = qty * current_rate if current_rate else 0.0
        pl         = nilai_idr - modal_idr
        pl_pct     = (pl / modal_idr * 100) if modal_idr > 0 else 0.0

        total_modal += modal_idr
        total_nilai += nilai_idr

        # ── Tentukan signal ────────────────────────────────────────────
        signal      = "HOLD"
        priority    = "normal"
        signal_reason = ""

        if status != "ok" or current_rate is None:
            signal        = "DATA_ERROR"
            priority      = "high"
            signal_reason = f"Gagal fetch kurs {code} — cek koneksi"

        elif pl_pct <= STOPLOSS_PL_THRESHOLD:
            signal        = "STOPLOSS"
            priority      = "critical"
            signal_reason = (
                f"P&L {pl_pct:+.2f}% — kurs {code}/IDR melemah signifikan "
                f"dari Rp{avg_buy_rate:,.0f} → Rp{display_rate:,.0f}"
            )

        elif change_pct is not None and change_pct >= SIGNAL_SELL_THRESHOLD:
            signal        = "SELL_PARTIAL"
            priority      = "medium"
            signal_reason = (
                f"Kurs {code}/IDR naik {display_change_pct:+.2f}% hari ini "
                f"→ pertimbangkan konversi sebagian ke IDR"
            )

        elif change_pct is not None and change_pct <= BUY_THRESHOLD:
            signal        = "BUY"
            priority      = "high"
            signal_reason = (
                f"Kurs {code}/IDR turun {display_change_pct:+.2f}% hari ini "
                f"→ peluang beli valas lebih murah"
            )

        # Tambahkan ke sinyal global jika bukan HOLD normal
        if signal != "HOLD":
            signals.append({
                "aset":          aset.get("nama", code),
                "code":          code,
                "type":          signal,
                "priority":      priority,
                "signal_reason": signal_reason,
                "current_rate":  current_rate,
                "change_pct":    change_pct,
                "pl_pct":        round(pl_pct, 2),
                "timestamp":     datetime.now(WIB).isoformat(),
            })

        items.append({
            "id":            aset.get("id"),
            "nama":          aset.get("nama"),
            "code":          code,
            "symbol":        rate_data.get("symbol", code),
            "qty_unit":      qty,
            "avg_buy_rate":  avg_buy_rate,
            "current_rate":  current_rate,
            "change_pct":    round(change_pct, 4) if change_pct is not None else None,
            "modal_idr":     round(modal_idr, 0),
            "nilai_idr":     round(nilai_idr, 0),
            "pl":            round(pl, 0),
            "pl_pct":        round(pl_pct, 2),
            "signal":        signal,
            "priority":      priority,
            "signal_reason": signal_reason,
            "data_status":   status,
        })

    total_pl     = total_nilai - total_modal
    total_pl_pct = (total_pl / total_modal * 100) if total_modal > 0 else 0.0

    return {
        "items":       items,
        "summary": {
            "total_modal": round(total_modal, 0),
            "total_nilai": round(total_nilai, 0),
            "total_pl":    round(total_pl, 0),
            "total_pl_pct": round(total_pl_pct, 2),
            "count":       len(items),
        },
        "signals":     signals,
        "analyzed_at": datetime.now(WIB).isoformat(),
    }


# ── Test standalone ───────────────────────────────────────────────────────
if __name__ == "__main__":
    # Simulasi data
    dummy_portfolio = [
        {"id": "usd_01", "nama": "USD Tabungan",    "code": "USD", "qty_unit": 500,  "avg_buy_rate": 15800},
        {"id": "sgd_01", "nama": "SGD Travel Fund", "code": "SGD", "qty_unit": 200,  "avg_buy_rate": 11500},
        {"id": "eur_01", "nama": "EUR Savings",     "code": "EUR", "qty_unit": 100,  "avg_buy_rate": 17200},
        {"id": "jpy_01", "nama": "JPY Cash",        "code": "JPY", "qty_unit": 50000,"avg_buy_rate": 105},
    ]
    dummy_rates = {
        "USD": {"rate": 16250.0, "change_pct": 0.31,  "status": "ok", "symbol": "$"},
        "SGD": {"rate": 12100.0, "change_pct": -0.15, "status": "ok", "symbol": "S$"},
        "EUR": {"rate": 17800.0, "change_pct": 2.5,   "status": "ok", "symbol": "€"},
        "JPY": {"rate":  108.5,  "change_pct": -1.8,  "status": "ok", "symbol": "¥"},
    }

    result = analyze_valas(dummy_portfolio, dummy_rates)

    print("\n=== HASIL ANALISIS VALAS ===")
    for item in result["items"]:
        pl_sign = "▲" if item["pl"] >= 0 else "▼"
        print(f"  {item['code']:3s} | qty:{item['qty_unit']:>8,.0f} | "
              f"rate: Rp{item['current_rate']:>10,.2f} | "
              f"P&L: {pl_sign}Rp{abs(item['pl']):>10,.0f} ({item['pl_pct']:+.2f}%) | "
              f"Signal: {item['signal']}")

    s = result["summary"]
    print(f"\n  Total Modal : Rp{s['total_modal']:>15,.0f}")
    print(f"  Total Nilai : Rp{s['total_nilai']:>15,.0f}")
    print(f"  Total P&L   : Rp{s['total_pl']:>+15,.0f}  ({s['total_pl_pct']:+.2f}%)")

    if result["signals"]:
        print(f"\n  Sinyal ({len(result['signals'])}):")
        for sig in result["signals"]:
            print(f"    [{sig['priority'].upper()}] {sig['type']} — {sig['aset']}: {sig['signal_reason']}")
