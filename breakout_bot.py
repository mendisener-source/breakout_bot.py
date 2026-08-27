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
    ("SPXL", "SPXS"),   # S&P 500 3x Bull/Bear
    ("SOXL", "SOXS"),   # Semiconductor 3x Bull/Bear
    ("TQQQ", "SQQQ"),   # Nasdaq-100 3x Bull/Bear
    ("NVDU", "NVDD"),   # Nvidia 2x Bull/Bear
    ("NUGT", "DUST")    # Gold Miners 2x Bull/Bear
]

# Taranacak Zaman Dilimleri: (Timeframe Kodu, Etiket, Veri Çekme Periyodu)
TIMEFRAMES = [
    ("15m", "15 Dakika (15m)", "5d"),
    ("1h",  "Saatlik (1h)",   "1mo"),
    ("1d",  "Günlük (1d)",    "6mo")
]

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

    # --- AÇILIŞ / KAPANIŞ BİLDİRİMLERİ ---
    if "16:30" <= saat_str < "16:45" and simdi.weekday() < 5:
        telegram_mesaj_gonder("🔔 **ABD BORSALARI AÇILDI (TSİ 16:30)!**\n🤖 Bot aktif; 15m, 1h ve 1d zaman dilimlerinde canlı tarama başladı.")
    elif "23:00" <= saat_str < "23:15" and simdi.weekday() < 5:
        telegram_mesaj_gonder("🔔 **ABD BORSALARI KAPANDI (TSİ 23:00)!**\n💤 Tüm zaman dilimi taramaları tamamlandı. Bot nöbet modunda.")

    # --- ZAMAN DİLİMİ DÖNGÜSÜ (15m, 1h, 1d) ---
    for tf_code, tf_label, period_val in TIMEFRAMES:
        for symbol_a, symbol_b in PAIRS:
            try:
                # Veri Çekme
                data = yf.download([symbol_a, symbol_b], period=period_val, interval=tf_code, progress=False)
                if data.empty:
                    continue

                # A Sembolü Verileri
                df_a = pd.DataFrame({
                    'Open': data['Open'][symbol_a],
                    'High': data['High'][symbol_a],
                    'Low': data['Low'][symbol_a],
                    'Close': data['Close'][symbol_a],
                    'Volume': data['Volume'][symbol_a]
                }).dropna()

                # B Sembolü Kapanış Fiyatı
                df_b_close = data['Close'][symbol_b].dropna()

                if len(df_a) < 30 or len(df_b_close) < 30:
                    continue

                # -------------------------------------------------------------
                # İNDİKATÖR HESAPLAMALARI
                # -------------------------------------------------------------
                price_a = df_a['Close'].iloc[-1]
                price_b = df_b_close.iloc[-1]

                # 1. Z-Score & Pair Ratio
                ratio = df_a['Close'] / df_b_close
                mean_ratio = ratio.rolling(Z_PERIOD).mean()
                std_ratio = ratio.rolling(Z_PERIOD).std()
                z_score = (ratio - mean_ratio) / std_ratio
                z_val = z_score.iloc[-1]
                ratio_val = ratio.iloc[-1]

                # 2. RSI (3 Periyot)
                delta = df_a['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(3).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(3).mean()
                rsi = 100 - (100 / (1 + (gain / loss)))
                rsi_val = rsi.iloc[-1]

                # 3. Donchian Channel (20 Periyot)
                donchian_high = df_a['High'].rolling(20).max().shift(1).iloc[-1]

                # 4. Bollinger Bands (20 Periyot, 2 Std)
                bb_middle = df_a['Close'].rolling(20).mean()
                bb_std = df_a['Close'].rolling(20).std()
                bb_lower = (bb_middle - (2 * bb_std)).iloc[-1]

                # 5. MACD (12, 26, 9)
                ema12 = df_a['Close'].ewm(span=12, adjust=False).mean()
                ema26 = df_a['Close'].ewm(span=26, adjust=False).mean()
                macd_line = ema12 - ema26
                signal_line = macd_line.ewm(span=9, adjust=False).mean()
                macd_val = macd_line.iloc[-1]
                signal_val = signal_line.iloc[-1]
                prev_macd = macd_line.iloc[-2]
                prev_signal = signal_line.iloc[-2]

                # Volatilite Bazlı ATR Yaklaşımı
                atr_approx = price_a * 0.015

                # -------------------------------------------------------------
                # STRATEJİ SİNYAL KONTROLLERİ
                # -------------------------------------------------------------

                # --- STRATEJİ 1: PAIR TRADING Z-SCORE (Aşırı Dip) ---
                if z_val <= Z_LOWER:
                    tp = price_a + (2 * atr_approx)
                    sl = price_a - (1.5 * atr_approx)
                    msg = f"""⚖️ **STRATEJİ 1: PAIR TRADING (Aşırı Dip)**

🔀 **Çift:** {symbol_a} / {symbol_b}
⏱ **Zaman Dilimi:** {tf_label}
📉 **Z-Score:** {z_val:.2f} | **Rasyo:** {ratio_val:.4f}
⏰ **Saat (TSİ):** {saat_saniye}

🎯 **AKSİYON PLANINIZ:**
🟢 **LONG (AL):** {symbol_a} (Anlık: ${price_a:.2f})
🔴 **SHORT (AÇIĞA SAT):** {symbol_b} (Anlık: ${price_b:.2f}) *(Hedged)*

📊 **İŞLEM SEVİYELERİ:**
🎯 **Kar Al (TP):** ${tp:.2f}
🛡 **Stop Loss (SL):** ${sl:.2f}

💡 **Gerekçe:** {symbol_a} aşırı ucuzladı (Z <= -2.0). Reversion bekleniyor."""
                    telegram_mesaj_gonder(msg)

                # --- STRATEJİ 2: PRO BOTTOM REVERSAL (RSI + Z-Score) ---
                elif rsi_val <= 30 and z_val < -1.2:
                    tp = price_a * 1.03
                    sl = price_a * 0.985
                    msg = f"""🚀 **STRATEJİ 2: DİP DÖNÜŞÜ (Pro Bottom Reversal)**

📌 **Hisse / ETF:** {symbol_a}
⏱ **Zaman Dilimi:** {tf_label}
📊 **RSI (3):** {rsi_val:.1f} | **Z-Score:** {z_val:.2f}
⏰ **Saat (TSİ):** {saat_saniye}

🎯 **AKSİYON PLANINIZ:**
🟢 **LONG (AL):** {symbol_a} (Anlık: ${price_a:.2f})

📊 **İŞLEM SEVİYELERİ:**
🎯 **Kar Al (TP):** ${tp:.2f} (+%3.0)
🛡 **Stop Loss (SL):** ${sl:.2f} (-%1.5)

💡 **Gerekçe:** Çiftli aşırı satım dip dönüş sinyali verdi."""
                    telegram_mesaj_gonder(msg)

                # --- STRATEJİ 3: MOMENTUM & ZİRVE ROTASYONU ---
                elif z_val >= Z_UPPER:
                    tp = price_b + (2 * atr_approx)
                    sl = price_b - (1.5 * atr_approx)
                    msg = f"""⚡ **STRATEJİ 3: MOMENTUM & ZİRVE ROTASYONU**

🔀 **Çift:** {symbol_a} / {symbol_b}
⏱ **Zaman Dilimi:** {tf_label}
📈 **Z-Score:** {z_val:.2f} (Aşırı Zirve)
⏰ **Saat (TSİ):** {saat_saniye}

🎯 **AKSİYON PLANINIZ:**
🟢 **LONG (AL):** {symbol_b} (Anlık: ${price_b:.2f})
🔴 **SHORT (AÇIĞA SAT):** {symbol_a} (Anlık: ${price_a:.2f})

📊 **İŞLEM SEVİYELERİ:**
🎯 **Kar Al (TP):** ${tp:.2f}
🛡 **Stop Loss (SL):** ${sl:.2f}

💡 **Gerekçe:** {symbol_a} aşırı değerlendi, ters yöndeki {symbol_b} tarafına rotasyon fırsatı."""
                    telegram_mesaj_gonder(msg)

                # --- STRATEJİ 4: DONCHIAN CHANNEL BREAKOUT ---
                elif price_a > donchian_high:
                    tp = price_a * 1.025
                    sl = donchian_high
                    msg = f"""📐 **STRATEJİ 4: DONCHIAN YUKARI KIRILIM (Breakout)**

📌 **Hisse / ETF:** {symbol_a}
⏱ **Zaman Dilimi:** {tf_label}
📈 **20-Bar Zirve Kırılımı:** ${donchian_high:.2f}
⏰ **Saat (TSİ):** {saat_saniye}

🎯 **AKSİYON PLANINIZ:**
🟢 **LONG (AL):** {symbol_a} (Anlık: ${price_a:.2f})

📊 **İŞLEM SEVİYELERİ:**
🎯 **Kar Al (TP):** ${tp:.2f} (+%2.5)
🛡 **Stop Loss (SL):** ${sl:.2f} (Kırılım Desteği)

💡 **Gerekçe:** Fiyat 20 barlık en yüksek seviyeyi yukarı kırdı (Trend Takip)."""
                    telegram_mesaj_gonder(msg)

                # --- STRATEJİ 5: BOLLINGER BAND TAŞMASI ---
                elif price_a < bb_lower and rsi_val < 35:
                    tp = bb_middle.iloc[-1]
                    sl = price_a * 0.988
                    msg = f"""📊 **STRATEJİ 5: BOLLINGER ALT BAND TAŞMASI**

📌 **Hisse / ETF:** {symbol_a}
⏱ **Zaman Dilimi:** {tf_label}
📉 **Bollinger Alt Bant:** ${bb_lower:.2f}
⏰ **Saat (TSİ):** {saat_saniye}

🎯 **AKSİYON PLANINIZ:**
🟢 **LONG (AL):** {symbol_a} (Anlık: ${price_a:.2f})

📊 **İŞLEM SEVİYELERİ:**
🎯 **Kar Al (TP):** ${tp:.2f} (Orta Banda Dönüş)
🛡 **Stop Loss (SL):** ${sl:.2f}

💡 **Gerekçe:** Fiyat Bollinger alt bandının dışına taştı, ortalamaya tepki bekleniyor."""
                    telegram_mesaj_gonder(msg)

                # --- STRATEJİ 6: MACD MOMENTUM KESİŞİMİ ---
                elif prev_macd < prev_signal and macd_val > signal_val and macd_val < 0:
                    tp = price_a * 1.02
                    sl = price_a * 0.99
                    msg = f"""🌊 **STRATEJİ 6: MACD MOMENTUM KESİŞİMİ**

📌 **Hisse / ETF:** {symbol_a}
⏱ **Zaman Dilimi:** {tf_label}
📈 **MACD:** {macd_val:.3f} | **Sinyal:** {signal_val:.3f}
⏰ **Saat (TSİ):** {saat_saniye}

🎯 **AKSİYON PLANINIZ:**
🟢 **LONG (AL):** {symbol_a} (Anlık: ${price_a:.2f})

📊 **İŞLEM SEVİYELERİ:**
🎯 **Kar Al (TP):** ${tp:.2f} (+%2.0)
🛡 **Stop Loss (SL):** ${sl:.2f} (-%1.0)

💡 **Gerekçe:** MACD dip bölgesinde sinyal çizgisini yukarı kesti (Momentum Başlangıcı)."""
                    telegram_mesaj_gonder(msg)

            except Exception as e:
                print(f"Hata ({symbol_a}/{symbol_b} - {tf_code}): {e}")

if __name__ == "__main__":
    strateji_taramasi_yap()
