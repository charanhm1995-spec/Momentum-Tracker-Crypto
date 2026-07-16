#!/usr/bin/env python3
"""
Polls Bybit's public tickers endpoint and appends a price snapshot to
data/history.json. Meant to be run every 5 minutes by GitHub Actions.

No API key needed - this only reads public market data.
"""
import json
import os
import time
import urllib.error
import urllib.request

TICKERS_URL = "https://api.bybit.com/v5/market/tickers?category=linear"
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "history.json")
MIN_TURNOVER_USD = 2_000_000   # skip illiquid symbols to keep the file small
MAX_SNAPSHOTS = 30             # ~2.5 hours of history at 5 min spacing


def is_perp(symbol: str) -> bool:
    return symbol.endswith("USDT") and "-" not in symbol


def fetch_snapshot():
    req = urllib.request.Request(TICKERS_URL, headers={"User-Agent": "Mozilla/5.0 (momentum-collector)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        print(f"HTTP {e.code} from Bybit. Response body: {body}")
        raise
    except urllib.error.URLError as e:
        print(f"Network/URL error reaching Bybit: {e.reason}")
        raise

    if payload.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {payload.get('retMsg')}")

    prices = {}
    for item in payload["result"]["list"]:
        symbol = item["symbol"]
        if not is_perp(symbol):
            continue
        try:
            price = float(item["lastPrice"])
            turnover = float(item.get("turnover24h", 0) or 0)
        except (TypeError, ValueError):
            continue
        if turnover < MIN_TURNOVER_USD:
            continue
        prices[symbol] = [price, round(turnover)]

    return {"t": int(time.time() * 1000), "s": prices}


def main():
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)

    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {"snapshots": []}
    else:
        data = {"snapshots": []}

    snapshot = fetch_snapshot()
    data.setdefault("snapshots", []).append(snapshot)
    data["snapshots"] = data["snapshots"][-MAX_SNAPSHOTS:]
    data["updated"] = snapshot["t"]

    with open(DATA_PATH, "w") as f:
        json.dump(data, f, separators=(",", ":"))

    print(f"Snapshot saved: {len(snapshot['s'])} symbols, "
          f"{len(data['snapshots'])} snapshots total")


if __name__ == "__main__":
    main()
