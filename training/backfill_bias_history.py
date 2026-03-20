#!/usr/bin/env python3
"""
Backfill bias history — chạy model trên toàn bộ features_2006_2026.csv
và lưu mỗi tuần vào data/history/bias/YYYY-WNN.json.

Usage:
    python training/backfill_bias_history.py [--from-week 2024-W01] [--overwrite]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

_REPO_ROOT = Path(__file__).resolve().parent.parent

FEATURES_CSV   = _REPO_ROOT / "training" / "data" / "features_2006_2026.csv"
MODEL_PKL      = _REPO_ROOT / "models" / "model.pkl"
OUTPUT_DIR     = _REPO_ROOT / "data" / "history" / "bias"

FEATURE_COLS = [
    "cot_index", "cot_index_4w_change", "net_pct_change_1w",
    "momentum_acceleration", "oi_delta_direction", "oi_net_confluence",
    "flip_flag", "extreme_flag", "usd_index_cot", "rank_in_8",
    "spread_vs_usd", "weeks_since_flip",
    "dealer_net_contrarian", "lev_vs_assetmgr_divergence",
    "asset_mgr_net_direction", "lev_funds_net_index",
    "rate_diff_vs_usd", "rate_diff_trend_3m", "rate_hike_expectation",
    "cpi_diff_vs_usd", "cpi_trend", "pmi_composite_diff",
    "yield_10y_diff", "vix_regime",
    "gold_cot_index", "oil_cot_direction", "quarter",
]

# Feature importance ranking từ validate_model.py (top drivers theo global importance)
FEATURE_LABELS = {
    "net_pct_change_1w":        "Net position change",
    "oi_net_confluence":        "COT positioning",
    "momentum_acceleration":    "Momentum acceleration",
    "cot_index_4w_change":      "COT 4w momentum",
    "cot_index":                "COT index",
    "dealer_net_contrarian":    "Dealer contrarian",
    "usd_index_cot":            "USD COT index",
    "spread_vs_usd":            "Spread vs USD",
    "lev_vs_assetmgr_divergence": "Leveraged funds",
    "lev_funds_net_index":      "Lev funds net index",
    "rate_diff_vs_usd":         "Rate differential",
    "cpi_diff_vs_usd":          "CPI differential",
}

# Top-3 drivers theo thứ tự feature importance (global, fixed)
GLOBAL_TOP3_DRIVERS = ["Net position change", "COT positioning", "Momentum acceleration"]

CONF_HIGH   = 0.70
CONF_MEDIUM = 0.55


def week_label(dt: pd.Timestamp) -> str:
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def confidence_level(max_prob: float) -> str:
    if max_prob >= CONF_HIGH:
        return "HIGH"
    if max_prob >= CONF_MEDIUM:
        return "MEDIUM"
    return "LOW"


def build_weekly_alerts(week_df: pd.DataFrame) -> list:
    alerts = []
    seen = set()
    for _, row in week_df.iterrows():
        cur = row["currency"]
        cot_idx = float(row.get("cot_index", 50))
        flip = int(row.get("flip_flag", 0))

        if cot_idx < 10 or cot_idx > 90:
            key = ("EXTREME_POSITIONING", cur)
            if key not in seen:
                seen.add(key)
                direction = "oversold" if cot_idx < 10 else "overbought"
                alerts.append({
                    "type": "EXTREME_POSITIONING",
                    "currency": cur,
                    "message": f"{cur} COT index in extreme {direction} zone ({cot_idx:.1f})",
                    "severity": "MEDIUM",
                    "context": {"cot_index": round(cot_idx, 2)},
                })

        if flip == 1:
            key = ("FLIP_DETECTED", cur)
            if key not in seen:
                seen.add(key)
                alerts.append({
                    "type": "FLIP_DETECTED",
                    "currency": cur,
                    "message": f"{cur} net position flipped direction this week",
                    "severity": "MEDIUM",
                })
    return alerts


def build_prediction(currency: str, bias: str, proba: dict,
                     week_df: pd.DataFrame, rank: int) -> dict:
    max_prob = max(proba.values())
    conf = confidence_level(max_prob)

    # Alerts per currency
    cur_alerts = []
    row = week_df[week_df["currency"] == currency]
    if not row.empty:
        cot_idx = float(row.iloc[0].get("cot_index", 50))
        flip = int(row.iloc[0].get("flip_flag", 0))
        if cot_idx < 10 or cot_idx > 90:
            cur_alerts.append("EXTREME_POSITIONING")
        if flip == 1:
            cur_alerts.append("FLIP_DETECTED")

    return {
        "currency": currency,
        "bias": bias,
        "probability": {
            "bull":    round(proba.get("BULL", 0), 4),
            "neutral": round(proba.get("NEUTRAL", 0), 4),
            "bear":    round(proba.get("BEAR", 0), 4),
        },
        "confidence": conf,
        "rank": rank,
        "key_drivers": GLOBAL_TOP3_DRIVERS,
        "alerts": cur_alerts,
    }


def run_backfill(from_week: str = None, overwrite: bool = False) -> int:
    print(f"Loading model: {MODEL_PKL}")
    model = joblib.load(MODEL_PKL)

    print(f"Loading features: {FEATURES_CSV}")
    df = pd.read_csv(FEATURES_CSV, parse_dates=["date"])
    df = df.sort_values(["date", "currency"]).reset_index(drop=True)

    # Currency encoder — must match training
    currencies_in_data = sorted(df["currency"].unique())
    enc = LabelEncoder()
    enc.fit(currencies_in_data)
    print(f"Currencies: {currencies_in_data}")

    # Build week groups
    df["week_label"] = df["date"].apply(week_label)
    weeks = df["week_label"].unique()
    weeks = sorted(weeks)

    if from_week:
        weeks = [w for w in weeks if w >= from_week]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    skipped = 0
    written = 0
    errors = 0

    for wlabel in weeks:
        out_file = OUTPUT_DIR / f"{wlabel}.json"
        if out_file.exists() and not overwrite:
            skipped += 1
            continue

        week_df = df[df["week_label"] == wlabel].copy()
        date_ts = week_df["date"].iloc[0]

        # Prepare feature matrix
        week_df["currency_enc"] = enc.transform(week_df["currency"])
        all_feat_cols = FEATURE_COLS + ["currency_enc"]
        present = [c for c in all_feat_cols if c in week_df.columns]
        missing = [c for c in all_feat_cols if c not in week_df.columns]
        if missing:
            for c in missing:
                week_df[c] = 0.0

        X = week_df[all_feat_cols].values.astype(np.float32)
        X = np.nan_to_num(X, nan=0.0)

        try:
            probas = model.predict_proba(X)   # shape (n_currencies, 3)
            classes = list(model.classes_)
        except Exception as e:
            print(f"  ERROR {wlabel}: {e}")
            errors += 1
            continue

        # Build predictions sorted by max_prob descending
        preds = []
        for i, (_, row) in enumerate(week_df.iterrows()):
            cur = row["currency"]
            proba_dict = {cls: float(probas[i][j]) for j, cls in enumerate(classes)}
            bias = max(proba_dict, key=proba_dict.get)
            preds.append((cur, bias, proba_dict, float(max(proba_dict.values()))))

        preds.sort(key=lambda x: x[3], reverse=True)

        predictions = []
        for rank, (cur, bias, proba_dict, _) in enumerate(preds, start=1):
            predictions.append(build_prediction(cur, bias, proba_dict, week_df, rank))

        # Overall confidence
        mean_max_p = float(np.mean([max(p["probability"].values()) for p in predictions]))
        if mean_max_p >= CONF_HIGH:
            overall_conf = "HIGH"
        elif mean_max_p >= CONF_MEDIUM:
            overall_conf = "MEDIUM"
        else:
            overall_conf = "LOW"

        weekly_alerts = build_weekly_alerts(week_df)

        report = {
            "meta": {
                "weekLabel": wlabel,
                "generatedAt": datetime.now(tz=timezone.utc).isoformat(),
                "modelVersion": "rf-v2.1",
                "featureVersion": "v2.1-28f",
                "overallConfidence": overall_conf,
                "dataSourceStatus": {
                    "cot": "OK", "macro": "OK",
                    "cross_asset": "OK", "calendar": "N/A"
                },
                "source": "backfill",
            },
            "predictions": predictions,
            "pair_recommendations": {
                "strong_long": [], "strong_short": [], "avoid": []
            },
            "weekly_alerts": weekly_alerts,
        }

        with open(out_file, "w") as f:
            json.dump(report, f, indent=2)
        written += 1

        if written % 50 == 0 or written == 1:
            print(f"  [{written}] {wlabel} → {out_file.name}")

    print(f"\nDone. Written: {written}  Skipped: {skipped}  Errors: {errors}")
    return 0 if errors == 0 else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-week", default=None,
                        help="Start từ tuần này (vd: 2024-W01). Mặc định: toàn bộ lịch sử")
    parser.add_argument("--overwrite", action="store_true",
                        help="Ghi đè các file đã tồn tại")
    args = parser.parse_args()
    sys.exit(run_backfill(from_week=args.from_week, overwrite=args.overwrite))


if __name__ == "__main__":
    main()
