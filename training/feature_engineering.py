#!/usr/bin/env python3
"""
Feature engineering for FX Bias AI — 28 features per currency per week.

Groups:
  A — COT Legacy features   (12): cot_index, momentum, OI confluence, etc.
  B — TFF OI features        (4): lev_funds, asset_mgr, dealer positioning
  C — Macro features         (8): rates, CPI, yields, VIX
  D — Cross-asset + seasonal (4): gold/oil COT, month, quarter

Two usage modes:
  1. Historical training — build_historical_features(cot_df, macro_rates, ...)
     Caller supplies raw DataFrames; lag rules are applied internally.
  2. Inference — build_current_week(data_dir)
     Reads from latest JSON files; pre-computed values used where available.

Lag enforcement (B2-03e):
  All macro feature calculations use get_valid_date_for() from lag_rules.py.
  CRITICAL: never read a data point whose publication date is after week T.

Reference: Task List B2-03, RPD Section 3.2, System Design Section 5.2
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# Allow import from both training/ and backend/ paths
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from backend.utils.lag_rules import PUBLICATION_LAG, get_valid_date_for

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CURRENCIES = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]  # prediction currencies
ALL_CURRENCIES = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "USD"]  # incl. USD futures

FEATURE_NAMES: List[str] = [
    # Group A — COT Legacy (12)
    "cot_index",
    "cot_index_4w_change",
    "net_pct_change_1w",
    "momentum_acceleration",
    "oi_delta_direction",
    "oi_net_confluence",
    "flip_flag",
    "extreme_flag",
    "usd_index_cot",
    "rank_in_8",
    "spread_vs_usd",
    "weeks_since_flip",
    # Group B — TFF OI (4)
    "lev_funds_net_index",
    "asset_mgr_net_direction",
    "dealer_net_contrarian",
    "lev_vs_assetmgr_divergence",
    # Group C — Macro (8)
    "rate_diff_vs_usd",
    "rate_diff_trend_3m",
    "rate_hike_expectation",
    "cpi_diff_vs_usd",
    "cpi_trend",
    "pmi_composite_diff",
    "yield_10y_diff",
    "vix_regime",
    # Group D — Cross-asset + Seasonal (4)
    "gold_cot_index",
    "oil_cot_direction",
    "month",
    "quarter",
]

assert len(FEATURE_NAMES) == 28, f"Expected 28 features, got {len(FEATURE_NAMES)}"

# Map currency to yield country in FRED (only EUR→DE, GBP→GB, JPY→JP available)
CURRENCY_TO_YIELD_COUNTRY: Dict[str, Optional[str]] = {
    "EUR": "DE",
    "GBP": "GB",
    "JPY": "JP",
    "AUD": None,
    "CAD": None,
    "CHF": None,
    "NZD": None,
}

# oi_net_confluence regime encoding
OI_NET_REGIME = {
    (1, 1): 1,   # Strong: OI↑, Net↑
    (-1, 1): 2,  # Covering/Squeeze: OI↓, Net↑
    (1, -1): 3,  # NewShort/Buildup: OI↑, Net↓
    (-1, -1): 4, # Liquidation: OI↓, Net↓
}

# VIX regime thresholds
VIX_THRESHOLDS = [15.0, 20.0, 30.0]  # Low <15, Normal 15-20, Elevated 20-30, Extreme >30

# Rolling window for COT index normalization
COT_INDEX_WINDOW = 52  # weeks


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _rolling_norm(series: pd.Series, window: int = COT_INDEX_WINDOW) -> pd.Series:
    """
    Rolling min-max normalization to 0–100 range.

    When range is zero (flat series) or window not yet filled, returns 50.0
    (neutral) rather than raising an error.

    Formula: (x − min_w) / (max_w − min_w) × 100
    """
    rolling_min = series.rolling(window=window, min_periods=window).min()
    rolling_max = series.rolling(window=window, min_periods=window).max()
    spread = (rolling_max - rolling_min).replace(0.0, np.nan)
    norm = (series - rolling_min) / spread * 100.0
    # Fill positions where window not yet full or range=0
    return norm.fillna(50.0).clip(0.0, 100.0)


def _weeks_since_flip(flip_series: pd.Series) -> pd.Series:
    """
    Count the number of weeks elapsed since the most recent flip event.

    A flip is where flip_series == 1. If no flip has occurred yet, returns NaN.
    """
    result = np.full(len(flip_series), np.nan)
    last_flip_idx: Optional[int] = None
    for i, val in enumerate(flip_series):
        if val == 1:
            last_flip_idx = i
        if last_flip_idx is not None:
            result[i] = i - last_flip_idx
    return pd.Series(result, index=flip_series.index, dtype=float)


def _vix_regime(vix_value: float) -> int:
    """Map VIX value to regime bucket (0=Low, 1=Normal, 2=Elevated, 3=Extreme)."""
    if np.isnan(vix_value):
        return 1  # Default to Normal
    if vix_value < VIX_THRESHOLDS[0]:
        return 0
    elif vix_value < VIX_THRESHOLDS[1]:
        return 1
    elif vix_value < VIX_THRESHOLDS[2]:
        return 2
    else:
        return 3


def _align_monthly_to_weekly(
    monthly_series: pd.Series,
    weekly_index: pd.DatetimeIndex,
    series_type: str,
) -> pd.Series:
    """
    Align a monthly (or irregular) data series to a weekly DatetimeIndex
    while enforcing the publication lag rule for `series_type`.

    For each week T, selects the latest observation available on or before
    get_valid_date_for(series_type, T). Returns NaN where no data is available.

    This is the core lag enforcement for macro features (B2-03e).
    """
    result = pd.Series(np.nan, index=weekly_index, dtype=float)
    monthly_sorted = monthly_series.sort_index()

    for i, week_dt in enumerate(weekly_index):
        valid_date = pd.Timestamp(get_valid_date_for(series_type, week_dt.date()))
        mask = monthly_sorted.index <= valid_date
        available = monthly_sorted[mask]
        if not available.empty:
            result.iloc[i] = available.iloc[-1]

    return result


def _align_daily_to_weekly(
    daily_series: pd.Series,
    weekly_index: pd.DatetimeIndex,
    series_type: str = "price",
) -> pd.Series:
    """
    Align a daily data series to a weekly DatetimeIndex, applying lag rules.

    For series_type with lag=0 (price, yield_10y), uses the last available
    value on or before the weekly date (Friday).
    """
    result = pd.Series(np.nan, index=weekly_index, dtype=float)
    daily_sorted = daily_series.sort_index().dropna()

    for i, week_dt in enumerate(weekly_index):
        valid_date = pd.Timestamp(get_valid_date_for(series_type, week_dt.date()))
        mask = daily_sorted.index <= valid_date
        available = daily_sorted[mask]
        if not available.empty:
            result.iloc[i] = available.iloc[-1]

    return result


# ---------------------------------------------------------------------------
# Group A — COT Legacy features
# ---------------------------------------------------------------------------

def _compute_group_a(
    cot_wide: pd.DataFrame,
    currency: str,
    usd_cot_index: pd.Series,
    all_cot_indices: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute Group A features (12) for one currency across the full time series.

    Args:
        cot_wide:         Wide DataFrame with columns like 'net_EUR', 'open_interest_EUR', etc.
        currency:         Currency code (e.g. 'EUR')
        usd_cot_index:    Pre-computed rolling COT index for USD
        all_cot_indices:  DataFrame of cot_index per currency column (used for rank_in_8)

    Returns:
        DataFrame with Group A feature columns, indexed by date.
    """
    net = cot_wide[f"net_{currency}"].astype(float)
    oi = cot_wide[f"open_interest_{currency}"].astype(float)

    # 1. cot_index — rolling 52w normalization of net position
    cot_idx = _rolling_norm(net, COT_INDEX_WINDOW)

    # 2. cot_index_4w_change
    cot_idx_4w_change = cot_idx - cot_idx.shift(4)

    # 3. net_pct_change_1w — (Net[t] − Net[t−1]) / |Net[t−1]| × 100
    net_prev = net.shift(1)
    abs_prev = net_prev.abs().replace(0.0, np.nan)
    net_pct_change = (net - net_prev) / abs_prev * 100.0
    net_pct_change = net_pct_change.fillna(0.0).clip(-500.0, 500.0)

    # 4. momentum_acceleration — delta[t] − delta[t−1] (raw contracts)
    delta = net.diff()           # Net[t] − Net[t−1]
    momentum_accel = delta.diff().fillna(0.0)

    # 5. oi_delta_direction — sign(OI[t] − OI[t−1])
    oi_delta_dir = np.sign(oi.diff()).fillna(0.0).astype(int)

    # 6. oi_net_confluence — 4-regime encoding
    net_dir = np.sign(delta).fillna(0.0).astype(int)
    confluence = pd.Series(0, index=cot_wide.index)
    for (oi_sign, net_sign), regime in OI_NET_REGIME.items():
        mask = (oi_delta_dir == oi_sign) & (net_dir == net_sign)
        confluence[mask] = regime

    # 7. flip_flag — 1 if sign(Net[t]) ≠ sign(Net[t−1])
    net_sign = np.sign(net)
    net_sign_prev = net_sign.shift(1)
    flip = ((net_sign != net_sign_prev) & net_sign_prev.notna()).astype(int)

    # 8. extreme_flag — 1 if cot_index < 10 or > 90
    extreme = ((cot_idx < 10.0) | (cot_idx > 90.0)).astype(int)

    # 9. usd_index_cot — pre-computed, same value for all currencies
    usd_idx = usd_cot_index

    # 10. rank_in_8 — rank among all 8 currencies (1=strongest, 8=weakest)
    # Stronger = higher cot_index; rank 1 = highest cot_index
    rank = all_cot_indices.rank(axis=1, ascending=False, method="min")[currency]
    rank = rank.astype(float)

    # 11. spread_vs_usd — cot_index − usd_index_cot
    spread = cot_idx - usd_idx

    # 12. weeks_since_flip
    wsf = _weeks_since_flip(flip)
    wsf = wsf.fillna(wsf.max() + 1 if wsf.notna().any() else 52.0)

    return pd.DataFrame(
        {
            "cot_index": cot_idx,
            "cot_index_4w_change": cot_idx_4w_change.fillna(0.0),
            "net_pct_change_1w": net_pct_change,
            "momentum_acceleration": momentum_accel,
            "oi_delta_direction": oi_delta_dir,
            "oi_net_confluence": confluence,
            "flip_flag": flip,
            "extreme_flag": extreme,
            "usd_index_cot": usd_idx,
            "rank_in_8": rank,
            "spread_vs_usd": spread,
            "weeks_since_flip": wsf,
        },
        index=cot_wide.index,
    )


# ---------------------------------------------------------------------------
# Group B — TFF OI features
# ---------------------------------------------------------------------------

def _compute_group_b(cot_wide: pd.DataFrame, currency: str) -> pd.DataFrame:
    """
    Compute Group B features (4) for one currency: TFF OI features.

    If TFF data is all zeros (not yet available), features gracefully return
    neutral values (50.0, 0, 0, 0) per B2-03f guidance.

    Args:
        cot_wide: Wide DataFrame with lev_funds_net_{cur}, asset_mgr_net_{cur},
                  dealer_net_{cur} columns.
        currency: Currency code.

    Returns:
        DataFrame with 4 Group B columns.
    """
    lev_net_col = f"lev_funds_net_{currency}"
    asset_net_col = f"asset_mgr_net_{currency}"
    dealer_net_col = f"dealer_net_{currency}"

    lev_net = cot_wide.get(lev_net_col, pd.Series(0.0, index=cot_wide.index)).astype(float)
    asset_net = cot_wide.get(asset_net_col, pd.Series(0.0, index=cot_wide.index)).astype(float)
    dealer_net = cot_wide.get(dealer_net_col, pd.Series(0.0, index=cot_wide.index)).astype(float)

    # 13. lev_funds_net_index — rolling 52w normalization
    lev_net_idx = _rolling_norm(lev_net, COT_INDEX_WINDOW)

    # 14. asset_mgr_net_direction — sign(AssetMgr_Net[t] − AssetMgr_Net[t−4])
    asset_net_dir = np.sign(asset_net - asset_net.shift(4)).fillna(0.0).astype(int)

    # 15. dealer_net_contrarian — Dealer_Net normalized 52w
    # Values near 0 = neutral; large negative = market crowded long (contrarian short signal)
    dealer_norm = _rolling_norm(dealer_net, COT_INDEX_WINDOW)

    # 16. lev_vs_assetmgr_divergence — speculative vs institutional split
    asset_net_norm = _rolling_norm(asset_net, COT_INDEX_WINDOW)
    divergence = lev_net_idx - asset_net_norm

    return pd.DataFrame(
        {
            "lev_funds_net_index": lev_net_idx,
            "asset_mgr_net_direction": asset_net_dir,
            "dealer_net_contrarian": dealer_norm,
            "lev_vs_assetmgr_divergence": divergence,
        },
        index=cot_wide.index,
    )


# ---------------------------------------------------------------------------
# Group C — Macro features
# ---------------------------------------------------------------------------

def _compute_group_c(
    weekly_index: pd.DatetimeIndex,
    currency: str,
    macro_rates: Optional[pd.DataFrame],
    macro_cpi: Optional[pd.DataFrame],
    yields_df: Optional[pd.DataFrame],
    vix_series: Optional[pd.Series],
) -> pd.DataFrame:
    """
    Compute Group C features (8) for one currency across the full time series.

    Lag rules are applied internally via get_valid_date_for().
    If any macro DataFrame is None, that feature group fills with 0.0 (B2-03f).

    Args:
        weekly_index:  DatetimeIndex aligned to weekly Fridays.
        currency:      Currency code (e.g. 'EUR').
        macro_rates:   DataFrame indexed by date, columns = currency codes (USD, EUR, …).
                       Raw monthly policy rates — lag applied internally.
        macro_cpi:     DataFrame indexed by date, columns = currency codes.
                       Raw monthly CPI YoY values — lag applied internally.
        yields_df:     DataFrame indexed by date, columns = country codes (US, DE, GB, JP).
                       Daily 10Y yields — lag applied internally.
        vix_series:    Series indexed by date with VIX daily values.

    Returns:
        DataFrame with 8 Group C columns.
    """
    n = len(weekly_index)
    result = pd.DataFrame(0.0, index=weekly_index, columns=[
        "rate_diff_vs_usd", "rate_diff_trend_3m", "rate_hike_expectation",
        "cpi_diff_vs_usd", "cpi_trend", "pmi_composite_diff",
        "yield_10y_diff", "vix_regime",
    ])

    # ---- Policy rates (lag=0: policy_rate published same day as meeting) ----
    if macro_rates is not None and "USD" in macro_rates.columns:
        usd_rate = _align_monthly_to_weekly(macro_rates["USD"], weekly_index, "policy_rate")
        if currency in macro_rates.columns:
            cur_rate = _align_monthly_to_weekly(macro_rates[currency], weekly_index, "policy_rate")
        else:
            cur_rate = pd.Series(np.nan, index=weekly_index)

        rate_diff = (cur_rate - usd_rate).fillna(0.0)

        # 17. rate_diff_vs_usd
        result["rate_diff_vs_usd"] = rate_diff

        # 18. rate_diff_trend_3m — diff[t] − diff[t−12w]
        result["rate_diff_trend_3m"] = (rate_diff - rate_diff.shift(12)).fillna(0.0)

        # 19. rate_hike_expectation — proxy: sign of rate_diff trend momentum
        # sign(diff[t] - diff[t-4]): +1 rising differential, -1 falling, 0 flat
        result["rate_hike_expectation"] = (
            np.sign(rate_diff - rate_diff.shift(4)).fillna(0.0).astype(int)
        )

    # ---- CPI (lag = T-2 months: CPI published ~6 weeks after reference month) ----
    if macro_cpi is not None and "USD" in macro_cpi.columns:
        usd_cpi = _align_monthly_to_weekly(macro_cpi["USD"], weekly_index, "cpi")
        if currency in macro_cpi.columns:
            cur_cpi = _align_monthly_to_weekly(macro_cpi[currency], weekly_index, "cpi")
        else:
            cur_cpi = pd.Series(np.nan, index=weekly_index)

        # 20. cpi_diff_vs_usd
        result["cpi_diff_vs_usd"] = (cur_cpi - usd_cpi).fillna(0.0)

        # 21. cpi_trend — sign(CPI[t] − CPI[t−3M])
        # 3 months ≈ 13 weeks on weekly index, but CPI is monthly so ~3 rows back
        cpi_trend = np.sign(cur_cpi - cur_cpi.shift(3)).fillna(0.0).astype(int)
        result["cpi_trend"] = cpi_trend

    # 22. pmi_composite_diff — optional, fill with 0 (B2-03f)
    result["pmi_composite_diff"] = 0.0

    # ---- 10Y yields (lag=0) ----
    yield_country = CURRENCY_TO_YIELD_COUNTRY.get(currency)
    if yields_df is not None and yield_country is not None and yield_country in yields_df.columns:
        if "US" in yields_df.columns:
            us_yield_weekly = _align_daily_to_weekly(yields_df["US"], weekly_index, "yield_10y")
            cy_yield_weekly = _align_daily_to_weekly(yields_df[yield_country], weekly_index, "yield_10y")
            result["yield_10y_diff"] = (cy_yield_weekly - us_yield_weekly).fillna(0.0)

    # ---- VIX ----
    if vix_series is not None:
        vix_weekly = _align_daily_to_weekly(vix_series, weekly_index, "price")  # lag=0
        result["vix_regime"] = vix_weekly.apply(lambda v: _vix_regime(v if not pd.isna(v) else np.nan))

    return result


# ---------------------------------------------------------------------------
# Group D — Cross-asset & Seasonal features
# ---------------------------------------------------------------------------

def _compute_group_d(
    weekly_index: pd.DatetimeIndex,
    gold_net: Optional[pd.Series],
    oil_net: Optional[pd.Series],
) -> pd.DataFrame:
    """
    Compute Group D features (4) across the full time series.

    Note: month and quarter are the same for all currencies on a given date.

    Args:
        weekly_index: DatetimeIndex of weekly Fridays.
        gold_net:     Weekly gold futures net positions (noncomm_long - short).
        oil_net:      Weekly oil futures net positions.

    Returns:
        DataFrame with 4 Group D columns.
    """
    result = pd.DataFrame(0.0, index=weekly_index, columns=[
        "gold_cot_index", "oil_cot_direction", "month", "quarter",
    ])

    # 25. gold_cot_index — rolling 52w normalization of gold net
    if gold_net is not None:
        gold_aligned = gold_net.reindex(weekly_index).ffill()
        result["gold_cot_index"] = _rolling_norm(gold_aligned, COT_INDEX_WINDOW)

    # 26. oil_cot_direction — sign of trend in oil COT index
    if oil_net is not None:
        oil_aligned = oil_net.reindex(weekly_index).ffill()
        oil_idx = _rolling_norm(oil_aligned, COT_INDEX_WINDOW)
        # direction: sign of 4-week change in oil COT index
        result["oil_cot_direction"] = np.sign(oil_idx - oil_idx.shift(4)).fillna(0.0).astype(int)

    # 27. month — calendar month 1–12
    result["month"] = weekly_index.month.astype(int)

    # 28. quarter — calendar quarter 1–4
    result["quarter"] = weekly_index.quarter.astype(int)

    return result


# ---------------------------------------------------------------------------
# Historical feature builder (B2-03a–f)
# ---------------------------------------------------------------------------

def build_historical_features(
    cot_df: pd.DataFrame,
    macro_rates: Optional[pd.DataFrame] = None,
    macro_cpi: Optional[pd.DataFrame] = None,
    yields_df: Optional[pd.DataFrame] = None,
    vix_series: Optional[pd.Series] = None,
    gold_net: Optional[pd.Series] = None,
    oil_net: Optional[pd.Series] = None,
    currencies: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Build the full historical feature matrix for all currencies.

    Args:
        cot_df:       Long-format COT historical data — columns:
                      date, currency, noncomm_long, noncomm_short, open_interest, net,
                      lev_funds_net, asset_mgr_net, dealer_net, …
        macro_rates:  Monthly policy rates DataFrame; index=date, columns=currency codes.
                      Pass raw FRED data — lag rules applied internally.
        macro_cpi:    Monthly CPI YoY DataFrame; same structure as macro_rates.
        yields_df:    Daily 10Y yields; index=date, columns=['US', 'DE', 'GB', 'JP'].
        vix_series:   Daily VIX series; index=date.
        gold_net:     Weekly gold futures net positions; index=date.
        oil_net:      Weekly WTI/Brent oil futures net positions; index=date.
        currencies:   List of currencies to process (default: CURRENCIES = 7 non-USD).

    Returns:
        DataFrame with columns: [date, currency] + FEATURE_NAMES (28).
        Suitable for joining with labels from build_labels.py.
    """
    if currencies is None:
        currencies = CURRENCIES

    # ---- Pivot COT data to wide format ----------------------------------------
    logger.info("Pivoting COT data to wide format...")
    cot_df = cot_df.copy()
    cot_df["date"] = pd.to_datetime(cot_df["date"])
    cot_df = cot_df.sort_values("date")

    value_cols = [
        "noncomm_long", "noncomm_short", "open_interest", "net",
        "lev_funds_long", "lev_funds_short", "lev_funds_net",
        "asset_mgr_long", "asset_mgr_short", "asset_mgr_net",
        "dealer_long", "dealer_short", "dealer_net",
    ]
    available_cols = [c for c in value_cols if c in cot_df.columns]

    # Pivot: (date, currency) → flat columns like 'net_EUR'
    cot_wide = cot_df.pivot_table(index="date", columns="currency", values=available_cols, aggfunc="last")
    cot_wide.columns = [f"{field}_{cur}" for field, cur in cot_wide.columns]
    cot_wide = cot_wide.sort_index()

    weekly_index = cot_wide.index  # already weekly (COT reports are weekly)

    # ---- Pre-compute USD COT index (needed for all currencies) ----------------
    if "net_USD" in cot_wide.columns:
        usd_cot_index = _rolling_norm(cot_wide["net_USD"].astype(float), COT_INDEX_WINDOW)
    else:
        logger.warning("USD COT data not found — usd_index_cot will be 50.0 (neutral)")
        usd_cot_index = pd.Series(50.0, index=weekly_index)

    # ---- Pre-compute all COT indices for rank_in_8 ----------------------------
    all_cot_indices = pd.DataFrame(index=weekly_index)
    for cur in ALL_CURRENCIES:
        if f"net_{cur}" in cot_wide.columns:
            all_cot_indices[cur] = _rolling_norm(
                cot_wide[f"net_{cur}"].astype(float), COT_INDEX_WINDOW
            )
        else:
            all_cot_indices[cur] = 50.0

    # ---- Group D (same for all currencies) ------------------------------------
    logger.info("Computing Group D features (cross-asset + seasonal)...")
    group_d = _compute_group_d(weekly_index, gold_net, oil_net)

    # ---- Per-currency feature computation -------------------------------------
    all_rows: list = []

    for cur in currencies:
        if f"net_{cur}" not in cot_wide.columns:
            logger.warning(f"{cur}: net position column not found — skipping")
            continue

        logger.info(f"Computing features for {cur}...")

        # Group A
        grp_a = _compute_group_a(cot_wide, cur, usd_cot_index, all_cot_indices)

        # Group B
        grp_b = _compute_group_b(cot_wide, cur)

        # Group C (with lag enforcement)
        grp_c = _compute_group_c(
            weekly_index, cur,
            macro_rates, macro_cpi, yields_df, vix_series,
        )

        # Concatenate all groups for this currency
        feature_df = pd.concat([grp_a, grp_b, grp_c, group_d], axis=1)
        feature_df = feature_df[FEATURE_NAMES]  # enforce column order

        # Add currency column
        feature_df = feature_df.copy()
        feature_df.insert(0, "currency", cur)
        feature_df.index.name = "date"

        all_rows.append(feature_df)

    if not all_rows:
        raise ValueError("No currency data found in COT DataFrame")

    result = pd.concat(all_rows, axis=0)
    result = result.reset_index()  # move date from index to column
    result = result.sort_values(["date", "currency"]).reset_index(drop=True)

    # Final NaN fill for optional features (B2-03f)
    result["pmi_composite_diff"] = result["pmi_composite_diff"].fillna(0.0)
    for col in FEATURE_NAMES:
        if col not in result.columns:
            result[col] = 0.0
        # Fill remaining NaN with median per column (safe default for optional features)
        if result[col].isna().any():
            col_median = result[col].median()
            result[col] = result[col].fillna(col_median if not np.isnan(col_median) else 0.0)

    logger.info(
        f"Historical features built: {len(result)} rows "
        f"({len(result['date'].unique())} weeks × {len(currencies)} currencies)"
    )
    return result


# ---------------------------------------------------------------------------
# Inference: build_current_week() from latest JSON files (B2-03g)
# ---------------------------------------------------------------------------

def _load_json(path: str) -> dict:
    """Load a JSON file, raising FileNotFoundError with a helpful message."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Required data file not found: {path}\n"
            "Run fetch_cot.py / fetch_macro.py / fetch_cross_asset.py first."
        )
    with open(p, "r") as f:
        return json.load(f)


def _parse_cot_json(cot_data: dict) -> Dict[str, dict]:
    """
    Parse cot-latest.json into a per-currency dict with all fields needed for inference.

    Returns:
        {
          'EUR': {
            'cot_index': float,          # cot_indices.EUR.index (current)
            'trend_12w': list[float],    # cot_indices.EUR.trend_12w
            'net': int,                  # legacy[].net
            'net_delta_1w': int,         # legacy[].net_delta_1w
            'open_interest': int,
            'extreme_flag': bool,
            'flip_flag': bool,
            'lev_funds_net': int,
            'asset_mgr_net': int,
            'dealer_net': int,
            'lev_vs_assetmgr_divergence': float,
          },
          ...
        }
    """
    result: Dict[str, dict] = {}

    # Index legacy records by currency
    legacy_by_cur = {r["currency"]: r for r in cot_data.get("legacy", [])}
    tff_by_cur = {r["currency"]: r for r in cot_data.get("tff", [])}
    cot_indices = cot_data.get("cot_indices", {})

    for cur in ALL_CURRENCIES:
        leg = legacy_by_cur.get(cur, {})
        tff = tff_by_cur.get(cur, {})
        idx = cot_indices.get(cur, {})

        result[cur] = {
            "cot_index": idx.get("index", 50.0),
            "trend_12w": idx.get("trend_12w", [50.0] * 12),
            "net": leg.get("net", 0),
            "net_delta_1w": leg.get("net_delta_1w", 0),
            "open_interest": leg.get("open_interest", 0),
            "extreme_flag": int(bool(leg.get("extreme_flag", False))),
            "flip_flag": int(bool(leg.get("flip_flag", False))),
            "cot_index_52w": leg.get("cot_index_52w", 50.0),
            "lev_funds_net": tff.get("lev_funds_net", 0),
            "asset_mgr_net": tff.get("asset_mgr_net", 0),
            "dealer_net": tff.get("dealer_net", 0),
            "lev_vs_assetmgr_divergence": tff.get("lev_vs_assetmgr_divergence", 0.0),
        }

    return result


def _parse_macro_json(macro_data: dict, currency: str) -> dict:
    """
    Extract macro features for one currency from macro-latest.json.

    Returns a flat dict with keys: rate_diff_vs_usd, rate_diff_trend_3m,
    rate_hike_expectation, cpi_diff_vs_usd, cpi_trend, yield_10y_diff, vix_regime.
    """
    out: dict = {}

    # Policy rates → pre-computed diff_vs_usd
    rate_diff = 0.0
    rate_trend_3m = 0.0
    for rec in macro_data.get("policy_rates", []):
        if rec.get("currency") == currency:
            rate_diff = float(rec.get("diff_vs_usd", 0.0))
            # trend_3m is RISING/FALLING/STABLE → encode to +1/0/-1
            trend_str = rec.get("trend_3m", "STABLE")
            rate_trend_3m = {"RISING": 1.0, "FALLING": -1.0, "STABLE": 0.0}.get(trend_str, 0.0)
            break

    out["rate_diff_vs_usd"] = rate_diff
    out["rate_diff_trend_3m"] = rate_trend_3m
    out["rate_hike_expectation"] = float(np.sign(rate_trend_3m))

    # CPI → diff_vs_usd, trend
    cpi_diff = 0.0
    cpi_trend = 0.0
    for rec in macro_data.get("cpi_yoy", []):
        if rec.get("currency") == currency:
            cpi_diff = float(rec.get("diff_vs_usd", 0.0))
            trend_str = rec.get("trend_3m", "STABLE")
            cpi_trend = {"RISING": 1.0, "FALLING": -1.0, "STABLE": 0.0}.get(trend_str, 0.0)
            break

    out["cpi_diff_vs_usd"] = cpi_diff
    out["cpi_trend"] = cpi_trend
    out["pmi_composite_diff"] = 0.0  # optional, not in JSON schema

    # 10Y yields → spread_vs_us for relevant currencies
    yield_country = CURRENCY_TO_YIELD_COUNTRY.get(currency)
    yield_diff = 0.0
    for rec in macro_data.get("yields_10y", []):
        if yield_country and rec.get("country") == yield_country:
            yield_diff = float(rec.get("spread_vs_us", 0.0))
            break
    out["yield_10y_diff"] = yield_diff

    # VIX regime
    vix = macro_data.get("vix", {})
    vix_val = float(vix.get("value", 18.0))
    out["vix_regime"] = float(_vix_regime(vix_val))

    return out


def _parse_cross_asset_json(cross_data: dict) -> dict:
    """
    Extract Group D cross-asset features from cross-asset-latest.json.

    Returns:
        {'gold_cot_index': float, 'oil_cot_direction': float}
    """
    commodities = cross_data.get("commodities", {})
    gold = commodities.get("gold", {})
    oil = commodities.get("oil", {})

    gold_cot_index = float(gold.get("cot_index", 50.0))

    oil_trend_dir = oil.get("trend_direction", "FLAT")
    oil_cot_direction = {"RISING": 1.0, "FALLING": -1.0, "FLAT": 0.0}.get(oil_trend_dir, 0.0)

    return {
        "gold_cot_index": gold_cot_index,
        "oil_cot_direction": oil_cot_direction,
    }


def build_current_week(
    data_dir: Optional[str] = None,
    cot_path: Optional[str] = None,
    macro_path: Optional[str] = None,
    cross_path: Optional[str] = None,
) -> pd.DataFrame:
    """
    Build feature matrix for the current week from latest JSON data files.

    This is the inference entry point called by predict_bias.py.

    Args:
        data_dir:   Directory containing cot-latest.json, macro-latest.json,
                    cross-asset-latest.json. Default: repo root / 'data'.
        cot_path:   Override path for cot-latest.json.
        macro_path: Override path for macro-latest.json.
        cross_path: Override path for cross-asset-latest.json.

    Returns:
        DataFrame with shape (7, 28):
          index = ['EUR', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF', 'NZD']
          columns = FEATURE_NAMES (28 features in canonical order)

    Notes:
        Features requiring 52-week rolling history (lev_funds_net_index,
        dealer_net_contrarian) use pre-computed values from cot-latest.json
        where available, falling back to 50.0 (neutral) if absent.
        Features requiring 12-week trend (cot_index_4w_change) use
        cot_indices.{cur}.trend_12w from the COT JSON.
    """
    # Resolve paths
    if data_dir is None:
        data_dir = str(_REPO_ROOT / "data")

    cot_path = cot_path or os.path.join(data_dir, "cot-latest.json")
    macro_path = macro_path or os.path.join(data_dir, "macro-latest.json")
    cross_path = cross_path or os.path.join(data_dir, "cross-asset-latest.json")

    logger.info(f"Loading COT data from: {cot_path}")
    cot_data = _load_json(cot_path)
    logger.info(f"Loading macro data from: {macro_path}")
    macro_data = _load_json(macro_path)
    logger.info(f"Loading cross-asset data from: {cross_path}")
    cross_data = _load_json(cross_path)

    cot_by_cur = _parse_cot_json(cot_data)
    cross_features = _parse_cross_asset_json(cross_data)

    # Extract reference date for seasonal features
    report_date_str = cot_data.get("publishDate") or cot_data.get("reportDate", "")
    if report_date_str:
        ref_date = pd.Timestamp(report_date_str)
    else:
        ref_date = pd.Timestamp.today()

    # ---- Cross-currency derived: rank_in_8 ------------------------------------
    # Rank by cot_index across all 8 currencies (1=strongest/highest COT index)
    all_indices = {cur: cot_by_cur[cur]["cot_index"] for cur in ALL_CURRENCIES}
    sorted_currencies = sorted(ALL_CURRENCIES, key=lambda c: all_indices[c], reverse=True)
    rank_map = {cur: rank + 1 for rank, cur in enumerate(sorted_currencies)}

    usd_cot_index = all_indices.get("USD", 50.0)

    # ---- Build per-currency feature vectors -----------------------------------
    rows: Dict[str, dict] = {}

    for cur in CURRENCIES:
        c = cot_by_cur.get(cur, {})
        trend = c.get("trend_12w", [50.0] * 12)

        # --- Group A ---
        cot_idx = c["cot_index"]
        trend_12 = list(trend)
        # cot_index_4w_change: trend_12w[-1] - trend_12w[-5] (requires len >= 5)
        cot_4w_change = (trend_12[-1] - trend_12[-5]) if len(trend_12) >= 5 else 0.0

        net = float(c.get("net", 0))
        net_delta = float(c.get("net_delta_1w", 0))
        prev_net = net - net_delta if net_delta != 0 else net

        # net_pct_change_1w
        abs_prev = abs(prev_net) if prev_net != 0 else np.nan
        net_pct_1w = (net_delta / abs_prev * 100.0) if not np.isnan(abs_prev or np.nan) else 0.0
        net_pct_1w = float(np.clip(net_pct_1w, -500.0, 500.0))

        # momentum_acceleration: we only have 1 delta → use 0 as fallback
        # (requires 2 consecutive deltas; not available from current JSON alone)
        momentum_accel = 0.0

        # oi_delta_direction: not directly available from JSON (no prev OI)
        # Use 0 (neutral) as fallback
        oi_delta_dir = 0

        # oi_net_confluence: need OI and Net directions
        oi_net_conf = 0  # neutral fallback

        flip = c.get("flip_flag", 0)
        extreme = c.get("extreme_flag", 0)
        spread_usd = cot_idx - usd_cot_index
        rank = float(rank_map.get(cur, 4))

        # weeks_since_flip: not computable from current JSON alone → fallback 0
        wsf = 0.0

        # --- Group B ---
        # lev_funds_net_index: need 52w history → use 50 (neutral) fallback
        # If cot-latest.json is enhanced to include these, they'd be read here
        lev_net_idx = 50.0
        asset_dir = 0
        dealer_contr = 50.0
        lev_vs_asset = c.get("lev_vs_assetmgr_divergence", 0.0)

        # --- Group C ---
        macro_feats = _parse_macro_json(macro_data, cur)

        # --- Group D ---
        month = int(ref_date.month)
        quarter = int(ref_date.quarter)

        rows[cur] = {
            # Group A
            "cot_index": cot_idx,
            "cot_index_4w_change": cot_4w_change,
            "net_pct_change_1w": net_pct_1w,
            "momentum_acceleration": momentum_accel,
            "oi_delta_direction": float(oi_delta_dir),
            "oi_net_confluence": float(oi_net_conf),
            "flip_flag": float(flip),
            "extreme_flag": float(extreme),
            "usd_index_cot": usd_cot_index,
            "rank_in_8": rank,
            "spread_vs_usd": spread_usd,
            "weeks_since_flip": wsf,
            # Group B
            "lev_funds_net_index": lev_net_idx,
            "asset_mgr_net_direction": float(asset_dir),
            "dealer_net_contrarian": dealer_contr,
            "lev_vs_assetmgr_divergence": float(lev_vs_asset),
            # Group C
            **macro_feats,
            # Group D
            "gold_cot_index": cross_features["gold_cot_index"],
            "oil_cot_direction": cross_features["oil_cot_direction"],
            "month": float(month),
            "quarter": float(quarter),
        }

    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "currency"
    df = df[FEATURE_NAMES]  # enforce canonical column order

    logger.info(
        f"build_current_week() complete — shape: {df.shape} "
        f"({len(df)} currencies × {len(df.columns)} features)"
    )
    return df


# ---------------------------------------------------------------------------
# CLI convenience
# ---------------------------------------------------------------------------

def main() -> int:
    """
    Quick validation: build current-week features if JSON files are present,
    otherwise run a smoke test with synthetic COT data.
    """
    import argparse

    parser = argparse.ArgumentParser(description="FX Bias AI — Feature Engineering")
    parser.add_argument(
        "--mode",
        choices=["current", "historical"],
        default="current",
        help="'current' reads JSON files; 'historical' runs a smoke test",
    )
    parser.add_argument("--data-dir", default=None, help="Path to data/ directory")
    parser.add_argument(
        "--cot-csv",
        default=str(_REPO_ROOT / "training" / "data" / "cot_historical_2006_2026.csv"),
        help="Path to cot_historical_2006_2026.csv (historical mode only)",
    )
    args = parser.parse_args()

    if args.mode == "current":
        logger.info("=== Mode: build_current_week ===")
        try:
            df = build_current_week(data_dir=args.data_dir)
            logger.info(f"\n{df.to_string()}")
            logger.info("\nbuild_current_week() succeeded.")
        except FileNotFoundError as exc:
            logger.error(str(exc))
            return 1

    else:
        logger.info("=== Mode: historical smoke test ===")
        if not Path(args.cot_csv).exists():
            logger.error(f"COT CSV not found: {args.cot_csv}")
            logger.error("Run training/download_cot_history.py first.")
            return 1

        cot_df = pd.read_csv(args.cot_csv)
        logger.info(f"Loaded COT history: {len(cot_df)} rows")

        df = build_historical_features(
            cot_df=cot_df,
            # Macro data not provided → Group C features = 0 (expected)
        )
        logger.info(f"\nFeature matrix shape: {df.shape}")
        logger.info(f"Columns: {list(df.columns)}")
        logger.info(f"\nDate range: {df['date'].min()} → {df['date'].max()}")
        logger.info(f"NaN count:\n{df[FEATURE_NAMES].isna().sum()}")

        group_a_cols = FEATURE_NAMES[:12]
        logger.info(f"\nGroup A sample (EUR, last 3 weeks):")
        eur_tail = df[df["currency"] == "EUR"].tail(3)[["date"] + group_a_cols]
        logger.info(f"\n{eur_tail.to_string()}")

        logger.info("\nHistorical smoke test passed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
