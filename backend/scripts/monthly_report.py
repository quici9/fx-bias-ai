#!/usr/bin/env python3
"""
B5-01c — monthly_report.py

Aggregate weekly accuracy data into a monthly report.

Reads:  data/history/model-metrics/weekly_accuracy.json
Writes: data/history/model-metrics/monthly_YYYY-MM.json

Logic:
  - By default reports on the previous calendar month (safe when run on the 1st).
  - Pass --month YYYY-MM to override.
  - Exits with code 1 (EXIT_PARTIAL) if fewer than 2 weeks have data.
  - Exits with code 2 (EXIT_FAILED) if weekly_accuracy.json is missing.

Exit codes: 0=success, 1=partial (<2 weeks), 2=failed
"""

import argparse
import json
import os
import sys
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.utils.file_io import EXIT_FAILED, EXIT_PARTIAL, EXIT_SUCCESS, setup_logging, write_output

logger = setup_logging(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT  = Path(__file__).resolve().parent.parent.parent
METRICS_DIR = _REPO_ROOT / "data" / "history" / "model-metrics"
ACC_FILE    = METRICS_DIR / "weekly_accuracy.json"

MIN_WEEKS = 2   # minimum weeks to produce a report

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def target_month(month_str: str | None) -> tuple[int, int]:
    """
    Return (year, month) for the report.
    Defaults to previous calendar month (safe when run on 1st of month).
    """
    if month_str:
        try:
            dt = datetime.strptime(month_str, "%Y-%m")
            return dt.year, dt.month
        except ValueError:
            logger.error("Invalid --month format '%s'; expected YYYY-MM", month_str)
            sys.exit(EXIT_FAILED)

    today = date.today()
    first_of_month = today.replace(day=1)
    last_month = first_of_month - timedelta(days=1)
    return last_month.year, last_month.month


def weeks_in_month(year: int, month: int, weeks: list[dict]) -> list[dict]:
    """
    Filter weekly records whose 'date' (Friday of the ISO week) falls
    within the given calendar month.
    """
    _, last_day = monthrange(year, month)
    start = date(year, month, 1)
    end   = date(year, month, last_day)

    result = []
    for w in weeks:
        try:
            d = date.fromisoformat(w["date"])
            if start <= d <= end:
                result.append(w)
        except Exception:
            continue
    return result


def aggregate_per_currency(week_records: list[dict]) -> dict:
    """
    Aggregate per-currency accuracy across multiple weeks.
    Returns dict: currency → {n_correct, n_predictions, accuracy}
    """
    totals: dict[str, dict] = {}
    for week in week_records:
        for cur, entry in week.get("per_currency", {}).items():
            if cur not in totals:
                totals[cur] = {"n_correct": 0, "n_predictions": 0}
            totals[cur]["n_predictions"] += 1
            if entry.get("correct"):
                totals[cur]["n_correct"] += 1

    result = {}
    for cur, t in sorted(totals.items()):
        n_p = t["n_predictions"]
        n_c = t["n_correct"]
        result[cur] = {
            "n_correct": n_c,
            "n_predictions": n_p,
            "accuracy": round(n_c / n_p, 4) if n_p > 0 else None,
        }
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate monthly accuracy report (B5-01c)")
    parser.add_argument(
        "--month",
        help="Target month in YYYY-MM format (default: previous calendar month)",
        default=None,
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Phase B5-01c: monthly_report.py")
    logger.info("=" * 60)

    # 1. Load weekly accuracy data
    if not ACC_FILE.exists():
        logger.error("weekly_accuracy.json not found at %s — run calc_weekly_accuracy.py first", ACC_FILE)
        return EXIT_FAILED

    with open(ACC_FILE) as f:
        acc_data = json.load(f)

    all_weeks = acc_data.get("weeks", [])
    baseline  = acc_data.get("baseline_accuracy")

    if not all_weeks:
        logger.error("weekly_accuracy.json contains no week records")
        return EXIT_FAILED

    # 2. Determine target month
    year, month = target_month(args.month)
    month_str = f"{year}-{month:02d}"
    logger.info("Reporting for month: %s", month_str)

    # 3. Filter weeks in target month
    month_weeks = weeks_in_month(year, month, all_weeks)
    logger.info("Weeks in %s: %d", month_str, len(month_weeks))

    if len(month_weeks) < MIN_WEEKS:
        logger.warning(
            "Only %d week(s) found for %s — minimum is %d. Exiting with EXIT_PARTIAL.",
            len(month_weeks), month_str, MIN_WEEKS,
        )
        return EXIT_PARTIAL

    # 4. Aggregate
    total_predictions = sum(w["n_predictions"] for w in month_weeks)
    total_correct     = sum(w["n_correct"]     for w in month_weeks)
    monthly_accuracy  = round(total_correct / total_predictions, 4) if total_predictions > 0 else None
    per_currency      = aggregate_per_currency(month_weeks)

    logger.info(
        "Monthly accuracy: %.3f (%d/%d correct across %d weeks)",
        monthly_accuracy or 0, total_correct, total_predictions, len(month_weeks),
    )

    # 5. Build output
    output = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "month": month_str,
        "baseline_accuracy": baseline,
        "monthly_accuracy": monthly_accuracy,
        "n_weeks": len(month_weeks),
        "n_predictions": total_predictions,
        "n_correct": total_correct,
        "weeks": [w["week_label"] for w in month_weeks],
        "per_currency": per_currency,
    }

    out_path = METRICS_DIR / f"monthly_{month_str}.json"
    write_output(output, str(out_path))
    logger.info("B5-01c COMPLETE — written: %s", out_path)

    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
