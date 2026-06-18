"""Download real XAUUSD historical OHLC data for backtesting.

Source: ejtraderLabs/historical-data (public GitHub repo, MIT-style historical
forex/commodity dataset). Prices are stored scaled by 100 (e.g. 196974.0 ==
1969.74 USD/oz) because the source feed quotes gold to 2 decimal places as an
integer-like field; this script rescales back to real USD prices.

Usage:
    python3 fetch_data.py
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

BASE_URL = "https://raw.githubusercontent.com/ejtraderLabs/historical-data/main/XAUUSD"
DATA_DIR = Path(__file__).resolve().parent / "data"
FILES = {
    "m15": "XAUUSDm15.csv",
    "h1": "XAUUSDh1.csv",
}


def download(timeframe: str, filename: str) -> Path:
    dest = DATA_DIR / filename
    url = f"{BASE_URL}/{filename}"
    print(f"Downloading {timeframe} data from {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:
        out.write(resp.read())
    print(f"  saved {dest} ({dest.stat().st_size / 1e6:.1f} MB)")
    return dest


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for timeframe, filename in FILES.items():
        download(timeframe, filename)


if __name__ == "__main__":
    sys.exit(main())
