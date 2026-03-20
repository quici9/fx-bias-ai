#!/usr/bin/env python3
"""
B4-01 — predict_bias.py

Main inference pipeline: load model → check version → build features →
predict → calibrate → pair selection → assemble BiasReport → validate → write.

Reference: System Design Section 5.3, RPD Section 6.3
Exit codes: 0=success, 1=partial (some currencies failed), 2=failed

Usage:
    python backend/scripts/predict_bias.py              # primary RF model
    python backend/scripts/predict_bias.py --fallback   # LR fallback
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.utils.file_io import EXIT_FAILED, EXIT_SUCCESS, setup_logging, write_output
from backend.utils.model_loader import load_model

logger = setup_logging(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

DATA_DIR          = _REPO_ROOT / "data"
HISTORY_BIAS_DIR  = DATA_DIR / "history" / "bias"
COT_FILE          = DATA_DIR / "cot-latest.json"
MACRO_FILE        = DATA_DIR / "macro-latest.json"
CROSS_ASSET_FILE  = DATA_DIR / "cross-asset-latest.json"
CALENDAR_FILE     = DATA_DIR / "calendar-latest.json"  # optional
BIAS_LATEST_FILE  = DATA_DIR / "bias-latest.json"
FEATURE_META_FILE = _REPO_ROOT / "models" / "feature_metadata.json"
SCHEMA_FILE       = _REPO_ROOT / "backend" / "schemas" / "bias-report.schema.json"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CURRENCIES = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "USD"]
# 7 traded vs USD + USD index itself

MODEL_VERSION    = "rf-v2.1"
EXPECTED_FEATURE_VERSION = "v2.1-28f"

# Confidence thresholds (match validate_model.py)
CONF_HIGH   = 0.70
CONF_MEDIUM = 0.55

# BIAS score: BULL=+1, BEAR=-1, NEUTRAL=0 (weighted by confidence)
CONF_WEIGHT = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}

# B4-01d — CURRENCY_CORRELATION matrix (System Design Section 5.4)
# Known high-correlation pairs that should not be recommended simultaneously
# (|r| > 0.75 threshold for filter)
CURRENCY_CORRELATION = {
    ("EUR", "GBP"): 0.82,
    ("EUR", "CHF"): 0.78,
    ("GBP", "CHF"): 0.76,
    ("AUD", "NZD"): 0.88,
    ("AUD", "CAD"): 0.72,   # both commodity currencies
    ("NZD", "CAD"): 0.68,
    ("EUR", "AUD"): 0.65,
    ("JPY", "CHF"): 0.71,   # both safe havens
}
CORRELATION_FILTER_THRESHOLD = 0.75

# VIX regime numeric encoding
VIX_REGIME_MAP = {"LOW": 0, "NORMAL": 1, "ELEVATED": 2, "EXTREME": 3}

# rate trend encoding
RATE_TREND_MAP = {"RISING": 1, "FALLING": -1, "STABLE": 0, "N/A": 0}

# 28 feature column order (must match training)
FEATURE_COLS = [
    "cot_index", "cot_index_4w_change", "net_pct_change_1w",
    "momentum_acceleration", "oi_delta_direction", "oi_net_confluence",
    "flip_flag", "extreme_flag", "usd_index_cot", "rank_in_8",
    "spread_vs_usd", "weeks_since_flip",
    # Group B — TFF
    # lev_funds_net_index excluded: r=0.836 với cot_index — redundant
    "dealer_net_contrarian", "lev_vs_assetmgr_divergence",
    "asset_mgr_net_direction",
    "rate_diff_vs_usd", "rate_diff_trend_3m", "rate_hike_expectation",
    "cpi_diff_vs_usd", "cpi_trend", "pmi_composite_diff",
    "yield_10y_diff", "vix_regime",
    # month excluded: r=0.97 with quarter
    "gold_cot_index", "oil_cot_direction", "quarter",
]

# Currency → yield differential pair mapping (for cross-asset)
YIELD_DIFF_MAP = {
    "EUR": "US-DE",
    "GBP": "US-GB",
    "JPY": "US-JP",
}

# ---------------------------------------------------------------------------
# B4-01a helpers — feature building
# ---------------------------------------------------------------------------

import numpy as np


def _vix_regime_numeric(regime_str: str) -> int:
    return VIX_REGIME_MAP.get(str(regime_str).upper(), 1)


def _trend_to_numeric(trend_str: str) -> float:
    return float(RATE_TREND_MAP.get(str(trend_str).upper(), 0))


def _safe(value, default=0.0) -> float:
    """Return float value or default if None/missing."""
    try:
        v = float(value)
        return v if not np.isnan(v) else default
    except (TypeError, ValueError):
        return default


def build_feature_vector(
    currency: str,
    cot_data: dict,
    macro_data: dict,
    cross_asset: dict,
    usd_cot_index: float,
    all_cot_indices: dict,
    now: datetime,
) -> dict:
    """
    Build one feature vector for a single currency from live data.

    Returns dict keyed by feature name (25 features + currency_enc).
    Defaults to 0.0 for any unavailable feature (non-fatal).
    """
    feat = {k: 0.0 for k in FEATURE_COLS}

    # ---- Group A — COT (Legacy) ----------------------------------------

    # Find currency entry in legacy list
    legacy_entry = next(
        (r for r in cot_data.get("legacy", []) if r.get("currency") == currency),
        {}
    )
    tff_entry = next(
        (r for r in cot_data.get("tff", []) if r.get("currency") == currency),
        {}
    )
    cot_index_entry = cot_data.get("cot_indices", {}).get(currency, {})

    trend_12w = cot_index_entry.get("trend_12w", [])

    # 1. cot_index — 52-week normalised COT index (pre-computed by fetch_cot)
    feat["cot_index"] = _safe(legacy_entry.get("cot_index_52w"), 50.0)

    # 2. cot_index_4w_change — index[now] − index[4w ago]
    if len(trend_12w) >= 5:
        feat["cot_index_4w_change"] = _safe(trend_12w[0]) - _safe(trend_12w[4])

    # 3. net_pct_change_1w — (net[t] − net[t-1]) / |net[t-1]| × 100
    net_now = _safe(legacy_entry.get("net"), 0.0)
    net_delta = _safe(legacy_entry.get("net_delta_1w"), 0.0)
    net_prev = net_now - net_delta
    if abs(net_prev) > 1:
        feat["net_pct_change_1w"] = net_delta / abs(net_prev) * 100.0
    else:
        feat["net_pct_change_1w"] = 0.0

    # 4. momentum_acceleration — (delta[t] − delta[t−1]) / |net[t−1]| × 100
    # Normalized as % of prior net, clipped ±500 — matches feature_engineering.py
    if len(trend_12w) >= 3:
        d1 = _safe(trend_12w[0]) - _safe(trend_12w[1])
        d2 = _safe(trend_12w[1]) - _safe(trend_12w[2])
        net_t1 = abs(_safe(trend_12w[1]))
        if net_t1 > 1:
            feat["momentum_acceleration"] = float(np.clip((d1 - d2) / net_t1 * 100.0, -500.0, 500.0))
        else:
            feat["momentum_acceleration"] = 0.0

    # 5. oi_delta_direction — not directly available in latest (no OI prev)
    # Default 0 (unavailable without history)
    feat["oi_delta_direction"] = 0.0

    # 6. oi_net_confluence — 0 (unavailable without OI direction history)
    feat["oi_net_confluence"] = 0.0

    # 7. flip_flag
    feat["flip_flag"] = 1.0 if legacy_entry.get("flip_flag") else 0.0

    # 8. extreme_flag
    feat["extreme_flag"] = 1.0 if legacy_entry.get("extreme_flag") else 0.0

    # 9. usd_index_cot — USD COT index (shared across all currencies)
    feat["usd_index_cot"] = _safe(usd_cot_index, 50.0)

    # 10. rank_in_8 — filled after all currencies computed (placeholder)
    feat["rank_in_8"] = 4.0  # midpoint placeholder

    # 11. spread_vs_usd
    feat["spread_vs_usd"] = feat["cot_index"] - feat["usd_index_cot"]

    # 12. weeks_since_flip — not available in latest data without history
    feat["weeks_since_flip"] = 0.0

    # ---- Group B — TFF -------------------------------------------------

    # lev_funds_net_index: normalize lev_funds_net by approximation
    # Without 52w history we use raw lev_funds_net scaled ÷ 100k as proxy
    lev_net = _safe(tff_entry.get("lev_funds_net"), 0.0)
    # Simple linear scale into [0,100] based on open interest context
    oi = _safe(legacy_entry.get("open_interest"), 1e6)
    if oi > 0:
        feat["lev_funds_net_index"] = np.clip((lev_net / oi * 100) + 50, 0, 100)
    else:
        feat["lev_funds_net_index"] = 50.0

    # asset_mgr_net_direction: sign of 4w change in asset_mgr_net
    # Approximate from TFF: if asset_mgr_net > 0 → institutional long trend (positive)
    asset_net = _safe(tff_entry.get("asset_mgr_net"), 0.0)
    feat["asset_mgr_net_direction"] = float(np.sign(asset_net))

    # dealer_net_contrarian: dealer_net normalized; extreme negative = market crowded long
    dealer_net = _safe(tff_entry.get("dealer_net"), 0.0)
    if oi > 0:
        feat["dealer_net_contrarian"] = np.clip(dealer_net / oi * 100, -100, 100)
    else:
        feat["dealer_net_contrarian"] = 0.0

    # lev_vs_assetmgr_divergence: pre-computed in fetch_cot
    feat["lev_vs_assetmgr_divergence"] = _safe(tff_entry.get("lev_vs_assetmgr_divergence"), 0.0)

    # ---- Group C — Macro -----------------------------------------------

    rates = {r["currency"]: r for r in macro_data.get("policy_rates", [])}
    cpis  = {r["currency"]: r for r in macro_data.get("cpi_yoy", [])}

    rate_entry = rates.get(currency, {})
    cpi_entry  = cpis.get(currency, {})
    usd_rate   = rates.get("USD", {})

    # rate_diff_vs_usd
    feat["rate_diff_vs_usd"] = _safe(rate_entry.get("diff_vs_usd"), 0.0)

    # rate_diff_trend_3m: trend_3m string → numeric
    feat["rate_diff_trend_3m"] = _trend_to_numeric(rate_entry.get("trend_3m", "STABLE"))

    # rate_hike_expectation: proxy from rate trend direction (not futures-based)
    feat["rate_hike_expectation"] = _trend_to_numeric(rate_entry.get("trend_3m", "STABLE"))

    # cpi_diff_vs_usd
    feat["cpi_diff_vs_usd"] = _safe(cpi_entry.get("diff_vs_usd"), 0.0)

    # cpi_trend
    feat["cpi_trend"] = _trend_to_numeric(cpi_entry.get("trend_3m", "STABLE"))

    # pmi_composite_diff — not available in current data sources
    feat["pmi_composite_diff"] = 0.0

    # yield_10y_diff — map via YIELD_DIFF_MAP
    yield_key = YIELD_DIFF_MAP.get(currency)
    if yield_key:
        yield_diffs = {
            r["pair"]: r for r in cross_asset.get("yield_differentials", [])
        }
        yd_entry = yield_diffs.get(yield_key, {})
        # "US-DE" means US yield − DE yield; for EUR we want DE − US = negative
        raw_spread = _safe(yd_entry.get("spread"), 0.0)
        feat["yield_10y_diff"] = -raw_spread  # invert: local − US
    else:
        feat["yield_10y_diff"] = 0.0

    # vix_regime
    vix_info = macro_data.get("vix", {})
    feat["vix_regime"] = float(_vix_regime_numeric(vix_info.get("regime", "NORMAL")))

    # ---- Group D — Cross-asset & Seasonal ------------------------------

    commodities = cross_asset.get("commodities", {})

    # gold_cot_index
    feat["gold_cot_index"] = _safe(commodities.get("gold", {}).get("cot_index"), 50.0)

    # oil_cot_direction: trend_direction → numeric
    oil_trend = commodities.get("oil", {}).get("trend_direction", "STABLE")
    feat["oil_cot_direction"] = _trend_to_numeric(oil_trend)

    # month, quarter
    feat["month"] = float(now.month)
    feat["quarter"] = float((now.month - 1) // 3 + 1)

    return feat


def compute_rank_in_8(features_by_currency: dict) -> dict:
    """Compute rank_in_8 (1=strongest, 8=weakest) for all currencies."""
    sorted_currencies = sorted(
        features_by_currency.keys(),
        key=lambda c: features_by_currency[c]["cot_index"],
        reverse=True,
    )
    return {cur: float(rank + 1) for rank, cur in enumerate(sorted_currencies)}


# ---------------------------------------------------------------------------
# B4-01b — Feature version check
# ---------------------------------------------------------------------------

def check_feature_version() -> tuple[bool, str]:
    """
    Compare feature_metadata.json version against EXPECTED_FEATURE_VERSION.
    Returns (mismatch: bool, actual_version: str).
    """
    if not FEATURE_META_FILE.exists():
        logger.warning("feature_metadata.json not found — skipping version check")
        return False, EXPECTED_FEATURE_VERSION

    with open(FEATURE_META_FILE) as f:
        meta = json.load(f)

    actual = meta.get("version", "unknown")
    mismatch = actual != EXPECTED_FEATURE_VERSION
    if mismatch:
        logger.warning(
            f"FEATURE_VERSION_MISMATCH: model expects '{EXPECTED_FEATURE_VERSION}', "
            f"feature_metadata has '{actual}'"
        )
    return mismatch, actual


# ---------------------------------------------------------------------------
# B4-01c/d — Pair selection + correlation filter
# ---------------------------------------------------------------------------

def classify_confidence(max_prob: float) -> str:
    if max_prob >= CONF_HIGH:
        return "HIGH"
    elif max_prob >= CONF_MEDIUM:
        return "MEDIUM"
    return "LOW"


def _bias_score(bias: str, confidence: str) -> float:
    """Signed weighted score: BULL → positive, BEAR → negative, NEUTRAL → 0."""
    w = CONF_WEIGHT.get(confidence, 0.3)
    if bias == "BULL":
        return w
    elif bias == "BEAR":
        return -w
    return 0.0


def _correlation(c1: str, c2: str) -> float:
    key1 = (c1, c2)
    key2 = (c2, c1)
    return CURRENCY_CORRELATION.get(key1, CURRENCY_CORRELATION.get(key2, 0.0))


def select_pairs(predictions: list) -> dict:
    """
    RPD Section 6.3 pair selection Steps 1-7.

    Steps:
      1. Assign directional score to each currency
      2. Enumerate all currency pairs
      3. Compute spread = base_score − quote_score
      4. Filter: spread > 0 → LONG candidate, < 0 → SHORT candidate
      5. Correlation filter: skip pairs where |r| > threshold (B4-01d)
      6. Sort by |spread| descending
      7. Cap recommendations: top 3 LONG, top 3 SHORT, flag NEUTRAL pairs as AVOID

    Returns: {strong_long: [...], strong_short: [...], avoid: [...]}
    """
    pred_map = {p["currency"]: p for p in predictions}

    # Step 1 — directional scores
    scores = {
        cur: _bias_score(p["bias"], p["confidence"])
        for cur, p in pred_map.items()
    }

    currencies = [p["currency"] for p in predictions]

    long_pairs  = []
    short_pairs = []
    avoid_pairs = []

    seen_currencies_long  = set()
    seen_currencies_short = set()

    # Step 2-4 — enumerate pairs
    for i, base in enumerate(currencies):
        for j, quote in enumerate(currencies):
            if base == quote:
                continue

            spread = scores[base] - scores[quote]

            # Step 5 — Correlation filter (B4-01d)
            corr = _correlation(base, quote)
            if corr >= CORRELATION_FILTER_THRESHOLD:
                continue  # too correlated, skip

            # Skip USD as base (we trade currency vs USD, not USD vs currency)
            if base == "USD":
                continue

            pair_label = f"{base}/{quote}"
            base_bias  = pred_map[base]["bias"]
            quote_bias = pred_map[quote].get("bias")
            pair_conf  = "LOW"
            if pred_map[base]["confidence"] == "HIGH" and pred_map[quote]["confidence"] in ("HIGH", "MEDIUM"):
                pair_conf = "HIGH"
            elif pred_map[base]["confidence"] in ("HIGH", "MEDIUM"):
                pair_conf = "MEDIUM"

            rec = {
                "pair": pair_label,
                "spread": round(float(spread), 4),
                "base_currency": base,
                "quote_currency": quote,
                "confidence": pair_conf,
            }

            # Avoid NEUTRAL on both sides
            if base_bias == "NEUTRAL" and quote_bias == "NEUTRAL":
                avoid_pairs.append(rec)
                continue

            if spread > 0.3:
                long_pairs.append(rec)
            elif spread < -0.3:
                short_pairs.append(rec)

    # Step 6 — Sort by |spread|
    long_pairs.sort(key=lambda x: -abs(x["spread"]))
    short_pairs.sort(key=lambda x: -abs(x["spread"]))
    avoid_pairs.sort(key=lambda x: abs(x["spread"]))

    # Step 7 — De-duplicate: don't recommend same base twice in long
    def dedupe(pairs: list, max_results: int = 3) -> list:
        seen = set()
        out = []
        for p in pairs:
            key = (p["base_currency"], p["quote_currency"])
            if key[0] not in seen and len(out) < max_results:
                seen.add(key[0])
                out.append(p)
        return out

    return {
        "strong_long":  dedupe(long_pairs),
        "strong_short": dedupe(short_pairs),
        "avoid":        avoid_pairs[:3],
    }


# ---------------------------------------------------------------------------
# Key drivers — top 3 feature names driving the prediction
# ---------------------------------------------------------------------------

def identify_key_drivers(feat: dict, bias: str) -> list[str]:
    """
    Simple heuristic: pick top 3 features with highest absolute value,
    filtered to those coherent with the predicted bias direction.
    """
    driver_map = {
        "cot_index": "COT positioning",
        "cot_index_4w_change": "COT 4w momentum",
        "net_pct_change_1w": "Net position change",
        "momentum_acceleration": "Momentum acceleration",
        "spread_vs_usd": "Spread vs USD",
        "lev_funds_net_index": "Leveraged funds",
        "asset_mgr_net_direction": "Asset manager flow",
        "dealer_net_contrarian": "Dealer contrarian",
        "rate_diff_vs_usd": "Rate differential",
        "rate_diff_trend_3m": "Rate trend",
        "cpi_diff_vs_usd": "CPI differential",
        "vix_regime": "VIX regime",
        "gold_cot_index": "Gold COT",
        "oil_cot_direction": "Oil direction",
    }

    scored = []
    for col, label in driver_map.items():
        val = feat.get(col, 0.0)
        if val != 0.0:
            scored.append((label, abs(val)))

    scored.sort(key=lambda x: -x[1])
    return [label for label, _ in scored[:3]]


# ---------------------------------------------------------------------------
# Data source status check
# ---------------------------------------------------------------------------

def check_data_sources(cot_data: dict, macro_data: dict) -> dict:
    """Check freshness of each data source — returns status dict."""
    import datetime as dt

    today = dt.date.today()

    def _freshness(date_str: str, max_days: int) -> str:
        try:
            d = dt.date.fromisoformat(date_str)
            delta = (today - d).days
            return "OK" if delta <= max_days else "STALE"
        except Exception:
            return "FAILED"

    cot_date  = cot_data.get("publishDate", "")
    macro_date = macro_data.get("fetchDate", "")

    return {
        "cot":        _freshness(cot_date, 10),
        "macro":      _freshness(macro_date, 40),
        "cross_asset": "OK",  # cross-asset is fetched with macro
        "calendar":   "OK" if CALENDAR_FILE.exists() else "FALLBACK",
    }


# ---------------------------------------------------------------------------
# B4-01f — Schema validation
# ---------------------------------------------------------------------------

def validate_schema(report: dict) -> bool:
    """Validate BiasReport against bias-report.schema.json."""
    try:
        import jsonschema
        if not SCHEMA_FILE.exists():
            logger.warning("Schema file not found — skipping validation")
            return True
        with open(SCHEMA_FILE) as f:
            schema = json.load(f)
        jsonschema.validate(instance=report, schema=schema)
        logger.info("Schema validation: PASSED")
        return True
    except ImportError:
        logger.warning("jsonschema not installed — skipping validation")
        return True
    except Exception as exc:
        logger.error(f"Schema validation FAILED: {exc}")
        return False


# ---------------------------------------------------------------------------
# B4-01g/h — Output writers
# ---------------------------------------------------------------------------

def week_label(now: datetime) -> str:
    """Format ISO week label, e.g. '2026-W12'."""
    iso = now.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def write_bias_latest(report: dict) -> None:
    """B4-01g: write compact JSON (no indent) to data/bias-latest.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(BIAS_LATEST_FILE, "w") as f:
        json.dump(report, f, separators=(",", ":"))
    logger.info(f"Written: {BIAS_LATEST_FILE}")


def append_bias_history(report: dict, now: datetime) -> None:
    """B4-01h: write to data/history/bias/YYYY-WNN.json."""
    iso = now.isocalendar()
    filename = f"{iso[0]}-W{iso[1]:02d}.json"
    HISTORY_BIAS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = HISTORY_BIAS_DIR / filename
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"History appended: {out_path}")


# ---------------------------------------------------------------------------
# Main pipeline — B4-01a
# ---------------------------------------------------------------------------

def main(use_fallback: bool = False) -> int:
    t_start = time.time()
    now = datetime.now(tz=timezone.utc)

    logger.info("=" * 60)
    logger.info("Phase B4-01: predict_bias.py")
    logger.info(f"  Timestamp : {now.isoformat()}")
    logger.info(f"  Week      : {week_label(now)}")
    logger.info(f"  Fallback  : {use_fallback}")
    logger.info("=" * 60)

    alerts = []  # accumulated alerts for weekly_alerts field

    # --- B4-01b: Feature version check -----------------------------------
    version_mismatch, feature_ver = check_feature_version()
    if version_mismatch:
        alerts.append({
            "type": "FEATURE_VERSION_MISMATCH",
            "message": (
                f"Model expects '{EXPECTED_FEATURE_VERSION}', "
                f"feature_metadata has '{feature_ver}'"
            ),
            "severity": "HIGH",
        })

    # --- Load model ------------------------------------------------------
    try:
        predictor = load_model(use_fallback=use_fallback)
        logger.info(f"Model loaded: {predictor.model_type} | classes: {list(predictor.classes_)}")
    except FileNotFoundError as exc:
        logger.error(f"Model not found: {exc}")
        return EXIT_FAILED

    # --- Load data sources -----------------------------------------------
    for path, label in [(COT_FILE, "COT"), (MACRO_FILE, "macro")]:
        if not path.exists():
            logger.error(f"{label} data not found: {path}")
            return EXIT_FAILED

    with open(COT_FILE)        as f: cot_data    = json.load(f)
    with open(MACRO_FILE)      as f: macro_data  = json.load(f)

    cross_asset = {}
    if CROSS_ASSET_FILE.exists():
        with open(CROSS_ASSET_FILE) as f: cross_asset = json.load(f)
    else:
        logger.warning("cross-asset-latest.json not found — cross-asset features will be 0")

    # --- Data source status check ----------------------------------------
    data_status = check_data_sources(cot_data, macro_data)
    for src, status in data_status.items():
        if status == "STALE":
            alerts.append({
                "type": "DATA_SOURCE_STALE",
                "message": f"{src} data is stale (>threshold days old)",
                "severity": "MEDIUM",
                "context": {"source": src},
            })
        elif status == "FAILED":
            alerts.append({
                "type": "MISSING_DATA",
                "message": f"{src} data failed to load",
                "severity": "HIGH",
                "context": {"source": src},
            })

    # --- VIX RISK_OFF alert ----------------------------------------------
    vix_val = macro_data.get("vix", {}).get("value", 0.0)
    if vix_val and float(vix_val) > 25:
        alerts.append({
            "type": "RISK_OFF_REGIME",
            "message": f"VIX elevated at {vix_val:.1f} — risk-off regime active",
            "severity": "HIGH",
            "context": {"vix": vix_val},
        })

    # --- USD COT index ---------------------------------------------------
    usd_cot_entry = cot_data.get("cot_indices", {}).get("USD", {})
    usd_cot_index = _safe(usd_cot_entry.get("index"), 50.0)

    # Collect all cot_indices for ranking
    all_cot_indices = cot_data.get("cot_indices", {})

    # --- Build features for all currencies --------------------------------
    # LabelEncoder order must match training (alphabetical: AUD, CAD, CHF, EUR, GBP, JPY, NZD, USD)
    import numpy as np
    from sklearn.preprocessing import LabelEncoder

    currency_encoder = LabelEncoder()
    currency_encoder.fit(sorted(CURRENCIES))

    features_by_currency = {}
    for cur in CURRENCIES:
        feat = build_feature_vector(
            currency=cur,
            cot_data=cot_data,
            macro_data=macro_data,
            cross_asset=cross_asset,
            usd_cot_index=usd_cot_index,
            all_cot_indices=all_cot_indices,
            now=now,
        )
        features_by_currency[cur] = feat

    # Fill in rank_in_8 after all currencies built
    ranks = compute_rank_in_8(features_by_currency)
    for cur in CURRENCIES:
        features_by_currency[cur]["rank_in_8"] = ranks[cur]

    # --- Assemble X matrix -----------------------------------------------
    currency_order = sorted(CURRENCIES)  # must match training encoder fit order
    X_rows = []
    for cur in currency_order:
        feat = features_by_currency[cur]
        row = [feat.get(col, 0.0) for col in FEATURE_COLS]
        row.append(float(currency_encoder.transform([cur])[0]))  # currency_enc
        X_rows.append(row)

    X = np.array(X_rows, dtype=np.float32)
    X = np.nan_to_num(X, nan=0.0)

    # --- B4-01a: Inference -----------------------------------------------
    labels   = predictor.predict(X)
    proba_mx = predictor.predict_proba(X)
    classes  = list(predictor.classes_)

    logger.info("Predictions:")
    for i, cur in enumerate(currency_order):
        logger.info(
            f"  {cur}: {labels[i]}  "
            f"proba={dict(zip(classes, [f'{p:.3f}' for p in proba_mx[i]]))}"
        )

    # --- B4-01e: Assemble predictions list --------------------------------
    # Map class names to probability dict
    def _proba_dict(row: np.ndarray) -> dict:
        d = {c.lower(): round(float(p), 4) for c, p in zip(classes, row)}
        # Ensure all three keys exist
        return {
            "bull":    d.get("bull", 0.0),
            "neutral": d.get("neutral", 0.0),
            "bear":    d.get("bear", 0.0),
        }

    predictions = []
    overall_confidence_scores = []

    for i, cur in enumerate(currency_order):
        feat     = features_by_currency[cur]
        bias     = labels[i]
        proba    = proba_mx[i]
        max_prob = float(proba.max())
        confidence = classify_confidence(max_prob)
        overall_confidence_scores.append(max_prob)

        # Per-currency alerts
        cur_alerts = []
        if feat.get("extreme_flag", 0) == 1.0:
            cur_alerts.append("EXTREME_POSITIONING")
            alerts.append({
                "type": "EXTREME_POSITIONING",
                "currency": cur,
                "message": f"{cur} COT index in extreme zone ({feat['cot_index']:.1f})",
                "severity": "MEDIUM",
                "context": {"cot_index": feat["cot_index"]},
            })
        if feat.get("flip_flag", 0) == 1.0:
            cur_alerts.append("FLIP_DETECTED")
            alerts.append({
                "type": "FLIP_DETECTED",
                "currency": cur,
                "message": f"{cur} net position flipped direction this week",
                "severity": "MEDIUM",
            })
        if max_prob < 0.50:
            cur_alerts.append("LOW_CONFIDENCE")

        key_drivers = identify_key_drivers(feat, bias)

        # Rank based on cot_index descending (1=strongest bull)
        rank = int(ranks[cur])

        predictions.append({
            "currency": cur,
            "bias": bias,
            "probability": _proba_dict(proba),
            "confidence": confidence,
            "rank": rank,
            "key_drivers": key_drivers,
            "alerts": cur_alerts,
        })

    # Sort predictions by rank
    predictions.sort(key=lambda x: x["rank"])

    # Overall confidence
    mean_max_prob = float(np.mean(overall_confidence_scores))
    overall_conf = classify_confidence(mean_max_prob)

    # LOW_CONFIDENCE pipeline alert if mean_max < 0.50
    if mean_max_prob < 0.50:
        alerts.append({
            "type": "LOW_CONFIDENCE",
            "message": f"Mean model confidence {mean_max_prob:.3f} below 50% threshold",
            "severity": "HIGH",
        })

    # --- B4-01c/d: Pair selection -----------------------------------------
    pair_recommendations = select_pairs(predictions)

    # --- B4-01e: Assemble BiasReport ----------------------------------------
    runtime = round(time.time() - t_start, 2)
    report = {
        "meta": {
            "weekLabel":        week_label(now),
            "generatedAt":      now.isoformat(),
            "modelVersion":     MODEL_VERSION,
            "featureVersion":   feature_ver,
            "overallConfidence": overall_conf,
            "dataSourceStatus": data_status,
            "pipelineRuntime":  runtime,
        },
        "predictions":         predictions,
        "pair_recommendations": pair_recommendations,
        "weekly_alerts":       alerts,
    }

    # --- B4-01f: Validate schema ------------------------------------------
    valid = validate_schema(report)
    if not valid:
        logger.warning("Schema validation failed — writing output anyway (check logs)")

    # --- B4-01g: Write bias-latest.json (compact) -------------------------
    write_bias_latest(report)

    # --- B4-01h: Append history ------------------------------------------
    append_bias_history(report, now)

    # --- Summary ----------------------------------------------------------
    logger.info("=" * 60)
    logger.info("B4-01 COMPLETE")
    logger.info(f"  Week         : {report['meta']['weekLabel']}")
    logger.info(f"  Confidence   : {overall_conf}  (mean_max_prob={mean_max_prob:.3f})")
    logger.info(f"  Alerts       : {len(alerts)}")
    logger.info(f"  Long recs    : {[r['pair'] for r in pair_recommendations['strong_long']]}")
    logger.info(f"  Short recs   : {[r['pair'] for r in pair_recommendations['strong_short']]}")
    logger.info(f"  Runtime      : {runtime}s")
    logger.info("  Next: B4-02 generate_alerts.py")
    logger.info("=" * 60)

    return EXIT_SUCCESS


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FX Bias AI inference pipeline")
    parser.add_argument(
        "--fallback",
        action="store_true",
        help="Use Logistic Regression fallback model instead of primary RF",
    )
    args = parser.parse_args()
    sys.exit(main(use_fallback=args.fallback))
