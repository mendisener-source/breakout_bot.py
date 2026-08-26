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

# Pair Trading Çiftleri (A / B)
PAIRS = [
    ("SPXL", "SPXS"),   # S&P 500 3x Bull/Bear
    ("SOXL", "SOXS"),   # Semiconductor 3x Bull/Bear
    ("TQQQ", "SQQQ"),   # Nasdaq-100 3x Bull/Bear
    ("NVDU", "NVDD"),   # Nvidia 2x Bull/Bear
    ("TNA", "TZA"),     # Russell 2000 (Small Cap) 3x Bull/Bear
    ("FAS", "FAZ"),     # Financials 3x Bull/Bear
    ("LABU", "LABD"),   # Biotech 3x Bull/Bear
    ("YINN", "YANG"),   # China 3x Bull/Bear
    ("UDOW", "SDOW"),   # Dow Jones 3x Bull/Bear
    ("ERX", "ERY"),     # Energy 2x Bull/Bear
    ("NUGT", "DUST"),   # Gold Miners 2x Bull/Bear
    ("AGQ", "ZSL"),     # Silver 2x Bull/Bear
    ("TMF", "TMV"),     # 20+ Yr Treasury 3x Bull/Bear
    ("UVXY", "SVXY"),   # VIX Volatility Long/Short
    ("BULZ", "BERZ"),   # FANG+ 3x Bull/Bear
    ("WEBL", "WEBS")    # Internet 3x Bull/Bear
]

# Takip Edilecek Tekil Sembol Listesini Çiftlerden Otomatik Çıkar
SYMBOLS = list(set([sym for pair in PAIRS for sym in pair]))

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
                f"🔔 **US Market Open Alert (3 Strateji Aktif)**\n"
                f"📅 **Date:** `{now.strftime('%d.%m.%Y')}`\n"
                f"⏰ **Time (TR):** `{now.strftime('%H:%M:%S')}`\n"
                f"📊 **Tracked Tickers:** `{len(SYMBOLS)}` units\n"
                f"🔄 **Tracked Pairs:** `{len(PAIRS)}` pairs\n"
                f"🚀 *Reversal, Breakout ve Multi-Pair Trading canlı!*"
            )
            send_telegram_message(open_msg)
            heartbeat_sent_today = True
            print("[INFO] ABD borsa açılış bildirim mesajı gönderildi.")

    # ==========================================================
    # 2. STRATEJİ 1 & STRATEJİ 2: TEKİL VARLIK TARAMASI
    # ==========================================================
    for symbol in SYMBOLS:
        try:
            df = yf.download(symbol, period="1mo", interval="15m", progress=False)
            if df.empty or len(df) < 50:
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # İndikatör Hesaplamaları
            df['RSI'] = calculate_rsi(df['Close'], period=3)
            df['Stoch_K'], df['Stoch_D'] = calculate_stochastic(df, period=14, smooth_k=3, smooth_d=3)
            
            # Bollinger Bantları
            df['SMA20'] = df['Close'].rolling(window=20).mean()
            df['STD20'] = df['Close'].rolling(window=20).std()
            df['Upper_BB'] = df['SMA20'] + (df['STD20'] * 2.5)
            df['Lower_BB'] = df['SMA20'] - (df['STD20'] * 2.5)

            # EMA 50 ve Donchian Bantları (20 Periyot)
            df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
            df['Donchian_Upper'] = df['High'].rolling(window=20).max()
            df['Donchian_Lower'] = df['Low'].rolling(window=20).min()

            last_row = df.iloc[-1]
            prev_row = df.iloc[-2]
            close_price = last_row['Close']
            rsi_val = last_row['RSI']
            stoch_k = last_row['Stoch_K']

            # STRATEJİ 1: REVERSAL
            is_rev_long = (rsi_val < 15) and (stoch_k < 15) and (close_price <= last_row['Lower_BB'])
            is_rev_short = (rsi_val > 85) and (stoch_k > 85) and (close_price >= last_row['Upper_BB'])

            if is_rev_long:
                signal_key = f"{symbol}_REV_LONG_{now.strftime('%Y-%m-%d')}"
                if signal_key not in sent_signals_today:
                    msg = (
                        f"🟢 **REVERSAL LONG SİNYALİ: {symbol}**\n"
                        f"💰 **Fiyat:** `{close_price:.2f}`\n"
                        f"📊 **RSI (3):** `{rsi_val:.1f}` | **Stoch K:** `{stoch_k:.1f}`\n"
                        f"⚠️ *Aşırı dip bölgesi ve Bollinger alt bant teması!*"
                    )
                    send_telegram_message(msg)
                    sent_signals_today.add(signal_key)

            elif is_rev_short:
                signal_key = f"{symbol}_REV_SHORT_{now.strftime('%Y-%m-%d')}"
                if signal_key not in sent_signals_today:
                    msg = (
                        f"🔴 **REVERSAL SHORT SİNYALİ: {symbol}**\n"
                        f"💰 **Fiyat:** `{close_price:.2f}`\n"
                        f"📊 **RSI (3):** `{rsi_val:.1f}` | **Stoch K:** `{stoch_k:.1f}`\n"
                        f"⚠️ *Aşırı zirve bölgesi ve Bollinger üst bant teması!*"
                    )
                    send_telegram_message(msg)
                    sent_signals_today.add(signal_key)

            # STRATEJİ 2: BREAKOUT & TREND STOP
            if prev_row['Close'] <= prev_row['Donchian_Upper'] and close_price > last_row['Donchian_Upper']:
                signal_key = f"{symbol}_BREAKOUT_UP_{now.strftime('%Y-%m-%d')}"
                if signal_key not in sent_signals_today:
                    msg = (
                        f"🚀 **BREAKOUT SİNYALİ: {symbol}**\n"
                        f"💰 **Fiyat:** `{close_price:.2f}`\n"
                        f"📈 **Neden:** Donchian Üst Bandı Yukarı Kırıldı!\n"
                        f"⚡ *Güçlü yukarı momentum tespiti.*"
                    )
                    send_telegram_message(msg)
                    sent_signals_today.add(signal_key)

            elif (prev_row['Close'] >= prev_row['EMA50'] and close_price < last_row['EMA50']) or \
                 (close_price <= last_row['Donchian_Lower']):
                signal_key = f"{symbol}_BREAKOUT_STOP_{now.strftime('%Y-%m-%d')}"
                if signal_key not in sent_signals_today:
                    msg = (
                        f"🔻 **TREND STOP / ÇIKIŞ SİNYALİ: {symbol}**\n"
                        f"💰 **Fiyat:** `{close_price:.2f}`\n"
                        f"⚠️ **Neden:** EMA50 Kırıldı / Donchian Alt Band Teması!"
                    )
                    send_telegram_message(msg)
                    sent_signals_today.add(signal_key)

            time.sleep(0.5)

        except Exception as e:
            print(f"[HATA] {symbol} taranırken hata oluştu: {e}")

    # ==========================================================
    # 3. STRATEJİ 3: PAIR TRADING TARAMASI (16 ÇİFT)
    # ==========================================================
    for sym_a, sym_b in PAIRS:
        try:
            df_a = yf.download(sym_a, period="1mo", interval="15m", progress=False)
            df_b = yf.download(sym_b, period="1mo", interval="15m", progress=False)

            if df_a.empty or df_b.empty:
                continue

            if isinstance(df_a.columns, pd.MultiIndex):
                df_a.columns = df_a.columns.get_level_values(0)
            if isinstance(df_b.columns, pd.MultiIndex):
                df_b.columns = df_b.columns.get_level_values(0)

            ratio = df_a['Close'] / df_b['Close']
            mean_ratio = ratio.rolling(window=20).mean()
            std_ratio = ratio.rolling(window=20).std()
            z_score = (ratio - mean_ratio) / std_ratio

            last_z = z_score.iloc[-1]
            last_ratio = ratio.iloc[-1]

            if last_z >= 2.0:
                signal_key = f"PAIR_{sym_a}_{sym_b}_HIGH_{now.strftime('%Y-%m-%d')}"
                if signal_key not in sent_signals_today:
                    msg = (
                        f"⚖️ **PAIR TRADING SİNYALİ (Aşırı Zirve)**\n"
                        f"🔀 **Çift:** `{sym_a} / {sym_b}`\n"
                        f"📈 **Z-Score:** `{last_z:.2f}` (Aşırı Genişleme)\n"
                        f"📊 **Mevcut Rasyo:** `{last_ratio:.4f}`\n"
                        f"💡 *Öneri:* `{sym_a}` aşırı pahalandı, `{sym_b}` tarafına rotasyon beklentisi (*pair ratio mean reversion*)!"
                    )
                    send_telegram_message(msg)
                    sent_signals_today.add(signal_key)

            elif last_z <= -2.0:
                signal_key = f"PAIR_{sym_a}_{sym_b}_LOW_{now.strftime('%Y-%m-%d')}"
                if signal_key not in sent_signals_today:
                    msg = (
                        f"⚖️ **PAIR TRADING SİNYALİ (Aşırı Dip)**\n"
                        f"🔀 **Çift:** `{sym_a} / {sym_b}`\n"
                        f"📉 **Z-Score:** `{last_z:.2f}` (Aşırı Daralma)\n"
                        f"📊 **Mevcut Rasyo:** `{last_ratio:.4f}`\n"
                        f"💡 *Öneri:* `{sym_a}` aşırı ucuzladı, `{sym_a}` tarafına rotasyon beklentisi (*pair ratio mean reversion*)!"
                    )
                    send_telegram_message(msg)
                    sent_signals_today.add(signal_key)

            time.sleep(0.5)

        except Exception as e:
            print(f"[HATA] Pair {sym_a}/{sym_b} taranırken hata oluştu: {e}")

    # ==========================================================
    # 4. ABD BORSA KAPANIŞ ÖZET BİLDİRİMİ (TSİ 23:00)
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
    send_telegram_message("🤖 **Multi-Strategy Bot Başlatıldı:** 16 Pair Çifti & 3 Strateji Aktif!")
    
    while True:
        try:
            run_screener()
        except Exception as e:
            print(f"[CRITICAL HATA] Ana döngü hatası: {e}")
            
        print("[INFO] Tarama tamamlandı. 15 dakika (900 sn) bekleniyor...")
        time.sleep(900)
