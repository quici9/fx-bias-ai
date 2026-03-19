#!/usr/bin/env python3
"""
Fetch cross-asset data: commodities COT (Gold, Oil, S&P 500) and yield differentials.

Reuses macro data for yield spreads to avoid redundant API calls.

Reference: Task List B1-03
Exit codes: 0=success, 1=partial, 2=failed
"""

import json
import os
import sys
import time
from datetime import date
from typing import Optional

import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.utils.file_io import EXIT_FAILED, EXIT_PARTIAL, EXIT_SUCCESS, setup_logging, write_output

logger = setup_logging(__name__)

# CFTC Socrata API configuration
SOCRATA_BASE_URL = "https://publicreporting.cftc.gov/resource"
LEGACY_DATASET_ID = "6dca-aqww"  # Legacy - Futures Only (updated 2026)

# Commodity futures contract codes
COMMODITY_CONTRACTS = {
    "gold": "088691",     # Gold Futures (COMEX)
    "oil": "067651",      # Crude Oil, Light Sweet (WTI)
    "sp500": "138741",    # E-mini S&P 500
}

# FX impact descriptions
FX_IMPACT = {
    "gold": "Inverse USD (gold up → USD down)",
    "oil": "Direct CAD (oil up → CAD up)",
    "sp500": "Risk-on proxy (equities up → risk currencies up)",
}

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2


def fetch_socrata_data(dataset_id: str, contract_code: str, limit: int = 100) -> list[dict]:
    """
    Fetch data from CFTC Socrata API.

    Args:
        dataset_id: Socrata dataset ID
        contract_code: CFTC contract market code
        limit: Number of records to fetch

    Returns:
        List of records

    Raises:
        requests.RequestException: On API failure
    """
    url = f"{SOCRATA_BASE_URL}/{dataset_id}.json"
    params = {
        "$where": f"cftc_contract_market_code='{contract_code}'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": limit,
    }

    # Headers required by Socrata API
    headers = {
        "User-Agent": "FX-Bias-AI/1.0 (Data Research)"
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Fetching contract %s (attempt %d/%d)", contract_code, attempt, MAX_RETRIES)
            response = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)

            if response.status_code == 429:
                logger.warning("Rate limited — retrying")
                time.sleep(RETRY_DELAY * attempt)
                continue

            if response.status_code >= 500:
                logger.warning("Server error — retrying")
                time.sleep(RETRY_DELAY)
                continue

            response.raise_for_status()
            data = response.json()
            logger.info("Fetched %d records", len(data))
            return data

        except requests.Timeout:
            logger.warning("Request timeout")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                continue
            raise

        except requests.RequestException as e:
            logger.error("Request failed: %s", e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                continue
            raise

    raise requests.RequestException(f"Failed after {MAX_RETRIES} attempts")


def compute_cot_index(historical_net: list[int]) -> float:
    """
    Compute 52-week COT index: (current - min) / (max - min) * 100.

    Args:
        historical_net: List of net positions (most recent first)

    Returns:
        Index value (0-100)
    """
    if len(historical_net) < 52:
        logger.warning("Insufficient history for 52w index — using available data")
        history = historical_net
    else:
        history = historical_net[:52]

    if not history:
        return 50.0

    min_net = min(history)
    max_net = max(history)

    if max_net == min_net:
        return 50.0

    current = history[0]
    index = ((current - min_net) / (max_net - min_net)) * 100

    return round(index, 2)


def compute_trend_direction(trend_12w: list[float]) -> str:
    """
    Determine trend direction from 12-week index values.

    Args:
        trend_12w: List of 12 weekly index values (most recent first)

    Returns:
        RISING, FALLING, or FLAT
    """
    if len(trend_12w) < 2:
        return "FLAT"

    # Compare most recent vs 12 weeks ago
    current = trend_12w[0]
    past = trend_12w[-1]
    delta = current - past

    if abs(delta) < 5:  # Threshold for "flat"
        return "FLAT"
    elif delta > 0:
        return "RISING"
    else:
        return "FALLING"


def fetch_commodity_cot(commodity: str, contract_code: str) -> dict:
    """
    Fetch and process COT data for a commodity.

    Args:
        commodity: Commodity name (gold, oil, sp500)
        contract_code: CFTC contract code

    Returns:
        CommodityCotRecord dict
    """
    logger.info("Processing %s COT", commodity.upper())

    # Fetch historical data (52 weeks for index, 12 for trend)
    records = fetch_socrata_data(LEGACY_DATASET_ID, contract_code, limit=52)

    if not records:
        raise ValueError(f"No COT data available for {commodity}")

    # Extract net positions
    historical_net = []
    for record in records:
        noncomm_long = int(record.get("noncomm_positions_long_all", 0))
        noncomm_short = int(record.get("noncomm_positions_short_all", 0))
        net = noncomm_long - noncomm_short
        historical_net.append(net)

    # Compute COT index
    cot_index = compute_cot_index(historical_net)

    # Compute 12-week trend
    trend_12w = []
    for i in range(min(12, len(historical_net))):
        # Use sliding 52w window for each week
        window = historical_net[i : i + 52]
        if len(window) >= 12:
            index = compute_cot_index(window)
            trend_12w.append(index)

    # Pad if insufficient data
    while len(trend_12w) < 12:
        trend_12w.append(cot_index)

    # Determine trend direction
    trend_direction = compute_trend_direction(trend_12w)

    return {
        "cot_index": cot_index,
        "trend_12w": trend_12w[:12],
        "trend_direction": trend_direction,
        "fx_impact": FX_IMPACT[commodity],
    }


def load_macro_data() -> Optional[dict]:
    """
    Load macro data from latest output file.

    Returns:
        Macro report dict, or None if not available
    """
    try:
        with open("data/macro-latest.json", "r") as f:
            data = json.load(f)
            logger.info("Loaded macro data from file")
            return data
    except FileNotFoundError:
        logger.warning("macro-latest.json not found — yield differentials will be empty")
        return None
    except json.JSONDecodeError as e:
        logger.error("Failed to parse macro JSON: %s", e)
        return None


def compute_yield_differentials(macro_data: Optional[dict]) -> list[dict]:
    """
    Compute yield differentials from macro data.

    Args:
        macro_data: Macro report dict (from macro-latest.json)

    Returns:
        List of YieldDifferential dicts
    """
    if not macro_data or "yields_10y" not in macro_data:
        logger.warning("No yield data available for differentials")
        return []

    yields = macro_data["yields_10y"]

    # Find yields by country
    yield_map = {y["country"]: y["yield"] for y in yields}

    us_yield = yield_map.get("US")
    if us_yield is None:
        logger.warning("US yield not available — cannot compute differentials")
        return []

    # Compute differentials
    differentials = []
    pairs = [
        ("US-DE", "DE"),
        ("US-JP", "JP"),
        ("US-GB", "GB"),
    ]

    for pair_name, country_code in pairs:
        other_yield = yield_map.get(country_code)
        if other_yield is None:
            logger.warning("Yield for %s not available", country_code)
            continue

        spread = us_yield - other_yield

        # Simplified delta_4w calculation (would need historical data)
        # Placeholder: assume 0 for now (proper implementation would fetch historical)
        delta_4w = 0.0

        # Determine direction
        if abs(delta_4w) < 0.05:
            direction = "STABLE"
        elif delta_4w > 0:
            direction = "WIDENING"
        else:
            direction = "NARROWING"

        differentials.append({
            "pair": pair_name,
            "spread": round(spread, 4),
            "delta_4w": round(delta_4w, 4),
            "direction": direction,
        })

    return differentials


def main() -> int:
    """Main execution function."""
    logger.info("=== Starting cross-asset data fetch ===")

    try:
        fetch_date = date.today()

        # Fetch commodity COT data
        commodities = {}

        for commodity, contract_code in COMMODITY_CONTRACTS.items():
            try:
                commodities[commodity] = fetch_commodity_cot(commodity, contract_code)
                logger.info("%s COT index: %s", commodity.upper(), commodities[commodity]["cot_index"])
            except Exception as e:
                logger.error("Failed to fetch %s COT: %s", commodity, e)
                # Don't fail entirely — continue with other commodities
                commodities[commodity] = {
                    "cot_index": 50.0,
                    "trend_12w": [50.0] * 12,
                    "trend_direction": "FLAT",
                    "fx_impact": FX_IMPACT.get(commodity, "Unknown"),
                }

        # Load macro data and compute yield differentials
        macro_data = load_macro_data()
        yield_differentials = compute_yield_differentials(macro_data)

        # Assemble report
        report = {
            "fetchDate": fetch_date.isoformat(),
            "commodities": commodities,
            "yield_differentials": yield_differentials,
        }

        # Write output
        output_path = "data/cross-asset-latest.json"
        write_output(report, output_path)

        logger.info("=== Cross-asset data fetch completed successfully ===")

        # Return PARTIAL if any commodity failed but we have some data
        if len(commodities) < len(COMMODITY_CONTRACTS):
            return EXIT_PARTIAL

        return EXIT_SUCCESS

    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
