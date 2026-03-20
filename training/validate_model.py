#!/usr/bin/env python3
"""
B3-02 — validate_model.py

Baseline comparison, per-currency/confidence metrics, feature importance,
min_samples_leaf tuning, model card generation.

Also handles B3-03: Logistic Regression fallback training.

Walk-forward folds (same splits as train_model.py):
  Fold 1: train ≤ 2020-12-31, test 2021
  Fold 2: train ≤ 2021-12-31, test 2022
  Fold 3: train ≤ 2022-12-31, test 2023
  Fold 4: train ≤ 2023-12-31, test 2024

Gate: RF must beat COT-only baseline by ≥ +5% (B3-02b).

Outputs:
  models/model_card.md               — full validation report (B3-02d)
  models/validation_chart.png        — accuracy per fold chart (B3-02g)
  models/model_lr_fallback.pkl       — Logistic Regression fallback (B3-03)
  DECISIONS.md                       — min_samples_leaf tuning (B3-02e)
  data/history/model-metrics/validation_results.json
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.preprocessing import LabelEncoder, StandardScaler

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent

FEATURES_CSV = _REPO_ROOT / "training" / "data" / "features_2006_2026.csv"
MODELS_DIR = _REPO_ROOT / "models"
METRICS_DIR = _REPO_ROOT / "data" / "history" / "model-metrics"
MODEL_CARD_PATH = MODELS_DIR / "model_card.md"
CHART_PATH = MODELS_DIR / "validation_chart.png"
DECISIONS_PATH = _REPO_ROOT / "DECISIONS.md"
VALIDATION_JSON = METRICS_DIR / "validation_results.json"
LR_FALLBACK_PATH = MODELS_DIR / "model_lr_fallback.pkl"

# ---------------------------------------------------------------------------
# Constants — must match train_model.py
# ---------------------------------------------------------------------------

RF_PARAMS_BASE = {
    "n_estimators": 300,
    "max_depth": 8,
    "max_features": "sqrt",
    "class_weight": "balanced",
    "random_state": 42,
    "n_jobs": -1,
}

FOLDS = [
    ("2020-12-31", "2021-01-01", "2021-12-31", "Fold1_2021"),
    ("2021-12-31", "2022-01-01", "2022-12-31", "Fold2_2022"),
    ("2022-12-31", "2023-01-01", "2023-12-31", "Fold3_2023"),
    ("2023-12-31", "2024-01-01", "2024-12-31", "Fold4_2024"),
]

FEATURE_COLS = [
    # Group A — COT
    "cot_index", "cot_index_4w_change", "net_pct_change_1w",
    "momentum_acceleration", "oi_delta_direction", "oi_net_confluence",
    "flip_flag", "extreme_flag", "usd_index_cot", "rank_in_8",
    "spread_vs_usd", "weeks_since_flip",
    # Group B — TFF
    "lev_funds_net_index", "asset_mgr_net_direction", "dealer_net_contrarian",
    "lev_vs_assetmgr_divergence",
    # Group C — Macro
    "rate_diff_vs_usd", "rate_diff_trend_3m", "rate_hike_expectation",
    "cpi_diff_vs_usd", "cpi_trend", "pmi_composite_diff",
    "yield_10y_diff", "vix_regime",
    # Group D — Cross-asset & Seasonal
    "gold_cot_index", "oil_cot_direction", "month", "quarter",
]

GROUP_B_FEATURES = [
    "lev_funds_net_index", "asset_mgr_net_direction", "dealer_net_contrarian",
    "lev_vs_assetmgr_divergence",
]

# Confidence thresholds for predict_proba
CONFIDENCE_HIGH = 0.70
CONFIDENCE_MEDIUM = 0.55

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
# Data helpers
# ---------------------------------------------------------------------------

def load_dataset() -> pd.DataFrame:
    if not FEATURES_CSV.exists():
        logger.error(f"Features CSV not found: {FEATURES_CSV}")
        sys.exit(1)
    df = pd.read_csv(FEATURES_CSV, parse_dates=["date"])
    df = df.sort_values(["date", "currency"]).reset_index(drop=True)
    df = df.dropna(subset=["label"]).reset_index(drop=True)
    return df


def prepare_X(df: pd.DataFrame, currency_encoder: LabelEncoder) -> np.ndarray:
    df = df.copy()
    df["currency_enc"] = currency_encoder.transform(df["currency"])
    cols = FEATURE_COLS + ["currency_enc"]
    present = [c for c in cols if c in df.columns]
    for c in cols:
        if c not in df.columns:
            df[c] = 0.0
    X = df[present].values.astype(np.float32)
    return np.nan_to_num(X, nan=0.0)


def get_feature_names(currency_encoder: LabelEncoder) -> list:
    cols = FEATURE_COLS + ["currency_enc"]
    return cols


# ---------------------------------------------------------------------------
# B3-02a — Baseline models
# ---------------------------------------------------------------------------

def baseline_random(y_test: np.ndarray, classes: list, rng_seed: int = 42) -> np.ndarray:
    """Random: uniform random from {BULL, BEAR, NEUTRAL}."""
    rng = np.random.default_rng(rng_seed)
    return rng.choice(classes, size=len(y_test))


def baseline_always_bull(y_test: np.ndarray) -> np.ndarray:
    return np.full(len(y_test), "BULL")


def baseline_cot_rule(df_test: pd.DataFrame) -> np.ndarray:
    """
    COT Rule: cot_index > 60 → BULL, < 40 → BEAR, else NEUTRAL.
    (Threshold-based, no training needed.)
    """
    preds = []
    for _, row in df_test.iterrows():
        idx = row.get("cot_index", 50.0)
        if idx > 60:
            preds.append("BULL")
        elif idx < 40:
            preds.append("BEAR")
        else:
            preds.append("NEUTRAL")
    return np.array(preds)


def train_logistic_regression(
    X_train: np.ndarray,
    y_train: np.ndarray,
    scaler: StandardScaler,
) -> CalibratedClassifierCV:
    """Logistic Regression with Platt calibration (same pipeline as RF)."""
    X_scaled = scaler.transform(X_train)
    lr = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        random_state=42,
        solver="lbfgs",
    )
    model = CalibratedClassifierCV(lr, method="sigmoid", cv=5)
    model.fit(X_scaled, y_train)
    return model


# ---------------------------------------------------------------------------
# B3-02c — Confidence-level bucketing
# ---------------------------------------------------------------------------

def accuracy_by_confidence(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    proba: np.ndarray,
) -> dict:
    """
    Bin predictions by max(proba) confidence level:
      HIGH   : max_p >= 0.70
      MEDIUM : 0.55 <= max_p < 0.70
      LOW    : max_p < 0.55
    """
    max_proba = proba.max(axis=1)
    results = {}
    for level, (lo, hi) in [
        ("HIGH",   (CONFIDENCE_HIGH,   1.01)),
        ("MEDIUM", (CONFIDENCE_MEDIUM, CONFIDENCE_HIGH)),
        ("LOW",    (0.0,               CONFIDENCE_MEDIUM)),
    ]:
        mask = (max_proba >= lo) & (max_proba < hi)
        n = mask.sum()
        if n > 0:
            acc = accuracy_score(y_true[mask], y_pred[mask])
            results[level] = {"n": int(n), "accuracy": round(float(acc), 4)}
        else:
            results[level] = {"n": 0, "accuracy": None}
    return results


# ---------------------------------------------------------------------------
# B3-02e — min_samples_leaf tuning
# ---------------------------------------------------------------------------

def tune_min_samples_leaf(
    df: pd.DataFrame,
    currency_encoder: LabelEncoder,
    candidates: list = (10, 15),
) -> dict:
    """
    Run walk-forward for each candidate min_samples_leaf.
    Returns dict: {leaf_size: mean_accuracy}.
    """
    results = {}
    for leaf in candidates:
        params = {**RF_PARAMS_BASE, "min_samples_leaf": leaf}
        fold_accs = []
        for train_end, test_start, test_end, fold_label in FOLDS:
            df_train = df[df["date"] <= pd.Timestamp(train_end)]
            df_test = df[
                (df["date"] >= pd.Timestamp(test_start)) &
                (df["date"] <= pd.Timestamp(test_end))
            ]
            if df_train.empty or df_test.empty:
                continue
            X_tr = prepare_X(df_train, currency_encoder)
            y_tr = df_train["label"].values
            X_te = prepare_X(df_test, currency_encoder)
            y_te = df_test["label"].values

            base_rf = RandomForestClassifier(**params)
            model = CalibratedClassifierCV(base_rf, method="sigmoid", cv=5)
            model.fit(X_tr, y_tr)
            fold_accs.append(accuracy_score(y_te, model.predict(X_te)))

        mean_acc = float(np.mean(fold_accs)) if fold_accs else 0.0
        results[leaf] = round(mean_acc, 4)
        logger.info(f"  min_samples_leaf={leaf}: mean_acc={mean_acc:.4f}")
    return results


# ---------------------------------------------------------------------------
# B3-02f — Feature importance
# ---------------------------------------------------------------------------

def get_feature_importances(
    model: CalibratedClassifierCV,
    feature_names: list,
) -> list:
    """
    Extract mean feature importances from CalibratedClassifierCV.
    Each calibrated sub-estimator holds a fitted RF.
    """
    importances = []
    for cal_clf in model.calibrated_classifiers_:
        base = cal_clf.estimator
        if hasattr(base, "feature_importances_"):
            importances.append(base.feature_importances_)

    if not importances:
        logger.warning("Could not extract feature importances from calibrated model.")
        return []

    mean_imp = np.mean(importances, axis=0)
    ranked = sorted(
        zip(feature_names, mean_imp),
        key=lambda x: -x[1],
    )
    return [(name, round(float(imp), 6)) for name, imp in ranked]


# ---------------------------------------------------------------------------
# B3-02g — Chart
# ---------------------------------------------------------------------------

def plot_fold_accuracy(fold_results: dict) -> bool:
    """Plot RF vs COT baseline accuracy per fold. Returns True if saved."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        folds = list(fold_results.keys())
        rf_accs = [fold_results[f]["rf"] for f in folds]
        cot_accs = [fold_results[f]["cot_rule"] for f in folds]
        x = np.arange(len(folds))
        width = 0.35

        fig, ax = plt.subplots(figsize=(10, 5))
        bars1 = ax.bar(x - width / 2, rf_accs, width, label="Random Forest (calibrated)", color="#2196F3")
        bars2 = ax.bar(x + width / 2, cot_accs, width, label="COT Rule baseline", color="#FF9800")

        ax.axhline(0.68, color="red", linestyle="--", linewidth=1.2, label="Gate (68%)")
        ax.set_xlabel("Fold")
        ax.set_ylabel("Accuracy")
        ax.set_title("Walk-Forward Accuracy: Random Forest vs COT Baseline")
        ax.set_xticks(x)
        ax.set_xticklabels(folds, rotation=20, ha="right")
        ax.set_ylim(0, 1)
        ax.legend()
        ax.bar_label(bars1, fmt="%.3f", padding=3, fontsize=8)
        ax.bar_label(bars2, fmt="%.3f", padding=3, fontsize=8)
        fig.tight_layout()

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(CHART_PATH, dpi=150, bbox_inches="tight")
        plt.close(fig)
        logger.info(f"Chart saved: {CHART_PATH}")
        return True
    except ImportError:
        logger.warning("matplotlib not available — skipping chart (B3-02g)")
        return False


# ---------------------------------------------------------------------------
# Main walk-forward with all baselines
# ---------------------------------------------------------------------------

def run_validation(df: pd.DataFrame, currency_encoder: LabelEncoder) -> dict:
    """
    Run walk-forward for RF + all 4 baselines.
    Returns consolidated results dict.
    """
    all_classes = ["BULL", "BEAR", "NEUTRAL"]
    fold_results = {}
    all_fold_data = []   # for global summary

    for train_end, test_start, test_end, fold_label in FOLDS:
        df_train = df[df["date"] <= pd.Timestamp(train_end)].copy()
        df_test = df[
            (df["date"] >= pd.Timestamp(test_start)) &
            (df["date"] <= pd.Timestamp(test_end))
        ].copy()

        if df_train.empty or df_test.empty:
            logger.warning(f"{fold_label}: empty split — skipping")
            continue

        X_tr = prepare_X(df_train, currency_encoder)
        y_tr = df_train["label"].values
        X_te = prepare_X(df_test, currency_encoder)
        y_te = df_test["label"].values

        # ---- RF (B3-02b) ----
        rf_params = {**RF_PARAMS_BASE, "min_samples_leaf": 10}
        base_rf = RandomForestClassifier(**rf_params)
        rf_model = CalibratedClassifierCV(base_rf, method="sigmoid", cv=5)
        rf_model.fit(X_tr, y_tr)
        y_rf = rf_model.predict(X_te)
        rf_proba = rf_model.predict_proba(X_te)
        rf_acc = accuracy_score(y_te, y_rf)

        # ---- Baselines (B3-02a) ----
        y_random = baseline_random(y_te, all_classes)
        y_bull = baseline_always_bull(y_te)
        y_cot = baseline_cot_rule(df_test)

        scaler = StandardScaler()
        scaler.fit(X_tr)
        lr_model = train_logistic_regression(X_tr, y_tr, scaler)
        X_te_scaled = scaler.transform(X_te)
        y_lr = lr_model.predict(X_te_scaled)
        lr_proba = lr_model.predict_proba(X_te_scaled)

        acc_random = accuracy_score(y_te, y_random)
        acc_bull = accuracy_score(y_te, y_bull)
        acc_cot = accuracy_score(y_te, y_cot)
        acc_lr = accuracy_score(y_te, y_lr)

        # Beat COT gate
        cot_gap = rf_acc - acc_cot

        # B3-02c — per-currency accuracy
        df_test["pred_rf"] = y_rf
        per_currency = {}
        for cur, grp in df_test.groupby("currency"):
            per_currency[cur] = round(
                float(accuracy_score(grp["label"], grp["pred_rf"])), 4
            )

        # B3-02c — confidence-level accuracy
        conf_acc = accuracy_by_confidence(y_te, y_rf, rf_proba)

        fold_results[fold_label] = {
            "rf":        round(float(rf_acc), 4),
            "random":    round(float(acc_random), 4),
            "always_bull": round(float(acc_bull), 4),
            "cot_rule":  round(float(acc_cot), 4),
            "logistic_regression": round(float(acc_lr), 4),
            "rf_vs_cot_gap": round(float(cot_gap), 4),
            "gate_pass": cot_gap >= 0.05,
            "per_currency_accuracy": per_currency,
            "confidence_accuracy": conf_acc,
        }

        all_fold_data.append({
            "y_te": y_te, "y_rf": y_rf,
            "rf_acc": rf_acc, "acc_cot": acc_cot,
        })

        logger.info(
            f"{fold_label}: RF={rf_acc:.4f} | COT={acc_cot:.4f} | "
            f"LR={acc_lr:.4f} | Random={acc_random:.4f} | "
            f"Gap(RF-COT)={cot_gap:+.4f} | Gate={'✓' if cot_gap >= 0.05 else '✗'}"
        )

    return fold_results


# ---------------------------------------------------------------------------
# B3-02d — Model card
# ---------------------------------------------------------------------------

def write_model_card(
    fold_results: dict,
    top_features: list,
    leaf_tune: dict,
    best_leaf: int,
    gate_overall: bool,
    generated_at: str,
) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    rf_accs = [v["rf"] for v in fold_results.values()]
    cot_accs = [v["cot_rule"] for v in fold_results.values()]
    lr_accs = [v["logistic_regression"] for v in fold_results.values()]
    gaps = [v["rf_vs_cot_gap"] for v in fold_results.values()]
    mean_rf = float(np.mean(rf_accs)) if rf_accs else 0.0
    mean_cot = float(np.mean(cot_accs)) if cot_accs else 0.0
    mean_gap = float(np.mean(gaps)) if gaps else 0.0

    lines = [
        "# Model Card — FX Bias AI Random Forest",
        "",
        f"> Generated: {generated_at}  |  Phase: B3-02",
        "",
        "## Model Overview",
        "",
        "| Field | Value |",
        "|-------|-------|",
        "| Model type | RandomForestClassifier + Platt Scaling (CalibratedClassifierCV) |",
        "| n_estimators | 300 |",
        "| max_depth | 8 |",
        f"| min_samples_leaf | {best_leaf} (tuned B3-02e) |",
        "| max_features | sqrt |",
        "| class_weight | balanced |",
        "| calibration | Sigmoid (Platt) |",
        "| training window | 2006 – 2023 |",
        "| features | 28 + currency_enc |",
        "| classes | BULL / BEAR / NEUTRAL |",
        "",
        "## Walk-Forward Validation Results",
        "",
        "| Fold | RF | COT Rule | LR | Random | RF−COT | Gate |",
        "|------|----|----------|----|--------|--------|------|",
    ]

    for fold, v in fold_results.items():
        gate_icon = "✓" if v["gate_pass"] else "✗"
        lines.append(
            f"| {fold} | {v['rf']:.4f} | {v['cot_rule']:.4f} | "
            f"{v['logistic_regression']:.4f} | {v['random']:.4f} | "
            f"{v['rf_vs_cot_gap']:+.4f} | {gate_icon} |"
        )

    lines += [
        f"| **Mean** | **{mean_rf:.4f}** | **{mean_cot:.4f}** | "
        f"**{float(np.mean(lr_accs)):.4f}** | — | **{mean_gap:+.4f}** | "
        f"{'✓ PASS' if gate_overall else '✗ FAIL'} |",
        "",
        "**Gate:** RF must beat COT-only baseline by ≥ +5%.",
        f"**Result:** {'PASS ✓ — RF beats COT by ' + f'{mean_gap:.1%}' if gate_overall else 'FAIL ✗ — does not meet gate'}",
        "",
        "## Per-Currency Accuracy (last fold)",
    ]

    if fold_results:
        last_fold = list(fold_results.values())[-1]
        lines += ["", "| Currency | RF Accuracy |", "|----------|-------------|"]
        for cur, acc in sorted(last_fold["per_currency_accuracy"].items()):
            lines.append(f"| {cur} | {acc:.4f} |")

        lines += [
            "",
            "## Accuracy by Confidence Level (last fold)",
            "",
            "| Level | Threshold | n | Accuracy |",
            "|-------|-----------|---|----------|",
        ]
        conf = last_fold["confidence_accuracy"]
        for level, thresh in [("HIGH", "≥70%"), ("MEDIUM", "55–70%"), ("LOW", "<55%")]:
            d = conf.get(level, {})
            acc_str = f"{d['accuracy']:.4f}" if d.get("accuracy") is not None else "—"
            lines.append(f"| {level} | {thresh} | {d.get('n', 0)} | {acc_str} |")

    lines += [
        "",
        "## Top 10 Feature Importances",
        "",
        "| Rank | Feature | Importance | Group |",
        "|------|---------|------------|-------|",
    ]

    group_map = {
        **{f: "A — COT" for f in FEATURE_COLS[:12]},
        **{f: "B — TFF" for f in GROUP_B_FEATURES},
        "rate_diff_vs_usd": "C — Macro", "rate_diff_trend_3m": "C — Macro",
        "rate_hike_expectation": "C — Macro", "cpi_diff_vs_usd": "C — Macro",
        "cpi_trend": "C — Macro", "pmi_composite_diff": "C — Macro",
        "yield_10y_diff": "C — Macro", "vix_regime": "C — Macro",
        "gold_cot_index": "D — Cross-asset", "oil_cot_direction": "D — Cross-asset",
        "month": "D — Seasonal", "quarter": "D — Seasonal",
        "currency_enc": "Meta",
    }

    group_b_ranks = []
    for rank, (feat, imp) in enumerate(top_features[:10], 1):
        grp = group_map.get(feat, "—")
        lines.append(f"| {rank} | `{feat}` | {imp:.6f} | {grp} |")
        if feat in GROUP_B_FEATURES:
            group_b_ranks.append(rank)

    if group_b_ranks:
        lines.append(f"\n> Group B TFF features appear at ranks: {group_b_ranks} — positive contribution confirmed.")
    else:
        lines.append("\n> Group B TFF features not in top 10 — review feature engineering.")

    lines += [
        "",
        "## Outputs",
        "",
        "| File | Description |",
        "|------|-------------|",
        "| `models/model.pkl` | CalibratedClassifierCV (production) |",
        "| `models/calibrator.pkl` | Alias of model.pkl |",
        "| `models/model_lr_fallback.pkl` | Logistic Regression fallback (B3-03) |",
        "| `models/validation_chart.png` | Walk-forward accuracy chart |",
        "| `data/history/model-metrics/initial_training.json` | Training metrics |",
        "| `data/history/model-metrics/validation_results.json` | Validation metrics |",
        "",
        "---",
        "*Auto-generated by `training/validate_model.py` — Phase B3-02*",
    ]

    MODEL_CARD_PATH.write_text("\n".join(lines))
    logger.info(f"Model card saved: {MODEL_CARD_PATH}")


# ---------------------------------------------------------------------------
# B3-02e — DECISIONS.md
# ---------------------------------------------------------------------------

def write_decisions(leaf_tune: dict, best_leaf: int, generated_at: str) -> None:
    decision_block = f"""
## min_samples_leaf Tuning — B3-02e

**Date:** {generated_at}

**Candidates tested:** {list(leaf_tune.keys())}

| min_samples_leaf | Mean Walk-Forward Accuracy |
|------------------|---------------------------|
"""
    for leaf, acc in leaf_tune.items():
        marker = " ← selected" if leaf == best_leaf else ""
        decision_block += f"| {leaf} | {acc:.4f}{marker} |\n"

    decision_block += f"""
**Selected:** `min_samples_leaf = {best_leaf}`
**Reason:** Higher mean walk-forward accuracy across 4 folds.
**Impact:** Lower values allow finer splits (risk overfit); higher values regularize more.

---
"""

    decisions_path = _REPO_ROOT / "DECISIONS.md"
    if decisions_path.exists():
        existing = decisions_path.read_text()
        # Avoid duplicating the section
        if "min_samples_leaf Tuning" not in existing:
            decisions_path.write_text(existing.rstrip() + "\n" + decision_block)
        else:
            logger.info("DECISIONS.md already has min_samples_leaf section — skipping append")
    else:
        decisions_path.write_text(f"# DECISIONS.md — FX Bias AI\n{decision_block}")

    logger.info(f"DECISIONS.md updated: {decisions_path}")


# ---------------------------------------------------------------------------
# B3-03 — Logistic Regression fallback
# ---------------------------------------------------------------------------

def train_lr_fallback(
    df: pd.DataFrame,
    currency_encoder: LabelEncoder,
    final_train_end: str = "2023-12-31",
) -> None:
    """Train LR on full training window, save as model_lr_fallback.pkl."""
    df_train = df[df["date"] <= pd.Timestamp(final_train_end)].copy()
    X = prepare_X(df_train, currency_encoder)
    y = df_train["label"].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    lr = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        random_state=42,
        solver="lbfgs",
    )
    lr_cal = CalibratedClassifierCV(lr, method="sigmoid", cv=5)
    lr_cal.fit(X_scaled, y)

    # Bundle scaler + model together for easy loading
    lr_bundle = {"model": lr_cal, "scaler": scaler, "features": FEATURE_COLS + ["currency_enc"]}
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(lr_bundle, LR_FALLBACK_PATH)
    logger.info(f"LR fallback saved: {LR_FALLBACK_PATH}")

    # In-sample sanity
    y_pred = lr_cal.predict(X_scaled)
    acc = accuracy_score(y, y_pred)
    logger.info(f"LR fallback in-sample accuracy: {acc:.4f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    logger.info("=" * 60)
    logger.info("Phase B3-02: validate_model.py — Baseline Comparison")
    logger.info("=" * 60)

    df = load_dataset()

    currency_encoder = LabelEncoder()
    currency_encoder.fit(df["currency"])
    logger.info(f"Currencies: {list(currency_encoder.classes_)}")

    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # --- B3-02a/b/c: Walk-forward with all baselines ---
    logger.info("\n=== Walk-Forward Validation + Baseline Comparison ===")
    fold_results = run_validation(df, currency_encoder)

    if not fold_results:
        logger.error("No fold results — check date ranges.")
        return 1

    # Gate check (B3-02b)
    gaps = [v["rf_vs_cot_gap"] for v in fold_results.values()]
    mean_gap = float(np.mean(gaps))
    gate_overall = mean_gap >= 0.05
    logger.info(f"\nMean RF−COT gap: {mean_gap:+.4f}")
    logger.info(f"Gate (≥+5%): {'PASS ✓' if gate_overall else 'FAIL ✗'}")

    # --- B3-02e: min_samples_leaf tuning ---
    logger.info("\n=== Tuning min_samples_leaf (B3-02e) ===")
    leaf_tune = tune_min_samples_leaf(df, currency_encoder, candidates=[10, 15])
    best_leaf = max(leaf_tune, key=leaf_tune.get)
    logger.info(f"Best min_samples_leaf: {best_leaf} (acc={leaf_tune[best_leaf]:.4f})")

    # --- B3-02f: Feature importance ---
    logger.info("\n=== Feature Importance Analysis (B3-02f) ===")
    # Train one final RF on full training data for importances
    df_train_full = df[df["date"] <= pd.Timestamp("2023-12-31")].copy()
    X_imp = prepare_X(df_train_full, currency_encoder)
    y_imp = df_train_full["label"].values
    rf_for_imp = RandomForestClassifier(**{**RF_PARAMS_BASE, "min_samples_leaf": best_leaf})
    rf_cal_imp = CalibratedClassifierCV(rf_for_imp, method="sigmoid", cv=5)
    rf_cal_imp.fit(X_imp, y_imp)

    feat_names = get_feature_names(currency_encoder)
    top_features = get_feature_importances(rf_cal_imp, feat_names)

    logger.info("Top 10 features:")
    for rank, (feat, imp) in enumerate(top_features[:10], 1):
        group_b_tag = " [GROUP B]" if feat in GROUP_B_FEATURES else ""
        logger.info(f"  {rank:2d}. {feat:35s} {imp:.6f}{group_b_tag}")

    group_b_in_top10 = [f for f, _ in top_features[:10] if f in GROUP_B_FEATURES]
    if group_b_in_top10:
        logger.info(f"Group B features in top-10: {group_b_in_top10} — positive contribution confirmed ✓")
    else:
        logger.warning("Group B TFF features not in top-10 — review feature engineering")

    # --- B3-02g: Chart ---
    logger.info("\n=== Plotting accuracy chart (B3-02g) ===")
    chart_data = {k: {"rf": v["rf"], "cot_rule": v["cot_rule"]} for k, v in fold_results.items()}
    plot_fold_accuracy(chart_data)

    # --- B3-02d: Model card ---
    logger.info("\n=== Writing model card (B3-02d) ===")
    write_model_card(fold_results, top_features, leaf_tune, best_leaf, gate_overall, generated_at)

    # --- B3-02e: DECISIONS.md ---
    write_decisions(leaf_tune, best_leaf, generated_at)

    # --- B3-03: LR fallback ---
    logger.info("\n=== Training LR Fallback (B3-03) ===")
    train_lr_fallback(df, currency_encoder)

    # --- Save validation JSON ---
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    validation_out = {
        "phase": "B3-02",
        "generated_at": generated_at,
        "gate_pass": gate_overall,
        "mean_rf_vs_cot_gap": round(mean_gap, 4),
        "min_samples_leaf_tuning": {str(k): v for k, v in leaf_tune.items()},
        "best_min_samples_leaf": best_leaf,
        "top_10_features": top_features[:10],
        "group_b_in_top10": group_b_in_top10,
        "folds": {
            k: {
                fk: fv for fk, fv in v.items()
                if fk != "per_currency_accuracy"  # keep JSON concise
            }
            for k, v in fold_results.items()
        },
        "per_currency_last_fold": list(fold_results.values())[-1]["per_currency_accuracy"],
    }
    with open(VALIDATION_JSON, "w") as f:
        json.dump(validation_out, f, indent=2)
    logger.info(f"Validation JSON: {VALIDATION_JSON}")

    # --- Final summary ---
    rf_accs = [v["rf"] for v in fold_results.values()]
    logger.info("\n" + "=" * 60)
    logger.info("B3-02 COMPLETE")
    logger.info(f"  RF mean accuracy     : {np.mean(rf_accs):.4f}")
    logger.info(f"  RF vs COT mean gap   : {mean_gap:+.4f}")
    logger.info(f"  Phase gate (≥+5%)    : {'PASS ✓' if gate_overall else 'FAIL ✗'}")
    logger.info(f"  best min_samples_leaf: {best_leaf}")
    logger.info(f"  model_card.md        : {MODEL_CARD_PATH}")
    logger.info(f"  model_lr_fallback.pkl: {LR_FALLBACK_PATH}")
    logger.info("  Next: B3-03 ✓ (LR fallback already trained above)")
    logger.info("  Then: B4 — Inference pipeline")
    logger.info("=" * 60)

    return 0 if gate_overall else 1


if __name__ == "__main__":
    sys.exit(main())
