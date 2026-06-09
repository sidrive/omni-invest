"""
OMNI-INVEST SENTINEL — Main Orchestrator
Menjalankan: Scavenger → Analyst → Messenger
"""
import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "config" / ".env")

sys.path.insert(0, str(Path(__file__).parent))

from scavenger.runner import run_scavenger
from analyst.engine import Analyst
from messenger.fcm_sender import send_signals, send_daily_summary

log_dir = Path(os.getenv("LOG_DIR", "~/omni-invest/logs")).expanduser()
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SENTINEL] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_dir / "sentinel.log")
    ]
)
log = logging.getLogger(__name__)

def run():
    start = datetime.now()
    log.info("🛡️  ================================")
    log.info("🛡️  OMNI-INVEST SENTINEL STARTED")
    log.info(f"🛡️  {start.strftime('%Y-%m-%d %H:%M:%S WIB')}")
    log.info("🛡️  ================================")

    # ── PHASE 1: SCAVENGER ──
    log.info("\n🔍 [1/3] Running Scavenger...")
    try:
        market_data = run_scavenger()
        log.info("✅ Scavenger selesai")
    except Exception as e:
        log.error(f"❌ Scavenger error: {e}")
        return

    # ── PHASE 2: ANALYST ──
    log.info("\n🧮 [2/3] Running Analyst...")
    try:
        analyst = Analyst()
        report = analyst.run()
        log.info(f"✅ Analyst selesai — {report['total_signals']} sinyal")
    except Exception as e:
        log.error(f"❌ Analyst error: {e}")
        return

    # ── PHASE 3: MESSENGER ──
    log.info("\n📲 [3/3] Running Messenger...")
    try:
        hour = datetime.now().hour

        # Kirim sinyal aktif
        if report["signals"]:
            sent = send_signals(report["signals"])
            log.info(f"✅ Messenger: {sent} notifikasi terkirim")
        else:
            log.info("📭 Tidak ada sinyal aktif")

        # Kirim summary harian jam 16:00
        if hour == 16:
            log.info("📊 Mengirim daily summary...")
            send_daily_summary(report)

    except Exception as e:
        log.error(f"❌ Messenger error: {e}")

    # ── SELESAI ──
    elapsed = (datetime.now() - start).seconds
    log.info(f"\n🛡️  ================================")
    log.info(f"🛡️  SENTINEL SELESAI ({elapsed}s)")
    log.info(f"💰  Total Aset : Rp{report['summary']['total_nilai']:,.0f}")
    log.info(f"📈  P&L        : Rp{report['summary']['total_pl']:,.0f} ({report['summary']['total_pl_pct']}%)")
    log.info(f"🚨  Sinyal     : {report['total_signals']}")
    log.info(f"🛡️  ================================")

if __name__ == "__main__":
    run()
