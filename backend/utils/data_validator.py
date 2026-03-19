"""
Data validation utilities for FX Bias AI pipeline.

Handles freshness checks, format validation, and alert emission
for all data sources in the pipeline.

Reference: Task List S-05c
"""

import json
import logging
import os
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

STALE_THRESHOLD_DAYS = 14
ALERTS_PENDING_FILE = "data/alerts-pending.json"


def check_freshness(
    last_update: date,
    as_of: Optional[date] = None,
    threshold_days: int = STALE_THRESHOLD_DAYS,
) -> dict:
    """
    Check if a data source is fresh or stale.

    Args:
        last_update: Date when the data was last updated
        as_of: Reference date (defaults to today)
        threshold_days: Number of days before data is considered stale

    Returns:
        dict with keys: freshness_days, is_stale, status
    """
    if as_of is None:
        as_of = date.today()

    freshness_days = (as_of - last_update).days
    is_stale = freshness_days > threshold_days

    status = "STALE" if is_stale else "OK"

    if is_stale:
        logger.warning(
            "Data source stale: %d days old (threshold: %d)",
            freshness_days,
            threshold_days,
        )

    return {
        "freshness_days": freshness_days,
        "is_stale": is_stale,
        "status": status,
    }


def validate_json_format(data: dict, required_keys: list[str]) -> dict:
    """
    Validate that a JSON data dict contains all required top-level keys.

    Args:
        data: The data dictionary to validate
        required_keys: List of required key names

    Returns:
        dict with keys: valid, missing_keys
    """
    missing = [key for key in required_keys if key not in data]
    valid = len(missing) == 0

    if not valid:
        logger.error("Validation failed — missing keys: %s", missing)

    return {
        "valid": valid,
        "missing_keys": missing,
    }


def validate_date_format(date_str: str) -> bool:
    """Validate that a string is a valid ISO date (YYYY-MM-DD)."""
    try:
        date.fromisoformat(date_str)
        return True
    except (ValueError, TypeError):
        return False


def validate_week_label(week_label: str) -> bool:
    """Validate ISO week label format (YYYY-Wnn)."""
    if not isinstance(week_label, str):
        return False

    parts = week_label.split("-W")
    if len(parts) != 2:
        return False

    try:
        year = int(parts[0])
        week = int(parts[1])
        return 2020 <= year <= 2099 and 1 <= week <= 53
    except ValueError:
        return False


def emit_alert(
    alert_type: str,
    message: str,
    severity: str,
    currency: Optional[str] = None,
    context: Optional[dict] = None,
) -> dict:
    """
    Create an alert entry and append to the pending alerts file.

    Args:
        alert_type: Alert type enum value (e.g. DATA_SOURCE_STALE)
        message: Human-readable alert message
        severity: HIGH | MEDIUM | LOW
        currency: Optional currency code
        context: Optional additional context dict

    Returns:
        The alert dict that was created
    """
    valid_severities = {"HIGH", "MEDIUM", "LOW"}
    if severity not in valid_severities:
        raise ValueError(
            f"Invalid severity '{severity}'. Must be one of: {valid_severities}"
        )

    alert = {
        "type": alert_type,
        "message": message,
        "severity": severity,
    }

    if currency is not None:
        alert["currency"] = currency

    if context is not None:
        alert["context"] = context

    _append_alert_to_file(alert)

    logger.info("[ALERT] %s — %s: %s", severity, alert_type, message)

    return alert


def _append_alert_to_file(alert: dict) -> None:
    """Append an alert to the pending alerts JSON file."""
    alerts = []

    if os.path.exists(ALERTS_PENDING_FILE):
        try:
            with open(ALERTS_PENDING_FILE, "r") as f:
                alerts = json.load(f)
        except (json.JSONDecodeError, IOError):
            logger.warning("Could not read existing alerts file — creating new one")
            alerts = []

    alerts.append(alert)

    os.makedirs(os.path.dirname(ALERTS_PENDING_FILE), exist_ok=True)
    with open(ALERTS_PENDING_FILE, "w") as f:
        json.dump(alerts, f, indent=2, default=str)
