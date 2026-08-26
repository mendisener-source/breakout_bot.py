import os
import time
from datetime import datetime
import pandas as pd
import numpy as np
import yfinance as yf
import requests

# --- TELEGRAM VE SUNUCU AYARLARI ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

# Takip Edilecek ABD Sembol Listesi
SYMBOLS = ["SPXL", "SPXS", "SOXL", "SOXS", "TQQQ", "SQQQ", "NVDU", "NVDD"]

# Günlük Takip Bayrakları (Hafıza)
sent_signals_today = set()
heartbeat_sent_today = False
close_summary_sent_today = False
last_reset_day = datetime.now().day

def send_telegram_message(message):
    """Telegram mesajı gönderir."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.ok
    except Exception as e:
        print(f"[HATA] Telegram mesajı gönderilemedi: {e}")
        return False

def calculate_rsi(series, period=3):
    """RSI hesaplar."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_stochastic(df, period=14, smooth_k=3, smooth_d=3):
    """Stochastic Oscillator hesaplar."""
    low_min = df['Low'].rolling(window=period).min()
    high_max = df['High'].rolling(window=period).max()
    k = 100 * ((df['Close'] - low_min) / (high_max - low_min))
    k_smoothed = k.rolling(window=smooth_k).mean()
    d_smoothed = k_smoothed.rolling(window=smooth_d).mean()
    return k_smoothed, d_smoothed

def run_screener():
    global sent_signals_today, heartbeat_sent_today, close_summary_sent_today, last_reset_day
    
    now = datetime.now()
    current_day = now.day
    current_weekday = now.weekday()  # 0=Pazartesi, 4=Cuma, 5=Cumartesi, 6=Pazar

    # Gece yarısı geçtiğinde tüm hafızayı sıfırla
    if current_day != last_reset_day:
        sent_signals_today.clear()
        heartbeat_sent_today = False
        close_summary_sent_today = False
        last_reset_day = current_day
        print("[INFO] Yeni gün başladı, sinyal ve bildirim hafızaları sıfırlandı.")

    print(f"\n[INFO] Tarama Başladı: {now.strftime('%d.%m.%Y %H:%M:%S')}")

    # ==========================================================
    # 1. ABD BORSA AÇILIŞ BİLDİRİMİ (TSİ 16:20)
    # ==========================================================
    if current_weekday < 5 and not heartbeat_sent_today:
        if now.hour == 16 and now.minute >= 20:
            open_msg = (
                f"🔔 **US Market Open Alert (Bot Active)**\n"
                f"📅 **Date:** `{now.strftime('%d.%m.%Y')}`\n"
                f"⏰ **Time (TR):** `{now.strftime('%H:%M:%S')}`\n"
                f"📊 **Tracked Tickers:** `{len(SYMBOLS)}` units\n"
                f"🚀 *US market scan is live. Good trading session!*"
            )
            send_telegram_message(open_msg)
            heartbeat_sent_today = True
            print("[INFO] ABD borsa açılış bildirim mesajı gönderildi.")

    # ==========================================================
    # 2. TEKNİK ANALİZ VE TARAMA DÖNGÜSÜ
    # ==========================================================
    for symbol in SYMBOLS:
        try:
            df = yf.download(symbol, period="1mo", interval="15m", progress=False)
            if df.empty or len(df) < 20:
                continue

            # MultiIndex düzeltmesi
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # İndikatör Hesaplamaları
            df['RSI'] = calculate_rsi(df['Close'], period=3)
            df['Stoch_K'], df['Stoch_D'] = calculate_stochastic(df, period=14, smooth_k=3, smooth_d=3)
            
            # Bollinger Bantları (2.5 Std Dev)
            df['SMA20'] = df['Close'].rolling(window=20).mean()
            df['STD20'] = df['Close'].rolling(window=20).std()
            df['Upper_BB'] = df['SMA20'] + (df['STD20'] * 2.5)
            df['Lower_BB'] = df['SMA20'] - (df['STD20'] * 2.5)

            # Son Mum Verileri
            last_row = df.iloc[-1]
            close_price = last_row['Close']
            rsi_val = last_row['RSI']
            stoch_k = last_row['Stoch_K']
            stoch_d = last_row['Stoch_D']
            
            # --- STRATEJİ KONTROLLERİ ---
            # LONG Sinyali: RSI < 15, Stoch K < 15 ve Lower BB Teması
            is_long = (rsi_val < 15) and (stoch_k < 15) and (close_price <= last_row['Lower_BB'])
            
            # SHORT Sinyali: RSI > 85, Stoch K > 85 ve Upper BB Teması
            is_short = (rsi_val > 85) and (stoch_k > 85) and (close_price >= last_row['Upper_BB'])

            if is_long:
                signal_key = f"{symbol}_LONG_{now.strftime('%Y-%m-%d')}"
                if signal_key not in sent_signals_today:
                    msg = (
                        f"🟢 **LONG SİNYALİ: {symbol}**\n"
                        f"💰 **Fiyat:** `{close_price:.2f}`\n"
                        f"📊 **RSI (3):** `{rsi_val:.1f}` | **Stoch K:** `{stoch_k:.1f}`\n"
                        f"⚠️ *Aşırı dip bölgesi ve Bollinger alt bant teması!*"
                    )
                    send_telegram_message(msg)
                    sent_signals_today.add(signal_key)

            elif is_short:
                signal_key = f"{symbol}_SHORT_{now.strftime('%Y-%m-%d')}"
                if signal_key not in sent_signals_today:
                    msg = (
                        f"🔴 **SHORT SİNYALİ: {symbol}**\n"
                        f"💰 **Fiyat:** `{close_price:.2f}`\n"
                        f"📊 **RSI (3):** `{rsi_val:.1f}` | **Stoch K:** `{stoch_k:.1f}`\n"
                        f"⚠️ *Aşırı zirve bölgesi ve Bollinger üst bant teması!*"
                    )
                    send_telegram_message(msg)
                    sent_signals_today.add(signal_key)

            time.sleep(1) # yfinance rate limit engelleyici

        except Exception as e:
            print(f"[HATA] {symbol} taranırken hata oluştu: {e}")

    # ==========================================================
    # 3. ABD BORSA KAPANIŞ ÖZET BİLDİRİMİ (TSİ 23:00)
    # ==========================================================
    if current_weekday < 5 and not close_summary_sent_today:
        if now.hour == 23 and now.minute >= 0:
            close_msg = (
                f"🔔 **US Market Close Summary**\n"
                f"📅 **Date:** `{now.strftime('%d.%m.%Y')}`\n"
                f"⏰ **Time (TR):** `{now.strftime('%H:%M:%S')}`\n"
                f"📈 **Total Signals Triggered Today:** `{len(sent_signals_today)}`\n"
                f"😴 *US market is closed. Night scanning mode active.*"
            )
            send_telegram_message(close_msg)
            close_summary_sent_today = True
            print("[INFO] ABD borsa kapanış özet mesajı gönderildi.")

# --- ANA ÇALIŞMA DÖNGÜSÜ ---
if __name__ == "__main__":
    # Başlangıç Test Mesajı
    send_telegram_message("🤖 **Breakout & Reversal Bot Başlatıldı:** ABD Piyasa Taraması Aktif!")
    
    while True:
        try:
            run_screener()
        except Exception as e:
            print(f"[CRITICAL HATA] Ana döngü hatası: {e}")
            
        print("[INFO] Tarama tamamlandı. 15 dakika (900 sn) bekleniyor...")
        time.sleep(900)
