#!/usr/bin/env python3
"""
Download historical CFTC COT data (Legacy + TFF) for 8 FX futures.

Uses CFTC Socrata API with pagination -- same source as fetch_cot.py
but fetches full history from 2006-01-01 instead of latest week only.

Equivalent to downloading CFTC annual bulk ZIP files from cftc.gov but
avoids per-year ZIP parsing complexity (Socrata has identical data).

Output: training/data/cot_historical_2006_2026.csv
Columns: date, currency, noncomm_long, noncomm_short, open_interest, net,
         lev_funds_long, lev_funds_short, lev_funds_net,
         asset_mgr_long, asset_mgr_short, asset_mgr_net,
         dealer_long, dealer_short, dealer_net

Reference: Task List B2-02
"""

import logging
import os
import sys
import time

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SOCRATA_BASE_URL = "https://publicreporting.cftc.gov/resource"
LEGACY_DATASET_ID = "6dca-aqww"   # Legacy - Futures Only
TFF_DATASET_ID    = "gpe5-46if"   # Traders in Financial Futures - Futures Only

CURRENCY_CONTRACTS = {
    "EUR": "099741",
    "GBP": "096742",
    "JPY": "097741",
    "AUD": "232741",
    "CAD": "090741",
    "CHF": "092741",
    "NZD": "112741",
    "USD": "098662",
}

START_DATE = "2006-01-01"

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "data", "cot_historical_2006_2026.csv")

PAGE_SIZE     = 5000
REQUEST_TIMEOUT = 30
MAX_RETRIES   = 3
RETRY_DELAY   = 3

HEADERS = {"User-Agent": "FX-Bias-AI/1.0 (Training Data Download)"}

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
# Socrata paginated fetch
# ---------------------------------------------------------------------------

def fetch_all_pages(dataset_id: str, contract_code: str) -> list[dict]:
    """
    Fetch all pages of a Socrata dataset for one contract from START_DATE.

    Note: No $select used -- some CFTC datasets reject $select with $where
    combination. Fetch all fields and parse needed ones from response.

    Args:
        dataset_id:     Socrata dataset identifier
        contract_code:  CFTC_CONTRACT_MARKET_CODE value

    Returns:
        All records as a list of dicts
    """
    url = f"{SOCRATA_BASE_URL}/{dataset_id}.json"
    where_clause = (
        f"cftc_contract_market_code='{contract_code}' "
        f"AND report_date_as_yyyy_mm_dd >= '{START_DATE}'"
    )

    all_records: list[dict] = []
    offset = 0

    while True:
        params = {
            "$where":  where_clause,
            "$order":  "report_date_as_yyyy_mm_dd ASC",
            "$limit":  PAGE_SIZE,
            "$offset": offset,
        }

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 429:
                    wait = RETRY_DELAY * attempt
                    logger.warning("Rate limited -- waiting %ds", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                page = resp.json()
                break
            except requests.exceptions.RequestException as exc:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                    continue
                logger.error("Failed fetching %s contract %s offset %d: %s", dataset_id, contract_code, offset, exc)
                raise

        if not page:
            break

        all_records.extend(page)
        logger.info("  %s contract %s: fetched %d records (total so far: %d)",
                    dataset_id, contract_code, len(page), len(all_records))

        if len(page) < PAGE_SIZE:
            break

        offset += PAGE_SIZE
        time.sleep(0.3)  # polite pacing between pages

    return all_records


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------

def _int(val: object) -> int:
    try:
        return int(float(str(val)))
    except (TypeError, ValueError):
        return 0


def parse_legacy(records: list[dict], currency: str) -> pd.DataFrame:
    """
    Parse Legacy COT records into a standardized DataFrame.

    Columns: date, currency, noncomm_long, noncomm_short, open_interest, net
    """
    rows = []
    for r in records:
        date_str = r.get("report_date_as_yyyy_mm_dd", "")[:10]
        if not date_str:
            continue
        long_  = _int(r.get("noncomm_positions_long_all",  0))
        short_ = _int(r.get("noncomm_positions_short_all", 0))
        oi     = _int(r.get("open_interest_all",            0))
        rows.append({
            "date":           pd.Timestamp(date_str),
            "currency":       currency,
            "noncomm_long":   long_,
            "noncomm_short":  short_,
            "open_interest":  oi,
            "net":            long_ - short_,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    return df


def parse_tff(records: list[dict], currency: str) -> pd.DataFrame:
    """
    Parse TFF records into a standardized DataFrame.

    Columns: date, lev_funds_long, lev_funds_short, lev_funds_net,
             asset_mgr_long, asset_mgr_short, asset_mgr_net,
             dealer_long, dealer_short, dealer_net
    """
    rows = []
    for r in records:
        date_str = r.get("report_date_as_yyyy_mm_dd", "")[:10]
        if not date_str:
            continue
        lf_l  = _int(r.get("lev_money_positions_long",   0))
        lf_s  = _int(r.get("lev_money_positions_short",  0))
        am_l  = _int(r.get("asset_mgr_positions_long",   0))
        am_s  = _int(r.get("asset_mgr_positions_short",  0))
        dl_l  = _int(r.get("dealer_positions_long_all",      0))
        dl_s  = _int(r.get("dealer_positions_short_all",     0))
        rows.append({
            "date":             pd.Timestamp(date_str),
            "lev_funds_long":   lf_l,
            "lev_funds_short":  lf_s,
            "lev_funds_net":    lf_l - lf_s,
            "asset_mgr_long":   am_l,
            "asset_mgr_short":  am_s,
            "asset_mgr_net":    am_l - am_s,
            "dealer_long":      dl_l,
            "dealer_short":     dl_s,
            "dealer_net":       dl_l - dl_s,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Per-currency download
# ---------------------------------------------------------------------------

def download_currency(currency: str, contract_code: str) -> pd.DataFrame:
    """
    Download and merge Legacy + TFF history for one currency.

    Returns:
        Combined DataFrame with all columns for this currency,
        indexed by COT report date. Empty rows filled with 0 for TFF
        (TFF only available from 2006, Legacy from 1986).
    """
    logger.info("=== %s (%s) ===", currency, contract_code)

    # Legacy
    logger.info("  Fetching Legacy COT...")
    leg_raw = fetch_all_pages(LEGACY_DATASET_ID, contract_code)
    df_leg  = parse_legacy(leg_raw, currency)
    logger.info("  Legacy: %d weekly records", len(df_leg))

    # TFF
    logger.info("  Fetching TFF...")
    tff_raw = fetch_all_pages(TFF_DATASET_ID, contract_code)
    df_tff  = parse_tff(tff_raw, currency)
    logger.info("  TFF: %d weekly records", len(df_tff))

    # Merge on date (outer join -- some early weeks may lack TFF)
    df = pd.merge(df_leg, df_tff, on="date", how="left")

    # Fill missing TFF values with 0
    tff_cols = ["lev_funds_long", "lev_funds_short", "lev_funds_net",
                "asset_mgr_long", "asset_mgr_short", "asset_mgr_net",
                "dealer_long", "dealer_short", "dealer_net"]
    df[tff_cols] = df[tff_cols].fillna(0).astype(int)

    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    logger.info("=" * 60)
    logger.info("Phase B2-02: Download Historical COT Data")
    logger.info("=" * 60)
    logger.info("Source  : CFTC Socrata API (Legacy + TFF)")
    logger.info("Start   : %s", START_DATE)
    logger.info("Output  : %s", OUTPUT_PATH)
    logger.info("Pairs   : %s", list(CURRENCY_CONTRACTS.keys()))

    all_frames: list[pd.DataFrame] = []

    for currency, code in CURRENCY_CONTRACTS.items():
        try:
            df = download_currency(currency, code)
            all_frames.append(df)
        except Exception as exc:
            logger.error("FAILED %s: %s", currency, exc)
            return 1

    if not all_frames:
        logger.error("No data downloaded")
        return 1

    df_all = pd.concat(all_frames, ignore_index=True)
    df_all = df_all.sort_values(["date", "currency"]).reset_index(drop=True)

    # Validate
    logger.info("\n=== Validation ===")
    logger.info("Total rows    : %d", len(df_all))
    logger.info("Currencies    : %s", sorted(df_all["currency"].unique()))
    logger.info("Date range    : %s -> %s", df_all["date"].min().date(), df_all["date"].max().date())

    for cur in sorted(df_all["currency"].unique()):
        n = len(df_all[df_all["currency"] == cur])
        logger.info("  %-4s : %d records", cur, n)

    missing_net = (df_all["net"] == 0).sum()
    if missing_net > len(df_all) * 0.1:
        logger.warning("Many zero net values (%d) -- check data quality", missing_net)

    # Save
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    df_all.to_csv(OUTPUT_PATH, index=False)
    logger.info("\nSaved: %s", OUTPUT_PATH)
    logger.info("=" * 60)
    logger.info("B2-02 COMPLETE")
    logger.info("  Next: B2-03 feature_engineering.py")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
