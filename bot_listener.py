import os
import time
import requests
import subprocess

# ========================
# ENV (Render'dan alacak)
# ========================
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = str(os.getenv("TG_CHAT_ID"))

# ========================
# TELEGRAM GÖNDER
# ========================
def send(msg):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TG_CHAT_ID, "text": msg}, timeout=20)

# ========================
# STATE DOSYALARI
# ========================
def read_file(path, default="yok"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return default

# ========================
# MAIN ÇALIŞTIR
# ========================
def run_main():
    subprocess.Popen(["python", "main.py"])

# ========================
# TELEGRAM DİNLEYİCİ
# ========================
def main():
    send("🤖 BIST Bot aktif!\nKomutlar: /run /status /last")

    offset = None

    while True:
        try:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates"

            params = {"timeout": 30}
            if offset:
                params["offset"] = offset

            res = requests.get(url, params=params, timeout=35).json()

            if not res.get("ok"):
                time.sleep(2)
                continue

            for update in res.get("result", []):
                offset = update["update_id"] + 1

                msg = update.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = (msg.get("text") or "").strip()

                # sadece sen kullan
                if chat_id != TG_CHAT_ID:
                    continue

                # ========================
                # KOMUTLAR
                # ========================
                if text == "/run":
                    send("⏳ Çalıştırıyorum...")
                    run_main()

                elif text == "/status":
                    last = read_file("state/last_run.txt")
                    send(f"📌 Son çalışma:\n{last}")

                elif text == "/last":
                    summary = read_file("state/last_summary.txt")
                    send(summary[:3500])

                else:
                    send("Komutlar:\n/run\n/status\n/last")

        except Exception as e:
            print("Hata:", e)
            time.sleep(3)

if __name__ == "__main__":
    main()
