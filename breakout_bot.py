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

# Taranacak Hisse Senedi Sembolleri
SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", 
    "META", "TSLA", "AMD", "NFLX", "QQQ"
]

# ==========================================
# 2. TELEGRAM BİLDİRİM & GÖRSEL GÖNDERİMİ
# ==========================================
def send_telegram_photo(photo_path, caption):
    """
    Üretilen grafik görselini ve mesajı Telegram'a gönderir.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[-] HATA: Telegram Bot Token veya Chat ID eksik!")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    
    try:
        with open(photo_path, 'rb') as photo:
            payload = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'HTML'}
            files = {'photo': photo}
            response = requests.post(url, data=payload, files=files, timeout=20)
            
        if response.status_code == 200:
            print(f"[+] Telegram görsel bildirimi başarıyla gönderildi: {caption.splitlines()[0]}")
        else:
            print(f"[-] Telegram gönderim hatası: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[-] Telegram bağlantı hatası: {e}")

# ==========================================
# 3. GRAFİK ÇİZİMİ (MPLFINANCE)
# ==========================================
def generate_chart(df, symbol):
    """
    Hisse verilerinden mum grafiği ve hacim paneli üreterek PNG kaydeder.
    """
    filename = f"{symbol}_chart.png"
    
    # Mum grafiği renk stili
    mc = mpf.make_marketcolors(
        up='#26a69a',      # Yeşil mumlar
        down='#ef5350',    # Kırmızı mumlar
        edge='inherit',
        wick='inherit',
        volume='in'
    )
    style = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', gridcolor='#e0e0e0')
    
    # Grafiği çiz ve dosyaya kaydet
    mpf.plot(
        df.tail(60), # Son 60 periyodu göster
        type='candle',
        volume=True,
        title=f"\n{symbol} - Breakout Chart",
        style=style,
        savefig=dict(fname=filename, dpi=150, bbox_inches='tight')
    )
    return filename

# ==========================================
# 4. TEKNİK ANALİZ & TARAMA MOTORU
# ==========================================
def analyze_and_scan():
    print("[*] Tarama başlatılıyor...")
    
    for symbol in SYMBOLS:
        try:
            # yfinance ile 1 saatlik verileri çek
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1mo", interval="1h")
            
            if df.empty or len(df) < 20:
                print(f"[-] {symbol} için yeterli veri alınamadı.")
                continue

            # 20 periyotluk En Yüksek (High) ve En Düşük (Low) seviyeleri hesapla
            df['20_High'] = df['High'].shift(1).rolling(window=20).max()
            df['20_Low'] = df['Low'].shift(1).rolling(window=20).min()
            
            # Son kapanış ve kırılım kontrolleri
            last_row = df.iloc[-1]
            last_close = last_row['Close']
            prev_high_20 = last_row['20_High']
            prev_low_20 = last_row['20_Low']
            
            # Kırılım (Breakout) Koşulları
            is_bullish_breakout = last_close > prev_high_20
            is_bearish_breakout = last_close < prev_low_20

            if is_bullish_breakout or is_bearish_breakout:
                signal_type = "🚀 **YUKARI KIRILIM (BULLISH)**" if is_bullish_breakout else "🔻 **AŞAĞI KIRILIM (BEARISH)**"
                
                # Mesaj Metni
                caption = (
                    f"{signal_type}\n\n"
                    f"<b>Hisse:</b> {symbol}\n"
                    f"<b>Son Fiyat:</b> ${last_close:.2f}\n"
                    f"<b>20-Periyot Zirve:</b> ${prev_high_20:.2f}\n"
                    f"<b>Zaman:</b> {df.index[-1].strftime('%Y-%m-%d %H:%M UTC')}"
                )
                
                # Grafiği üret ve Telegram'a gönder
                chart_path = generate_chart(df, symbol)
                send_telegram_photo(chart_path, caption)
                
                # Geçici grafik dosyasını sil
                if os.path.exists(chart_path):
                    os.remove(chart_path)
            else:
                print(f"[i] {symbol}: Kırılım yok (Fiyat: ${last_close:.2f})")

        except Exception as e:
            print(f"[-] {symbol} işlenirken hata oluştu: {e}")

# ==========================================
# 5. UYGULAMA GİRİŞ NOKTASI
# ==========================================
if __name__ == "__main__":
    analyze_and_scan()
