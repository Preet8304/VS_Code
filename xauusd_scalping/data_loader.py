"""Load and clean the raw XAUUSD CSV files into a consistent OHLC schema.

The source files store gold prices scaled by 100 (e.g. 196974.0 means
$1,969.74/oz) because the feed quotes 2 decimal places as an integer-like
field. Timestamps are the data vendor's platform time (commonly broker/MT4
server time, typically UTC+2/UTC+3) -- not strictly UTC. The session filter
hours in strategy.py are tuned against this platform time, not true UTC.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
PRICE_SCALE = 100.0


def load_ohlc(filename: str) -> pd.DataFrame:
    path = DATA_DIR / filename
    df = pd.read_csv(path)
    df = df.rename(columns={"Date": "time"})
    df["time"] = pd.to_datetime(df["time"])
    for col in ("open", "high", "low", "close"):
        df[col] = df[col] / PRICE_SCALE
    df = df.sort_values("time").drop_duplicates(subset="time").reset_index(drop=True)
    return df[["time", "open", "high", "low", "close", "tick_volume"]]


def load_m15() -> pd.DataFrame:
    return load_ohlc("XAUUSDm15.csv")


def load_h1() -> pd.DataFrame:
    return load_ohlc("XAUUSDh1.csv")
