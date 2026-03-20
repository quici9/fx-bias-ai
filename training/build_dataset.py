#!/usr/bin/env python3
"""
Build complete training dataset: features_2006_2026.csv

Phase B2-04 — Align all data sources, apply feature engineering,
join with labels, save to training/data/features_2006_2026.csv.

Requires (already produced by B2-01 and B2-02):
  training/data/prices_2006_2026.csv
  training/data/cot_historical_2006_2026.csv

Optional (improves Group C features):
  FRED_API_KEY env var  → enables macro feature download
  Without it: Group C features default to 0.0 (COT-only mode)

Output:
  training/data/features_2006_2026.csv — ~7,300 rows × 30 columns
  Column layout: date, currency, [28 features], label

Reference: Task List B2-04, RPD Section 3.2–3.3
"""

import io
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from training.build_labels import (
    FX_SERIES,
    LABEL_CONFIRMATION_LAG,
    adjust_for_quoting,
    build_label,
    build_labels_for_currency,
    check_class_distribution,
    get_price_direction,
)
from training.feature_engineering import (
    CURRENCIES,
    FEATURE_NAMES,
    build_historical_features,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = _REPO_ROOT / "training" / "data"
COT_CSV = DATA_DIR / "cot_historical_2006_2026.csv"
PRICES_CSV = DATA_DIR / "prices_2006_2026.csv"
OUTPUT_CSV = DATA_DIR / "features_2006_2026.csv"

# ---------------------------------------------------------------------------
# FRED macro data download
# ---------------------------------------------------------------------------

FRED_API_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2
START_DATE = "2006-01-01"

# Policy rate series (monthly frequency in FRED)
POLICY_RATE_SERIES = {
    "USD": "FEDFUNDS",
    "GBP": "IR3TIB01GBM156N",   # UK 3M interbank (OECD) — IRSTCB01GBM156N not on FRED
    "JPY": "IRSTCB01JPM156N",
    "AUD": "IR3TBB01AUM156N",   # AUD 3M T-bill (OECD) — IRSTCB01AUM156N not on FRED
    "CAD": "IRSTCB01CAM156N",
    "CHF": "IR3TIB01CHM156N",   # CHF 3M interbank (OECD) — IRSTCB01CHM156N not on FRED
    "NZD": "IR3TBB01NZM156N",   # NZD 3M T-bill (OECD) — IRSTCB01NZM156N not on FRED
    # EUR fetched from ECB API separately
}

# CPI series — these are YoY indices (OECD format, already YoY %)
CPI_SERIES = {
    "USD": "CPIAUCSL",          # US CPI all-items (monthly level — compute YoY below)
    "GBP": "GBRCPIALLMINMEI",   # OECD UK CPI (monthly index → YoY computed below)
    "JPY": "CPALCY01JPM661N",   # Japan CPI YoY % (monthly) — JPNCPIALLMINMEI deprecated
    "AUD": "CPALTT01AUQ657N",   # Australia CPI YoY % (quarterly — use frequency=q)
    "CAD": "CPALCY01CAM661N",   # Canada CPI YoY
    "CHF": "CHECPIALLMINMEI",   # OECD Switzerland CPI (monthly index → YoY computed below)
    "NZD": "CPALTT01NZQ657N",   # New Zealand CPI YoY % (quarterly — use frequency=q)
    # EUR fetched from ECB API separately
}

# 10Y yield series (daily)
YIELD_10Y_SERIES = {
    "US": "DGS10",
    "DE": "IRLTLT01DEM156N",
    "GB": "IRLTLT01GBM156N",
    "JP": "IRLTLT01JPM156N",
}


def _fetch_fred(series_id: str, frequency: str = "m") -> Optional[pd.Series]:
    """
    Fetch a FRED series. Returns None on failure (non-fatal).

    Args:
        series_id: FRED series ID
        frequency: 'm' for monthly, 'd' for daily
    """
    params = {
        "series_id": series_id,
        "observation_start": START_DATE,
        "file_type": "json",
        "frequency": frequency,
        "sort_order": "asc",
    }
    if FRED_API_KEY:
        params["api_key"] = FRED_API_KEY

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(FRED_API_BASE_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            obs = resp.json().get("observations", [])
            records = {
                pd.Timestamp(o["date"]): float(o["value"])
                for o in obs
                if o["value"] != "."
            }
            s = pd.Series(records, dtype=float)
            s.index = pd.DatetimeIndex(s.index)
            logger.info(f"  ✓ {series_id}: {len(s)} observations")
            return s
        except Exception as exc:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                logger.warning(f"  ✗ {series_id} failed after {MAX_RETRIES} tries: {exc}")
                return None


def _fetch_ecb_rate() -> Optional[pd.Series]:
    """Fetch ECB Deposit Facility Rate from ECB Data Portal (no key required)."""
    url = "https://data-api.ecb.europa.eu/service/data/FM/B.U2.EUR.4F.KR.DFR.LEV"
    params = {
        "format": "csvdata",
        "startPeriod": "2006-01",
        "detail": "dataonly",
    }
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        if "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
            raise ValueError(f"Unexpected ECB CSV columns: {list(df.columns)}")
        records = {}
        for _, row in df.iterrows():
            try:
                records[pd.Timestamp(str(row["TIME_PERIOD"]) + "-01")] = float(row["OBS_VALUE"])
            except (ValueError, TypeError):
                pass
        if not records:
            raise ValueError("Empty ECB response")
        s = pd.Series(records, dtype=float)
        logger.info(f"  ✓ ECB DFR (EUR policy rate): {len(s)} observations")
        return s
    except Exception as exc:
        logger.warning(f"  ✗ ECB rate fetch failed: {exc} — EUR rate will be 0")
        return None


def _fetch_ecb_cpi() -> Optional[pd.Series]:
    """Fetch Euro Area HICP index from ECB Data Portal (index level; YoY computed by caller)."""
    # EA HICP All Items index (2015=100), monthly
    url = "https://data-api.ecb.europa.eu/service/data/ICP/M.U2.N.000000.4.INX"
    params = {
        "format": "csvdata",
        "startPeriod": "2006-01",
        "detail": "dataonly",
    }
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        if "TIME_PERIOD" not in df.columns or "OBS_VALUE" not in df.columns:
            raise ValueError(f"Unexpected ECB CSV columns: {list(df.columns)}")
        records = {}
        for _, row in df.iterrows():
            try:
                records[pd.Timestamp(str(row["TIME_PERIOD"]) + "-01")] = float(row["OBS_VALUE"])
            except (ValueError, TypeError):
                pass
        if not records:
            raise ValueError("Empty ECB CPI response")
        s = pd.Series(records, dtype=float)
        logger.info(f"  ✓ ECB HICP (EUR CPI): {len(s)} observations")
        return s
    except Exception as exc:
        logger.warning(f"  ✗ ECB CPI fetch failed: {exc} — EUR CPI will use fallback")
        return None


def download_macro_data() -> dict:
    """
    Download historical macro data from FRED and ECB.

    Returns dict with keys:
      'rates':  DataFrame (monthly) — columns = currency codes
      'cpi':    DataFrame (monthly) — columns = currency codes, values = YoY %
      'yields': DataFrame (daily)   — columns = ['US', 'DE', 'GB', 'JP']
      'vix':    Series (daily)
    """
    logger.info("=== Downloading macro data ===")

    if not FRED_API_KEY:
        logger.warning(
            "FRED_API_KEY not set — Group C macro features will be 0.0 (COT-only mode).\n"
            "  Set FRED_API_KEY env var and re-run for full 28-feature dataset.\n"
            "  Register free at https://fred.stlouisfed.org/docs/api/api_key.html"
        )
        return {"rates": None, "cpi": None, "yields": None, "vix": None}

    # ---- Policy rates --------------------------------------------------------
    logger.info("Downloading policy rates...")
    rate_series = {}
    for cur, series_id in POLICY_RATE_SERIES.items():
        s = _fetch_fred(series_id, frequency="m")
        if s is not None:
            rate_series[cur] = s

    eur_rate = _fetch_ecb_rate()
    if eur_rate is not None:
        rate_series["EUR"] = eur_rate

    macro_rates = pd.DataFrame(rate_series) if rate_series else None

    # ---- CPI ----------------------------------------------------------------
    logger.info("Downloading CPI data...")
    cpi_series = {}

    # CPIAUCSL is index levels — compute YoY after download
    us_cpi_raw = _fetch_fred("CPIAUCSL", frequency="m")
    if us_cpi_raw is not None:
        # YoY % = (level[t] - level[t-12]) / level[t-12] * 100
        us_cpi_yoy = us_cpi_raw.pct_change(12) * 100
        cpi_series["USD"] = us_cpi_yoy

    # AUD/NZD CPI are quarterly series — must request frequency=q
    _cpi_quarterly = {"AUD", "NZD"}
    for cur, series_id in CPI_SERIES.items():
        if cur == "USD":
            continue
        freq = "q" if cur in _cpi_quarterly else "m"
        s = _fetch_fred(series_id, frequency=freq)
        if s is not None:
            cpi_series[cur] = s

    eur_cpi = _fetch_ecb_cpi()
    if eur_cpi is not None:
        # ECB HICP is an index level — compute YoY
        eur_cpi_yoy = eur_cpi.pct_change(12) * 100
        cpi_series["EUR"] = eur_cpi_yoy
    elif "EUR" not in cpi_series:
        # Fallback: FRED HICP for Euro Area (CP0000EZ19M086NEST = HICP All Items, index 2015=100)
        # EA19CPIALLMINMEI was retired by FRED — use this replacement series
        s = _fetch_fred("CP0000EZ19M086NEST", frequency="m")
        if s is not None:
            # This series is an index level; compute YoY
            eur_cpi_yoy = s.pct_change(12) * 100
            cpi_series["EUR"] = eur_cpi_yoy

    macro_cpi = pd.DataFrame(cpi_series) if cpi_series else None

    # ---- 10Y yields ----------------------------------------------------------
    logger.info("Downloading 10Y yields...")
    # DGS10 (US) is daily; all others (DE/GB/JP) are monthly OECD series
    _yield_freq = {"US": "d", "DE": "m", "GB": "m", "JP": "m"}
    yield_series = {}
    for country, series_id in YIELD_10Y_SERIES.items():
        s = _fetch_fred(series_id, frequency=_yield_freq[country])
        if s is not None:
            yield_series[country] = s
    yields_df = pd.DataFrame(yield_series) if yield_series else None

    # ---- VIX -----------------------------------------------------------------
    logger.info("Downloading VIX...")
    vix = _fetch_fred("VIXCLS", frequency="d")

    return {
        "rates": macro_rates,
        "cpi": macro_cpi,
        "yields": yields_df,
        "vix": vix,
    }


# ---------------------------------------------------------------------------
# COT → Friday alignment
# ---------------------------------------------------------------------------

def align_cot_to_fridays(cot_df: pd.DataFrame) -> pd.DataFrame:
    """
    Map COT Tuesday dates → Friday of the same week.

    COT reports reflect Tuesday positions and are published on Friday.
    Prices are indexed on Friday closes. This maps COT data to the
    corresponding Friday so both datasets share the same date index.

    Args:
        cot_df: COT historical DataFrame with 'date' column (Tuesdays).

    Returns:
        Same DataFrame with 'date' shifted to the following Friday (+3 days).
    """
    cot_aligned = cot_df.copy()
    cot_aligned["date"] = pd.to_datetime(cot_aligned["date"]) + pd.Timedelta(days=3)
    return cot_aligned


# ---------------------------------------------------------------------------
# Label building
# ---------------------------------------------------------------------------

def build_all_labels(
    prices_df: pd.DataFrame,
    cot_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build BULL/BEAR/NEUTRAL labels for all 7 currencies.

    Args:
        prices_df: Weekly prices (Friday), columns = currency codes.
        cot_df:    COT historical, long format, dates = Fridays (after alignment).

    Returns:
        DataFrame with columns ['date', 'currency', 'label'].
    """
    logger.info("Building labels for all currencies...")
    label_rows = []

    for cur in CURRENCIES:
        if cur not in prices_df.columns:
            logger.warning(f"  {cur}: price column not found — skipping")
            continue

        cot_cur = cot_df[cot_df["currency"] == cur].set_index("date")["net"].sort_index()

        config = FX_SERIES.get(cur)
        if config is None:
            logger.warning(f"  {cur}: FX config not found — skipping")
            continue

        labels = build_labels_for_currency(
            weekly_price=prices_df[cur],
            cot_net=cot_cur,
            quote_usd=config["quote_usd"],
        )

        dist = check_class_distribution(labels, cur)
        if dist["neutral_exceeds_60pct"]:
            logger.warning(
                f"  {cur}: NEUTRAL > 60% — consider OR condition (RPD Section 2.1.2)"
            )

        for dt, lbl in labels.items():
            label_rows.append({"date": dt, "currency": cur, "label": lbl})

    labels_df = pd.DataFrame(label_rows)
    labels_df["date"] = pd.to_datetime(labels_df["date"])
    logger.info(f"Labels built: {len(labels_df)} rows")
    return labels_df


# ---------------------------------------------------------------------------
# Exploratory analysis (B2-04e)
# ---------------------------------------------------------------------------

def run_exploratory_analysis(df: pd.DataFrame) -> None:
    """
    B2-04e: feature correlation matrix, class distribution, missing values.
    """
    logger.info("\n" + "=" * 60)
    logger.info("EXPLORATORY ANALYSIS")
    logger.info("=" * 60)

    # Missing values
    feat_cols = [c for c in FEATURE_NAMES if c in df.columns]
    missing = df[feat_cols].isna().sum()
    if missing.any():
        logger.warning(f"Missing values:\n{missing[missing > 0]}")
    else:
        logger.info("Missing values: none in feature columns")

    # Class distribution per currency
    logger.info("\nClass distribution per currency:")
    for cur in CURRENCIES:
        cur_df = df[df["currency"] == cur]
        if cur_df.empty:
            continue
        total = len(cur_df)
        counts = cur_df["label"].value_counts()
        bull_pct = counts.get("BULL", 0) / total * 100
        bear_pct = counts.get("BEAR", 0) / total * 100
        neut_pct = counts.get("NEUTRAL", 0) / total * 100
        flag = " ⚠️  NEUTRAL>60%" if neut_pct > 60 else ""
        logger.info(
            f"  {cur}: BULL={bull_pct:.1f}%  BEAR={bear_pct:.1f}%  "
            f"NEUTRAL={neut_pct:.1f}%  n={total}{flag}"
        )

    # Overall distribution
    total = len(df)
    counts = df["label"].value_counts()
    logger.info(
        f"\nOverall: BULL={counts.get('BULL',0)/total*100:.1f}%  "
        f"BEAR={counts.get('BEAR',0)/total*100:.1f}%  "
        f"NEUTRAL={counts.get('NEUTRAL',0)/total*100:.1f}%  n={total}"
    )

    # Feature correlation matrix (top 10 most correlated pairs)
    logger.info("\nTop correlated feature pairs (|r| > 0.7):")
    corr = df[feat_cols].corr().abs()
    # Extract upper triangle
    corr_pairs = []
    for i in range(len(feat_cols)):
        for j in range(i + 1, len(feat_cols)):
            r = corr.iloc[i, j]
            if r > 0.7:
                corr_pairs.append((feat_cols[i], feat_cols[j], r))
    corr_pairs.sort(key=lambda x: -x[2])
    if corr_pairs:
        for f1, f2, r in corr_pairs[:10]:
            logger.info(f"  {f1} ↔ {f2}: r={r:.3f}")
    else:
        logger.info("  None above 0.7 threshold")

    # Feature ranges
    logger.info("\nFeature value ranges:")
    for col in feat_cols[:14]:  # Groups A + B
        s = df[col]
        logger.info(f"  {col:30s}  [{s.min():9.2f}, {s.max():9.2f}]  μ={s.mean():8.2f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    logger.info("=" * 60)
    logger.info("Phase B2-04: Build Training Dataset")
    logger.info("=" * 60)

    # ---- Pre-flight checks ---------------------------------------------------
    if not COT_CSV.exists():
        logger.error(f"COT CSV not found: {COT_CSV}")
        logger.error("Run training/download_cot_history.py first (B2-02).")
        return 1
    if not PRICES_CSV.exists():
        logger.error(f"Prices CSV not found: {PRICES_CSV}")
        logger.error("Run training/build_labels.py first (B2-01).")
        return 1

    # ---- Load COT data -------------------------------------------------------
    logger.info(f"\nLoading COT history from {COT_CSV.name}...")
    cot_df_raw = pd.read_csv(COT_CSV)
    logger.info(f"  Rows: {len(cot_df_raw)}")

    # Align COT Tuesday dates → Friday
    cot_df = align_cot_to_fridays(cot_df_raw)
    logger.info(f"  Aligned to Fridays. Date range: "
                f"{cot_df['date'].min().date()} → {cot_df['date'].max().date()}")

    # ---- Load price data -----------------------------------------------------
    logger.info(f"\nLoading prices from {PRICES_CSV.name}...")
    prices_df = pd.read_csv(PRICES_CSV, index_col=0, parse_dates=True)
    logger.info(f"  Rows: {len(prices_df)}, Currencies: {list(prices_df.columns)}")

    # ---- Download macro data (B2-04a) ----------------------------------------
    macro = download_macro_data()

    # ---- Build feature matrix (B2-04b) ---------------------------------------
    logger.info("\n=== Building feature matrix ===")
    features_df = build_historical_features(
        cot_df=cot_df,
        macro_rates=macro["rates"],
        macro_cpi=macro["cpi"],
        yields_df=macro["yields"],
        vix_series=macro["vix"],
    )
    logger.info(f"Feature matrix: {features_df.shape}")

    # ---- Build labels (B2-04c) -----------------------------------------------
    logger.info("\n=== Building labels ===")
    labels_df = build_all_labels(prices_df, cot_df)

    # ---- Align weekly index --------------------------------------------------
    # Feature dates come from COT (Fridays). Labels are also on Fridays.
    # Merge on (date, currency).
    logger.info("\n=== Joining features with labels (B2-04c) ===")
    merged = features_df.merge(
        labels_df,
        on=["date", "currency"],
        how="inner",
    )

    # Drop rows without a label (last 1 week per LABEL_CONFIRMATION_LAG=1)
    n_before = len(merged)
    merged = merged.dropna(subset=["label"])
    n_dropped = n_before - len(merged)
    if n_dropped:
        logger.info(f"  Dropped {n_dropped} rows without label (LABEL_CONFIRMATION_LAG enforcement)")

    merged = merged.sort_values(["date", "currency"]).reset_index(drop=True)

    # Enforce column order: date, currency, [28 features], label
    feat_cols = [f for f in FEATURE_NAMES if f in merged.columns]
    final_cols = ["date", "currency"] + feat_cols + ["label"]
    missing_feats = [f for f in FEATURE_NAMES if f not in merged.columns]
    if missing_feats:
        logger.warning(f"  Missing features (will be 0): {missing_feats}")
        for f in missing_feats:
            merged[f] = 0.0

    final = merged[final_cols]

    # ---- Save CSV (B2-04d) ---------------------------------------------------
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    final.to_csv(OUTPUT_CSV, index=False)
    logger.info(f"\nSaved: {OUTPUT_CSV}")
    logger.info(f"  Shape: {final.shape}  ({final['date'].nunique()} weeks × {final['currency'].nunique()} currencies)")
    logger.info(f"  Date range: {final['date'].min()} → {final['date'].max()}")
    logger.info(f"  Columns: {list(final.columns)}")

    # ---- Exploratory analysis (B2-04e) ---------------------------------------
    run_exploratory_analysis(final)

    # ---- Summary -----------------------------------------------------------
    logger.info("\n" + "=" * 60)
    logger.info("B2-04 COMPLETE")
    macro_mode = "FULL (28 features)" if FRED_API_KEY else "COT-only (Group C = 0)"
    logger.info(f"  Macro mode : {macro_mode}")
    logger.info(f"  Output     : {OUTPUT_CSV}")
    logger.info(f"  Total rows : {len(final)}")
    logger.info("  Next step  : B2-05 — Look-ahead bias tests")
    logger.info("  Then:        B3-01 — train_model.py (walk-forward)")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
