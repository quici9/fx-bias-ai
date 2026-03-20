#!/usr/bin/env python3
"""
B5-02b — test_fred_series.py

Verify all FRED series used by fetch_macro.py are still accessible.

Reads FRED_API_KEY from environment.
Tests each series ID with a minimal fetch (limit=1) and reports pass/fail.

Exit codes:
  0 — all series OK
  1 — some series failed (partial)
  2 — FRED_API_KEY missing or all series failed

Run via GitHub Actions (workflow_dispatch) — do NOT run locally due to IP
restrictions and missing secrets (see CLAUDE.md).
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.utils.file_io import EXIT_FAILED, EXIT_PARTIAL, EXIT_SUCCESS, setup_logging

logger = setup_logging(__name__)

# ---------------------------------------------------------------------------
# Import series definitions from fetch_macro
# ---------------------------------------------------------------------------

try:
    from backend.scripts.fetch_macro import (
        CPI_SERIES,
        POLICY_RATE_SERIES,
        SERIES_FREQUENCY,
        YIELD_10Y_SERIES,
    )
except ImportError as exc:
    logger.error("Cannot import from fetch_macro.py: %s", exc)
    sys.exit(EXIT_FAILED)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FRED_API_BASE = "https://api.stlouisfed.org/fred/series/observations"
REQUEST_TIMEOUT = 20  # seconds
RETRY_DELAY = 2       # seconds between retries
MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# Test a single series
# ---------------------------------------------------------------------------

def test_series(series_id: str, api_key: str) -> tuple[bool, str]:
    """
    Fetch 1 observation from FRED for the given series_id.

    Returns (passed: bool, detail: str).
    """
    import requests

    params = {
        "series_id": api_key and series_id,  # guard: only proceed if key present
        "api_key": api_key,
        "limit": 1,
        "sort_order": "desc",
        "file_type": "json",
    }
    native_freq = SERIES_FREQUENCY.get(series_id)
    if native_freq:
        params["frequency"] = native_freq

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(FRED_API_BASE, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                obs = data.get("observations", [])
                if obs:
                    latest = obs[0]
                    return True, f"OK — latest={latest.get('date')} value={latest.get('value')}"
                else:
                    return False, "HTTP 200 but no observations returned"
            elif resp.status_code == 404:
                return False, f"HTTP 404 — series not found on FRED"
            elif resp.status_code == 429:
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
                    continue
                return False, "HTTP 429 — rate limited"
            else:
                try:
                    err = resp.json().get("error_message", resp.text[:120])
                except Exception:
                    err = resp.text[:120]
                return False, f"HTTP {resp.status_code} — {err}"
        except Exception as exc:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                continue
            return False, f"Exception: {exc}"

    return False, "All retries exhausted"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    logger.info("=" * 60)
    logger.info("Phase B5-02b: test_fred_series.py")
    logger.info("=" * 60)

    api_key = os.getenv("FRED_API_KEY", "")
    if not api_key:
        logger.error("FRED_API_KEY environment variable not set — cannot test")
        return EXIT_FAILED

    # Collect all series to test
    test_cases: list[tuple[str, str, str]] = []  # (group, currency/key, series_id)

    for cur, sid in sorted(POLICY_RATE_SERIES.items()):
        test_cases.append(("POLICY_RATE", cur, sid))
    for cur, sid in sorted(CPI_SERIES.items()):
        test_cases.append(("CPI", cur, sid))
    for country, sid in sorted(YIELD_10Y_SERIES.items()):
        test_cases.append(("YIELD_10Y", country, sid))

    logger.info("Testing %d FRED series...", len(test_cases))

    passed = []
    failed = []

    for group, key, series_id in test_cases:
        ok, detail = test_series(series_id, api_key)
        status = "PASS" if ok else "FAIL"
        logger.info("[%s] %s/%s (%s): %s", status, group, key, series_id, detail)
        if ok:
            passed.append((group, key, series_id, detail))
        else:
            failed.append((group, key, series_id, detail))
        # Polite delay to avoid rate-limiting
        time.sleep(0.5)

    # Print summary table
    print("\n" + "=" * 70)
    print(f"FRED Series Health Check — {len(test_cases)} series")
    print("=" * 70)
    print(f"{'Group':<14} {'Key':<6} {'Series ID':<28} {'Status':<6} {'Detail'}")
    print("-" * 70)
    for group, key, sid, detail in passed:
        print(f"{'  ' + group:<14} {key:<6} {sid:<28} {'PASS':<6} {detail}")
    for group, key, sid, detail in failed:
        print(f"{'  ' + group:<14} {key:<6} {sid:<28} {'FAIL':<6} {detail}")
    print("-" * 70)
    print(f"Total: {len(passed)} passed, {len(failed)} failed")
    print("=" * 70 + "\n")

    if not passed and failed:
        logger.error("All %d series failed — check API key and FRED connectivity", len(failed))
        return EXIT_FAILED

    if failed:
        logger.warning("%d series failed — review above for details", len(failed))
        return EXIT_PARTIAL

    logger.info("All %d FRED series OK", len(passed))
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
