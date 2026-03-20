"""
Integration test: CFTC Socrata API — B4-05a

Validates that:
  - The CFTC Socrata endpoint is reachable
  - The response contains all 8 expected currencies
  - Required Legacy COT fields are present (noncomm_long, noncomm_short, open_interest_all)
  - TFF fields are present (lev_money_long/short, asset_mgr_long/short)
  - A real API response can be parsed without error

This test makes LIVE API calls. It is marked `@pytest.mark.integration` and
should only run in CI (fetch-data workflow) or via:
    pytest -m integration tests/integration/test_cftc_api.py

Reference: Task List B4-05a, System Design Section 3.1
"""

import os
import sys
from typing import Any

import pytest
import requests

# Resolve project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))


# ─── Constants ────────────────────────────────────────────────────────────────

SOCRATA_LEGACY_URL = (
    "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
)
SOCRATA_TFF_URL = (
    "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
)

# CFTC market codes for the 8 major FX futures
EXPECTED_CURRENCIES = {"EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "USD"}

# Futures market_and_exchange_names that map to our currencies
CURRENCY_MARKET_CODES: dict[str, str] = {
    "EUR": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
    "GBP": "BRITISH POUND STERLING - CHICAGO MERCANTILE EXCHANGE",
    "JPY": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE",
    "AUD": "AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "CAD": "CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "CHF": "SWISS FRANC - CHICAGO MERCANTILE EXCHANGE",
    "NZD": "NEW ZEALAND DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "USD": "U.S. DOLLAR INDEX - ICE FUTURES U.S.",
}

LEGACY_REQUIRED_FIELDS = [
    "noncomm_positions_long_all",
    "noncomm_positions_short_all",
    "open_interest_all",
    "report_date_as_yyyy_mm_dd",
    "market_and_exchange_names",
]

TFF_REQUIRED_FIELDS = [
    "lev_money_positions_long",
    "lev_money_positions_short",
    "asset_mgr_positions_long",
    "asset_mgr_positions_short",
    "dealer_positions_long_all",
    "dealer_positions_short_all",
    "report_date_as_yyyy_mm_dd",
    "market_and_exchange_names",
]

REQUEST_TIMEOUT_SECONDS = 30


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _fetch_latest_cot(url: str, market_name: str) -> list[dict[str, Any]]:
    """Fetch the latest record for a single market from CFTC Socrata."""
    params = {
        "$where": f"market_and_exchange_names='{market_name}'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": "1",
    }
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


# ─── Live API tests ────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestCftcLegacyCotApi:
    """Verify CFTC Legacy COT Socrata endpoint returns valid, complete data."""

    def test_should_reach_socrata_endpoint(self):
        """Endpoint must be reachable (HTTP 200)."""
        params = {"$limit": "1"}
        response = requests.get(SOCRATA_LEGACY_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        assert response.status_code == 200, (
            f"CFTC Socrata Legacy endpoint returned {response.status_code}"
        )

    @pytest.mark.parametrize("currency,market_name", CURRENCY_MARKET_CODES.items())
    def test_should_return_record_for_each_currency(self, currency, market_name):
        """Each of the 8 currencies must have at least one record."""
        records = _fetch_latest_cot(SOCRATA_LEGACY_URL, market_name)
        assert len(records) >= 1, (
            f"No Legacy COT record found for {currency} (market: '{market_name}')"
        )

    @pytest.mark.parametrize("currency,market_name", CURRENCY_MARKET_CODES.items())
    def test_should_have_required_fields_for_each_currency(self, currency, market_name):
        """All required Legacy fields must be present and non-empty."""
        records = _fetch_latest_cot(SOCRATA_LEGACY_URL, market_name)
        assert records, f"No record for {currency}"
        row = records[0]
        for field in LEGACY_REQUIRED_FIELDS:
            assert field in row, f"Missing field '{field}' in Legacy record for {currency}"
            assert row[field] is not None and str(row[field]).strip() != "", (
                f"Field '{field}' is empty in Legacy record for {currency}"
            )

    @pytest.mark.parametrize("currency,market_name", CURRENCY_MARKET_CODES.items())
    def test_should_have_numeric_position_values(self, currency, market_name):
        """Position counts must be parseable as integers."""
        records = _fetch_latest_cot(SOCRATA_LEGACY_URL, market_name)
        assert records
        row = records[0]
        for field in ["noncomm_positions_long_all", "noncomm_positions_short_all", "open_interest_all"]:
            value = row.get(field)
            assert value is not None, f"Missing '{field}' for {currency}"
            try:
                int(float(str(value)))
            except (ValueError, TypeError) as exc:
                pytest.fail(f"Cannot parse '{field}' = '{value}' as int for {currency}: {exc}")


@pytest.mark.integration
class TestCftcTffApi:
    """Verify CFTC TFF (Traders in Financial Futures) Socrata endpoint."""

    def test_should_reach_tff_endpoint(self):
        """TFF endpoint must be reachable (HTTP 200)."""
        params = {"$limit": "1"}
        response = requests.get(SOCRATA_TFF_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        assert response.status_code == 200, (
            f"CFTC Socrata TFF endpoint returned {response.status_code}"
        )

    @pytest.mark.parametrize("currency,market_name", CURRENCY_MARKET_CODES.items())
    def test_should_return_tff_record_for_each_currency(self, currency, market_name):
        """Each currency must have a TFF record."""
        records = _fetch_latest_cot(SOCRATA_TFF_URL, market_name)
        assert len(records) >= 1, (
            f"No TFF record found for {currency} (market: '{market_name}')"
        )

    @pytest.mark.parametrize("currency,market_name", CURRENCY_MARKET_CODES.items())
    def test_should_have_tff_required_fields(self, currency, market_name):
        """All TFF required fields must be present."""
        records = _fetch_latest_cot(SOCRATA_TFF_URL, market_name)
        assert records
        row = records[0]
        for field in TFF_REQUIRED_FIELDS:
            assert field in row, f"Missing TFF field '{field}' for {currency}"

    def test_legacy_and_tff_dates_should_match(self):
        """Latest Legacy and TFF records should have the same report date (released together)."""
        # Test against EUR as a proxy
        market = CURRENCY_MARKET_CODES["EUR"]
        legacy = _fetch_latest_cot(SOCRATA_LEGACY_URL, market)
        tff = _fetch_latest_cot(SOCRATA_TFF_URL, market)
        assert legacy and tff
        legacy_date = legacy[0]["report_date_as_yyyy_mm_dd"][:10]
        tff_date = tff[0]["report_date_as_yyyy_mm_dd"][:10]
        assert legacy_date == tff_date, (
            f"Legacy date ({legacy_date}) != TFF date ({tff_date}) for EUR"
        )
