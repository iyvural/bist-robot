import os
import hashlib
from datetime import datetime

import pandas as pd
import numpy as np
import yfinance as yf
import requests

print("PROGRAM BASLADI")  # emoji koymak istersen cloud'da sorun olmaz, windows log'da bozulabiliyor

# ========================
# TELEGRAM (ENV ÖNCELİKLİ)
# Render'da Environment Variables:
#   TG_TOKEN=...
#   TG_CHAT_ID=1110011334
# ========================
TG_TOKEN = os.getenv("TG_TOKEN", "").strip()
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "").strip()

# (İstersen lokal için fallback bırakabilirsin ama cloud'da ENV kullanmak en doğru)
# TG_TOKEN = TG_TOKEN or "BURAYA_TOKEN_YAZMA"   # tavsiye etmiyorum
# TG_CHAT_ID = TG_CHAT_ID or "1110011334"

def telegram_gonder(mesaj: str):
    """Telegram'a mesaj gönderir. Hata varsa terminalde gösterir."""
    if not TG_TOKEN or not TG_CHAT_ID:
        print("⚠️ Telegram ayarlı değil: TG_TOKEN / TG_CHAT_ID ENV kontrol et.")
        return False

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    chunks = [mesaj[i:i+3500] for i in range(0, len(mesaj), 3500)]

    for part in chunks:
        payload = {"chat_id": TG_CHAT_ID, "text": part}
        r = requests.post(url, json=payload, timeout=20)
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}

        if r.status_code != 200 or not data.get("ok", False):
            print("❌ Telegram gönderim hatası:", data)
            return False

    print("✅ Telegram OK")
    return True

# ========================
# STATE (listener için)
# ========================
os.makedirs("state", exist_ok=True)

def write_state(last_run_text: str, last_summary_text: str):
    with open("state/last_run.txt", "w", encoding="utf-8") as f:
        f.write(last_run_text)
    with open("state/last_summary.txt", "w", encoding="utf-8") as f:
        f.write(last_summary_text)

def read_last_digest() -> str:
    p = "state/last_digest.txt"
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

def write_last_digest(d: str):
    with open("state/last_digest.txt", "w", encoding="utf-8") as f:
        f.write(d)

# ========================
# OUTPUT
# ========================
os.makedirs("output", exist_ok=True)
OUTPUT_PATH = "output/signals.xlsx"

# ========================
# INDICATORS
# ========================
def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def macd_hist(series: pd.Series) -> pd.Series:
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    return macd_line - signal

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# ========================
# LOAD TICKERS
# ========================
def load_tickers(path="tickers.txt"):
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f.readlines()
                if line.strip() and not line.strip().startswith("#")]

tickers = load_tickers()
results = []

# ========================
# TELEGRAM FORMAT HELPERS
# ========================
def icon_for(signal: str) -> str:
    if signal.startswith("AL"):
        return "🟢"
    if signal == "SAT":
        return "🔴"
    return "🟡"

def yorum_uret(r):
    rsi_v = r.get("RSI")
    macd_d = r.get("MACD_dir")

    if rsi_v is None or macd_d in (None, "?"):
        return f"{r['Hisse']} → Veri yetersiz, takip et."

    if rsi_v >= 70:
        rsi_txt = "RSI yüksek (aşırı alım)"
    elif rsi_v <= 30:
        rsi_txt = "RSI düşük (aşırı satım)"
    else:
        rsi_txt = "RSI normal aralık"

    if macd_d == "↑":
        macd_txt = "MACD yükseliyor (momentum artıyor)"
    elif macd_d == "↓":
        macd_txt = "MACD düşüyor (momentum zayıflıyor)"
    else:
        macd_txt = "MACD yatay (kararsız)"

    if rsi_v >= 70 and macd_d == "↓":
        extra = "→ Dikkat: düzeltme/kâr satışı ihtimali artar."
    elif rsi_v <= 30 and macd_d == "↑":
        extra = "→ Dikkat: tepki yükselişi / fırsat olabilir."
    elif 40 <= rsi_v <= 60 and macd_d == "↑":
        extra = "→ Trend güçleniyor, fırsat doğabilir."
    elif 40 <= rsi_v <= 60 and macd_d == "↓":
        extra = "→ Zayıflama var, temkinli ol."
    else:
        extra = "→ Net değil, takip et."

    return f"{r['Hisse']} → {rsi_txt} + {macd_txt} {extra}"

# ========================
# MAIN LOOP
# ========================
for ticker in tickers:
    print(f"{ticker} analiz ediliyor...")

    try:
        df = yf.download(
            ticker,
            period="6mo",
            interval="1d",
            auto_adjust=False,
            progress=False
        )
    except Exception as e:
        print(f"⚠️ {ticker}: yfinance hata: {e}")
        continue

    if df is None or df.empty or len(df) < 80:
        print(f"⚠️ {ticker}: veri yetersiz")
        continue

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df["RSI"] = rsi(df["Close"], 14)
    df["MACD_H"] = macd_hist(df["Close"])
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["ATR"] = atr(df, 14)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = float(last["Close"])
    rsi_val = float(last["RSI"]) if pd.notna(last["RSI"]) else np.nan
    macd_val = float(last["MACD_H"]) if pd.notna(last["MACD_H"]) else np.nan
    prev_macd = float(prev["MACD_H"]) if pd.notna(prev["MACD_H"]) else np.nan
    ema50 = float(last["EMA50"]) if pd.notna(last["EMA50"]) else np.nan
    atr_val = float(last["ATR"]) if pd.notna(last["ATR"]) else 0.0

    if not np.isnan(macd_val) and not np.isnan(prev_macd):
        macd_dir = "↑" if macd_val > prev_macd else ("↓" if macd_val < prev_macd else "→")
    else:
        macd_dir = "?"

    signal = "BEKLE"

    # STRATEJİ
    if (not np.isnan(rsi_val)) and (not np.isnan(macd_val)) and (not np.isnan(prev_macd)) and (not np.isnan(ema50)):
        if (price > ema50) and (rsi_val < 40) and (macd_val > prev_macd):
            signal = "AL (GÜÇLÜ)"
        elif (rsi_val > 70) and (macd_val < prev_macd):
            signal = "SAT"

    # STOP / HEDEF
    if atr_val > 0:
        stop = price - (2 * atr_val)
        target = price + (price - stop) * 2
    else:
        stop = price * 0.95
        target = price * 1.10

    results.append({
        "Hisse": ticker,
        "Fiyat": round(price, 2),
        "RSI": round(rsi_val, 2) if not np.isnan(rsi_val) else None,
        "MACD": round(macd_val, 4) if not np.isnan(macd_val) else None,
        "MACD_dir": macd_dir,
        "EMA50": round(ema50, 2) if not np.isnan(ema50) else None,
        "ATR": round(atr_val, 2),
        "Sinyal": signal,
        "Stop": round(stop, 2),
        "Hedef": round(target, 2),
    })

# ========================
# SAVE EXCEL (izin hatasına dayanıklı)
# ========================
df_out = pd.DataFrame(results)
try:
    df_out.to_excel(OUTPUT_PATH, index=False)
    print("✅ Excel oluşturuldu:", OUTPUT_PATH)
except PermissionError:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    alt_path = f"output/signals_{ts}.xlsx"
    df_out.to_excel(alt_path, index=False)
    print(f"⚠️ Excel kilitliydi. Alternatif yazıldı: {alt_path}")

# ========================
# TELEGRAM MESSAGE (Sinyal Verenler -> Takip Listesi -> Yorumlar)
# ========================
sinyal_verenler = [r for r in results if r["Sinyal"] != "BEKLE"]
tum_liste = results

header = f"{'':<2} {'Hisse':<10} {'Sinyal':<12} {'Fiyat':>8} {'RSI':>6} {'MACD':>10} {'Stop':>9} {'Hedef':>9}"
sep = "-" * 74
now_txt = datetime.now().strftime("%d.%m.%Y %H:%M")

parts = []
parts.append(f"📌 BIST Takip Listesi ({now_txt})")

parts.append("")
parts.append("🚨 Sinyal Verenler")
parts.append("```")
parts.append(header)
parts.append(sep)

if sinyal_verenler:
    for r in sinyal_verenler:
        ic = icon_for(r["Sinyal"])
        macd_disp = f"{r['MACD']}{r['MACD_dir']}" if r.get("MACD") is not None else "None?"
        parts.append(
            f"{ic:<2} {r['Hisse']:<10} {r['Sinyal']:<12} {r['Fiyat']:>8} {str(r['RSI']):>6} "
            f"{macd_disp:>10} {r['Stop']:>9} {r['Hedef']:>9}"
        )
else:
    parts.append("🟡  Yok (bugün AL/SAT sinyali yok)")
parts.append("```")

parts.append("")
parts.append("📋 Takip Listesi")
parts.append("```")
parts.append(header)
parts.append(sep)

for r in tum_liste:
    ic = icon_for(r["Sinyal"])
    macd_disp = f"{r['MACD']}{r['MACD_dir']}" if r.get("MACD") is not None else "None?"
    parts.append(
        f"{ic:<2} {r['Hisse']:<10} {r['Sinyal']:<12} {r['Fiyat']:>8} {str(r['RSI']):>6} "
        f"{macd_disp:>10} {r['Stop']:>9} {r['Hedef']:>9}"
    )
parts.append("```")

parts.append("")
parts.append("🧠 Yorumlar (RSI + MACD)")
yorum_kaynak = sinyal_verenler if sinyal_verenler else tum_liste[:5]
for r in yorum_kaynak:
    parts.append("• " + yorum_uret(r))

mesaj = "\n".join(parts)

# ========================
# STATE + SPAM ENGELİ + TELEGRAM
# ========================
last_run_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
write_state(last_run_text, mesaj)

digest = hashlib.md5(mesaj.encode("utf-8")).hexdigest()
last_digest = read_last_digest()

if digest == last_digest:
    print("ℹ️ Değişiklik yok, Telegram gönderilmedi.")
else:
    ok = telegram_gonder(mesaj)
    if ok:
        write_last_digest(digest)
        print("📲 Telegram: yeni özet gönderildi.")

print("PROGRAM BITTI")
