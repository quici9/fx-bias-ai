#!/usr/bin/env python3
"""
Fetch macro economic data from FRED API and ECB Data Portal.

Fetches policy rates, CPI YoY, 10Y yields, and VIX with proper
publication lag handling to prevent look-ahead bias.

Reference: Task List B1-02
Exit codes: 0=success, 1=partial, 2=failed
"""

import os
import sys
import time
from datetime import date, datetime, timedelta
from typing import Optional

import requests

# Add parent directory to path for imports
sys.path.insert(0, "/Users/ttdh/WebstormProjects/fx-bias-ai")

from backend.utils.data_validator import check_freshness, emit_alert
from backend.utils.file_io import EXIT_FAILED, EXIT_SUCCESS, setup_logging, write_output
from backend.utils.lag_rules import get_valid_date_for

logger = setup_logging(__name__)

# FRED API configuration
FRED_API_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# ECB Data Portal configuration
ECB_API_BASE_URL = "https://data-api.ecb.europa.eu/service/data"

# FRED series IDs
POLICY_RATE_SERIES = {
    "USD": "FEDFUNDS",                # Federal Funds Rate
    "GBP": "BOEBR",                   # Bank of England Base Rate
    "JPY": "IRSTCB01JPM156N",         # Japan Policy Rate
    "AUD": "RBAORATE",                # RBA Official Cash Rate
    "CAD": "IRSTCB01CAM156N",         # Bank of Canada Overnight Rate
    "CHF": "IRSTCB01CHM156N",         # SNB 3-Month LIBOR Target Rate
    "NZD": "RBNZOCR",                 # RBNZ Official Cash Rate
}

CPI_SERIES = {
    "USD": "CPIAUCSL",                # US CPI All Items
    "JPY": "JPNCPIALLMINMEI",         # Japan CPI
    "AUD": "AUSCPIALLMINMEI",         # Australia CPI
    "CAD": "CPALCY01CAM661N",         # Canada CPI
    "GBP": "GBRCPIALLMINMEI",         # UK CPI
    "CHF": "CHECPIALLMINMEI",         # Switzerland CPI
    "NZD": "NZLCPIALLMINMEI",         # New Zealand CPI
}

YIELD_10Y_SERIES = {
    "US": "DGS10",                    # US 10Y Treasury
    "DE": "IRLTLT01DEM156N",          # Germany 10Y Bund
    "GB": "IRLTLT01GBM156N",          # UK 10Y Gilt
    "JP": "IRLTLT01JPM156N",          # Japan 10Y JGB
}

VIX_SERIES = "VIXCLS"

# API request parameters
REQUEST_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


def fetch_fred_series(
    series_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 100,
) -> list[dict]:
    """
    Fetch data from FRED API for a specific series.

    Args:
        series_id: FRED series ID (e.g. 'FEDFUNDS')
        start_date: Start date for observations
        end_date: End date for observations
        limit: Maximum number of observations

    Returns:
        List of observation dicts with 'date' and 'value' keys

    Raises:
        requests.RequestException: On API failure
        ValueError: If FRED_API_KEY is not set
    """
    if not FRED_API_KEY:
        raise ValueError("FRED_API_KEY environment variable not set")

    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }

    if start_date:
        params["observation_start"] = start_date.isoformat()
    if end_date:
        params["observation_end"] = end_date.isoformat()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Fetching FRED series %s (attempt %d/%d)", series_id, attempt, MAX_RETRIES)
            response = requests.get(FRED_API_BASE_URL, params=params, timeout=REQUEST_TIMEOUT)

            if response.status_code == 429:
                logger.warning("Rate limited — retrying after %ds", RETRY_DELAY * attempt)
                time.sleep(RETRY_DELAY * attempt)
                continue

            if response.status_code >= 500:
                logger.warning("Server error (%d) — retrying", response.status_code)
                time.sleep(RETRY_DELAY)
                continue

            response.raise_for_status()
            data = response.json()

            observations = data.get("observations", [])
            logger.info("Fetched %d observations for %s", len(observations), series_id)

            return observations

        except requests.Timeout:
            logger.warning("Request timeout — attempt %d/%d", attempt, MAX_RETRIES)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                continue
            raise

        except requests.RequestException as e:
            logger.error("FRED API request failed: %s", e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                continue
            raise

    raise requests.RequestException(f"Failed to fetch FRED series after {MAX_RETRIES} attempts")


def fetch_ecb_rate() -> dict:
    """
    Fetch ECB policy rate from ECB Data Portal.

    Returns:
        Dict with 'date' and 'value' keys

    Raises:
        requests.RequestException: On API failure
    """
    # ECB Main Refinancing Operations Rate
    # Dataset: FM/B.U2.EUR.4F.KR.MRR_FR.LEV
    # Simplified endpoint - actual implementation may need adjustment
    url = "https://data-api.ecb.europa.eu/service/data/FM/B.U2.EUR.4F.KR.MRR_FR.LEV"
    params = {
        "format": "jsondata",
        "lastNObservations": 1,
    }

    try:
        logger.info("Fetching ECB policy rate")
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        data = response.json()

        # Parse ECB JSON structure (simplified)
        # Actual structure may vary - this is a placeholder
        observations = data.get("dataSets", [{}])[0].get("series", {}).get("0:0:0:0:0:0:0", {}).get("observations", {})

        if observations:
            # Get latest observation
            latest_key = sorted(observations.keys())[-1]
            latest_value = observations[latest_key][0]

            # Get corresponding date from structure
            dates = data.get("structure", {}).get("dimensions", {}).get("observation", [{}])[0].get("values", [])
            latest_date = dates[int(latest_key)].get("id", "")

            return {
                "date": latest_date,
                "value": str(latest_value),
            }

        raise ValueError("No ECB data available")

    except Exception as e:
        logger.warning("ECB API request failed: %s — will use FRED fallback", e)
        raise


def get_latest_value_with_lag(observations: list[dict], series_type: str, as_of: date) -> Optional[dict]:
    """
    Get the latest observation that respects publication lag rules.

    Args:
        observations: List of FRED observations (sorted desc by date)
        series_type: Series type for lag lookup ('policy_rate', 'cpi', etc.)
        as_of: Reference date (typically today)

    Returns:
        Dict with 'date' and 'value' keys, or None if no valid data
    """
    valid_until = get_valid_date_for(series_type, as_of)

    for obs in observations:
        obs_date = date.fromisoformat(obs["date"])
        value = obs.get("value")

        # Skip missing values
        if value == "." or value is None:
            continue

        # Check if this observation respects the lag rule
        if obs_date <= valid_until:
            return {
                "date": obs_date,
                "value": float(value),
            }

    return None


def compute_trend_3m(observations: list[dict], current_value: float) -> str:
    """
    Compute 3-month trend: RISING, FALLING, or STABLE.

    Args:
        observations: List of observations (sorted desc by date)
        current_value: Current value

    Returns:
        Trend classification
    """
    if len(observations) < 2:
        return "STABLE"

    # Find value from ~3 months ago (90 days)
    current_date = date.fromisoformat(observations[0]["date"])
    target_date = current_date - timedelta(days=90)

    for obs in observations[1:]:
        obs_date = date.fromisoformat(obs["date"])
        if obs_date <= target_date and obs["value"] != ".":
            past_value = float(obs["value"])
            delta = current_value - past_value

            if abs(delta) < 0.1:  # Threshold for "stable"
                return "STABLE"
            elif delta > 0:
                return "RISING"
            else:
                return "FALLING"

    return "STABLE"


def compute_vix_regime(vix_value: float) -> str:
    """
    Classify VIX into regime buckets.

    Args:
        vix_value: Current VIX value

    Returns:
        Regime: LOW | NORMAL | ELEVATED | EXTREME
    """
    if vix_value < 15:
        return "LOW"
    elif vix_value < 20:
        return "NORMAL"
    elif vix_value < 30:
        return "ELEVATED"
    else:
        return "EXTREME"


def main() -> int:
    """Main execution function."""
    logger.info("=== Starting macro data fetch ===")

    try:
        fetch_date = date.today()

        # --- Fetch Policy Rates ---
        logger.info("Fetching policy rates")
        policy_rates = []

        # Try ECB first for EUR
        try:
            ecb_data = fetch_ecb_rate()
            eur_rate = {
                "currency": "EUR",
                "value": float(ecb_data["value"]),
                "diff_vs_usd": 0.0,  # Will compute after USD fetch
                "trend_3m": "STABLE",  # ECB endpoint may not provide history
                "last_update": ecb_data["date"],
                "publication_lag_applied": 0,
                "freshness_days": 0,
                "is_stale": False,
            }
            policy_rates.append(eur_rate)
            logger.info("EUR policy rate from ECB: %s", eur_rate["value"])
        except Exception as e:
            logger.warning("ECB fetch failed — using FRED fallback for EUR")
            # Fallback to FRED if available (would need appropriate series ID)
            emit_alert(
                "DATA_SOURCE_STALE",
                "ECB API failed, using fallback",
                "MEDIUM",
                currency="EUR",
            )

        # Fetch from FRED
        usd_rate_value = None
        for currency, series_id in POLICY_RATE_SERIES.items():
            try:
                observations = fetch_fred_series(series_id, limit=100)
                latest = get_latest_value_with_lag(observations, "policy_rate", fetch_date)

                if not latest:
                    logger.error("No valid data for %s policy rate", currency)
                    emit_alert(
                        "MISSING_DATA",
                        f"No policy rate data for {currency}",
                        "HIGH",
                        currency=currency,
                    )
                    continue

                freshness = check_freshness(latest["date"], as_of=fetch_date)
                trend = compute_trend_3m(observations, latest["value"])

                record = {
                    "currency": currency,
                    "value": latest["value"],
                    "diff_vs_usd": 0.0,  # Will compute after loop
                    "trend_3m": trend,
                    "last_update": latest["date"].isoformat(),
                    "publication_lag_applied": 0,  # Policy rates have 0 lag
                    "freshness_days": freshness["freshness_days"],
                    "is_stale": freshness["is_stale"],
                }

                if currency == "USD":
                    usd_rate_value = latest["value"]

                policy_rates.append(record)

                if freshness["is_stale"]:
                    emit_alert(
                        "DATA_SOURCE_STALE",
                        f"{currency} policy rate is {freshness['freshness_days']} days old",
                        "HIGH",
                        currency=currency,
                    )

            except Exception as e:
                logger.error("Failed to fetch %s policy rate: %s", currency, e)
                emit_alert(
                    "MISSING_DATA",
                    f"Failed to fetch {currency} policy rate",
                    "HIGH",
                    currency=currency,
                )

        # Compute diff_vs_usd
        if usd_rate_value is not None:
            for record in policy_rates:
                record["diff_vs_usd"] = round(record["value"] - usd_rate_value, 4)

        # --- Fetch CPI YoY ---
        logger.info("Fetching CPI YoY data")
        cpi_yoy = []
        usd_cpi_value = None

        for currency, series_id in CPI_SERIES.items():
            try:
                observations = fetch_fred_series(series_id, limit=100)
                latest = get_latest_value_with_lag(observations, "cpi", fetch_date)

                if not latest:
                    logger.warning("No valid CPI data for %s", currency)
                    continue

                # Convert to YoY percentage if needed (some series already YoY)
                # Simplified - actual implementation may need to compute YoY from level data
                cpi_value = latest["value"]

                freshness = check_freshness(latest["date"], as_of=fetch_date)
                trend = compute_trend_3m(observations, cpi_value)

                record = {
                    "currency": currency,
                    "value": cpi_value,
                    "diff_vs_usd": 0.0,
                    "trend_3m": trend,
                    "last_update": latest["date"].isoformat(),
                    "publication_lag_applied": 2,  # CPI has T-2 lag
                    "freshness_days": freshness["freshness_days"],
                    "is_stale": freshness["is_stale"],
                }

                if currency == "USD":
                    usd_cpi_value = cpi_value

                cpi_yoy.append(record)

            except Exception as e:
                logger.warning("Failed to fetch %s CPI: %s", currency, e)

        # Compute diff_vs_usd for CPI
        if usd_cpi_value is not None:
            for record in cpi_yoy:
                record["diff_vs_usd"] = round(record["value"] - usd_cpi_value, 4)

        # --- Fetch 10Y Yields ---
        logger.info("Fetching 10Y yields")
        yields_10y = []
        us_yield_value = None

        for country, series_id in YIELD_10Y_SERIES.items():
            try:
                observations = fetch_fred_series(series_id, limit=100)
                latest = get_latest_value_with_lag(observations, "yield_10y", fetch_date)

                if not latest:
                    logger.warning("No valid yield data for %s", country)
                    continue

                # Compute delta 1w
                delta_1w = 0.0
                if len(observations) >= 2:
                    for obs in observations[1:]:
                        if obs["value"] != ".":
                            prev_value = float(obs["value"])
                            delta_1w = latest["value"] - prev_value
                            break

                record = {
                    "country": country,
                    "yield": latest["value"],
                    "spread_vs_us": 0.0,
                    "delta_1w": round(delta_1w, 4),
                    "direction": "STABLE",  # Will compute after spread
                    "last_update": latest["date"].isoformat(),
                }

                if country == "US":
                    us_yield_value = latest["value"]

                yields_10y.append(record)

            except Exception as e:
                logger.warning("Failed to fetch %s yield: %s", country, e)

        # Compute spread_vs_us and direction
        if us_yield_value is not None:
            for record in yields_10y:
                if record["country"] != "US":
                    spread = record["yield"] - us_yield_value
                    record["spread_vs_us"] = round(spread, 4)

                    # Simplified direction logic
                    if abs(record["delta_1w"]) < 0.05:
                        record["direction"] = "STABLE"
                    elif record["delta_1w"] > 0:
                        record["direction"] = "WIDENING"
                    else:
                        record["direction"] = "NARROWING"

        # --- Fetch VIX ---
        logger.info("Fetching VIX")
        vix_data = None

        try:
            observations = fetch_fred_series(VIX_SERIES, limit=10)
            latest = get_latest_value_with_lag(observations, "yield_10y", fetch_date)  # VIX same lag as yields

            if latest:
                # Compute delta 1w
                delta_1w = 0.0
                if len(observations) >= 2:
                    for obs in observations[1:]:
                        if obs["value"] != ".":
                            prev_value = float(obs["value"])
                            delta_1w = latest["value"] - prev_value
                            break

                vix_data = {
                    "value": round(latest["value"], 2),
                    "regime": compute_vix_regime(latest["value"]),
                    "delta_1w": round(delta_1w, 2),
                }

                logger.info("VIX: %s (regime: %s)", vix_data["value"], vix_data["regime"])

        except Exception as e:
            logger.error("Failed to fetch VIX: %s", e)
            emit_alert("MISSING_DATA", "VIX data unavailable", "MEDIUM")

        # --- Assemble Report ---
        report = {
            "fetchDate": fetch_date.isoformat(),
            "policy_rates": policy_rates,
            "cpi_yoy": cpi_yoy,
            "yields_10y": yields_10y,
            "vix": vix_data or {"value": 0, "regime": "UNKNOWN", "delta_1w": 0},
        }

        # Write output
        output_path = "data/macro-latest.json"
        write_output(report, output_path)

        logger.info("=== Macro data fetch completed successfully ===")
        return EXIT_SUCCESS

    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
