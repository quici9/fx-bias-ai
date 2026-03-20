#!/usr/bin/env python3
"""
Fetch CFTC COT data (Legacy + TFF reports) for 8 FX futures.

Fetches from CFTC Socrata API, computes pre-computed values,
validates output, and writes to data/cot-latest.json.

Reference: Task List B1-01
Exit codes: 0=success, 1=partial, 2=failed
"""

import os
import sys
import time
from datetime import date, datetime, timedelta
from typing import Optional

import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.utils.data_validator import check_freshness, emit_alert
from backend.utils.file_io import EXIT_FAILED, EXIT_SUCCESS, setup_logging, write_output

logger = setup_logging(__name__)

# CFTC Socrata API endpoints
SOCRATA_BASE_URL = "https://publicreporting.cftc.gov/resource"
LEGACY_DATASET_ID = "6dca-aqww"  # Legacy - Futures Only (updated 2026)
TFF_DATASET_ID = "gpe5-46if"     # Traders in Financial Futures - Futures Only

# FX Futures contract codes (CFTC_CONTRACT_MARKET_CODE)
CURRENCY_CONTRACTS = {
    "EUR": "099741",  # Euro FX
    "GBP": "096742",  # British Pound Sterling
    "JPY": "097741",  # Japanese Yen
    "AUD": "232741",  # Australian Dollar
    "CAD": "090741",  # Canadian Dollar
    "CHF": "092741",  # Swiss Franc
    "NZD": "112741",  # New Zealand Dollar
    "USD": "098662",  # U.S. Dollar Index
}

# API request parameters
REQUEST_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


def fetch_socrata_data(dataset_id: str, contract_code: str, limit: int = 100) -> list[dict]:
    """
    Fetch data from CFTC Socrata API for a specific contract.

    Args:
        dataset_id: Socrata dataset ID (e.g. 'jun7-fc8e')
        contract_code: CFTC contract market code (e.g. '099741')
        limit: Number of records to fetch (sorted by date desc)

    Returns:
        List of records (dicts)

    Raises:
        requests.RequestException: On API failure after retries
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
            logger.info(
                "Fetching %s contract %s (attempt %d/%d)",
                dataset_id,
                contract_code,
                attempt,
                MAX_RETRIES,
            )
            response = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)

            # Handle rate limiting
            if response.status_code == 429:
                logger.warning("Rate limited (429) — retrying after %ds", RETRY_DELAY * attempt)
                time.sleep(RETRY_DELAY * attempt)
                continue

            # Handle server errors
            if response.status_code >= 500:
                logger.warning("Server error (%d) — retrying", response.status_code)
                time.sleep(RETRY_DELAY)
                continue

            response.raise_for_status()
            data = response.json()

            logger.info("Fetched %d records for contract %s", len(data), contract_code)
            return data

        except requests.Timeout:
            logger.warning("Request timeout — attempt %d/%d", attempt, MAX_RETRIES)
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

    raise requests.RequestException(f"Failed to fetch data after {MAX_RETRIES} attempts")


def get_latest_friday() -> date:
    """
    Get the most recent Friday (report publish date).
    COT reports are published on Friday for Tuesday close data.
    """
    today = date.today()
    days_since_friday = (today.weekday() - 4) % 7
    latest_friday = today - timedelta(days=days_since_friday)
    return latest_friday


def get_report_date_for_friday(publish_friday: date) -> date:
    """
    Get the Tuesday report date for a given Friday publish date.
    COT reports reflect Tuesday close, published 3 days later on Friday.
    """
    return publish_friday - timedelta(days=3)


def parse_legacy_record(raw: dict, currency: str, historical_net: list[int]) -> dict:
    """
    Parse a Legacy COT record and compute derived fields.

    Args:
        raw: Raw Socrata API response dict
        currency: Currency code (e.g. 'EUR')
        historical_net: List of historical net positions (last 52 weeks) for computing index

    Returns:
        Parsed CotLegacyRecord dict
    """
    noncomm_long = int(raw.get("noncomm_positions_long_all", 0))
    noncomm_short = int(raw.get("noncomm_positions_short_all", 0))
    open_interest = int(raw.get("open_interest_all", 0))

    net = noncomm_long - noncomm_short

    # Net delta 1w (requires historical data)
    net_delta_1w = 0
    if len(historical_net) >= 2:
        net_delta_1w = historical_net[0] - historical_net[1]

    # COT Index 52w: (current - min) / (max - min) * 100
    cot_index_52w = 50.0  # Default to neutral
    if len(historical_net) >= 52:
        min_net = min(historical_net[:52])
        max_net = max(historical_net[:52])
        if max_net > min_net:
            cot_index_52w = ((net - min_net) / (max_net - min_net)) * 100

    # Extreme flag: index < 10 or > 90
    extreme_flag = cot_index_52w < 10 or cot_index_52w > 90

    # Flip flag: net changed sign in last 2 weeks
    flip_flag = False
    if len(historical_net) >= 3:
        current_sign = 1 if net >= 0 else -1
        prev_signs = [1 if n >= 0 else -1 for n in historical_net[1:3]]
        flip_flag = current_sign != prev_signs[0] or current_sign != prev_signs[1]

    return {
        "currency": currency,
        "noncomm_long": noncomm_long,
        "noncomm_short": noncomm_short,
        "open_interest": open_interest,
        "net": net,
        "net_delta_1w": net_delta_1w,
        "cot_index_52w": round(cot_index_52w, 2),
        "extreme_flag": extreme_flag,
        "flip_flag": flip_flag,
    }


def parse_tff_record(raw: dict, currency: str) -> dict:
    """
    Parse a TFF (Traders in Financial Futures) record.

    Args:
        raw: Raw Socrata API response dict
        currency: Currency code (e.g. 'EUR')

    Returns:
        Parsed CotTffRecord dict
    """
    lev_long = int(raw.get("lev_money_positions_long", 0))
    lev_short = int(raw.get("lev_money_positions_short", 0))
    lev_net = lev_long - lev_short

    asset_long = int(raw.get("asset_mgr_positions_long", 0))
    asset_short = int(raw.get("asset_mgr_positions_short", 0))
    asset_net = asset_long - asset_short

    dealer_long = int(raw.get("dealer_positions_long_all", 0))
    dealer_short = int(raw.get("dealer_positions_short_all", 0))
    dealer_net = dealer_long - dealer_short

    # Divergence: normalized difference between lev funds and asset managers
    # Simplified calculation (full version would normalize both first)
    lev_vs_assetmgr_divergence = 0.0
    if lev_net != 0 and asset_net != 0:
        lev_vs_assetmgr_divergence = (lev_net - asset_net) / max(abs(lev_net), abs(asset_net))

    return {
        "currency": currency,
        "lev_funds_long": lev_long,
        "lev_funds_short": lev_short,
        "lev_funds_net": lev_net,
        "asset_mgr_long": asset_long,
        "asset_mgr_short": asset_short,
        "asset_mgr_net": asset_net,
        "dealer_long": dealer_long,
        "dealer_short": dealer_short,
        "dealer_net": dealer_net,
        "lev_vs_assetmgr_divergence": round(lev_vs_assetmgr_divergence, 4),
    }


def fetch_historical_net(currency: str, weeks: int = 52) -> list[int]:
    """
    Fetch historical net positions for computing COT index and trends.

    Args:
        currency: Currency code
        weeks: Number of weeks to fetch

    Returns:
        List of net positions [current, t-1, t-2, ...] (most recent first)
    """
    try:
        contract_code = CURRENCY_CONTRACTS[currency]
        records = fetch_socrata_data(LEGACY_DATASET_ID, contract_code, limit=weeks)

        net_positions = []
        for record in records:
            noncomm_long = int(record.get("noncomm_positions_long_all", 0))
            noncomm_short = int(record.get("noncomm_positions_short_all", 0))
            net_positions.append(noncomm_long - noncomm_short)

        return net_positions

    except Exception as e:
        logger.warning("Failed to fetch historical data for %s: %s", currency, e)
        return []


def compute_cot_indices(all_legacy: list[dict]) -> dict:
    """
    Compute COT indices and 12-week trends for all currencies.

    Args:
        all_legacy: List of all legacy records

    Returns:
        Dict mapping currency code to {index, trend_12w}
    """
    indices = {}

    for record in all_legacy:
        currency = record["currency"]

        # Fetch 12-week trend data
        historical_net = fetch_historical_net(currency, weeks=12)

        if len(historical_net) >= 12:
            # Compute normalized indices for 12-week trend
            trend_12w = []
            for net in historical_net:
                # Use same normalization as main index
                min_net = min(historical_net)
                max_net = max(historical_net)
                if max_net > min_net:
                    normalized = ((net - min_net) / (max_net - min_net)) * 100
                else:
                    normalized = 50.0
                trend_12w.append(round(normalized, 2))

            indices[currency] = {
                "index": record["cot_index_52w"],
                "trend_12w": trend_12w[:12],  # Ensure exactly 12 values
            }
        else:
            # Fallback if insufficient data
            indices[currency] = {
                "index": record["cot_index_52w"],
                "trend_12w": [record["cot_index_52w"]] * 12,
            }

    return indices


def validate_output(data: dict) -> bool:
    """
    Validate COT report before writing.

    Args:
        data: The complete COT report dict

    Returns:
        True if valid, False otherwise
    """
    # Check required top-level keys
    required_keys = ["reportDate", "publishDate", "source", "legacy", "tff", "cot_indices"]
    for key in required_keys:
        if key not in data:
            logger.error("Missing required key: %s", key)
            return False

    # Check we have 8 currencies
    if len(data["legacy"]) != 8:
        logger.error("Expected 8 legacy records, got %d", len(data["legacy"]))
        return False

    if len(data["tff"]) != 8:
        logger.error("Expected 8 TFF records, got %d", len(data["tff"]))
        return False

    # Check no null values in required fields
    for record in data["legacy"]:
        if any(record[key] is None for key in ["noncomm_long", "noncomm_short", "open_interest"]):
            logger.error("Null value in legacy record for %s", record.get("currency"))
            return False

    for record in data["tff"]:
        if any(record[key] is None for key in ["lev_funds_long", "lev_funds_short"]):
            logger.error("Null value in TFF record for %s", record.get("currency"))
            return False

    logger.info("Validation passed")
    return True


def main() -> int:
    """Main execution function."""
    logger.info("=== Starting COT data fetch ===")

    try:
        # Determine expected report dates
        publish_friday = get_latest_friday()
        report_tuesday = get_report_date_for_friday(publish_friday)

        logger.info("Report date: %s (publish: %s)", report_tuesday, publish_friday)

        # Fetch Legacy COT data for all currencies
        legacy_records = []
        for currency, contract_code in CURRENCY_CONTRACTS.items():
            logger.info("Fetching Legacy COT for %s", currency)

            # Fetch historical data for computing indices
            historical_net = fetch_historical_net(currency, weeks=52)

            # Fetch latest record
            records = fetch_socrata_data(LEGACY_DATASET_ID, contract_code, limit=1)
            if not records:
                logger.error("No Legacy COT data for %s", currency)
                emit_alert(
                    "MISSING_DATA",
                    f"No Legacy COT data for {currency}",
                    "HIGH",
                    currency=currency,
                )
                return EXIT_FAILED

            latest = records[0]
            parsed = parse_legacy_record(latest, currency, historical_net)
            legacy_records.append(parsed)

        # Fetch TFF data for all currencies
        tff_records = []
        for currency, contract_code in CURRENCY_CONTRACTS.items():
            logger.info("Fetching TFF COT for %s", currency)

            records = fetch_socrata_data(TFF_DATASET_ID, contract_code, limit=1)
            if not records:
                logger.error("No TFF data for %s", currency)
                emit_alert(
                    "MISSING_DATA",
                    f"No TFF data for {currency}",
                    "HIGH",
                    currency=currency,
                )
                return EXIT_FAILED

            latest = records[0]
            parsed = parse_tff_record(latest, currency)
            tff_records.append(parsed)

        # Compute COT indices
        logger.info("Computing COT indices and trends")
        cot_indices = compute_cot_indices(legacy_records)

        # Assemble final report
        report = {
            "reportDate": report_tuesday.isoformat(),
            "publishDate": publish_friday.isoformat(),
            "source": "CFTC_LEGACY_TFF",
            "legacy": legacy_records,
            "tff": tff_records,
            "cot_indices": cot_indices,
        }

        # Validate before writing
        if not validate_output(report):
            logger.error("Output validation failed")
            return EXIT_FAILED

        # Check data freshness
        freshness = check_freshness(report_tuesday)
        if freshness["is_stale"]:
            emit_alert(
                "DATA_SOURCE_STALE",
                f"COT data is {freshness['freshness_days']} days old",
                "HIGH",
                context={"report_date": report_tuesday.isoformat()},
            )

        # Write output
        output_path = "data/cot-latest.json"
        write_output(report, output_path)

        logger.info("=== COT data fetch completed successfully ===")
        return EXIT_SUCCESS

    except requests.RequestException as e:
        logger.error("API request failed: %s", e)
        emit_alert(
            "MISSING_DATA",
            f"CFTC API request failed: {str(e)}",
            "HIGH",
        )
        return EXIT_FAILED

    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
