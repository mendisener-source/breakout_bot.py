import os
import requests
import yfinance as yf
import pandas as pd
import numpy as np
import pytz
import mplfinance as mpf

# ==========================================
# 1. ORTAM DEĞİŞKENLERİ & AYARLAR
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", 
    "META", "TSLA", "AMD", "NFLX", "QQQ"
]

# ==========================================
# 2. TELEGRAM MESAJ & GÖRSEL FONKSİYONLARI
# ==========================================
def send_telegram_message(message):
    """
    Telegram'a düz metin (durum raporu vb.) gönderir.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"[-] Mesaj gönderme hatası: {e}")

def send_telegram_photo(photo_path, caption):
    """
    Üretilen grafik görselini ve mesajı Telegram'a gönderir.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, 'rb') as photo:
            payload = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'HTML'}
            files = {'photo': photo}
            requests.post(url, data=payload, files=files, timeout=20)
    except Exception as e:
        print(f"[-] Görsel gönderme hatası: {e}")

# ==========================================
# 3. GRAFİK ÇİZİMİ (TRADINGVIEW DARK THEME)
# ==========================================
def generate_chart(df, symbol):
    filename = f"{symbol}_chart.png"
    mc = mpf.make_marketcolors(up='#26a69a', down='#ef5350', edge='inherit', wick='inherit', volume='#26a69a')
    style = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', gridcolor='#2a2e39', facecolor='#131722', figcolor='#131722')
    
    mpf.plot(
        df.tail(60),
        type='candle',
        volume=True,
        title=f"\n{symbol} - BREAKOUT CHART",
        style=style,
        savefig=dict(fname=filename, dpi=150, bbox_inches='tight')
    )
    return filename

# ==========================================
# 4. TEKNİK ANALİZ & TARAMA MOTORU
# ==========================================
def analyze_and_scan():
    print("[*] Tarama başlatılıyor...")
    
    # 1. BOTUN YAŞADIĞINI GÖSTEREN BAŞLANGIÇ MESAJI
    send_telegram_message("🤖 <b>Bot Çalıştı:</b> Piyasalar taranmaya başlandı...")
    
    breakout_count = 0
    
    for symbol in SYMBOLS:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1mo", interval="1h")
            
            if df.empty or len(df) < 20:
                continue

            df['20_High'] = df['High'].shift(1).rolling(window=20).max()
            df['20_Low'] = df['Low'].shift(1).rolling(window=20).min()
            
            last_row = df.iloc[-1]
            last_close = last_row['Close']
            prev_high_20 = last_row['20_High']
            prev_low_20 = last_row['20_Low']
            
            is_bullish_breakout = last_close > prev_high_20
            is_bearish_breakout = last_close < prev_low_20

            if is_bullish_breakout or is_bearish_breakout:
                breakout_count += 1
                signal_type = "🚀 <b>YUKARI KIRILIM (BULLISH)</b>" if is_bullish_breakout else "🔻 <b>AŞAĞI KIRILIM (BEARISH)</b>"
                breakout_level = prev_high_20 if is_bullish_breakout else prev_low_20
                level_label = "20-Periyot Zirve" if is_bullish_breakout else "20-Periyot Dip"
                
                caption = (
                    f"{signal_type}\n\n"
                    f"<b>Hisse:</b> {symbol}\n"
                    f"<b>Son Fiyat:</b> ${last_close:.2f}\n"
                    f"<b>{level_label}:</b> ${breakout_level:.2f}\n"
                    f"<b>Zaman:</b> {df.index[-1].strftime('%Y-%m-%d %H:%M UTC')}"
                )
                
                chart_path = generate_chart(df, symbol)
                send_telegram_photo(chart_path, caption)
                
                if os.path.exists(chart_path):
                    os.remove(chart_path)

        except Exception as e:
            print(f"[-] {symbol} hatası: {e}")

    # 2. TARAMA BİTTİĞİNDE ÖZET RAPOR MESAJI
    send_telegram_message(f"✅ <b>Tarama Tamamlandı.</b> Toplam {len(SYMBOLS)} hisse incelendi. Yeni Kırılım Sayısı: <b>{breakout_count}</b>")

if __name__ == "__main__":
    analyze_and_scan()
