#!/usr/bin/env python3
"""
B4-02 — generate_alerts.py

Generate all pipeline alerts from live data and model state.

13 alert conditions (schema-compliant AlertType):
  🔴 B4-02a  EXTREME_POSITIONING   — COT Index < 10 or > 90
  🔴 B4-02b  FLIP_DETECTED         — flip_flag == 1 this week
  🔴 B4-02c  MODEL_DRIFT           — rolling 4w accuracy < baseline − 5%
  🔴 B4-02d  MISSING_DATA          — data source fetch failed
  🔴 B4-02e  RISK_OFF_REGIME       — VIX > 25
  🔴 B4-02f  DATA_SOURCE_STALE     — freshness_days > 14
  🔴 B4-02g  FEATURE_VERSION_MISMATCH — version mismatch
  🔴 B4-02h  LOW_CONFIDENCE        — max model probability < 0.50
  🔴 B4-02i  MACRO_COT_CONFLICT    — COT bias contradicts macro direction
  🟡 B4-02j  MOMENTUM_DECEL        — momentum_acceleration negative 3 weeks
  🟡 B4-02k  OI_DIVERGENCE         — net and OI diverge direction
  🟡 B4-02l  CALENDAR_SOURCE_FALLBACK — using static calendar file
  🟡 B4-02m  MODEL_ROLLBACK        — model was rolled back this cycle

Output: data/alerts-pending.json (appends to existing, deduped by type+currency)
Exit codes: 0=success, 1=partial, 2=failed
"""

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.utils.file_io import EXIT_FAILED, EXIT_SUCCESS, setup_logging

logger = setup_logging(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR          = _REPO_ROOT / "data"
COT_FILE          = DATA_DIR / "cot-latest.json"
MACRO_FILE        = DATA_DIR / "macro-latest.json"
CROSS_ASSET_FILE  = DATA_DIR / "cross-asset-latest.json"
CALENDAR_FILE     = DATA_DIR / "calendar-latest.json"
BIAS_LATEST_FILE  = DATA_DIR / "bias-latest.json"
ALERTS_FILE       = DATA_DIR / "alerts-pending.json"
HISTORY_BIAS_DIR  = DATA_DIR / "history" / "bias"
METRICS_DIR       = DATA_DIR / "history" / "model-metrics"
FEATURE_META_FILE = _REPO_ROOT / "models" / "feature_metadata.json"
ROLLBACK_LOG_DIR  = METRICS_DIR  # rollback_YYYY-WNN.json files live here

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CURRENCIES = ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "USD"]
EXPECTED_FEATURE_VERSION = "v2.1-28f"

EXTREME_THRESH_LOW  = 10.0   # B4-02a
EXTREME_THRESH_HIGH = 90.0
VIX_RISK_OFF_THRESH = 25.0   # B4-02e
STALE_DAYS_THRESH   = 14     # B4-02f
LOW_CONF_THRESH     = 0.50   # B4-02h
MODEL_DRIFT_MARGIN  = 0.05   # B4-02c: baseline − 5%

# ---------------------------------------------------------------------------
# Alert builder helper
# ---------------------------------------------------------------------------

def _alert(
    alert_type: str,
    message: str,
    severity: str,
    currency: str = None,
    context: dict = None,
) -> dict:
    a = {"type": alert_type, "message": message, "severity": severity}
    if currency:
        a["currency"] = currency
    if context:
        a["context"] = context
    return a


# ---------------------------------------------------------------------------
# B4-02a — EXTREME_POSITIONING
# ---------------------------------------------------------------------------

def check_extreme_positioning(cot_data: dict) -> list:
    """COT Index < 10 or > 90 for any currency."""
    alerts = []
    for entry in cot_data.get("legacy", []):
        cur   = entry.get("currency", "?")
        idx   = float(entry.get("cot_index_52w", 50.0))
        if idx < EXTREME_THRESH_LOW or idx > EXTREME_THRESH_HIGH:
            direction = "oversold" if idx < EXTREME_THRESH_LOW else "overbought"
            alerts.append(_alert(
                "EXTREME_POSITIONING",
                f"{cur} COT Index at extreme {direction} level ({idx:.1f})",
                "MEDIUM",
                currency=cur,
                context={"cot_index": idx, "direction": direction},
            ))
    return alerts


# ---------------------------------------------------------------------------
# B4-02b — FLIP_DETECTED
# ---------------------------------------------------------------------------

def check_flip_detected(cot_data: dict) -> list:
    """Net position flipped sign this week (flip_flag == True)."""
    alerts = []
    for entry in cot_data.get("legacy", []):
        cur = entry.get("currency", "?")
        if entry.get("flip_flag") is True:
            net     = entry.get("net", 0)
            delta   = entry.get("net_delta_1w", 0)
            prev    = net - delta
            direction = "long → short" if net < 0 else "short → long"
            alerts.append(_alert(
                "FLIP_DETECTED",
                f"{cur} net position flipped ({direction}): prev={prev:+,} → now={net:+,}",
                "MEDIUM",
                currency=cur,
                context={"net_now": net, "net_prev": prev, "direction": direction},
            ))
    return alerts


# ---------------------------------------------------------------------------
# B4-02c — MODEL_DRIFT
# ---------------------------------------------------------------------------

def check_model_drift(metrics_dir: Path = METRICS_DIR) -> list:
    """
    Rolling 4-week accuracy < baseline − 5%.

    Primary path: reads weekly_accuracy.json (live accuracy from B5-01a).
    Fallback: reads validation_results.json (training folds).
    If no rolling accuracy is available, skips (returns []).
    """
    alerts = []

    try:
        # --- Primary: weekly_accuracy.json (live rolling accuracy) ---
        acc_file = metrics_dir / "weekly_accuracy.json"
        if acc_file.exists():
            with open(acc_file) as f:
                acc_data = json.load(f)
            rolling_4w = acc_data.get("rolling_4w_accuracy")
            baseline_acc = acc_data.get("baseline_accuracy")
            if rolling_4w is not None and baseline_acc and baseline_acc > 0:
                drift = baseline_acc - rolling_4w
                if drift > MODEL_DRIFT_MARGIN:
                    rolling_weeks = acc_data.get("rolling_4w_weeks", [])
                    alerts.append(_alert(
                        "MODEL_DRIFT",
                        (
                            f"Model accuracy drifted (live): baseline={baseline_acc:.3f}, "
                            f"rolling_4w={rolling_4w:.3f}, drift={drift:.3f} > {MODEL_DRIFT_MARGIN:.2f}"
                        ),
                        "HIGH",
                        context={
                            "baseline_accuracy": round(baseline_acc, 4),
                            "recent_accuracy": round(rolling_4w, 4),
                            "drift": round(float(drift), 4),
                            "threshold": MODEL_DRIFT_MARGIN,
                            "source": "weekly_accuracy",
                            "rolling_weeks": rolling_weeks,
                        },
                    ))
                return alerts  # primary path handled — skip fallback

        # --- Fallback: validation_results.json (training folds) ---
        baseline_file = metrics_dir / "initial_training.json"
        if not baseline_file.exists():
            return []
        with open(baseline_file) as f:
            training = json.load(f)
        baseline_acc = training.get("walk_forward_summary", {}).get("mean_accuracy", 0.0)
        if baseline_acc <= 0:
            return []

        val_file = metrics_dir / "validation_results.json"
        if not val_file.exists():
            return []
        with open(val_file) as f:
            val = json.load(f)

        # Compare: if mean RF walk-forward accuracy dropped >5% vs baseline
        rf_accs = [f.get("rf", baseline_acc) for f in val.get("folds", {}).values()]
        if not rf_accs:
            return []

        import statistics
        mean_recent = statistics.mean(rf_accs[-2:])  # last 2 folds = most recent
        drift = baseline_acc - mean_recent
        if drift > MODEL_DRIFT_MARGIN:
            alerts.append(_alert(
                "MODEL_DRIFT",
                (
                    f"Model accuracy drifted: baseline={baseline_acc:.3f}, "
                    f"recent={mean_recent:.3f}, drift={drift:.3f} > {MODEL_DRIFT_MARGIN:.2f}"
                ),
                "HIGH",
                context={
                    "baseline_accuracy": round(baseline_acc, 4),
                    "recent_accuracy": round(mean_recent, 4),
                    "drift": round(float(drift), 4),
                    "threshold": MODEL_DRIFT_MARGIN,
                    "source": "validation_results",
                },
            ))
    except Exception as exc:
        logger.warning(f"MODEL_DRIFT check error (non-fatal): {exc}")

    return alerts


# ---------------------------------------------------------------------------
# B4-02d — MISSING_DATA
# ---------------------------------------------------------------------------

def check_missing_data(
    cot_data: dict = None,
    macro_data: dict = None,
) -> list:
    """
    Tier-1 data sources failed or are empty.
    Called with None when the file could not be loaded.
    """
    alerts = []

    if cot_data is None:
        alerts.append(_alert(
            "MISSING_DATA",
            "COT data failed to load (cot-latest.json missing or invalid)",
            "HIGH",
            context={"source": "cot"},
        ))
    elif not cot_data.get("legacy"):
        alerts.append(_alert(
            "MISSING_DATA",
            "COT legacy data is empty — CFTC fetch may have failed",
            "HIGH",
            context={"source": "cot_legacy"},
        ))

    if macro_data is None:
        alerts.append(_alert(
            "MISSING_DATA",
            "Macro data failed to load (macro-latest.json missing or invalid)",
            "HIGH",
            context={"source": "macro"},
        ))
    elif not macro_data.get("policy_rates"):
        alerts.append(_alert(
            "MISSING_DATA",
            "Macro policy rates are empty — FRED fetch may have failed",
            "HIGH",
            context={"source": "macro_rates"},
        ))

    return alerts


# ---------------------------------------------------------------------------
# B4-02e — RISK_OFF_REGIME
# ---------------------------------------------------------------------------

def check_risk_off_regime(macro_data: dict) -> list:
    """VIX > 25 → risk-off alert."""
    alerts = []
    vix = macro_data.get("vix", {})
    val = float(vix.get("value", 0) or 0)
    if val > VIX_RISK_OFF_THRESH:
        regime = vix.get("regime", "ELEVATED")
        alerts.append(_alert(
            "RISK_OFF_REGIME",
            f"VIX at {val:.2f} ({regime}) — risk-off regime active, all FX signals unreliable",
            "HIGH",
            context={"vix": val, "regime": regime},
        ))
    return alerts


# ---------------------------------------------------------------------------
# B4-02f — DATA_SOURCE_STALE
# ---------------------------------------------------------------------------

def check_data_source_stale(macro_data: dict) -> list:
    """
    Any macro series with freshness_days > 14.
    Checks both policy_rates and cpi_yoy lists.
    """
    alerts = []
    today = date.today()

    def _days_since(date_str: str) -> int:
        try:
            return (today - date.fromisoformat(date_str)).days
        except Exception:
            return 0

    for series_key in ("policy_rates", "cpi_yoy"):
        for entry in macro_data.get(series_key, []):
            cur = entry.get("currency", "?")
            last_update = entry.get("last_update", "")
            if not last_update:
                continue
            days = _days_since(last_update)
            if days > STALE_DAYS_THRESH:
                alerts.append(_alert(
                    "DATA_SOURCE_STALE",
                    (
                        f"{cur} {series_key} is stale: "
                        f"last_update={last_update} ({days} days ago)"
                    ),
                    "MEDIUM",
                    currency=cur,
                    context={"source": series_key, "last_update": last_update, "days": days},
                ))
    return alerts


# ---------------------------------------------------------------------------
# B4-02g — FEATURE_VERSION_MISMATCH
# ---------------------------------------------------------------------------

def check_feature_version_mismatch() -> list:
    """Compare feature_metadata.json version vs expected."""
    if not FEATURE_META_FILE.exists():
        return []
    try:
        with open(FEATURE_META_FILE) as f:
            meta = json.load(f)
        actual = meta.get("version", "unknown")
        if actual != EXPECTED_FEATURE_VERSION:
            return [_alert(
                "FEATURE_VERSION_MISMATCH",
                (
                    f"Model expects feature version '{EXPECTED_FEATURE_VERSION}', "
                    f"but feature_metadata.json reports '{actual}'"
                ),
                "HIGH",
                context={
                    "expected": EXPECTED_FEATURE_VERSION,
                    "actual": actual,
                },
            )]
    except Exception as exc:
        logger.warning(f"Feature version check failed: {exc}")
    return []


# ---------------------------------------------------------------------------
# B4-02h — LOW_CONFIDENCE
# ---------------------------------------------------------------------------

def check_low_confidence(bias_report: dict) -> list:
    """
    Per-currency: max_probability < 0.50.
    Pipeline-level: overall confidence is LOW.
    """
    alerts = []
    for pred in bias_report.get("predictions", []):
        cur   = pred.get("currency", "?")
        proba = pred.get("probability", {})
        max_p = max(proba.get("bull", 0), proba.get("bear", 0), proba.get("neutral", 0))
        if max_p < LOW_CONF_THRESH:
            alerts.append(_alert(
                "LOW_CONFIDENCE",
                f"{cur} max probability {max_p:.3f} < {LOW_CONF_THRESH} — prediction unreliable",
                "LOW",
                currency=cur,
                context={"max_probability": round(max_p, 4)},
            ))

    overall = bias_report.get("meta", {}).get("overallConfidence", "")
    if overall == "LOW":
        alerts.append(_alert(
            "LOW_CONFIDENCE",
            f"Pipeline overall confidence is LOW — all signals below confidence threshold",
            "MEDIUM",
        ))

    return alerts


# ---------------------------------------------------------------------------
# B4-02i — MACRO_COT_CONFLICT
# ---------------------------------------------------------------------------

def check_macro_cot_conflict(cot_data: dict, macro_data: dict, bias_report: dict) -> list:
    """
    COT bias contradicts macro differential direction.

    Conflict: currency has BULL COT bias but negative rate_diff_vs_usd
              (or BEAR COT bias but positive rate_diff_vs_usd).
    Threshold: |rate_diff_vs_usd| > 1.0 to avoid noise.
    """
    alerts = []
    RATE_DIFF_THRESHOLD = 1.0

    rate_map = {r["currency"]: r for r in macro_data.get("policy_rates", [])}
    pred_map = {p["currency"]: p for p in bias_report.get("predictions", [])}

    for cur, pred in pred_map.items():
        bias = pred.get("bias", "NEUTRAL")
        if bias == "NEUTRAL":
            continue

        rate_entry = rate_map.get(cur, {})
        rate_diff  = float(rate_entry.get("diff_vs_usd", 0) or 0)

        # Only flag when rate differential is meaningful
        if abs(rate_diff) < RATE_DIFF_THRESHOLD:
            continue

        conflict = (
            (bias == "BULL" and rate_diff < 0) or
            (bias == "BEAR" and rate_diff > 0)
        )
        if conflict:
            alerts.append(_alert(
                "MACRO_COT_CONFLICT",
                (
                    f"{cur} COT signals {bias} but rate diff vs USD = {rate_diff:+.2f}% "
                    f"— macro and positioning conflict"
                ),
                "LOW",
                currency=cur,
                context={
                    "cot_bias": bias,
                    "rate_diff_vs_usd": rate_diff,
                },
            ))

    return alerts


# ---------------------------------------------------------------------------
# B4-02j — MOMENTUM_DECEL
# ---------------------------------------------------------------------------

def check_momentum_decel(cot_data: dict) -> list:
    """
    Momentum deceleration: momentum_acceleration negative for 3 consecutive weeks.
    Approximated from cot_indices.trend_12w (12-week COT index history).

    trend_12w[0] = current, [1] = 1w ago, [2] = 2w ago, etc.
    Weekly delta[i] = trend[i] − trend[i+1]
    Acceleration[i] = delta[i] − delta[i+1]
    Decel if acceleration[0], [1], [2] all < 0.
    """
    alerts = []
    cot_indices = cot_data.get("cot_indices", {})

    for cur, data in cot_indices.items():
        trend = data.get("trend_12w", [])
        if len(trend) < 5:
            continue

        # Compute 3 consecutive acceleration values
        deltas = [trend[i] - trend[i + 1] for i in range(len(trend) - 1)]
        accels = [deltas[i] - deltas[i + 1] for i in range(len(deltas) - 1)]

        if len(accels) >= 3 and all(a < 0 for a in accels[:3]):
            alerts.append(_alert(
                "MOMENTUM_DECEL",
                (
                    f"{cur} momentum decelerating for 3+ consecutive weeks "
                    f"(accels={[round(a,2) for a in accels[:3]]})"
                ),
                "LOW",
                currency=cur,
                context={
                    "acceleration_3w": [round(float(a), 2) for a in accels[:3]],
                    "trend_12w_current": round(float(trend[0]), 2),
                },
            ))

    return alerts


# ---------------------------------------------------------------------------
# B4-02k — OI_DIVERGENCE
# ---------------------------------------------------------------------------

def check_oi_divergence(cot_data: dict) -> list:
    """
    OI divergence: net position and open interest move in opposite directions.

    Uses net_delta_1w (net change) and compares sign vs OI change.
    NOTE: OI absolute change between weeks is not stored in current cot-latest.json.
    We infer direction from oi_delta if available, else skip gracefully.
    """
    alerts = []

    for entry in cot_data.get("legacy", []):
        cur       = entry.get("currency", "?")
        net_delta = float(entry.get("net_delta_1w", 0) or 0)

        # oi_delta_1w is not always present; skip if absent
        oi_delta = entry.get("oi_delta_1w", None)
        if oi_delta is None:
            continue  # not available in current data, skip

        oi_delta = float(oi_delta or 0)
        if net_delta == 0 or oi_delta == 0:
            continue

        # Divergence: net and OI move in opposite directions
        diverging = (net_delta > 0 and oi_delta < 0) or (net_delta < 0 and oi_delta > 0)
        if diverging:
            alerts.append(_alert(
                "OI_DIVERGENCE",
                (
                    f"{cur} net position and OI diverge: "
                    f"net_delta={net_delta:+,.0f}, oi_delta={oi_delta:+,.0f} — "
                    f"{'weakening bull' if net_delta > 0 else 'weakening bear'} signal"
                ),
                "LOW",
                currency=cur,
                context={"net_delta_1w": net_delta, "oi_delta_1w": oi_delta},
            ))

    return alerts


# ---------------------------------------------------------------------------
# B4-02l — CALENDAR_SOURCE_FALLBACK
# ---------------------------------------------------------------------------

def check_calendar_source_fallback(calendar_data: dict = None) -> list:
    """Calendar is using static fallback instead of live MQL5 data."""
    if calendar_data is None:
        return [_alert(
            "CALENDAR_SOURCE_FALLBACK",
            "calendar-latest.json not found — using empty calendar (no event data)",
            "LOW",
            context={"reason": "file_missing"},
        )]

    source = calendar_data.get("source", "")
    if source and source.lower() not in ("mql5", "live", "api"):
        return [_alert(
            "CALENDAR_SOURCE_FALLBACK",
            f"Using static/fallback calendar (source='{source}') — live events unavailable",
            "LOW",
            context={"source": source},
        )]

    return []


# ---------------------------------------------------------------------------
# B4-02m — MODEL_ROLLBACK
# ---------------------------------------------------------------------------

def check_model_rollback(rollback_log_dir: Path = ROLLBACK_LOG_DIR) -> list:
    """
    MODEL_ROLLBACK alert: emitted if a rollback log exists from the current week.
    Rollback files are named rollback_YYYY-WNN.json.
    """
    alerts = []
    if not rollback_log_dir.exists():
        return []

    now = datetime.now(tz=timezone.utc)
    iso = now.isocalendar()
    current_week_file = rollback_log_dir / f"rollback_{iso[0]}-W{iso[1]:02d}.json"

    if current_week_file.exists():
        try:
            with open(current_week_file) as f:
                log = json.load(f)
            alerts.append(_alert(
                "MODEL_ROLLBACK",
                (
                    f"Model was rolled back this week: "
                    f"{log.get('reason', 'accuracy below threshold')}"
                ),
                "HIGH",
                context=log,
            ))
        except Exception:
            alerts.append(_alert(
                "MODEL_ROLLBACK",
                "Model rollback occurred this week (details unavailable)",
                "HIGH",
            ))

    return alerts


# ---------------------------------------------------------------------------
# Deduplicate + write alerts
# ---------------------------------------------------------------------------

def _dedup_alerts(alerts: list) -> list:
    """
    Remove duplicate alerts (same type + currency).
    First occurrence wins.
    """
    seen = set()
    out  = []
    for a in alerts:
        key = (a["type"], a.get("currency", ""))
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out


def write_alerts(alerts: list) -> None:
    """Write deduplicated alerts to data/alerts-pending.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ALERTS_FILE, "w") as f:
        json.dump(alerts, f, indent=2)
    logger.info(f"Alerts written: {ALERTS_FILE}  ({len(alerts)} alerts)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_all_alerts(
    cot_data: dict = None,
    macro_data: dict = None,
    bias_report: dict = None,
    calendar_data: dict = None,
) -> list:
    """
    Run all 13 alert checks.
    Accepts pre-loaded data dicts for testability.
    Returns flat list of alert dicts (schema-compliant).
    """
    alerts = []

    # Load data if not provided (production path)
    if cot_data is None and COT_FILE.exists():
        with open(COT_FILE) as f:
            cot_data = json.load(f)
    if macro_data is None and MACRO_FILE.exists():
        with open(MACRO_FILE) as f:
            macro_data = json.load(f)
    if bias_report is None and BIAS_LATEST_FILE.exists():
        with open(BIAS_LATEST_FILE) as f:
            bias_report = json.load(f)
    if calendar_data is None and CALENDAR_FILE.exists():
        with open(CALENDAR_FILE) as f:
            calendar_data = json.load(f)

    cot   = cot_data   or {}
    macro = macro_data or {}
    bias  = bias_report or {}
    cal   = calendar_data

    # --- Run all checks ---
    alerts += check_missing_data(cot_data, macro_data)           # B4-02d first
    alerts += check_extreme_positioning(cot)                      # B4-02a
    alerts += check_flip_detected(cot)                            # B4-02b
    alerts += check_model_drift()                                  # B4-02c
    alerts += check_risk_off_regime(macro)                        # B4-02e
    alerts += check_data_source_stale(macro)                      # B4-02f
    alerts += check_feature_version_mismatch()                    # B4-02g
    alerts += check_low_confidence(bias)                          # B4-02h
    alerts += check_macro_cot_conflict(cot, macro, bias)          # B4-02i
    alerts += check_momentum_decel(cot)                           # B4-02j
    alerts += check_oi_divergence(cot)                            # B4-02k
    alerts += check_calendar_source_fallback(cal)                  # B4-02l
    alerts += check_model_rollback()                               # B4-02m

    return _dedup_alerts(alerts)


def main() -> int:
    logger.info("=" * 60)
    logger.info("Phase B4-02: generate_alerts.py")
    logger.info("=" * 60)

    alerts = generate_all_alerts()

    logger.info(f"Total alerts generated: {len(alerts)}")
    for a in alerts:
        cur_tag = f" [{a['currency']}]" if a.get("currency") else ""
        logger.info(f"  {a['severity']:6s} {a['type']}{cur_tag}: {a['message'][:80]}")

    write_alerts(alerts)

    logger.info("B4-02 COMPLETE — Next: B4-03 rollback_model.py")
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
