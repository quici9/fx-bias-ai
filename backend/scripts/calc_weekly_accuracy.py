#!/usr/bin/env python3
"""
B5-01a — calc_weekly_accuracy.py

Compute live weekly accuracy by comparing stored bias predictions
(data/history/bias/YYYY-WNN.json) against actual outcomes from
training/data/features_2006_2026.csv (label column).

Output: data/history/model-metrics/weekly_accuracy.json

Exit codes: 0=success, 1=partial (some weeks missing), 2=no usable data
"""

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.utils.file_io import EXIT_FAILED, EXIT_PARTIAL, EXIT_SUCCESS, setup_logging, write_output

logger = setup_logging(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT    = Path(__file__).resolve().parent.parent.parent
HISTORY_DIR   = _REPO_ROOT / "data" / "history" / "bias"
FEATURES_CSV  = _REPO_ROOT / "training" / "data" / "features_2006_2026.csv"
METRICS_DIR   = _REPO_ROOT / "data" / "history" / "model-metrics"
OUTPUT_FILE   = METRICS_DIR / "weekly_accuracy.json"
TRAINING_FILE = METRICS_DIR / "initial_training.json"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CURRENCIES = ["AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NZD"]
ROLLING_WINDOW = 4  # weeks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def week_label_to_friday(week_label: str) -> date | None:
    """
    Convert 'YYYY-WNN' → the Friday (weekday=5) of that ISO week.
    Returns None on parse error.
    """
    try:
        year, week_part = week_label.split("-W")
        return date.fromisocalendar(int(year), int(week_part), 5)
    except Exception:
        logger.warning("Cannot parse week_label: %s", week_label)
        return None


def load_actuals(csv_path: Path) -> dict[tuple[str, str], str]:
    """
    Load CSV and return a mapping (date_str, currency) → label.
    date_str format: 'YYYY-MM-DD' (Friday of the ISO week).
    """
    import csv

    actuals: dict[tuple[str, str], str] = {}
    if not csv_path.exists():
        logger.error("Features CSV not found: %s", csv_path)
        return actuals

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["date"], row["currency"])
            actuals[key] = row["label"]

    logger.info("Loaded %d rows from %s", len(actuals), csv_path)
    return actuals


def load_prediction_files(history_dir: Path) -> list[tuple[str, dict]]:
    """
    Return sorted list of (week_label, prediction_data) from history dir.
    """
    if not history_dir.exists():
        return []

    results = []
    for f in sorted(history_dir.glob("*.json")):
        week_label = f.stem  # e.g. '2026-W09'
        try:
            with open(f) as fp:
                data = json.load(fp)
            results.append((week_label, data))
        except Exception as exc:
            logger.warning("Skipping %s: %s", f.name, exc)

    return results


def load_baseline_accuracy() -> float:
    """Load baseline accuracy from initial_training.json."""
    if not TRAINING_FILE.exists():
        logger.warning("initial_training.json not found; baseline=0.5142 (7-class equal baseline)")
        return 1 / 3  # three-class uniform baseline
    try:
        with open(TRAINING_FILE) as f:
            training = json.load(f)
        acc = float(training.get("walk_forward_summary", {}).get("mean_accuracy", 0) or 0)
        return acc if acc > 0 else 1 / 3
    except Exception as exc:
        logger.warning("Could not read initial_training.json: %s", exc)
        return 1 / 3


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_week_accuracy(
    week_label: str,
    predictions: list[dict],
    actuals: dict[tuple[str, str], str],
) -> dict | None:
    """
    Compare predictions vs actual labels for a given week.
    Returns a week record dict, or None if no actual data is available.
    """
    friday = week_label_to_friday(week_label)
    if friday is None:
        return None

    date_str = friday.isoformat()

    # Build prediction map: currency → bias
    pred_map = {p["currency"]: p.get("bias", "NEUTRAL") for p in predictions}

    per_currency: dict[str, dict] = {}
    n_correct = 0
    n_total = 0

    for cur in CURRENCIES:
        predicted = pred_map.get(cur)
        actual_key = (date_str, cur)
        actual = actuals.get(actual_key)

        if predicted is None or actual is None:
            # Skip: either not predicted or no actual outcome yet
            continue

        correct = predicted == actual
        per_currency[cur] = {
            "predicted": predicted,
            "actual": actual,
            "correct": correct,
        }
        n_total += 1
        if correct:
            n_correct += 1

    if n_total == 0:
        return None  # no actual data for this week yet

    accuracy = round(n_correct / n_total, 4)

    return {
        "week_label": week_label,
        "date": date_str,
        "accuracy": accuracy,
        "n_predictions": n_total,
        "n_correct": n_correct,
        "per_currency": per_currency,
    }


def compute_rolling_4w(weeks: list[dict]) -> tuple[float | None, list[str]]:
    """
    Compute rolling 4-week mean accuracy from most recent 4 complete weeks.
    Returns (rolling_accuracy, list_of_week_labels) or (None, []).
    """
    complete = [w for w in weeks if w["n_predictions"] >= len(CURRENCIES) // 2]
    recent4 = complete[-ROLLING_WINDOW:]

    if len(recent4) < 2:
        return None, []

    avg = round(sum(w["accuracy"] for w in recent4) / len(recent4), 4)
    labels = [w["week_label"] for w in recent4]
    return avg, labels


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    logger.info("=" * 60)
    logger.info("Phase B5-01a: calc_weekly_accuracy.py")
    logger.info("=" * 60)

    # 1. Load actuals
    actuals = load_actuals(FEATURES_CSV)
    if not actuals:
        logger.error("No actual data loaded — cannot compute accuracy")
        return EXIT_FAILED

    # 2. Load prediction files
    prediction_files = load_prediction_files(HISTORY_DIR)
    if not prediction_files:
        logger.error("No prediction history files found in %s", HISTORY_DIR)
        return EXIT_FAILED

    # 3. Compute per-week accuracy
    weeks: list[dict] = []
    skipped = 0
    for week_label, data in prediction_files:
        predictions = data.get("predictions", [])
        result = compute_week_accuracy(week_label, predictions, actuals)
        if result is None:
            logger.info("Week %s: no actual data yet — skipped", week_label)
            skipped += 1
        else:
            logger.info(
                "Week %s: accuracy=%.3f (%d/%d correct)",
                week_label, result["accuracy"], result["n_correct"], result["n_predictions"],
            )
            weeks.append(result)

    if not weeks:
        logger.error("No weeks with actual outcomes — too early or data missing")
        return EXIT_FAILED

    # 4. Rolling 4-week accuracy
    rolling_4w, rolling_weeks = compute_rolling_4w(weeks)
    logger.info(
        "Rolling %dw accuracy: %s  (weeks: %s)",
        ROLLING_WINDOW,
        f"{rolling_4w:.4f}" if rolling_4w is not None else "N/A",
        rolling_weeks,
    )

    # 5. Baseline accuracy
    baseline = load_baseline_accuracy()
    logger.info("Baseline accuracy (training walk-forward): %.4f", baseline)

    # 6. Build output
    output = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "baseline_accuracy": round(baseline, 4),
        "rolling_4w_accuracy": rolling_4w,
        "rolling_4w_weeks": rolling_weeks,
        "weeks": weeks,
    }

    write_output(output, str(OUTPUT_FILE))
    logger.info("B5-01a COMPLETE — written: %s", OUTPUT_FILE)

    if skipped > 0:
        logger.info("%d prediction week(s) had no actual data yet (expected for current week)", skipped)
        return EXIT_PARTIAL if not weeks else EXIT_SUCCESS

    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
