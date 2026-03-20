#!/usr/bin/env python3
"""
B4-03 — rollback_model.py

Model backup, deployment, and automatic rollback logic.

Functions:
  B4-03a  backup_current_model()      — rotate model.pkl → backups
  B4-03b  deploy_candidate()          — promote model_candidate.pkl → model.pkl
  B4-03c  check_rollback_condition()  — accuracy_4w < baseline − 5%?
  B4-03d  execute_rollback()          — restore backup + emit alert + notify
  B4-03e  _log_rollback_event()       — write rollback_YYYY-WNN.json

Exit codes: 0=success, 1=partial, 2=failed
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.utils.file_io import EXIT_FAILED, EXIT_PARTIAL, EXIT_SUCCESS, setup_logging

logger = setup_logging(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT   = Path(__file__).resolve().parent.parent.parent
MODELS_DIR   = _REPO_ROOT / "models"
METRICS_DIR  = _REPO_ROOT / "data" / "history" / "model-metrics"

MODEL_PATH          = MODELS_DIR / "model.pkl"
MODEL_BACKUP_PATH   = MODELS_DIR / "model_backup.pkl"
MODEL_BACKUP_PREV   = MODELS_DIR / "model_backup_prev.pkl"
MODEL_CANDIDATE     = MODELS_DIR / "model_candidate.pkl"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROLLBACK_MARGIN = 0.05   # baseline − 5%

# ---------------------------------------------------------------------------
# B4-03a — backup_current_model
# ---------------------------------------------------------------------------


def backup_current_model() -> bool:
    """
    Rotate model backups:
      model_backup.pkl  → model_backup_prev.pkl  (overwrites)
      model.pkl         → model_backup.pkl

    Returns True on success, False if model.pkl does not exist.
    """
    if not MODEL_PATH.exists():
        logger.warning(f"backup_current_model: {MODEL_PATH} does not exist — nothing to backup")
        return False

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # Rotate: model_backup → model_backup_prev
    if MODEL_BACKUP_PATH.exists():
        shutil.copy2(MODEL_BACKUP_PATH, MODEL_BACKUP_PREV)
        logger.info(f"Rotated {MODEL_BACKUP_PATH.name} → {MODEL_BACKUP_PREV.name}")

    # Backup current: model → model_backup
    shutil.copy2(MODEL_PATH, MODEL_BACKUP_PATH)
    logger.info(f"Backed up {MODEL_PATH.name} → {MODEL_BACKUP_PATH.name}")

    return True


# ---------------------------------------------------------------------------
# B4-03b — deploy_candidate
# ---------------------------------------------------------------------------


def deploy_candidate() -> bool:
    """
    Promote model_candidate.pkl → model.pkl:
      1. Backup current model (B4-03a)
      2. Copy model_candidate.pkl → model.pkl

    Returns True on success, False if candidate does not exist.
    """
    if not MODEL_CANDIDATE.exists():
        logger.error(f"deploy_candidate: {MODEL_CANDIDATE} not found — cannot deploy")
        return False

    # Backup before overwriting
    backup_current_model()

    shutil.copy2(MODEL_CANDIDATE, MODEL_PATH)
    logger.info(f"Deployed {MODEL_CANDIDATE.name} → {MODEL_PATH.name}")

    return True


# ---------------------------------------------------------------------------
# B4-03c — check_rollback_condition
# ---------------------------------------------------------------------------


def check_rollback_condition(metrics_dir: Path = METRICS_DIR) -> tuple[bool, dict]:
    """
    Determine if rollback is needed.

    Reads:
      - initial_training.json  → baseline accuracy (walk_forward_summary.mean_accuracy)
      - validation_results.json → recent fold accuracies

    Rolling 4-week accuracy = mean of the 4 most recent folds' RF accuracy.
    Rollback if: accuracy_4w < baseline − ROLLBACK_MARGIN (5%).

    Returns:
        (should_rollback: bool, details: dict)

    details keys:
        baseline_accuracy, accuracy_4w, drift, threshold, folds_used
    """
    baseline_file = metrics_dir / "initial_training.json"
    val_file      = metrics_dir / "validation_results.json"

    details = {
        "baseline_accuracy": None,
        "accuracy_4w": None,
        "drift": None,
        "threshold": ROLLBACK_MARGIN,
        "folds_used": 0,
    }

    if not baseline_file.exists():
        logger.warning("check_rollback_condition: initial_training.json not found — skip")
        return False, details

    if not val_file.exists():
        logger.warning("check_rollback_condition: validation_results.json not found — skip")
        return False, details

    try:
        with open(baseline_file) as f:
            training = json.load(f)
        baseline_acc = float(
            training.get("walk_forward_summary", {}).get("mean_accuracy", 0) or 0
        )
        if baseline_acc <= 0:
            logger.warning("check_rollback_condition: baseline accuracy is 0 — skip")
            return False, details

        with open(val_file) as f:
            val = json.load(f)

        # Collect RF accuracy from most recent folds (up to 4)
        folds = val.get("folds", {})
        fold_keys = sorted(folds.keys())[-4:]          # last 4 fold labels
        rf_accs = [float(folds[k].get("rf", baseline_acc)) for k in fold_keys]

        if not rf_accs:
            logger.warning("check_rollback_condition: no fold data — skip")
            return False, details

        accuracy_4w = sum(rf_accs) / len(rf_accs)
        drift = baseline_acc - accuracy_4w

        details.update({
            "baseline_accuracy": round(baseline_acc, 4),
            "accuracy_4w": round(accuracy_4w, 4),
            "drift": round(drift, 4),
            "folds_used": len(rf_accs),
        })

        should_rollback = drift > ROLLBACK_MARGIN
        if should_rollback:
            logger.warning(
                f"Rollback condition met: baseline={baseline_acc:.4f}, "
                f"accuracy_4w={accuracy_4w:.4f}, drift={drift:.4f} > {ROLLBACK_MARGIN}"
            )
        else:
            logger.info(
                f"No rollback needed: baseline={baseline_acc:.4f}, "
                f"accuracy_4w={accuracy_4w:.4f}, drift={drift:.4f}"
            )

        return should_rollback, details

    except Exception as exc:
        logger.error(f"check_rollback_condition error: {exc}")
        return False, details


# ---------------------------------------------------------------------------
# B4-03e — log rollback event
# ---------------------------------------------------------------------------


def _log_rollback_event(details: dict, reason: str, metrics_dir: Path = METRICS_DIR) -> Path:
    """
    Write rollback event to data/history/model-metrics/rollback_YYYY-WNN.json.

    Returns the path written.
    """
    now = datetime.now(tz=timezone.utc)
    iso = now.isocalendar()
    week_label = f"{iso[0]}-W{iso[1]:02d}"
    filename   = f"rollback_{week_label}.json"

    metrics_dir.mkdir(parents=True, exist_ok=True)
    out_path = metrics_dir / filename

    event = {
        "week_label":        week_label,
        "timestamp_utc":     now.isoformat(),
        "reason":            reason,
        "baseline_accuracy": details.get("baseline_accuracy"),
        "accuracy_4w":       details.get("accuracy_4w"),
        "drift":             details.get("drift"),
        "threshold":         details.get("threshold"),
        "folds_used":        details.get("folds_used"),
    }

    with open(out_path, "w") as f:
        json.dump(event, f, indent=2)

    logger.info(f"Rollback event logged: {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# B4-03d — execute_rollback
# ---------------------------------------------------------------------------


def execute_rollback(
    details: dict,
    reason: str = "accuracy_4w below baseline − 5%",
    notify_script: Path = None,
) -> bool:
    """
    Restore model_backup.pkl → model.pkl, log event, and notify.

    Steps:
      1. Restore model_backup.pkl → model.pkl
      2. Log rollback event (B4-03e)
      3. Emit MODEL_ROLLBACK alert JSON (append to data/alerts-pending.json)
      4. Call notify.py --rollback immediately

    Returns True on success, False if backup does not exist.
    """
    if not MODEL_BACKUP_PATH.exists():
        logger.error(f"execute_rollback: {MODEL_BACKUP_PATH} not found — cannot rollback")
        return False

    # 1. Restore backup → model
    shutil.copy2(MODEL_BACKUP_PATH, MODEL_PATH)
    logger.info(f"Restored {MODEL_BACKUP_PATH.name} → {MODEL_PATH.name}")

    # 2. Log rollback event
    log_path = _log_rollback_event(details, reason, METRICS_DIR)

    # 3. Emit MODEL_ROLLBACK alert to alerts-pending.json
    _emit_rollback_alert(details, reason, log_path)

    # 4. Notify immediately
    _send_rollback_notification(details, reason, notify_script)

    return True


def _emit_rollback_alert(details: dict, reason: str, log_path: Path) -> None:
    """Append a MODEL_ROLLBACK alert to data/alerts-pending.json."""
    from datetime import date

    alerts_file = _REPO_ROOT / "data" / "alerts-pending.json"
    alerts_file.parent.mkdir(parents=True, exist_ok=True)

    existing = []
    if alerts_file.exists():
        try:
            with open(alerts_file) as f:
                existing = json.load(f)
        except Exception:
            existing = []

    # Remove any existing MODEL_ROLLBACK alert (deduplicate)
    existing = [a for a in existing if a.get("type") != "MODEL_ROLLBACK"]

    now = datetime.now(tz=timezone.utc)
    iso = now.isocalendar()

    new_alert = {
        "type":     "MODEL_ROLLBACK",
        "message":  f"Model rolled back this week ({now.isocalendar()[0]}-W{iso[1]:02d}): {reason}",
        "severity": "HIGH",
        "context":  {
            "reason":            reason,
            "week_label":        f"{iso[0]}-W{iso[1]:02d}",
            "baseline_accuracy": details.get("baseline_accuracy"),
            "accuracy_4w":       details.get("accuracy_4w"),
            "drift":             details.get("drift"),
            "log_file":          str(log_path),
        },
    }

    existing.append(new_alert)
    with open(alerts_file, "w") as f:
        json.dump(existing, f, indent=2)

    logger.info(f"MODEL_ROLLBACK alert written to {alerts_file}")


def _send_rollback_notification(
    details: dict,
    reason: str,
    notify_script: Path = None,
) -> None:
    """Call notify.py --rollback as a subprocess."""
    if notify_script is None:
        notify_script = Path(__file__).resolve().parent / "notify.py"

    if not notify_script.exists():
        logger.warning(f"notify.py not found at {notify_script} — skipping notification")
        return

    try:
        result = subprocess.run(
            [sys.executable, str(notify_script), "--rollback"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info("Rollback notification sent via notify.py")
        else:
            logger.warning(
                f"notify.py returned {result.returncode}: {result.stderr.strip()}"
            )
    except subprocess.TimeoutExpired:
        logger.error("notify.py timed out (30s)")
    except Exception as exc:
        logger.error(f"Failed to call notify.py: {exc}")


# ---------------------------------------------------------------------------
# Main — auto-rollback check
# ---------------------------------------------------------------------------


def main() -> int:
    logger.info("=" * 60)
    logger.info("Phase B4-03: rollback_model.py")
    logger.info("=" * 60)

    should_rollback, details = check_rollback_condition(METRICS_DIR)

    if should_rollback:
        logger.warning("AUTO-ROLLBACK triggered")
        success = execute_rollback(
            details=details,
            reason=(
                f"accuracy_4w={details['accuracy_4w']:.4f} < "
                f"baseline={details['baseline_accuracy']:.4f} − {ROLLBACK_MARGIN}"
            ),
        )
        if success:
            logger.info("Rollback completed successfully")
            return EXIT_SUCCESS
        else:
            logger.error("Rollback FAILED — no backup available")
            return EXIT_FAILED
    else:
        logger.info("No rollback needed — model within acceptable accuracy range")
        return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
