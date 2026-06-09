"""
THE MESSENGER — FCM Push Notification Sender
Kirim alert dari STB ke HP via Firebase FCM V1 API
"""
import os
import json
import logging
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "config" / ".env")

import firebase_admin
from firebase_admin import credentials, messaging as fcm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MESSENGER] %(message)s"
)
log = logging.getLogger(__name__)

def init_firebase():
    if not firebase_admin._apps:
        key_path = os.getenv("FIREBASE_KEY_PATH")
        cred = credentials.Certificate(key_path)
        firebase_admin.initialize_app(cred)

# ─────────────────────────────────────────
# TEMPLATE PESAN
# ─────────────────────────────────────────
TEMPLATES = {
    "BUY": {
        "title": "💚 Sinyal BELI — {aset}",
        "body": "Harga {aset} Rp{harga:,} menyentuh zona Support!\n{alasan}\nWaktunya aksi! 🎯"
    },
    "AVG_DOWN": {
        "title": "📉 Average Down — {aset}",
        "body": "Harga diskon! {aset} di Rp{harga:,}\n{alasan}\nPertimbangkan tambah posisi 💪"
    },
    "SELL": {
        "title": "🔴 Sinyal JUAL — {aset}",
        "body": "Target tercapai! {aset} Rp{harga:,}\n{alasan}\nWaktunya ambil profit! 💰"
    },
    "STOPLOSS": {
        "title": "🚨 STOP LOSS — {aset}",
        "body": "PERHATIAN! {aset} di Rp{harga:,}\n{alasan}\nSegera review posisi! ⚠️"
    },
    "REBALANCE": {
        "title": "⚖️ Rebalance Alert",
        "body": "{alasan}\nBuka dashboard untuk simulasi rebalancing 📊"
    },
    "DAILY_SUMMARY": {
        "title": "📊 Ringkasan Harian Portofolio",
        "body": "Total Aset: Rp{total_nilai:,}\nP&L: {pl_sign}Rp{total_pl:,} ({total_pl_pct}%)\nSinyal aktif: {total_signals}"
    }
}

def format_message(signal: dict) -> tuple[str, str]:
    """Format pesan notifikasi dari signal"""
    tipe = signal.get("type", "BUY")
    template = TEMPLATES.get(tipe, TEMPLATES["BUY"])

    harga = signal.get("harga", 0)
    aset = signal.get("aset", "")
    alasan = signal.get("alasan", "")

    title = template["title"].format(aset=aset, harga=harga, alasan=alasan)
    body = template["body"].format(aset=aset, harga=harga, alasan=alasan)

    return title, body

def send_notification(title: str, body: str, data: dict = None) -> bool:
    """Kirim push notification ke device token"""
    init_firebase()

    device_token = os.getenv("FCM_DEVICE_TOKEN")
    if not device_token:
        log.error("❌ FCM_DEVICE_TOKEN belum diset di .env!")
        log.error("   Buka fcm-token.html di browser HP, copy token, lalu:")
        log.error("   nano /home/sidrive/omni-invest/config/.env")
        log.error("   Tambahkan: FCM_DEVICE_TOKEN=<token>")
        return False

    try:
        message = fcm.Message(
            notification=fcm.Notification(
                title=title,
                body=body
            ),
            data=data or {},
            token=device_token,
            android=fcm.AndroidConfig(
                priority="high",
                notification=fcm.AndroidNotification(
                    sound="default",
                    priority="high",
                    channel_id="omni_invest_alerts"
                )
            ),
            apns=fcm.APNSConfig(
                payload=fcm.APNSPayload(
                    aps=fcm.Aps(sound="default")
                )
            )
        )

        response = fcm.send(message)
        log.info(f"✅ Notifikasi terkirim! ID: {response}")
        return True

    except Exception as e:
        log.error(f"❌ Gagal kirim notifikasi: {e}")
        return False

def send_signals(signals: list) -> int:
    """Kirim semua sinyal aktif sebagai notifikasi"""
    if not signals:
        log.info("📭 Tidak ada sinyal untuk dikirim")
        return 0

    sent = 0
    # Urutkan: critical dulu
    priority_order = {"critical": 0, "high": 1, "medium": 2, "normal": 3}
    signals_sorted = sorted(signals, key=lambda s: priority_order.get(s.get("priority", "normal"), 3))

    for signal in signals_sorted:
        title, body = format_message(signal)
        log.info(f"📤 Mengirim: [{signal['type']}] {signal['aset']}")

        success = send_notification(
            title=title,
            body=body,
            data={
                "type": signal["type"],
                "aset": signal["aset"],
                "harga": str(signal.get("harga", 0)),
                "priority": signal.get("priority", "normal"),
                "timestamp": signal.get("timestamp", datetime.now().isoformat())
            }
        )
        if success:
            sent += 1

    log.info(f"📬 Total terkirim: {sent}/{len(signals)} notifikasi")
    return sent

def send_daily_summary(report: dict) -> bool:
    """Kirim ringkasan harian portofolio"""
    summary = report.get("summary", {})
    total_pl = summary.get("total_pl", 0)

    template = TEMPLATES["DAILY_SUMMARY"]
    title = template["title"]
    body = template["body"].format(
        total_nilai=summary.get("total_nilai", 0),
        pl_sign="+" if total_pl >= 0 else "-",
        total_pl=abs(total_pl),
        total_pl_pct=summary.get("total_pl_pct", 0),
        total_signals=report.get("total_signals", 0)
    )

    return send_notification(title, body)


if __name__ == "__main__":
    # Test kirim notifikasi
    log.info("🧪 Test kirim notifikasi...")

    test_signal = {
        "type": "AVG_DOWN",
        "aset": "BBCA",
        "harga": 5800,
        "alasan": "Harga turun 5% dari avg beli Rp6.100",
        "priority": "high",
        "timestamp": datetime.now().isoformat()
    }

    title, body = format_message(test_signal)
    print(f"\n📤 Title : {title}")
    print(f"📝 Body  : {body}\n")

    success = send_notification(title, body, data={"type": "test"})
    if success:
        print("✅ Notifikasi test berhasil dikirim ke HP!")
    else:
        print("❌ Gagal — pastikan FCM_DEVICE_TOKEN sudah diset di .env")
