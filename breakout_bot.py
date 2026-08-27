import os
import time
from datetime import datetime
import pytz
import pandas as pd
import numpy as np
import yfinance as yf
import requests

# ==========================================
# 1. AYARLAR & ORTAM DEĞİŞKENLERİ
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

TURKEY_TZ = pytz.timezone("Europe/Istanbul")

# Takip Edilecek Çiftler ve Semboller
PAIRS = [
    ("SPXL", "SPXS"),  # S&P 500 3x Bull/Bear
    ("SOXL", "SOXS"),  # Semiconductor 3x Bull/Bear
    ("TQQQ", "SQQQ"),  # Nasdaq-100 3x Bull/Bear
    ("NVDU", "NVDD"),  # Nvidia 2x Bull/Bear
    ("NUGT", "DUST")   # Gold Miners 2x Bull/Bear
]

# Strateji Parametreleri
TIMEFRAME = "15m"
Z_PERIOD = 20
Z_LOWER = -2.0
Z_UPPER = 2.0

# ==========================================
# 2. TELEGRAM BİLDİRİM FONKSİYONU
# ==========================================
def telegram_mesaj_gonder(mesaj):
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        print("⚠️ Telegram token bulunamadı.")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mesaj,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("✅ Telegram bildirimi gönderildi.")
        else:
            print(f"❌ Telegram Hatası: {res.text}")
    except Exception as e:
        print(f"⚠️ Bağlantı hatası: {e}")

# ==========================================
# 3. STRATEJİ & HESAPLAMA MOTORU
# ==========================================
def strateji_taramasi_yap():
    simdi = datetime.now(TURKEY_TZ)
    saat_str = simdi.strftime("%H:%M")
    saat_saniye = simdi.strftime("%H:%M:%S")

    # --- AÇILIŞ / KAPANIŞ & HEARTBEAT (HAYATTAYIM) BİLDİRİMLERİ ---
    if "16:30" <= saat_str < "16:45" and simdi.weekday() < 5:
        telegram_mesaj_gonder("🔔 **ABD BORSALARI AÇILDI (TSİ 16:30)!**\n🤖 Bot hayatta (*alive*), 3 strateji ile canlı tarama başladı.")
    elif "23:00" <= saat_str < "23:15" and simdi.weekday() < 5:
        telegram_mesaj_gonder("🔔 **ABD BORSALARI KAPANDI (TSİ 23:00)!**\n💤 Günlük taramalar tamamlandı. Bot nöbet modunda.")

    # Tüm Çiftleri Tara
    for symbol_a, symbol_b in PAIRS:
        try:
            df = yf.download([symbol_a, symbol_b], period="5d", interval=TIMEFRAME, progress=False)['Close']
            df = df.dropna()
            if df.empty or len(df) < Z_PERIOD + 5:
                continue

            # 1. Z-Score & Pair Rasyo Hesaplama
            df['Ratio'] = df[symbol_a] / df[symbol_b]
            mean = df['Ratio'].rolling(Z_PERIOD).mean()
            std = df['Ratio'].rolling(Z_PERIOD).std()
            df['Z_Score'] = (df['Ratio'] - mean) / std

            # 2. RSI (3 Periyot) Hesaplama
            delta = df[symbol_a].diff()
            gain = (delta.where(delta > 0, 0)).rolling(3).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(3).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))

            price_a = df[symbol_a].iloc[-1]
            price_b = df[symbol_b].iloc[-1]
            z_val = df['Z_Score'].iloc[-1]
            rsi_val = df['RSI'].iloc[-1]
            ratio_val = df['Ratio'].iloc[-1]

            atr_approx = price_a * 0.015  # Volatilite seviyesi
            
            # --- STRATEJİ 1: PAIR TRADING Z-SCORE (Aşırı Dip) ---
            if z_val <= Z_LOWER:
                tp = price_a + (2 * atr_approx)
                sl = price_a - (1.5 * atr_approx)
                msg = f"""⚖️ **STRATEJİ 1: PAIR TRADING (Aşırı Dip)**

🔀 **Çift:** {symbol_a} / {symbol_b}
⏱ **Zaman Dilimi:** {TIMEFRAME} (15 Dakika)
📉 **Z-Score:** {z_val:.2f} | **Rasyo:** {ratio_val:.4f}
⏰ **Saat (TSİ):** {saat_saniye}

🎯 **AKSİYON PLANINIZ:**
🟢 **LONG (AL):** {symbol_a} (Anlık Fiyat: ${price_a:.2f})
🔴 **SHORT (AÇIĞA SAT / ÇIKAR):** {symbol_b} (Anlık Fiyat: ${price_b:.2f}) *(Hedged)*

📊 **İŞLEM SEVİYELERİ:**
🎯 **Kar Al (TP):** ${tp:.2f} *(Ratio Mean Reversion)*
🛡 **Stop Loss (SL):** ${sl:.2f}

💡 **Gerekçe:** {symbol_a} aşırı ucuzladı (Z <= -2.0). Tepki alımı ve rotasyon bekleniyor."""
                telegram_mesaj_gonder(msg)

            # --- STRATEJİ 2: PRO BOTTOM REVERSAL (Aşırı Satım + Dip Dönüşü) ---
            elif rsi_val <= 30 and z_val < -1.2:
                tp = price_a * 1.03
                sl = price_a * 0.985
                msg = f"""🚀 **STRATEJİ 2: DİP DÖNÜŞÜ (Pro Bottom Reversal)**

📌 **Hisse / ETF:** {symbol_a}
⏱ **Zaman Dilimi:** {TIMEFRAME} (15 Dakika)
📊 **RSI (3):** {rsi_val:.1f} (Aşırı Satım) | **Z-Score:** {z_val:.2f}
⏰ **Saat (TSİ):** {saat_saniye}

🎯 **AKSİYON PLANINIZ:**
🟢 **LONG (AL):** {symbol_a} (Anlık Fiyat: ${price_a:.2f})
💡 **Yön Notu:** Satış/Short pozisyonları kapatın veya azaltın.

📊 **İŞLEM SEVİYELERİ:**
🎯 **Kar Al (TP):** ${tp:.2f} (+%3.0)
🛡 **Stop Loss (SL):** ${sl:.2f} (-%1.5)

💡 **Gerekçe:** Çiftli aşırı satım (RSI + Z-Score) dip dönüş sinyali verdi."""
                telegram_mesaj_gonder(msg)

            # --- STRATEJİ 3: MOMENTUM & ZİRVE ROTASYONU ---
            elif z_val >= Z_UPPER:
                tp = price_b + (2 * atr_approx)
                sl = price_b - (1.5 * atr_approx)
                msg = f"""⚡ **STRATEJİ 3: MOMENTUM & ZİRVE ROTASYONU**

🔀 **Çift:** {symbol_a} / {symbol_b}
⏱ **Zaman Dilimi:** {TIMEFRAME} (15 Dakika)
📈 **Z-Score:** {z_val:.2f} (Aşırı Zirve)
⏰ **Saat (TSİ):** {saat_saniye}

🎯 **AKSİYON PLANINIZ:**
🟢 **LONG (AL):** {symbol_b} (Anlık Fiyat: ${price_b:.2f})
🔴 **SHORT (AÇIĞA SAT):** {symbol_a} (Anlık Fiyat: ${price_a:.2f})

📊 **İŞLEM SEVİYELERİ:**
🎯 **Kar Al (TP):** ${tp:.2f}
🛡 **Stop Loss (SL):** ${sl:.2f}

💡 **Gerekçe:** {symbol_a} aşırı değerlendi, ters yöndeki {symbol_b} tarafına rotasyon fırsatı."""
                telegram_mesaj_gonder(msg)

        except Exception as e:
            print(f"Hata ({symbol_a}/{symbol_b}): {e}")

if __name__ == "__main__":
    strateji_taramasi_yap()
