#!/usr/bin/env python3
"""
Build training labels for FX Bias AI system.

Downloads historical FRED FX price series (2006–present), resamples to weekly
Friday closes, and provides utilities for building BULL/BEAR/NEUTRAL labels.

Label Logic (AND condition, RPD Section 3.3):
  BULL    = COT direction positive AND price direction positive (currency↑ vs USD)
  BEAR    = COT direction negative AND price direction negative (currency↓ vs USD)
  NEUTRAL = All other cases (conflicting or flat signals)

Label Confirmation Lag (RPD Section 5.1):
  LABEL_CONFIRMATION_LAG = 1 week
  → Label for week T requires price close at week T+1 (to compute direction)
  → At inference time week T, we can only use labels up to T−1

Usage:
  python training/build_labels.py
  → Downloads prices, saves training/data/prices_2006_2026.csv

Output:
  training/data/prices_2006_2026.csv — weekly Friday closes (raw FRED values)

Reference: Task List B2-01, RPD Section 2.1.2, 3.3, 5.1
"""

import logging
import os
import sys
import time
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FRED_API_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# Label confirmation lag — CRITICAL: DO NOT CHANGE (RPD Section 5.1)
LABEL_CONFIRMATION_LAG = 1  # weeks

# Training start date — TFF available from 2006 (RPD Section 2.1.1)
START_DATE = "2006-01-01"

# Output path
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "data", "prices_2006_2026.csv")

# FRED FX price series
# quote_usd=True  → series is "currency per USD-quote" (EUR/USD, GBP/USD, AUD/USD, NZD/USD)
#                   → higher price = currency STRONGER vs USD
# quote_usd=False → series is "USD per foreign currency" (USD/JPY, USD/CAD, USD/CHF)
#                   → higher price = USD STRONGER = foreign currency WEAKER
#                   → must INVERT to get "currency direction vs USD"
FX_SERIES = {
    "EUR": {"series_id": "DEXUSEU", "quote_usd": True},   # USD per EUR
    "GBP": {"series_id": "DEXUSUK", "quote_usd": True},   # USD per GBP
    "JPY": {"series_id": "DEXJPUS", "quote_usd": False},  # JPY per USD → invert
    "AUD": {"series_id": "DEXUSAL", "quote_usd": True},   # USD per AUD
    "CAD": {"series_id": "DEXCAUS", "quote_usd": False},  # CAD per USD → invert
    "CHF": {"series_id": "DEXSZUS", "quote_usd": False},  # CHF per USD → invert
    "NZD": {"series_id": "DEXUSNZ", "quote_usd": True},   # USD per NZD
}

REQUEST_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FRED client
# ---------------------------------------------------------------------------

def fetch_fred_series(series_id: str, start_date: str = START_DATE) -> pd.Series:
    """
    Fetch a FRED series and return as a daily pandas Series.

    Args:
        series_id: FRED series identifier (e.g. "DEXUSEU")
        start_date: ISO date string for observation start

    Returns:
        Series with DatetimeIndex and float values; FRED "." observations dropped

    Raises:
        requests.exceptions.RequestException: If all retries fail
    """
    params: dict = {
        "series_id": series_id,
        "observation_start": start_date,
        "file_type": "json",
        "frequency": "d",
        "sort_order": "asc",
    }
    if FRED_API_KEY:
        params["api_key"] = FRED_API_KEY

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(FRED_API_BASE_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            observations = resp.json().get("observations", [])

            records: dict = {}
            for obs in observations:
                if obs["value"] == ".":  # FRED missing value sentinel
                    continue
                records[pd.Timestamp(obs["date"])] = float(obs["value"])

            series = pd.Series(records, name=series_id, dtype=float)
            series.index = pd.DatetimeIndex(series.index)
            return series

        except requests.exceptions.RequestException as exc:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAY * (attempt + 1)
                logger.warning(
                    f"FRED fetch {series_id} attempt {attempt + 1}/{MAX_RETRIES} failed: {exc}. "
                    f"Retrying in {wait}s..."
                )
                time.sleep(wait)
            else:
                logger.error(f"FRED fetch {series_id} failed after {MAX_RETRIES} attempts: {exc}")
                raise


# ---------------------------------------------------------------------------
# Resampling
# ---------------------------------------------------------------------------

def resample_to_weekly_friday(daily: pd.Series) -> pd.Series:
    """
    Resample a daily series to weekly Friday closes.

    Handles holidays and missing trading days by forward-filling before
    resampling. Each weekly observation is the last available price on or
    before Friday of that week.

    Args:
        daily: Daily price series with DatetimeIndex

    Returns:
        Weekly series indexed to Fridays (W-FRI anchor), NaN where no data
    """
    # Expand to every calendar day and forward-fill (carries last known price)
    daily_full = daily.resample("D").last().ffill()
    # Take last value of each Friday-anchored week
    weekly = daily_full.resample("W-FRI").last()
    return weekly


# ---------------------------------------------------------------------------
# Direction helpers
# ---------------------------------------------------------------------------

def get_price_direction(weekly: pd.Series) -> pd.Series:
    """
    Compute week-to-week price direction (outcome = next week's move).

    direction[T] = sign(close[T+1] - close[T])
      +1 → price rose next week
      -1 → price fell next week
       0 → no change

    The last row will be NaN because T+1 is not available yet.
    """
    next_close = weekly.shift(-1)
    direction = np.sign(next_close - weekly).astype("Int64")  # nullable int
    return direction


def adjust_for_quoting(direction: pd.Series, quote_usd: bool) -> pd.Series:
    """
    Normalise direction so +1 = currency STRENGTHENS vs USD.

    For series where USD is the base (DEXJPUS, DEXCAUS, DEXSZUS):
      rising price → USD stronger → foreign currency WEAKER → invert sign
    For series where currency is the base (DEXUSEU, DEXUSUK, etc.):
      rising price → currency stronger → keep sign
    """
    if not quote_usd:
        return -direction
    return direction.copy()


# ---------------------------------------------------------------------------
# Label building
# ---------------------------------------------------------------------------

def build_label(cot_direction: int, price_direction: int) -> str:
    """
    Build BULL/BEAR/NEUTRAL label using AND condition (RPD Section 3.3).

    BULL    = COT direction > 0 AND price direction > 0
    BEAR    = COT direction < 0 AND price direction < 0
    NEUTRAL = all other cases (conflicting or flat)

    Args:
        cot_direction:   +1 (net↑), -1 (net↓), 0 (flat)
        price_direction: +1 (currency↑ vs USD), -1 (currency↓), 0 (flat)
    """
    if cot_direction > 0 and price_direction > 0:
        return "BULL"
    elif cot_direction < 0 and price_direction < 0:
        return "BEAR"
    else:
        return "NEUTRAL"


def build_label_or(cot_direction: int, price_direction: int) -> str:
    """
    Alternative OR condition label definition (RPD Section 2.1.2 contingency).

    Used only if AND condition produces NEUTRAL > 60% in training set.
    Labelled BULL/BEAR when either signal agrees and neither contradicts.
    Conflicting signals (one positive, one negative) → NEUTRAL.

    Comparison vs AND condition accuracy done in B2-04 (walk-forward).
    Document chosen definition in DECISIONS.md.
    """
    if cot_direction > 0 and price_direction < 0:
        return "NEUTRAL"
    if cot_direction < 0 and price_direction > 0:
        return "NEUTRAL"
    if cot_direction > 0 or price_direction > 0:
        return "BULL"
    if cot_direction < 0 or price_direction < 0:
        return "BEAR"
    return "NEUTRAL"


def build_labels_for_currency(
    weekly_price: pd.Series,
    cot_net: pd.Series,
    quote_usd: bool,
    reference_date: Optional[date] = None,
    use_or_condition: bool = False,
) -> pd.Series:
    """
    Build a labelled Series for one currency (used in B2-04).

    Combines weekly price data and COT net positions into BULL/BEAR/NEUTRAL
    labels with LABEL_CONFIRMATION_LAG = 1 enforced.

    Args:
        weekly_price:   Weekly Friday closes (raw FRED values)
        cot_net:        Weekly COT net position = long − short, indexed to Fridays
        quote_usd:      See FX_SERIES config above
        reference_date: "Current week" — labels only generated up to this−1.
                        Defaults to today's most recent Friday.
        use_or_condition: If True, use OR label definition instead of AND

    Returns:
        Series of 'BULL'/'BEAR'/'NEUTRAL' strings, indexed by Friday dates.
        Covers 2006-01-01 to (reference_date − LABEL_CONFIRMATION_LAG weeks).
    """
    if reference_date is None:
        today = pd.Timestamp.today().normalize()
        # Roll back to last Friday
        days_since_friday = (today.weekday() - 4) % 7
        reference_date_ts = today - pd.Timedelta(days=days_since_friday)
    else:
        reference_date_ts = pd.Timestamp(reference_date)

    # Enforce LABEL_CONFIRMATION_LAG: cutoff = reference_date − 1 week
    cutoff = reference_date_ts - pd.Timedelta(weeks=LABEL_CONFIRMATION_LAG)

    # COT direction: week-to-week change in net position
    cot_direction = np.sign(cot_net.diff()).fillna(0).astype(int)

    # Price direction: sign(close[T+1] − close[T]) — forward looking for label
    price_dir_raw = get_price_direction(weekly_price)
    price_dir = adjust_for_quoting(price_dir_raw, quote_usd)

    label_fn = build_label_or if use_or_condition else build_label

    # Align on common dates within cutoff
    common_idx = cot_direction.index.intersection(price_dir.index)
    common_idx = common_idx[common_idx <= cutoff]
    # Drop rows where price direction is NaN (last row — T+1 not available)
    valid_mask = price_dir.loc[common_idx].notna()
    common_idx = common_idx[valid_mask]

    labels = pd.Series(
        [label_fn(int(cot_direction.get(dt, 0)), int(price_dir.get(dt, 0))) for dt in common_idx],
        index=common_idx,
        name="label",
        dtype=str,
    )
    return labels


# ---------------------------------------------------------------------------
# Class distribution analysis
# ---------------------------------------------------------------------------

def check_class_distribution(labels: pd.Series, currency: str) -> dict:
    """
    Log class distribution and flag if NEUTRAL > 60% (B2-01f, B2-01g).

    Args:
        labels:   Series of 'BULL'/'BEAR'/'NEUTRAL'
        currency: Currency code for logging

    Returns:
        Dict with pct_bull, pct_bear, pct_neutral, neutral_exceeds_60pct
    """
    counts = labels.value_counts()
    total = len(labels)

    pct_bull = counts.get("BULL", 0) / total * 100
    pct_bear = counts.get("BEAR", 0) / total * 100
    pct_neutral = counts.get("NEUTRAL", 0) / total * 100

    neutral_flag = bool(pct_neutral > 60.0)

    logger.info(
        f"  {currency}: BULL={pct_bull:.1f}%  BEAR={pct_bear:.1f}%  "
        f"NEUTRAL={pct_neutral:.1f}%  n={total}"
        + ("  ⚠️  NEUTRAL > 60%" if neutral_flag else "")
    )

    if neutral_flag:
        logger.warning(
            f"  {currency}: NEUTRAL > 60% threshold. "
            "Will implement OR condition in B2-04 and compare walk-forward accuracy. "
            "See RPD Section 2.1.2."
        )

    return {
        "pct_bull": round(pct_bull, 2),
        "pct_bear": round(pct_bear, 2),
        "pct_neutral": round(pct_neutral, 2),
        "neutral_exceeds_60pct": neutral_flag,
    }


# ---------------------------------------------------------------------------
# Main — download prices and save CSV
# ---------------------------------------------------------------------------

def download_prices() -> pd.DataFrame:
    """
    Download all FRED FX price series and return as a weekly DataFrame.

    Returns:
        DataFrame indexed by Friday dates, columns = [EUR, GBP, JPY, AUD, CAD, CHF, NZD]
        Values are raw FRED prices (not direction-adjusted).
    """
    frames: dict = {}

    for currency, config in FX_SERIES.items():
        series_id = config["series_id"]
        logger.info(f"Fetching {currency} ({series_id}) from FRED...")

        daily = fetch_fred_series(series_id)
        weekly = resample_to_weekly_friday(daily)
        frames[currency] = weekly

        logger.info(f"  → {len(weekly)} weekly observations ({weekly.index.min().date()} → {weekly.index.max().date()})")

    df = pd.DataFrame(frames)
    df.index.name = "date"
    return df


def log_price_direction_distribution(df_prices: pd.DataFrame) -> None:
    """
    Log preliminary price-direction distribution as proxy for class distribution.

    Note: Full class distribution requires COT net data (B2-02).
    This proxy uses price momentum only to estimate whether NEUTRAL will
    exceed 60% — actual label distribution will be verified in B2-04.
    """
    logger.info("=== Preliminary price-direction distribution (proxy — COT not yet available) ===")
    for currency, config in FX_SERIES.items():
        if currency not in df_prices.columns:
            continue
        price_dir = get_price_direction(df_prices[currency])
        price_dir = adjust_for_quoting(price_dir, config["quote_usd"])
        price_dir_clean = price_dir.dropna()
        total = len(price_dir_clean)
        counts = price_dir_clean.value_counts()
        pct_up = counts.get(1, 0) / total * 100
        pct_down = counts.get(-1, 0) / total * 100
        pct_flat = counts.get(0, 0) / total * 100
        logger.info(f"  {currency}: UP={pct_up:.1f}%  DOWN={pct_down:.1f}%  FLAT={pct_flat:.1f}%  n={total}")

    logger.info(
        "Note: Full BULL/BEAR/NEUTRAL distribution will be computed in B2-04 "
        "after COT historical data (B2-02) is merged."
    )


def main() -> int:
    """
    B2-01 main: Download FRED FX prices and save training/data/prices_2006_2026.csv.

    Returns:
        0 on success, 1 on failure
    """
    logger.info("=" * 60)
    logger.info("Phase B2-01: FX Price Data Download")
    logger.info("=" * 60)
    logger.info(f"Start date : {START_DATE}")
    logger.info(f"Output     : {OUTPUT_PATH}")

    if not FRED_API_KEY:
        logger.error(
            "FRED_API_KEY environment variable is not set.\n"
            "  1. Register at https://fred.stlouisfed.org/docs/api/api_key.html (free)\n"
            "  2. export FRED_API_KEY=your_key_here\n"
            "  3. Re-run this script\n"
            "  For CI/CD: add FRED_API_KEY to GitHub Secrets (Task S-03b)"
        )
        return 1

    logger.info(f"FRED API   : authenticated")

    try:
        df_prices = download_prices()
    except Exception as exc:
        logger.error(f"Download failed: {exc}")
        return 1

    # Sanity checks
    logger.info(f"\nDownloaded: {len(df_prices)} weekly rows × {len(df_prices.columns)} currencies")
    logger.info(f"Date range: {df_prices.index.min().date()} → {df_prices.index.max().date()}")

    missing = df_prices.isnull().sum()
    missing_nonzero = missing[missing > 0]
    if missing_nonzero.empty:
        logger.info("Missing values: none")
    else:
        logger.warning(f"Missing values:\n{missing_nonzero}")

    # Save CSV
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    df_prices.to_csv(OUTPUT_PATH)
    logger.info(f"\nSaved: {OUTPUT_PATH}")

    # B2-01f: Preliminary class distribution (price direction proxy)
    log_price_direction_distribution(df_prices)

    logger.info("\n" + "=" * 60)
    logger.info("B2-01 COMPLETE")
    logger.info("  Next step: B2-02 — Download historical COT data (CFTC bulk files)")
    logger.info("  Then:      B2-04 — Build features_2006_2026.csv (full labels with COT)")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
