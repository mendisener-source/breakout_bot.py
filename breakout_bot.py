import os
import json
import html
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

# ============================================================
# AYARLAR
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX", "QQQ"]
INTERVAL = "1h"
PERIOD = "3mo"

# Strateji parametreleri
BREAKOUT_PERIOD = 20
EMA_FAST = 20
EMA_SLOW = 50
RSI_PERIOD = 14
ATR_PERIOD = 14
VOLUME_PERIOD = 20
VOLUME_FACTOR = 1.20
STOP_ATR = 1.50
TARGET_ATR = 3.00
TRAIL_ATR = 1.50

STATE_FILE = Path("trading_state.json")


def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[-] Telegram bilgileri eksik. Mesaj terminale yazdırıldı:")
        print(message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
        timeout=20,
    )
    if response.status_code != 200:
        print(f"[-] Telegram hatası: {response.status_code} - {response.text}")


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def prepare_data(df):
    df = df.copy().dropna(how="all")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Son mum tamamlanmamış olabilir; sinyalde kullanma.
    if len(df) > 1:
        df = df.iloc[:-1].copy()

    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - df["Close"].shift()).abs(),
            (df["Low"] - df["Close"].shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df["EMA20"] = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=EMA_SLOW, adjust=False).mean()
    df["RSI"] = rsi(df["Close"], RSI_PERIOD)
    df["ATR"] = tr.rolling(ATR_PERIOD).mean()
    df["AvgVolume"] = df["Volume"].rolling(VOLUME_PERIOD).mean()
    df["BreakoutHigh"] = df["High"].shift(1).rolling(BREAKOUT_PERIOD).max()
    df["BreakoutLow"] = df["Low"].shift(1).rolling(BREAKOUT_PERIOD).min()
    return df.dropna()


def fmt_time(index_value):
    timestamp = pd.Timestamp(index_value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    return timestamp.tz_convert("Europe/Istanbul").strftime("%d.%m.%Y %H:%M")


def make_message(side, symbol, row, entry, stop, target, reason):
    label = "ALIM SİNYALİ" if side == "LONG" else "SATIŞ SİNYALİ"
    emoji = "🟢" if side == "LONG" else "🔴"
    return (
        f"{emoji} <b>{label}</b>\n\n"
        f"<b>Hisse:</b> {html.escape(symbol)}\n"
        f"<b>Fiyat:</b> ${row['Close']:.2f}\n"
        f"<b>RSI:</b> {row['RSI']:.1f}\n"
        f"<b>Hacim oranı:</b> {row['Volume'] / row['AvgVolume']:.2f}x\n"
        f"<b>Giriş:</b> ${entry:.2f}\n"
        f"<b>Stop:</b> ${stop:.2f}\n"
        f"<b>Hedef:</b> ${target:.2f}\n"
        f"<b>Gerekçe:</b> {reason}\n"
        f"<b>Zaman:</b> {fmt_time(row.name)}"
    )


def scan_symbol(symbol, state):
    df = yf.Ticker(symbol).history(period=PERIOD, interval=INTERVAL, auto_adjust=False)
    if df.empty or len(df) < 100:
        print(f"[-] {symbol}: yeterli veri yok")
        return

    df = prepare_data(df)
    row = df.iloc[-1]
    candle_id = str(df.index[-1])
    current = state.get(symbol)

    # Açık pozisyon varsa önce çıkış koşullarını kontrol et.
    if current:
        side = current["side"]
        entry = float(current["entry"])
        stop = float(current["stop"])
        target = float(current["target"])
        exit_reason = None

        if side == "LONG":
            current["highest"] = max(float(current.get("highest", entry)), float(row["High"]))
            trailing_stop = current["highest"] - TRAIL_ATR * row["ATR"]
            stop = max(stop, trailing_stop)
            if row["Low"] <= stop:
                exit_reason = f"Stop/trailing stop (${stop:.2f})"
            elif row["High"] >= target:
                exit_reason = f"Hedef fiyat (${target:.2f})"
            elif row["Close"] < row["EMA20"]:
                exit_reason = "EMA20 aşağı kırıldı"
        else:
            current["lowest"] = min(float(current.get("lowest", entry)), float(row["Low"]))
            trailing_stop = current["lowest"] + TRAIL_ATR * row["ATR"]
            stop = min(stop, trailing_stop)
            if row["High"] >= stop:
                exit_reason = f"Stop/trailing stop (${stop:.2f})"
            elif row["Low"] <= target:
                exit_reason = f"Hedef fiyat (${target:.2f})"
            elif row["Close"] > row["EMA20"]:
                exit_reason = "EMA20 yukarı kırıldı"

        current["stop"] = stop
        if exit_reason and current.get("last_exit_candle") != candle_id:
            send_telegram(
                f"⚪ <b>POZİSYON KAPAT</b>\n\n"
                f"<b>Hisse:</b> {html.escape(symbol)}\n"
                f"<b>Yön:</b> {side}\n"
                f"<b>Çıkış fiyatı:</b> ${row['Close']:.2f}\n"
                f"<b>Giriş:</b> ${entry:.2f}\n"
                f"<b>Yaklaşık getiri:</b> {((row['Close'] / entry - 1) * 100 if side == 'LONG' else (entry / row['Close'] - 1) * 100):.2f}%\n"
                f"<b>Gerekçe:</b> {exit_reason}\n"
                f"<b>Zaman:</b> {fmt_time(row.name)}"
            )
            state.pop(symbol, None)
        return

    volume_ok = row["Volume"] >= row["AvgVolume"] * VOLUME_FACTOR
    bullish = (
        row["Close"] > row["BreakoutHigh"]
        and row["Close"] > row["EMA20"] > row["EMA50"]
        and 55 <= row["RSI"] <= 75
        and volume_ok
        and row["Close"] > row["Open"]
    )
    bearish = (
        row["Close"] < row["BreakoutLow"]
        and row["Close"] < row["EMA20"] < row["EMA50"]
        and 25 <= row["RSI"] <= 45
        and volume_ok
        and row["Close"] < row["Open"]
    )

    # Aynı mumda tekrar tekrar AL/SAT mesajı göndermeyi önle.
    if state.get(f"{symbol}_last_signal") == candle_id:
        return

    if bullish:
        entry = float(row["Close"])
        stop = entry - STOP_ATR * row["ATR"]
        target = entry + TARGET_ATR * row["ATR"]
        send_telegram(make_message("LONG", symbol, row, entry, stop, target, "20 periyot yukarı kırılım + trend/hacim/RSI onayı"))
        state[symbol] = {"side": "LONG", "entry": entry, "stop": stop, "target": target, "highest": entry}
        state[f"{symbol}_last_signal"] = candle_id
    elif bearish:
        entry = float(row["Close"])
        stop = entry + STOP_ATR * row["ATR"]
        target = entry - TARGET_ATR * row["ATR"]
        send_telegram(make_message("SHORT", symbol, row, entry, stop, target, "20 periyot aşağı kırılım + trend/hacim/RSI onayı"))
        state[symbol] = {"side": "SHORT", "entry": entry, "stop": stop, "target": target, "lowest": entry}
        state[f"{symbol}_last_signal"] = candle_id
    else:
        print(f"[i] {symbol}: sinyal yok | fiyat ${row['Close']:.2f} | RSI {row['RSI']:.1f}")


def main():
    state = load_state()
    print("[*] Gelişmiş al-sat taraması başladı...")
    for symbol in SYMBOLS:
        try:
            scan_symbol(symbol, state)
        except Exception as exc:
            print(f"[-] {symbol} hata: {exc}")
    save_state(state)


if __name__ == "__main__":
    main()
