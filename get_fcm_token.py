"""
Generate FCM Registration Token via Firebase
Jalankan ini, lalu scan QR code di HP
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv("config/.env")

import firebase_admin
from firebase_admin import credentials, auth

# Init Firebase
cred = credentials.Certificate(os.getenv("FIREBASE_KEY_PATH"))
firebase_admin.initialize_app(cred)

project_id = os.getenv("FIREBASE_PROJECT_ID")

print("\n" + "="*55)
print("📲 CARA DAPAT FCM TOKEN — 2 OPSI:")
print("="*55)

print("""
OPSI A — Pakai Chrome di HP (Recommended):
─────────────────────────────────────────
1. Di HP, buka Chrome
2. Ketik di address bar:
   chrome://flags/#unsafely-treat-insecure-origin-as-secure

3. Di kolom input, ketik:
   http://192.168.192.81:4500

4. Klik Enable → Relaunch

5. Buka lagi: http://192.168.192.81:4500
6. Klik Generate FCM Token
7. Izinkan notifikasi → Token akan muncul

OPSI B — Pakai ngrok (HTTPS otomatis):
─────────────────────────────────────────
Jalankan di terminal STB:
  curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc
  
Atau cara cepat:
  pip install pyngrok
  python3 tunnel.py
""")

print("="*55)
print("Pilih opsi mana? Ketik A atau B lalu Enter:")
opsi = input("> ").strip().upper()

if opsi == "B":
    print("\n📦 Install pyngrok...")
    os.system("pip install pyngrok -q")
    
    print("\n⚠️  Butuh ngrok account gratis.")
    print("1. Daftar di: https://ngrok.com (gratis)")
    print("2. Copy authtoken dari dashboard ngrok")
    print("3. Paste di sini:")
    token = input("Ngrok authtoken: ").strip()
    
    if token:
        with open("tunnel.py", "w") as f:
            f.write(f"""
from pyngrok import ngrok, conf
conf.get_default().auth_token = "{token}"
public_url = ngrok.connect(4500)
print("\\n✅ HTTPS URL:", public_url)
print("Buka URL ini di browser HP untuk generate FCM token")
print("Tekan Ctrl+C untuk stop")
import time
while True:
    time.sleep(1)
""")
        print("\n▶  Jalankan: python3 tunnel.py")
    else:
        print("Token kosong, batal.")
