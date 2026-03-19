#!/usr/bin/env python3
"""
Fetch economic calendar events (FOMC meetings and NFP releases).

Attempts MQL5 Economic Calendar API first, falls back to static JSON if unavailable.

Reference: Task List B1-04
Exit codes: 0=success, 1=partial (fallback used), 2=failed
"""

import json
import sys
from datetime import date, datetime, timedelta
from typing import Optional

import requests

# Add parent directory to path for imports
sys.path.insert(0, "/Users/ttdh/WebstormProjects/fx-bias-ai")

from backend.utils.data_validator import emit_alert
from backend.utils.file_io import EXIT_PARTIAL, EXIT_SUCCESS, setup_logging, write_output

logger = setup_logging(__name__)

# MQL5 Economic Calendar API (placeholder - actual endpoint may differ)
# Note: MQL5 may not have a public REST API for economic calendar
# This is a simplified implementation - real version would need API key or web scraping
MQL5_CALENDAR_URL = "https://www.mql5.com/en/economic-calendar"

REQUEST_TIMEOUT = 10  # seconds


def fetch_mql5_calendar() -> Optional[dict]:
    """
    Attempt to fetch calendar events from MQL5.

    Note: This is a placeholder. MQL5 does not provide a simple public REST API
    for economic calendar. A real implementation would require:
    - Web scraping
    - Or using a third-party calendar API (e.g., Trading Economics, Forex Factory)

    Returns:
        Dict with fomc_dates and nfp_dates lists, or None if failed
    """
    try:
        logger.info("Attempting to fetch from MQL5 Economic Calendar")

        # Placeholder: actual implementation would parse HTML or use API
        # For now, this always fails to trigger fallback
        response = requests.get(MQL5_CALENDAR_URL, timeout=REQUEST_TIMEOUT)

        if response.status_code != 200:
            logger.warning("MQL5 calendar returned status %d", response.status_code)
            return None

        # Would parse HTML here to extract FOMC and NFP dates
        # For this implementation, we'll just return None to use fallback

        logger.warning("MQL5 calendar parsing not implemented — using fallback")
        return None

    except requests.Timeout:
        logger.warning("MQL5 calendar request timed out")
        return None

    except Exception as e:
        logger.warning("MQL5 calendar fetch failed: %s", e)
        return None


def load_static_calendar(year: int) -> dict:
    """
    Load calendar from static JSON file.

    Args:
        year: Year to load calendar for

    Returns:
        Dict with fomc_dates and nfp_dates lists

    Raises:
        FileNotFoundError: If static file not found
        ValueError: If file is invalid
    """
    calendar_file = f"backend/static/calendar_{year}.json"

    logger.info("Loading fallback calendar from %s", calendar_file)

    try:
        with open(calendar_file, "r") as f:
            data = json.load(f)

        # Validate structure
        if "fomc_dates" not in data or "nfp_dates" not in data:
            raise ValueError("Static calendar missing required fields")

        logger.info(
            "Loaded static calendar: %d FOMC, %d NFP dates",
            len(data["fomc_dates"]),
            len(data["nfp_dates"]),
        )

        return data

    except FileNotFoundError:
        logger.error("Static calendar file not found: %s", calendar_file)
        raise

    except json.JSONDecodeError as e:
        logger.error("Failed to parse calendar JSON: %s", e)
        raise ValueError(f"Invalid JSON in {calendar_file}: {e}")


def find_next_event(event_dates: list[str], as_of: date) -> Optional[tuple[str, int]]:
    """
    Find the next upcoming event date.

    Args:
        event_dates: List of ISO date strings
        as_of: Reference date (typically today)

    Returns:
        Tuple of (next_date, days_until), or None if no future events
    """
    future_dates = []

    for date_str in event_dates:
        event_date = date.fromisoformat(date_str)
        if event_date >= as_of:
            days_until = (event_date - as_of).days
            future_dates.append((date_str, days_until))

    if not future_dates:
        return None

    # Sort by days_until and return the nearest
    future_dates.sort(key=lambda x: x[1])
    return future_dates[0]


def main() -> int:
    """Main execution function."""
    logger.info("=== Starting calendar data fetch ===")

    try:
        today = date.today()
        current_year = today.year

        # Try MQL5 first
        calendar_data = fetch_mql5_calendar()
        used_fallback = False

        # Fall back to static JSON if MQL5 failed
        if calendar_data is None:
            logger.info("Using static calendar fallback")
            calendar_data = load_static_calendar(current_year)
            used_fallback = True

            # Emit fallback alert
            emit_alert(
                "CALENDAR_SOURCE_FALLBACK",
                f"Using static calendar for {current_year} — MQL5 unavailable",
                "LOW",
            )

        # Find next FOMC meeting
        next_fomc = find_next_event(calendar_data["fomc_dates"], today)
        if next_fomc:
            next_fomc_date, days_to_fomc = next_fomc
            logger.info("Next FOMC: %s (%d days)", next_fomc_date, days_to_fomc)
        else:
            logger.warning("No future FOMC dates found in %d", current_year)
            next_fomc_date = None
            days_to_fomc = None

        # Find next NFP release
        next_nfp = find_next_event(calendar_data["nfp_dates"], today)
        if next_nfp:
            next_nfp_date, days_to_nfp = next_nfp
            logger.info("Next NFP: %s (%d days)", next_nfp_date, days_to_nfp)
        else:
            logger.warning("No future NFP dates found in %d", current_year)
            next_nfp_date = None
            days_to_nfp = None

        # Assemble output (minimal for now - not a full report schema)
        output = {
            "fetchDate": today.isoformat(),
            "source": "STATIC_FALLBACK" if used_fallback else "MQL5",
            "next_fomc": {
                "date": next_fomc_date,
                "days_until": days_to_fomc,
            } if next_fomc_date else None,
            "next_nfp": {
                "date": next_nfp_date,
                "days_until": days_to_nfp,
            } if next_nfp_date else None,
        }

        # Write output (optional - calendar data might be embedded in other reports)
        output_path = "data/calendar-latest.json"
        write_output(output, output_path)

        logger.info("=== Calendar data fetch completed ===")

        # Return PARTIAL if fallback was used
        if used_fallback:
            return EXIT_PARTIAL

        return EXIT_SUCCESS

    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        return EXIT_PARTIAL  # Don't fail hard on calendar - it's not critical


if __name__ == "__main__":
    sys.exit(main())
