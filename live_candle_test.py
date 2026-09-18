import os
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

SYMBOL = "EUR/USD"
INTERVAL = "5min"
OUTPUTSIZE = 5

IST = timezone(timedelta(hours=5, minutes=30))

API_KEY = os.environ["TWELVE_DATA_API_KEY"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def fetch_candles():
    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "outputsize": str(OUTPUTSIZE),
        "order": "DESC",
        "timezone": "UTC",
        "apikey": API_KEY,
    }

    url = (
        "https://api.twelvedata.com/time_series?"
        + urllib.parse.urlencode(params)
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Kavi-Live-Candle-Test/1.0"}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    if "values" not in data:
        raise RuntimeError(
            "Twelve Data error: " + json.dumps(data)
        )

    return data["values"]


def utc_to_ist(utc_string):
    dt = datetime.strptime(
        utc_string,
        "%Y-%m-%d %H:%M:%S"
    ).replace(tzinfo=timezone.utc)

    return dt.astimezone(IST)


def send_telegram(message):
    url = (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/sendMessage"
    )

    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message
    }).encode()

    request = urllib.request.Request(
        url,
        data=data,
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        print(response.read().decode())


def main():
    candles = fetch_candles()

    # Twelve Data returns the newest candle first.
    # The newest candle may still be forming.
    # Therefore use the second candle as the latest CLOSED candle.

    closed = candles[1]

    candle_time_ist = utc_to_ist(closed["datetime"])

    open_price = float(closed["open"])
    high_price = float(closed["high"])
    low_price = float(closed["low"])
    close_price = float(closed["close"])

    if close_price > open_price:
        candle_type = "BULLISH"
    elif close_price < open_price:
        candle_type = "BEARISH"
    else:
        candle_type = "DOJI"

    message = f"""🟢 KAVI LIVE CANDLE TEST

EUR/USD • 5 MIN

Candle Close: {candle_time_ist:%Y-%m-%d %H:%M} IST

Open:  {open_price:.5f}
High:  {high_price:.5f}
Low:   {low_price:.5f}
Close: {close_price:.5f}

Candle: {candle_type}

Twelve Data → GitHub Actions → Telegram ✅"""

    print(message)

    send_telegram(message)


if __name__ == "__main__":
    main()
