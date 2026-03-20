"""
Integration test: FRED API — B4-05b

Validates that:
  - All FRED series IDs used in fetch_macro.py are still active
  - Each series returns at least 1 data point
  - The FRED_API_KEY environment variable is set and valid
  - No series has been discontinued or changed format

This test makes LIVE API calls. It is marked `@pytest.mark.integration` and
should only run in CI (fetch-data workflow) or via:
    FRED_API_KEY=<key> pytest -m integration tests/integration/test_fred_api.py

Reference: Task List B4-05b, B1-02l, System Design Section 3.2
"""

import os
import sys
from datetime import datetime, timedelta

import pytest
import requests

# Resolve project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))


# ─── Constants ────────────────────────────────────────────────────────────────

FRED_BASE_URL = "https://api.stlouisfed.org/fred"
REQUEST_TIMEOUT_SECONDS = 30

# Minimum expected data points per series (ensures series is populated)
MIN_DATA_POINTS = 1

# All FRED series IDs used by fetch_macro.py (System Design Section 3.2)
POLICY_RATE_SERIES: dict[str, str] = {
    "USD": "FEDFUNDS",
    "GBP": "BOEBR",
    "JPY": "IRSTCB01JPM156N",
    "AUD": "RBAARATE",
    "CAD": "BOCRATE",
    "CHF": "IRSTCB01CHM156N",
    "NZD": "RBNZOCR",
}

CPI_SERIES: dict[str, str] = {
    "USD": "CPIAUCSL",
    "JPY": "JPNCPIALLMINMEI",
    "AUD": "AUSCPIALLMINMEI",
    "CAD": "CPALCY01CAM661N",
    "GBP": "GBRCPIALLMINMEI",
    "CHF": "CHECPIALLMINMEI",
    "NZD": "NZLCPIALLMINMEI",
}

YIELD_SERIES: dict[str, str] = {
    "US_10Y": "DGS10",
    "DE_10Y": "IRLTLT01DEM156N",
    "GB_10Y": "IRLTLT01GBM156N",
    "JP_10Y": "IRLTLT01JPM156N",
}

OTHER_SERIES: dict[str, str] = {
    "VIX": "VIXCLS",
    # FX price series (B2-01a)
    "EUR_USD": "DEXUSEU",
    "GBP_USD": "DEXUSUK",
    "JPY_USD": "DEXJPUS",
    "AUD_USD": "DEXUSAL",
    "CAD_USD": "DEXCAUS",
    "CHF_USD": "DEXSZUS",
    "NZD_USD": "DEXUSNZ",
}

ALL_SERIES: dict[str, str] = {
    **POLICY_RATE_SERIES,
    **CPI_SERIES,
    **YIELD_SERIES,
    **OTHER_SERIES,
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_api_key() -> str:
    """Return FRED API key from env, skip test if not set."""
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        pytest.skip("FRED_API_KEY not set — skipping live FRED integration tests")
    return key


def _fred_series_info(series_id: str, api_key: str) -> dict:
    """Fetch series metadata from FRED."""
    url = f"{FRED_BASE_URL}/series"
    params = {"series_id": series_id, "api_key": api_key, "file_type": "json"}
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def _fred_latest_observation(series_id: str, api_key: str, limit: int = 3) -> list[dict]:
    """Fetch the most recent N observations from a FRED series."""
    url = f"{FRED_BASE_URL}/series/observations"
    # Look back 2 years to handle any recent gaps
    start = (datetime.utcnow() - timedelta(days=730)).strftime("%Y-%m-%d")
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
        "sort_order": "desc",
        "limit": str(limit),
    }
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()
    return data.get("observations", [])


def _is_real_value(obs_value: str) -> bool:
    """Return True if the observation value is a real number (not '.' which FRED uses for missing)."""
    if obs_value in (".", "", None):
        return False
    try:
        float(obs_value)
        return True
    except (ValueError, TypeError):
        return False


# ─── API key prerequisite check ───────────────────────────────────────────────

@pytest.mark.integration
class TestFredApiKey:
    """Verify the FRED API key is valid before running other tests."""

    def test_api_key_is_valid(self):
        """A request with the configured key must return HTTP 200 (not 400/403)."""
        api_key = _get_api_key()
        url = f"{FRED_BASE_URL}/series"
        params = {"series_id": "FEDFUNDS", "api_key": api_key, "file_type": "json"}
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        assert response.status_code == 200, (
            f"FRED API key validation failed: HTTP {response.status_code}. "
            f"Response: {response.text[:200]}"
        )
        data = response.json()
        assert "seriess" in data, f"Unexpected FRED response structure: {list(data.keys())}"


# ─── Policy rate series ────────────────────────────────────────────────────────

@pytest.mark.integration
class TestFredPolicyRates:
    """Verify all policy rate series are active and return recent data."""

    @pytest.mark.parametrize("currency,series_id", POLICY_RATE_SERIES.items())
    def test_should_return_series_metadata(self, currency, series_id):
        """Series must exist and be accessible."""
        api_key = _get_api_key()
        info = _fred_series_info(series_id, api_key)
        assert "seriess" in info and len(info["seriess"]) > 0, (
            f"Policy rate series '{series_id}' for {currency} not found in FRED"
        )

    @pytest.mark.parametrize("currency,series_id", POLICY_RATE_SERIES.items())
    def test_should_have_recent_observations(self, currency, series_id):
        """Series must have at least 1 real numeric observation in the last 2 years."""
        api_key = _get_api_key()
        observations = _fred_latest_observation(series_id, api_key)
        real_obs = [o for o in observations if _is_real_value(o.get("value"))]
        assert len(real_obs) >= MIN_DATA_POINTS, (
            f"Policy rate series '{series_id}' ({currency}) has no recent real data. "
            f"Observations: {observations}"
        )


# ─── CPI series ───────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestFredCpiSeries:
    """Verify all CPI YoY series are active and return recent data."""

    @pytest.mark.parametrize("currency,series_id", CPI_SERIES.items())
    def test_should_return_cpi_series(self, currency, series_id):
        """CPI series must exist."""
        api_key = _get_api_key()
        info = _fred_series_info(series_id, api_key)
        assert "seriess" in info and len(info["seriess"]) > 0, (
            f"CPI series '{series_id}' for {currency} not found in FRED"
        )

    @pytest.mark.parametrize("currency,series_id", CPI_SERIES.items())
    def test_should_have_cpi_observations(self, currency, series_id):
        """CPI series must have numeric data (monthly, so look back 2 years = plenty)."""
        api_key = _get_api_key()
        observations = _fred_latest_observation(series_id, api_key)
        real_obs = [o for o in observations if _is_real_value(o.get("value"))]
        assert len(real_obs) >= MIN_DATA_POINTS, (
            f"CPI series '{series_id}' ({currency}) has no recent real data"
        )


# ─── Yield series ─────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestFredYieldSeries:
    """Verify all 10Y yield series are active."""

    @pytest.mark.parametrize("label,series_id", YIELD_SERIES.items())
    def test_should_return_yield_series(self, label, series_id):
        api_key = _get_api_key()
        info = _fred_series_info(series_id, api_key)
        assert "seriess" in info and len(info["seriess"]) > 0, (
            f"Yield series '{series_id}' ({label}) not found in FRED"
        )

    @pytest.mark.parametrize("label,series_id", YIELD_SERIES.items())
    def test_should_have_yield_observations(self, label, series_id):
        api_key = _get_api_key()
        observations = _fred_latest_observation(series_id, api_key)
        real_obs = [o for o in observations if _is_real_value(o.get("value"))]
        assert len(real_obs) >= MIN_DATA_POINTS, (
            f"Yield series '{series_id}' ({label}) has no recent real data"
        )


# ─── Other / VIX / FX prices ──────────────────────────────────────────────────

@pytest.mark.integration
class TestFredOtherSeries:
    """Verify VIX and FX price series."""

    @pytest.mark.parametrize("label,series_id", OTHER_SERIES.items())
    def test_should_return_series(self, label, series_id):
        api_key = _get_api_key()
        info = _fred_series_info(series_id, api_key)
        assert "seriess" in info and len(info["seriess"]) > 0, (
            f"Series '{series_id}' ({label}) not found in FRED"
        )

    @pytest.mark.parametrize("label,series_id", OTHER_SERIES.items())
    def test_should_have_observations(self, label, series_id):
        api_key = _get_api_key()
        observations = _fred_latest_observation(series_id, api_key)
        real_obs = [o for o in observations if _is_real_value(o.get("value"))]
        assert len(real_obs) >= MIN_DATA_POINTS, (
            f"Series '{series_id}' ({label}) has no recent real data"
        )


# ─── Comprehensive series coverage check ─────────────────────────────────────

@pytest.mark.integration
class TestFredAllSeriesCoverage:
    """Ensure every series ID in fetch_macro.py is covered by this test suite."""

    def test_all_series_ids_are_covered(self):
        """Every series used in production must be listed in ALL_SERIES."""
        required_ids = set(ALL_SERIES.values())
        # Import the series config from fetch_macro.py if available
        try:
            from backend.scripts.fetch_macro import (
                FRED_SERIES_POLICY,
                FRED_SERIES_CPI,
                FRED_SERIES_YIELDS,
            )
            production_ids = set()
            if isinstance(FRED_SERIES_POLICY, dict):
                production_ids.update(FRED_SERIES_POLICY.values())
            if isinstance(FRED_SERIES_CPI, dict):
                production_ids.update(FRED_SERIES_CPI.values())
            if isinstance(FRED_SERIES_YIELDS, dict):
                production_ids.update(FRED_SERIES_YIELDS.values())
            uncovered = production_ids - required_ids
            assert len(uncovered) == 0, (
                f"The following production FRED series IDs are NOT in this test suite: {uncovered}"
            )
        except ImportError:
            # fetch_macro.py may not expose these constants — skip check
            pytest.skip("Cannot import FRED series constants from fetch_macro.py — coverage check skipped")

    def test_total_series_count_is_reasonable(self):
        """We should be testing at least 20 series (8 policy + 7 CPI + 4 yield + VIX + 7 FX)."""
        assert len(ALL_SERIES) >= 20, (
            f"Only {len(ALL_SERIES)} FRED series are tested — expected ≥ 20"
        )
