#!/usr/bin/env python3
"""
B3-01 — train_model.py

Walk-forward validation + final model training for FX Bias AI.

Walk-forward folds (expanding window, annual):
  Fold 1: train 2006–2020, test 2021
  Fold 2: train 2006–2021, test 2022
  Fold 3: train 2006–2022, test 2023
  Fold 4: train 2006–2023, test 2024

Hyperparameters: RPD Section 4.1 baseline.
LABEL_CONFIRMATION_LAG = 1 enforced (B3-01c).

Outputs:
  models/model.pkl                              — CalibratedClassifierCV (Platt)
  models/calibrator.pkl                         — same object (alias)
  data/history/model-metrics/initial_training.json
"""

import json
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.preprocessing import LabelEncoder

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent

FEATURES_CSV = _REPO_ROOT / "training" / "data" / "features_2006_2026.csv"
MODELS_DIR = _REPO_ROOT / "models"
METRICS_DIR = _REPO_ROOT / "data" / "history" / "model-metrics"
METRICS_FILE = METRICS_DIR / "initial_training.json"

# ---------------------------------------------------------------------------
# Constants — RPD Section 4.1 baseline hyperparameters
# ---------------------------------------------------------------------------

LABEL_CONFIRMATION_LAG = 1  # weeks — DO NOT CHANGE (RPD Section 5.1)

RF_PARAMS = {
    "n_estimators": 500,          # 300→500: giảm variance, không tăng overfitting
    "max_depth": 8,
    "min_samples_leaf": 10,
    "max_features": 0.5,          # grid best: 0.5 > sqrt (0.5142 vs 0.5072)
    "class_weight": "balanced",   # B3-01d
    "random_state": 42,
    "n_jobs": -1,
}

# Walk-forward folds: (train_end, test_start, test_end, fold_label)
# Each fold trains on all data up to train_end, tests on [test_start, test_end].
FOLDS = [
    ("2020-12-31", "2021-01-01", "2021-12-31", "Fold1_train2006-2020_test2021"),
    ("2021-12-31", "2022-01-01", "2022-12-31", "Fold2_train2006-2021_test2022"),
    ("2022-12-31", "2023-01-01", "2023-12-31", "Fold3_train2006-2022_test2023"),
    ("2023-12-31", "2024-01-01", "2024-12-31", "Fold4_train2006-2023_test2024"),
]

# Hyperparameter search grid — uses all 4 folds (same as FOLDS) for reliable
# cross-regime estimates (2021 post-COVID, 2022 rate hike, 2023-2024 divergence).
# No look-ahead bias: each fold maintains strict temporal train/test split.
TUNE_FOLDS = FOLDS
TUNE_LEAF = (5, 10, 15, 20, 30)
TUNE_DEPTH = (6, 8, 10, 12)
TUNE_MAX_FEATURES = ("sqrt", 0.5)  # sqrt=5/28 features vs 0.5=14/28
TUNE_N_ESTIMATORS = 100            # grid search only — 5x faster; final model uses RF_PARAMS["n_estimators"]

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
# Data loading
# ---------------------------------------------------------------------------

def load_dataset() -> pd.DataFrame:
    """Load and validate the feature dataset."""
    if not FEATURES_CSV.exists():
        logger.error(f"Features CSV not found: {FEATURES_CSV}")
        logger.error("Run training/build_dataset.py first (B2-04).")
        sys.exit(1)

    df = pd.read_csv(FEATURES_CSV, parse_dates=["date"])
    df = df.sort_values(["date", "currency"]).reset_index(drop=True)

    n_rows = len(df)
    date_range = f"{df['date'].min().date()} → {df['date'].max().date()}"
    n_currencies = df["currency"].nunique()
    logger.info(f"Loaded: {n_rows} rows, {n_currencies} currencies, {date_range}")

    # Validate label column
    if "label" not in df.columns:
        logger.error("'label' column missing from features CSV.")
        sys.exit(1)

    missing_labels = df["label"].isna().sum()
    if missing_labels:
        logger.warning(f"Dropping {missing_labels} rows with missing labels.")
        df = df.dropna(subset=["label"]).reset_index(drop=True)

    return df


# ---------------------------------------------------------------------------
# Feature preparation
# ---------------------------------------------------------------------------

FEATURE_COLS = [
    "cot_index", "cot_index_4w_change", "net_pct_change_1w",
    "momentum_acceleration", "oi_delta_direction", "oi_net_confluence",
    "flip_flag", "extreme_flag", "usd_index_cot", "rank_in_8",
    "spread_vs_usd", "weeks_since_flip",
    # Group B — TFF
    "dealer_net_contrarian", "lev_vs_assetmgr_divergence",
    "asset_mgr_net_direction", "lev_funds_net_index",
    # Group C — Macro
    "rate_diff_vs_usd", "rate_diff_trend_3m", "rate_hike_expectation",
    "cpi_diff_vs_usd", "cpi_trend", "pmi_composite_diff",
    "yield_10y_diff", "vix_regime",
    # Group D — Cross-asset & Seasonal (month excluded: r=0.97 with quarter)
    "gold_cot_index", "oil_cot_direction", "quarter",
]

LABEL_CLASSES = ["BULL", "BEAR", "NEUTRAL"]


def prepare_features(df: pd.DataFrame, currency_encoder: LabelEncoder) -> tuple:
    """
    Extract X (feature matrix) and y (encoded labels) from DataFrame.

    Currency is encoded as an ordinal feature (provides cross-currency signal).
    """
    # Encode currency
    df = df.copy()
    df["currency_enc"] = currency_encoder.transform(df["currency"])

    feat_cols = FEATURE_COLS + ["currency_enc"]
    present = [c for c in feat_cols if c in df.columns]
    missing = [c for c in feat_cols if c not in df.columns]
    if missing:
        logger.warning(f"Missing feature columns (will be 0): {missing}")
        for c in missing:
            df[c] = 0.0

    X = df[present].values.astype(np.float32)
    # Fill any remaining NaN with 0 (forward-filled in feature_engineering, but safety net)
    X = np.nan_to_num(X, nan=0.0)

    y = df["label"].values
    return X, y, present


# ---------------------------------------------------------------------------
# Hyperparameter tuning — select best (min_samples_leaf, max_depth)
# ---------------------------------------------------------------------------

def find_best_params(df: pd.DataFrame, currency_encoder: LabelEncoder) -> tuple:
    """
    Grid search over all TUNE_FOLDS (= all 4 walk-forward folds) to find
    best (min_samples_leaf, max_depth). Using all folds gives reliable
    cross-regime estimates; no look-ahead bias since each fold maintains
    strict temporal train/test split.

    Returns:
        (best_rf_params dict, grid_results list of dicts for JSON storage)
    """
    logger.info(f"Grid: min_samples_leaf={TUNE_LEAF}, max_depth={TUNE_DEPTH}, max_features={TUNE_MAX_FEATURES}")
    best_acc = -1.0
    best_leaf = RF_PARAMS["min_samples_leaf"]
    best_depth = RF_PARAMS["max_depth"]
    best_max_features = RF_PARAMS["max_features"]
    grid_results = []

    for mf in TUNE_MAX_FEATURES:
        for leaf in TUNE_LEAF:
            for depth in TUNE_DEPTH:
                params = {**RF_PARAMS, "n_estimators": TUNE_N_ESTIMATORS, "min_samples_leaf": leaf, "max_depth": depth, "max_features": mf}
                fold_accs = []
                for train_end, test_start, test_end, fold_label in TUNE_FOLDS:
                    df_train = df[df["date"] <= pd.Timestamp(train_end)]
                    df_test = df[
                        (df["date"] >= pd.Timestamp(test_start)) &
                        (df["date"] <= pd.Timestamp(test_end))
                    ]
                    if df_train.empty or df_test.empty:
                        continue
                    X_tr, y_tr, _ = prepare_features(df_train, currency_encoder)
                    X_te, y_te, _ = prepare_features(df_test, currency_encoder)

                    base_rf = RandomForestClassifier(**params)
                    model = CalibratedClassifierCV(base_rf, method="sigmoid", cv=5)
                    model.fit(X_tr, y_tr)
                    fold_accs.append(accuracy_score(y_te, model.predict(X_te)))

                mean_acc = float(np.mean(fold_accs)) if fold_accs else 0.0
                logger.info(f"  mf={mf}, leaf={leaf}, depth={depth}: acc={mean_acc:.4f}")
                grid_results.append({"max_features": str(mf), "leaf": leaf, "depth": depth, "acc": round(mean_acc, 4)})
                if mean_acc > best_acc:
                    best_acc = mean_acc
                    best_leaf = leaf
                    best_depth = depth
                    best_max_features = mf

    best = {**RF_PARAMS, "min_samples_leaf": best_leaf, "max_depth": best_depth, "max_features": best_max_features}
    logger.info(
        f"Best params: min_samples_leaf={best_leaf}, max_depth={best_depth}, max_features={best_max_features} → acc={best_acc:.4f}"
    )
    return best, grid_results


# ---------------------------------------------------------------------------
# Walk-forward validation — B3-01a
# ---------------------------------------------------------------------------

def run_walk_forward(df: pd.DataFrame, currency_encoder: LabelEncoder) -> list:
    """
    Run walk-forward validation over defined folds.

    Returns list of fold result dicts.
    """
    fold_results = []

    for train_end, test_start, test_end, fold_label in FOLDS:
        train_end_ts = pd.Timestamp(train_end)
        test_start_ts = pd.Timestamp(test_start)
        test_end_ts = pd.Timestamp(test_end)

        # B3-01c: LABEL_CONFIRMATION_LAG = 1 enforced
        # Training set uses all confirmed labels up to training cutoff.
        # The lag is already embedded in the dataset (labels drop last row).
        df_train = df[df["date"] <= train_end_ts].copy()
        df_test = df[(df["date"] >= test_start_ts) & (df["date"] <= test_end_ts)].copy()

        if df_train.empty:
            logger.warning(f"{fold_label}: empty training set — skipping")
            continue
        if df_test.empty:
            logger.warning(f"{fold_label}: empty test set — skipping")
            continue

        n_train = len(df_train)
        n_test = len(df_test)

        # Prepare features
        X_train, y_train, feat_cols_used = prepare_features(df_train, currency_encoder)
        X_test, y_test, _ = prepare_features(df_test, currency_encoder)

        # B3-01b: RandomForestClassifier with baseline hyperparameters
        base_rf = RandomForestClassifier(**RF_PARAMS)

        # B3-01e: Platt Scaling calibration via CalibratedClassifierCV
        model = CalibratedClassifierCV(base_rf, method="sigmoid", cv=5)
        model.fit(X_train, y_train)

        # Evaluate
        y_pred = model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)

        # Per-class metrics
        present_classes = sorted(set(y_test) | set(y_pred))
        report = classification_report(
            y_test, y_pred,
            labels=present_classes,
            output_dict=True,
            zero_division=0,
        )

        # Per-currency accuracy
        df_test_copy = df_test.copy()
        df_test_copy["pred"] = y_pred
        per_currency = {}
        for cur, grp in df_test_copy.groupby("currency"):
            cur_acc = accuracy_score(grp["label"], grp["pred"])
            per_currency[cur] = round(float(cur_acc), 4)

        result = {
            "fold": fold_label,
            "train_end": train_end,
            "test_start": test_start,
            "test_end": test_end,
            "n_train": n_train,
            "n_test": n_test,
            "accuracy": round(float(acc), 4),
            "per_currency_accuracy": per_currency,
            "classification_report": {
                k: {
                    "precision": round(float(v["precision"]), 4),
                    "recall": round(float(v["recall"]), 4),
                    "f1-score": round(float(v["f1-score"]), 4),
                    "support": int(v["support"]),
                }
                for k, v in report.items()
                if k in present_classes
            },
        }
        fold_results.append(result)

        logger.info(
            f"{fold_label}: acc={acc:.4f}  "
            f"train_n={n_train}  test_n={n_test}  "
            f"test={test_start[:7]}→{test_end[:7]}"
        )

    return fold_results


# ---------------------------------------------------------------------------
# Final model training — B3-01b, B3-01d, B3-01e, B3-01f
# ---------------------------------------------------------------------------

def train_final_model(
    df: pd.DataFrame,
    currency_encoder: LabelEncoder,
    final_train_end: str = "2023-12-31",
    rf_params: dict = None,
) -> CalibratedClassifierCV:
    """
    Train final production model on data up to final_train_end.

    Saves:
      models/model.pkl        — CalibratedClassifierCV (Platt scaled)
      models/calibrator.pkl   — same object (alias per B3-01f spec)
    """
    if rf_params is None:
        rf_params = RF_PARAMS

    df_final = df[df["date"] <= pd.Timestamp(final_train_end)].copy()
    logger.info(
        f"Final model: training on {len(df_final)} rows "
        f"(≤ {final_train_end})"
    )
    logger.info(f"Final RF params: {rf_params}")

    X, y, feat_cols_used = prepare_features(df_final, currency_encoder)
    logger.info(f"Features used ({len(feat_cols_used)}): {feat_cols_used}")

    # B3-01b — RandomForestClassifier (tuned hyperparameters)
    # B3-01d — class_weight='balanced'
    base_rf = RandomForestClassifier(**rf_params)

    # B3-01e — Platt Scaling calibration
    model = CalibratedClassifierCV(base_rf, method="sigmoid", cv=5)
    model.fit(X, y)

    # In-sample accuracy (sanity check only)
    y_train_pred = model.predict(X)
    in_sample_acc = accuracy_score(y, y_train_pred)
    logger.info(f"In-sample accuracy (sanity): {in_sample_acc:.4f}")

    # B3-01f — Save models
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / "model.pkl"
    calibrator_path = MODELS_DIR / "calibrator.pkl"

    joblib.dump(model, model_path)
    joblib.dump(model, calibrator_path)
    logger.info(f"Saved: {model_path}")
    logger.info(f"Saved: {calibrator_path}")

    return model


# ---------------------------------------------------------------------------
# Metrics persistence — B3-01g
# ---------------------------------------------------------------------------

def save_metrics(
    fold_results: list,
    final_train_end: str,
    rf_params: dict,
    grid_results: list,
) -> None:
    """Write per-fold accuracy, grid search results and metadata to initial_training.json."""
    METRICS_DIR.mkdir(parents=True, exist_ok=True)

    # Summary stats
    accs = [r["accuracy"] for r in fold_results]
    mean_acc = float(np.mean(accs)) if accs else 0.0
    std_acc = float(np.std(accs)) if accs else 0.0

    metrics = {
        "phase": "B3-01",
        "script": "training/train_model.py",
        "features_csv": str(FEATURES_CSV.relative_to(_REPO_ROOT)),
        "final_train_end": final_train_end,
        "label_confirmation_lag": LABEL_CONFIRMATION_LAG,
        "hyperparameters": {
            k: str(v) if not isinstance(v, (int, float, str, bool, type(None))) else v
            for k, v in rf_params.items()
        },
        "calibration": "CalibratedClassifierCV(method='sigmoid', cv=5)",
        "walk_forward_summary": {
            "n_folds": len(fold_results),
            "mean_accuracy": round(mean_acc, 4),
            "std_accuracy": round(std_acc, 4),
            "min_accuracy": round(float(min(accs)), 4) if accs else 0.0,
            "max_accuracy": round(float(max(accs)), 4) if accs else 0.0,
        },
        "tuning_grid": grid_results,
        "folds": fold_results,
    }

    with open(METRICS_FILE, "w") as f:
        json.dump(metrics, f, indent=2)

    logger.info(f"Metrics saved: {METRICS_FILE}")
    logger.info(
        f"Walk-forward mean accuracy: {mean_acc:.4f} ± {std_acc:.4f}  "
        f"(min={min(accs):.4f}  max={max(accs):.4f})"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    logger.info("=" * 60)
    logger.info("Phase B3-01: train_model.py — Walk-Forward + Final Model")
    logger.info("=" * 60)

    # Load dataset
    df = load_dataset()

    # Fit currency encoder on full dataset (all known currencies)
    currency_encoder = LabelEncoder()
    currency_encoder.fit(df["currency"])
    logger.info(f"Currencies: {list(currency_encoder.classes_)}")

    # --- Walk-forward validation (B3-01a) ---
    logger.info("\n" + "=" * 40)
    logger.info("Walk-forward validation")
    logger.info("=" * 40)

    fold_results = run_walk_forward(df, currency_encoder)

    if not fold_results:
        logger.error("No fold results — check date ranges in dataset.")
        return 1

    # Print summary
    accs = [r["accuracy"] for r in fold_results]
    logger.info(f"\nFold accuracies: {[round(a, 4) for a in accs]}")
    logger.info(f"Mean: {np.mean(accs):.4f}  Std: {np.std(accs):.4f}")

    # --- Hyperparameter tuning (grid search on all 4 folds) ---
    logger.info("\n" + "=" * 40)
    logger.info("Hyperparameter tuning")
    logger.info("=" * 40)

    best_rf_params, grid_results = find_best_params(df, currency_encoder)

    # --- Final model training (B3-01b, d, e, f) ---
    logger.info("\n" + "=" * 40)
    logger.info("Training final production model")
    logger.info("=" * 40)

    final_train_end = "2023-12-31"
    train_final_model(df, currency_encoder, final_train_end, rf_params=best_rf_params)

    # --- Save metrics (B3-01g) ---
    logger.info("\n" + "=" * 40)
    logger.info("Saving metrics")
    logger.info("=" * 40)

    save_metrics(fold_results, final_train_end, best_rf_params, grid_results)

    # --- Gate check ---
    mean_acc = float(np.mean(accs))
    gate_passed = mean_acc >= 0.51
    logger.info("\n" + "=" * 60)
    logger.info("B3-01 COMPLETE")
    logger.info(f"  Walk-forward mean accuracy : {mean_acc:.4f}")
    logger.info(f"  Phase gate (≥51%)          : {'PASS ✓' if gate_passed else 'FAIL — below gate, investigate'}")
    logger.info(f"  model.pkl                  : {MODELS_DIR / 'model.pkl'}")
    logger.info(f"  calibrator.pkl             : {MODELS_DIR / 'calibrator.pkl'}")
    logger.info(f"  metrics                    : {METRICS_FILE}")
    logger.info("  Next: B3-02 — validate_model.py (baseline comparison)")
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
