"""
Unit tests for backend/utils/lag_rules.py

Validates PUBLICATION_LAG dictionary entries and get_valid_date_for()
calculations against known expected values from System Design Section 5.2.
"""

import pytest
from datetime import date
from backend.utils.lag_rules import (
    PUBLICATION_LAG,
    SUPPORTED_SERIES_TYPES,
    get_lag_description,
    get_valid_date_for,
)


class TestPublicationLagDict:
    """Verify PUBLICATION_LAG dict completeness and structure."""

    EXPECTED_SERIES = {"cpi", "gdp", "pmi", "policy_rate", "cot", "price", "yield_10y"}

    def test_should_contain_all_expected_series(self):
        assert set(PUBLICATION_LAG.keys()) == self.EXPECTED_SERIES

    def test_should_have_unit_and_lag_for_each_entry(self):
        for series, rule in PUBLICATION_LAG.items():
            assert "unit" in rule, f"{series} missing 'unit'"
            assert "lag" in rule, f"{series} missing 'lag'"

    def test_should_have_valid_units(self):
        valid_units = {"month", "quarter", "day"}
        for series, rule in PUBLICATION_LAG.items():
            assert rule["unit"] in valid_units, (
                f"{series} has invalid unit '{rule['unit']}'"
            )

    def test_supported_series_types_should_match_keys(self):
        assert SUPPORTED_SERIES_TYPES == frozenset(PUBLICATION_LAG.keys())


class TestGetValidDateFor:
    """Verify get_valid_date_for() lag calculations."""

    # Reference date from System Design Section 5.2 tests
    REFERENCE_DATE = date(2026, 3, 21)

    def test_should_return_correct_date_for_cpi_with_2_month_lag(self):
        # CPI has -2 month lag
        result = get_valid_date_for("cpi", self.REFERENCE_DATE)
        assert result == date(2026, 1, 21)

    def test_should_return_same_date_for_policy_rate_with_zero_lag(self):
        # policy_rate has 0 month lag
        result = get_valid_date_for("policy_rate", self.REFERENCE_DATE)
        assert result == date(2026, 3, 21)

    def test_should_return_correct_date_for_cot_with_3_day_lag(self):
        # COT has -3 day lag (published Friday for Tuesday close)
        result = get_valid_date_for("cot", self.REFERENCE_DATE)
        assert result == date(2026, 3, 18)

    def test_should_return_same_date_for_price_with_zero_lag(self):
        result = get_valid_date_for("price", self.REFERENCE_DATE)
        assert result == date(2026, 3, 21)

    def test_should_return_same_date_for_yield_with_zero_lag(self):
        result = get_valid_date_for("yield_10y", self.REFERENCE_DATE)
        assert result == date(2026, 3, 21)

    def test_should_return_correct_date_for_pmi_with_1_month_lag(self):
        result = get_valid_date_for("pmi", self.REFERENCE_DATE)
        assert result == date(2026, 2, 21)

    def test_should_return_correct_date_for_gdp_with_1_quarter_lag(self):
        # GDP has -1 quarter lag = -3 months
        result = get_valid_date_for("gdp", self.REFERENCE_DATE)
        assert result == date(2025, 12, 21)

    def test_should_raise_value_error_for_unknown_series(self):
        with pytest.raises(ValueError, match="Unknown series_type"):
            get_valid_date_for("unknown_series", self.REFERENCE_DATE)

    def test_should_handle_year_boundary_correctly(self):
        # CPI at Jan 15 → Nov 15 of previous year
        result = get_valid_date_for("cpi", date(2026, 1, 15))
        assert result == date(2025, 11, 15)

    def test_should_handle_month_end_dates(self):
        # CPI at Mar 31 → Jan 31
        result = get_valid_date_for("cpi", date(2026, 3, 31))
        assert result == date(2026, 1, 31)


class TestGetLagDescription:
    """Verify human-readable lag descriptions."""

    def test_should_describe_real_time_series(self):
        desc = get_lag_description("price")
        assert "real-time" in desc.lower() or "no lag" in desc.lower()

    def test_should_describe_month_lag(self):
        desc = get_lag_description("cpi")
        assert "2" in desc and "month" in desc

    def test_should_describe_quarter_lag(self):
        desc = get_lag_description("gdp")
        assert "quarter" in desc

    def test_should_raise_for_unknown_series(self):
        with pytest.raises(ValueError):
            get_lag_description("invalid")
