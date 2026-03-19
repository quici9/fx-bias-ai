#!/usr/bin/env python3
"""
Send Telegram notifications for weekly predictions and critical alerts.

Formats messages with Markdown and sends via Telegram Bot API.

Reference: Task List B1-05
Exit codes: 0=success, 1=partial (send failed but not critical), 2=failed
"""

import json
import os
import sys
from typing import Optional

import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.utils.file_io import EXIT_PARTIAL, EXIT_SUCCESS, setup_logging

logger = setup_logging(__name__)

# Telegram Bot API configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API_BASE_URL = "https://api.telegram.org"

REQUEST_TIMEOUT = 10  # seconds


def send_telegram_message(message: str, parse_mode: str = "Markdown") -> bool:
    """
    Send a message via Telegram Bot API.

    Args:
        message: Message text (supports Markdown formatting)
        parse_mode: Parse mode (Markdown or HTML)

    Returns:
        True if successful, False otherwise
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("Telegram credentials not configured")
        return False

    url = f"{TELEGRAM_API_BASE_URL}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        logger.info("Sending Telegram message")
        response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)

        if response.status_code != 200:
            logger.error("Telegram API returned status %d: %s", response.status_code, response.text)
            return False

        result = response.json()
        if not result.get("ok"):
            logger.error("Telegram API error: %s", result.get("description"))
            return False

        logger.info("Telegram message sent successfully")
        return True

    except requests.Timeout:
        logger.error("Telegram API request timed out")
        return False

    except Exception as e:
        logger.error("Failed to send Telegram message: %s", e)
        return False


def format_weekly_message(bias_data: dict, alerts: list[dict], dashboard_url: str) -> str:
    """
    Format the weekly prediction summary message.

    Args:
        bias_data: BiasReport dict from bias-latest.json
        alerts: List of HIGH severity alerts
        dashboard_url: URL to the dashboard

    Returns:
        Formatted Markdown message
    """
    # Extract pair recommendations
    pairs = bias_data.get("pair_recommendations", {})
    strong_long = pairs.get("strong_long", [])
    strong_short = pairs.get("strong_short", [])
    avoid = pairs.get("avoid", [])

    # Build message
    lines = [
        "📊 *FX Bias Weekly Update*",
        f"📅 Week: {bias_data.get('week_label', 'N/A')}",
        "",
    ]

    # Strong Long
    if strong_long:
        lines.append("🟢 *Strong Long (Top 3):*")
        for pair in strong_long[:3]:
            conf = pair.get("confidence", "MEDIUM")
            lines.append(f"  • `{pair.get('pair')}` — {conf}")
        lines.append("")

    # Strong Short
    if strong_short:
        lines.append("🔴 *Strong Short (Top 3):*")
        for pair in strong_short[:3]:
            conf = pair.get("confidence", "MEDIUM")
            lines.append(f"  • `{pair.get('pair')}` — {conf}")
        lines.append("")

    # Avoid
    if avoid:
        lines.append("⚠️ *Avoid (Low Conviction):*")
        for pair in avoid[:3]:
            lines.append(f"  • `{pair.get('pair')}`")
        lines.append("")

    # HIGH alerts
    if alerts:
        lines.append("🚨 *HIGH Alerts:*")
        for alert in alerts[:5]:  # Limit to 5 alerts
            alert_type = alert.get("type", "UNKNOWN")
            currency = alert.get("currency", "")
            msg = alert.get("message", "")
            if currency:
                lines.append(f"  • `{currency}`: {alert_type}")
            else:
                lines.append(f"  • {alert_type}: {msg}")
        lines.append("")

    # Dashboard link
    lines.append(f"📈 [View Dashboard]({dashboard_url})")
    lines.append("")
    lines.append("_Generated with FX Bias AI_")

    return "\n".join(lines)


def format_rollback_alert(rollback_data: dict) -> str:
    """
    Format an immediate model rollback alert.

    Args:
        rollback_data: Rollback event data

    Returns:
        Formatted Markdown message
    """
    week = rollback_data.get("week_label", "N/A")
    reason = rollback_data.get("reason", "Unknown")
    accuracy_4w = rollback_data.get("accuracy_4w", 0)
    baseline = rollback_data.get("baseline_accuracy", 0)

    message = [
        "🚨 *MODEL ROLLBACK ALERT*",
        "",
        f"Week: `{week}`",
        f"Reason: {reason}",
        f"4-week accuracy: {accuracy_4w:.1f}%",
        f"Baseline: {baseline:.1f}%",
        "",
        "⚠️ Model has been rolled back to previous version.",
        "Manual review required.",
    ]

    return "\n".join(message)


def load_bias_report() -> Optional[dict]:
    """Load the latest bias report."""
    try:
        with open("data/bias-latest.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("bias-latest.json not found")
        return None
    except json.JSONDecodeError as e:
        logger.error("Failed to parse bias JSON: %s", e)
        return None


def load_alerts() -> list[dict]:
    """Load pending alerts."""
    try:
        with open("data/alerts-pending.json", "r") as f:
            all_alerts = json.load(f)
            # Filter HIGH alerts only
            return [a for a in all_alerts if a.get("severity") == "HIGH"]
    except FileNotFoundError:
        logger.info("No pending alerts file")
        return []
    except json.JSONDecodeError:
        logger.warning("Failed to parse alerts JSON")
        return []


def main() -> int:
    """Main execution function."""
    logger.info("=== Starting notification send ===")

    # Check if this is a rollback alert
    rollback_mode = len(sys.argv) > 1 and sys.argv[1] == "--rollback"

    if rollback_mode:
        logger.info("Sending model rollback alert")

        # Load rollback data (would be passed as argument or read from file)
        # For now, use placeholder
        rollback_data = {
            "week_label": "2026-W12",
            "reason": "Accuracy dropped below threshold",
            "accuracy_4w": 58.3,
            "baseline_accuracy": 65.0,
        }

        message = format_rollback_alert(rollback_data)
        success = send_telegram_message(message)

        if success:
            logger.info("Rollback alert sent successfully")
            return EXIT_SUCCESS
        else:
            logger.error("Failed to send rollback alert")
            return EXIT_PARTIAL

    else:
        # Weekly update mode
        logger.info("Sending weekly update")

        bias_data = load_bias_report()
        if not bias_data:
            logger.error("No bias report available")
            return EXIT_PARTIAL

        alerts = load_alerts()

        # Dashboard URL (would come from config or environment)
        dashboard_url = os.getenv("DASHBOARD_URL", "https://github.com/YOUR_USERNAME/fx-bias-ai")

        message = format_weekly_message(bias_data, alerts, dashboard_url)
        success = send_telegram_message(message)

        if success:
            logger.info("Weekly update sent successfully")
            return EXIT_SUCCESS
        else:
            logger.error("Failed to send weekly update")
            # Don't fail hard - notification failure shouldn't break the pipeline
            return EXIT_PARTIAL


if __name__ == "__main__":
    sys.exit(main())
