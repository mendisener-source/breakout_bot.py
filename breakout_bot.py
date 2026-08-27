import datetime
import requests
import pandas as pd
import yfinance as yf

# ==========================================
# 1. AYARLAR & TOKEN BİLGİLERİ
# ==========================================
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"  # Telegram Bot Token'ınız
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID_HERE"      # Telegram Chat ID'niz

# Takip Edilecek Çift ve Zaman Dilimi Ayarları
PAIR_SYMBOL_1 = "NUGT"
PAIR_SYMBOL_2 = "DUST"
TIMEFRAME = "15m"          # Zaman Dilimi: '15m', '1h', '1d'
Z_PERIOD = 20              # Z-Score periyodu
Z_LOWER_THRESHOLD = -2.0   # Aşırı Dip Eşiği (Alım)
Z_UPPER_THRESHOLD = 2.0    # Aşırı Zirve Eşiği (Satım)

# ==========================================
# 2. TELEGRAM BİLDİRİM FONKSİYONU
# ==========================================
def telegram_mesaj_gonder(mesaj_metni):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mesaj_metni,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ Telegram bildirimi başarıyla gönderildi.")
        else:
            print(f"❌ Telegram Hatası: {response.text}")
    except Exception as e:
        print(f"⚠️ Baglantı Hatası: {e}")

# ==========================================
# 3. Z-SCORE HESAPLAMA VE SİNYAL MEKANİZMASI
# ==========================================
def sinyal_analiz_et():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Veriler çekiliyor: {PAIR_SYMBOL_1}/{PAIR_SYMBOL_2} ({TIMEFRAME})...")
    
    # 5 günlük canlı 15 dakikalık veriyi çek
    df = yf.download([PAIR_SYMBOL_1, PAIR_SYMBOL_2], period="5d", interval=TIMEFRAME)['Close']
    df = df.dropna()
    
    # Pair Rasyosu & Z-Score Hesaplama
    df['Ratio'] = df[PAIR_SYMBOL_1] / df[PAIR_SYMBOL_2]
    mean = df['Ratio'].rolling(Z_PERIOD).mean()
    std = df['Ratio'].rolling(Z_PERIOD).std()
    df['Z_Score'] = (df['Ratio'] - mean) / std

    # Anlık Bar Değerleri
    last_row = df.iloc[-1]
    z_val = last_row['Z_Score']
    ratio_val = last_row['Ratio']
    p1_price = last_row[PAIR_SYMBOL_1]
    p2_price = last_row[PAIR_SYMBOL_2]
    saat_tsi = datetime.datetime.now().strftime("%H:%M:%S")

    # AŞIRI DİP SİNYALİ (Z-Score <= -2.00)
    if z_val <= Z_LOWER_THRESHOLD:
        mesaj = f"""⚖️ **PAIR TRADING SİNYALİ (Aşırı Dip)**

🔀 **Çift:** {PAIR_SYMBOL_1} / {PAIR_SYMBOL_2}
⏱ **Zaman Dilimi:** {TIMEFRAME} (15 Dakika)
📉 **Z-Score:** {z_val:.2f}
📊 **Mevcut Rasyo:** {ratio_val:.4f}
⏰ **Saat (TSİ):** {saat_tsi}

🎯 **AKSİYON PLANI (NE ALINACAK / NE SATILACAK):**
🟢 **LONG (AL):** {PAIR_SYMBOL_1} (Anlık Fiyat: ${p1_price:.2f})
🔴 **SHORT (SAT / AÇIĞA SAT):** {PAIR_SYMBOL_2} (Anlık Fiyat: ${p2_price:.2f}) *(Hedged)*

💡 **Öneri:** {PAIR_SYMBOL_1} aşırı ucuzladı! {PAIR_SYMBOL_1} tarafında yükseliş ve rotasyon beklentisi (*pair ratio mean reversion*)."""
        
        telegram_mesaj_gonder(mesaj)

    # AŞIRI ZİRVE SİNYALİ (Z-Score >= +2.00)
    elif z_val >= Z_UPPER_THRESHOLD:
        mesaj = f"""⚖️ **PAIR TRADING SİNYALİ (Aşırı Zirve)**

🔀 **Çift:** {PAIR_SYMBOL_1} / {PAIR_SYMBOL_2}
⏱ **Zaman Dilimi:** {TIMEFRAME} (15 Dakika)
📈 **Z-Score:** {z_val:.2f}
📊 **Mevcut Rasyo:** {ratio_val:.4f}
⏰ **Saat (TSİ):** {saat_tsi}

🎯 **AKSİYON PLANI (NE ALINACAK / NE SATILACAK):**
🟢 **LONG (AL):** {PAIR_SYMBOL_2} (Anlık Fiyat: ${p2_price:.2f})
🔴 **SHORT (SAT / AÇIĞA SAT):** {PAIR_SYMBOL_1} (Anlık Fiyat: ${p1_price:.2f}) *(Hedged)*

💡 **Öneri:** {PAIR_SYMBOL_1} aşırı pahalılaştı! {PAIR_SYMBOL_2} tarafına rotasyon veya {PAIR_SYMBOL_1}'de düzeltme beklentisi (*pair ratio mean reversion*)."""
        
        telegram_mesaj_gonder(mesaj)

    else:
        print(f"[{saat_tsi}] Z-Score Nötr: {z_val:.2f} | Henüz sinyal bölgesinde değil.")

# ==========================================
# 4. ÇALIŞTIRMA
# ==========================================
if __name__ == "__main__":
    sinyal_analiz_et()
