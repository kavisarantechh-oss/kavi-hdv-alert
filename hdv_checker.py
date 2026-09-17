import os
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

# KAVI HDV V1 - historical signal test
SYMBOL = "EUR/USD"
INTERVAL = "5min"
OUTPUTSIZE = 5000
TEST_DATE_IST = os.getenv("TEST_DATE_IST", "2026-09-15")
API_KEY = os.environ["TWELVE_DATA_API_KEY"]
IST = timezone(timedelta(hours=5, minutes=30))

def fetch_candles():
    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "outputsize": str(OUTPUTSIZE),
        "order": "ASC",
        "timezone": "UTC",
        "apikey": API_KEY,
    }
    url = "https://api.twelvedata.com/time_series?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Kavi-HDV-Alert/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    if "values" not in data:
        raise RuntimeError("Twelve Data error: " + json.dumps(data))
    rows = []
    for r in data["values"]:
        rows.append({
            "datetime": r["datetime"],
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
        })
    return rows

def ema_sma_seed(values, length):
    out = [None] * len(values)
    alpha = 2.0 / (length + 1.0)
    seed = []
    prev = None
    for i, v in enumerate(values):
        if v is None:
            continue
        if prev is None:
            seed.append(v)
            if len(seed) == length:
                prev = sum(seed) / length
                out[i] = prev
        else:
            prev = alpha * v + (1.0 - alpha) * prev
            out[i] = prev
    return out

def sma(values, length):
    out = [None] * len(values)
    window = []
    for i, v in enumerate(values):
        if v is None:
            window = []
            continue
        window.append(v)
        if len(window) > length:
            window.pop(0)
        if len(window) == length:
            out[i] = sum(window) / length
    return out

def rma(values, length):
    out = [None] * len(values)
    seed = []
    prev = None
    for i, v in enumerate(values):
        if v is None:
            continue
        if prev is None:
            seed.append(v)
            if len(seed) == length:
                prev = sum(seed) / length
                out[i] = prev
        else:
            prev = ((length - 1) * prev + v) / length
            out[i] = prev
    return out

def calculate_hdv(candles):
    # Exact values from the user's FINAL Pine master.
    emaLen, atrLen, baseMult = 2, 200, 2.0
    volLookback, volPower = 80, 1.0
    trendLookback, trendImpact = 71, 0.3
    multMin, multMax, confirmBars = 3.0, 1.0, 1

    closes = [c["close"] for c in candles]
    basis = ema_sma_seed(closes, emaLen)

    tr = [None] * len(candles)
    for i, c in enumerate(candles):
        if i == 0:
            tr[i] = c["high"] - c["low"]
        else:
            pc = candles[i - 1]["close"]
            tr[i] = max(c["high"] - c["low"],
                        abs(c["high"] - pc),
                        abs(c["low"] - pc))

    atr = rma(tr, atrLen)
    atrAvg = sma(atr, volLookback)

    dir_step = [None] * len(candles)
    for i in range(1, len(candles)):
        if basis[i] is not None and basis[i - 1] is not None:
            dir_step[i] = 1.0 if basis[i] - basis[i - 1] >= 0.0 else -1.0

    trend_memory = ema_sma_seed(dir_step, trendLookback)

    trail_long = [None] * len(candles)
    trail_short = [None] * len(candles)
    regime = 0
    bull_count = 0
    bear_count = 0
    signals = []

    for i, c in enumerate(candles):
        if basis[i] is None or atr[i] is None or atrAvg[i] is None or trend_memory[i] is None:
            continue

        volStretchRaw = 1.0 if atrAvg[i] == 0.0 else atr[i] / atrAvg[i]
        volStretch = volStretchRaw ** volPower
        trendBoost = 1.0 + trendImpact * abs(trend_memory[i])

        multRaw = baseMult * volStretch * trendBoost
        # Preserve the unusual Pine bounds exactly:
        multUpper = min(multRaw, multMax)
        multFinal = max(multUpper, multMin)

        bandTop = basis[i] + multFinal * atr[i]
        bandBot = basis[i] - multFinal * atr[i]

        prevLong = trail_long[i - 1] if i > 0 else None
        prevShort = trail_short[i - 1] if i > 0 else None

        currentLong = prevLong if prevLong is not None else bandBot
        currentShort = prevShort if prevShort is not None else bandTop

        aboveShort = c["close"] > currentShort
        belowLong = c["close"] < currentLong

        bull_count = bull_count + 1 if aboveShort else 0
        bear_count = bear_count + 1 if belowLong else 0

        if regime == 1:
            newLong = max(bandBot, prevLong if prevLong is not None else bandBot)
            newShort = bandTop
        elif regime == -1:
            newShort = min(bandTop, prevShort if prevShort is not None else bandTop)
            newLong = bandBot
        else:
            newLong = bandBot
            newShort = bandTop

        trail_long[i] = newLong
        trail_short[i] = newShort

        old_regime = regime
        if regime == 0:
            if bull_count >= confirmBars:
                regime = 1
            elif bear_count >= confirmBars:
                regime = -1
        elif regime == 1 and bear_count >= confirmBars:
            regime = -1
        elif regime == -1 and bull_count >= confirmBars:
            regime = 1

        change = regime - old_regime
        if change == 2 or change == -2:
            signals.append({
                "side": "LONG" if change == 2 else "SHORT",
                "utc": c["datetime"],
                "close": c["close"],
                "long_trail": newLong,
                "short_trail": newShort,
            })

    return signals

def utc_to_ist(text):
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return dt.astimezone(IST)

def main():
    candles = fetch_candles()
    signals = calculate_hdv(candles)
    target = datetime.strptime(TEST_DATE_IST, "%Y-%m-%d").date()

    print("=" * 72)
    print("KAVI HDV V1 - TWELVE DATA TEST")
    print("Symbol:", SYMBOL)
    print("Test date (IST):", TEST_DATE_IST)
    print("Candles fetched:", len(candles))
    print("=" * 72)

    # Trading day: 02:30 IST to next day 02:25 IST
    start_dt = datetime.strptime(
        TEST_DATE_IST + " 02:30",
        "%Y-%m-%d %H:%M"
    ).replace(tzinfo=IST)

    end_dt = start_dt + timedelta(days=1) - timedelta(minutes=5)
    
    found = []
    for s in signals:
        ist = utc_to_ist(s["utc"])
        if start_dt <= ist <= end_dt:
            found.append((s, ist))

    print("Signals found:", len(found))
    for n, (s, ist) in enumerate(found, 1):
        print(
            f"{n}. {s['side']:5} | {ist:%Y-%m-%d %H:%M} IST | "
            f"Close {s['close']:.5f} | "
            f"LongTrail {s['long_trail']:.5f} | "
            f"ShortTrail {s['short_trail']:.5f}"
        )

    print("\nTEST ONLY - Telegram is not called yet.")

if __name__ == "__main__":
    main()
