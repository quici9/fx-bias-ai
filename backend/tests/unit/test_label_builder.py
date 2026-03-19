"""
Unit tests for training/build_labels.py — B2-06c

Tests BULL/BEAR/NEUTRAL label logic for both AND and OR condition definitions,
resampling, direction adjustment, and class distribution analysis.

Reference: Task List B2-01c, B2-01d, B2-01f, B2-01g, B2-06c
"""

import sys
import os
from datetime import date

import numpy as np
import pandas as pd
import pytest

# Add project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from training.build_labels import (
    LABEL_CONFIRMATION_LAG,
    FX_SERIES,
    adjust_for_quoting,
    build_label,
    build_label_or,
    build_labels_for_currency,
    check_class_distribution,
    get_price_direction,
    resample_to_weekly_friday,
)


# ---------------------------------------------------------------------------
# build_label() — AND condition (B2-01c)
# ---------------------------------------------------------------------------

class TestBuildLabelAnd:
    def test_bull_both_positive(self):
        assert build_label(1, 1) == "BULL"

    def test_bear_both_negative(self):
        assert build_label(-1, -1) == "BEAR"

    def test_neutral_conflicting_cot_pos_price_neg(self):
        assert build_label(1, -1) == "NEUTRAL"

    def test_neutral_conflicting_cot_neg_price_pos(self):
        assert build_label(-1, 1) == "NEUTRAL"

    def test_neutral_flat_cot(self):
        assert build_label(0, 1) == "NEUTRAL"
        assert build_label(0, -1) == "NEUTRAL"
        assert build_label(0, 0) == "NEUTRAL"

    def test_neutral_flat_price(self):
        assert build_label(1, 0) == "NEUTRAL"
        assert build_label(-1, 0) == "NEUTRAL"

    def test_returns_string(self):
        for cot in (-1, 0, 1):
            for price in (-1, 0, 1):
                result = build_label(cot, price)
                assert isinstance(result, str)
                assert result in ("BULL", "BEAR", "NEUTRAL")


# ---------------------------------------------------------------------------
# build_label_or() — OR condition (B2-01g)
# ---------------------------------------------------------------------------

class TestBuildLabelOr:
    def test_bull_both_positive(self):
        assert build_label_or(1, 1) == "BULL"

    def test_bear_both_negative(self):
        assert build_label_or(-1, -1) == "BEAR"

    def test_neutral_conflicting(self):
        # Conflicting signals → NEUTRAL regardless of OR condition
        assert build_label_or(1, -1) == "NEUTRAL"
        assert build_label_or(-1, 1) == "NEUTRAL"

    def test_bull_cot_pos_price_flat(self):
        assert build_label_or(1, 0) == "BULL"

    def test_bull_cot_flat_price_pos(self):
        assert build_label_or(0, 1) == "BULL"

    def test_bear_cot_neg_price_flat(self):
        assert build_label_or(-1, 0) == "BEAR"

    def test_bear_cot_flat_price_neg(self):
        assert build_label_or(0, -1) == "BEAR"

    def test_neutral_both_flat(self):
        assert build_label_or(0, 0) == "NEUTRAL"

    def test_returns_valid_label(self):
        for cot in (-1, 0, 1):
            for price in (-1, 0, 1):
                result = build_label_or(cot, price)
                assert result in ("BULL", "BEAR", "NEUTRAL")


# ---------------------------------------------------------------------------
# resample_to_weekly_friday()
# ---------------------------------------------------------------------------

class TestResampleToWeeklyFriday:
    def _make_daily(self, start="2006-01-02", periods=20):
        """Daily series Mon–Fri, one price per day."""
        idx = pd.date_range(start=start, periods=periods, freq="B")  # business days
        return pd.Series(range(1, periods + 1), index=idx, dtype=float)

    def test_output_index_all_fridays(self):
        daily = self._make_daily(periods=30)
        weekly = resample_to_weekly_friday(daily)
        assert all(dt.weekday() == 4 for dt in weekly.index), "All dates must be Fridays"

    def test_takes_last_value_of_week(self):
        # 5 business days, Mon–Fri, prices 1–5: Friday close = 5
        idx = pd.date_range("2006-01-02", periods=5, freq="B")
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=idx)
        weekly = resample_to_weekly_friday(s)
        # 2006-01-06 is Friday of that week
        assert weekly.loc["2006-01-06"] == 5.0

    def test_missing_friday_filled(self):
        # Series missing Friday — should forward-fill Thursday's value
        idx = pd.to_datetime(["2006-01-02", "2006-01-03", "2006-01-04", "2006-01-05"])
        s = pd.Series([1.0, 2.0, 3.0, 4.0], index=idx)  # Mon–Thu only
        weekly = resample_to_weekly_friday(s)
        assert weekly.loc["2006-01-06"] == 4.0  # Thursday ffilled to Friday


# ---------------------------------------------------------------------------
# get_price_direction()
# ---------------------------------------------------------------------------

class TestGetPriceDirection:
    def test_positive_direction(self):
        s = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2006-01-06", periods=3, freq="W-FRI"))
        dir_ = get_price_direction(s)
        assert dir_.iloc[0] == 1   # 2.0 > 1.0
        assert dir_.iloc[1] == 1   # 3.0 > 2.0
        assert pd.isna(dir_.iloc[2])  # no T+1

    def test_negative_direction(self):
        s = pd.Series([3.0, 2.0, 1.0], index=pd.date_range("2006-01-06", periods=3, freq="W-FRI"))
        dir_ = get_price_direction(s)
        assert dir_.iloc[0] == -1
        assert dir_.iloc[1] == -1

    def test_flat(self):
        s = pd.Series([1.5, 1.5, 1.5], index=pd.date_range("2006-01-06", periods=3, freq="W-FRI"))
        dir_ = get_price_direction(s)
        assert dir_.iloc[0] == 0
        assert dir_.iloc[1] == 0

    def test_last_row_nan(self):
        s = pd.Series([1.0, 2.0], index=pd.date_range("2006-01-06", periods=2, freq="W-FRI"))
        dir_ = get_price_direction(s)
        assert pd.isna(dir_.iloc[-1])


# ---------------------------------------------------------------------------
# adjust_for_quoting()
# ---------------------------------------------------------------------------

class TestAdjustForQuoting:
    def _make_dir(self, values):
        return pd.Series(values, dtype="Int64")

    def test_quote_usd_true_unchanged(self):
        dir_ = self._make_dir([1, -1, 0])
        result = adjust_for_quoting(dir_, quote_usd=True)
        assert list(result) == [1, -1, 0]

    def test_quote_usd_false_inverted(self):
        dir_ = self._make_dir([1, -1, 0])
        result = adjust_for_quoting(dir_, quote_usd=False)
        assert list(result) == [-1, 1, 0]

    def test_jpy_inverted(self):
        """DEXJPUS: higher = JPY weaker, so +1 price → -1 JPY direction"""
        dir_ = self._make_dir([1])
        result = adjust_for_quoting(dir_, quote_usd=FX_SERIES["JPY"]["quote_usd"])
        assert result.iloc[0] == -1

    def test_eur_unchanged(self):
        """DEXUSEU: higher = EUR stronger, so +1 price → +1 EUR direction"""
        dir_ = self._make_dir([1])
        result = adjust_for_quoting(dir_, quote_usd=FX_SERIES["EUR"]["quote_usd"])
        assert result.iloc[0] == 1


# ---------------------------------------------------------------------------
# build_labels_for_currency() — LABEL_CONFIRMATION_LAG (B2-01d)
# ---------------------------------------------------------------------------

class TestBuildLabelsForCurrency:
    def _make_weekly(self, prices, start="2006-01-06"):
        idx = pd.date_range(start, periods=len(prices), freq="W-FRI")
        return pd.Series(prices, index=idx, dtype=float)

    def test_bull_label_generated(self):
        """COT net up + price up → BULL (skip first row: COT diff=NaN → NEUTRAL)"""
        prices = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
        cot_net = self._make_weekly([100, 200, 300, 400, 500, 600])
        price_series = self._make_weekly(prices)
        ref_date = date(2006, 2, 17)
        labels = build_labels_for_currency(price_series, cot_net, quote_usd=True, reference_date=ref_date)
        # Skip first row (COT diff on first row = NaN → treated as 0 → NEUTRAL)
        assert all(l == "BULL" for l in labels.iloc[1:])

    def test_bear_label_generated(self):
        """COT net down + price down → BEAR (skip first row: COT diff=NaN → NEUTRAL)"""
        prices = [1.5, 1.4, 1.3, 1.2, 1.1, 1.0]
        cot_net = self._make_weekly([600, 500, 400, 300, 200, 100])
        price_series = self._make_weekly(prices)
        ref_date = date(2006, 2, 17)
        labels = build_labels_for_currency(price_series, cot_net, quote_usd=True, reference_date=ref_date)
        assert all(l == "BEAR" for l in labels.iloc[1:])

    def test_confirmation_lag_enforced(self):
        """Labels only generated up to reference_date − 1 week"""
        n = 10
        prices = list(range(1, n + 2))  # extra for T+1
        cot_net = list(range(100, 100 + n + 1))
        price_series = self._make_weekly(prices)
        cot_series = self._make_weekly(cot_net)
        # Use the 10th week as reference
        ref_friday = price_series.index[9]
        ref_date = ref_friday.date()
        labels = build_labels_for_currency(price_series, cot_series, quote_usd=True, reference_date=ref_date)
        # Cutoff = ref_friday − 1 week = price_series.index[8]
        cutoff = price_series.index[8]
        assert all(dt <= cutoff for dt in labels.index), "Labels must not exceed cutoff"

    def test_label_confirmation_lag_constant(self):
        """LABEL_CONFIRMATION_LAG must be exactly 1 (RPD Section 5.1)"""
        assert LABEL_CONFIRMATION_LAG == 1


# ---------------------------------------------------------------------------
# check_class_distribution() — B2-01f, B2-01g
# ---------------------------------------------------------------------------

class TestCheckClassDistribution:
    def test_balanced_distribution(self):
        labels = pd.Series(["BULL"] * 40 + ["BEAR"] * 40 + ["NEUTRAL"] * 20)
        result = check_class_distribution(labels, "EUR")
        assert abs(result["pct_bull"] - 40.0) < 0.1
        assert abs(result["pct_bear"] - 40.0) < 0.1
        assert abs(result["pct_neutral"] - 20.0) < 0.1
        assert result["neutral_exceeds_60pct"] is False

    def test_neutral_flag_when_over_60pct(self):
        labels = pd.Series(["BULL"] * 10 + ["BEAR"] * 20 + ["NEUTRAL"] * 70)
        result = check_class_distribution(labels, "EUR")
        assert result["neutral_exceeds_60pct"] is True

    def test_neutral_flag_exactly_60pct(self):
        """Exactly 60% NEUTRAL → flag should be False (strictly greater than)"""
        labels = pd.Series(["BULL"] * 20 + ["BEAR"] * 20 + ["NEUTRAL"] * 60)
        result = check_class_distribution(labels, "JPY")
        assert result["neutral_exceeds_60pct"] is False

    def test_neutral_flag_just_over_60pct(self):
        labels = pd.Series(["NEUTRAL"] * 61 + ["BULL"] * 39)
        result = check_class_distribution(labels, "GBP")
        assert result["neutral_exceeds_60pct"] is True

    def test_returns_dict_keys(self):
        labels = pd.Series(["BULL", "BEAR", "NEUTRAL"])
        result = check_class_distribution(labels, "AUD")
        assert "pct_bull" in result
        assert "pct_bear" in result
        assert "pct_neutral" in result
        assert "neutral_exceeds_60pct" in result


# ---------------------------------------------------------------------------
# FX_SERIES config sanity check
# ---------------------------------------------------------------------------

class TestFxSeriesConfig:
    def test_all_seven_currencies_present(self):
        expected = {"EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"}
        assert set(FX_SERIES.keys()) == expected

    def test_inverted_pairs_are_quote_usd_false(self):
        """JPY, CAD, CHF are priced as X per USD — should be inverted"""
        for currency in ("JPY", "CAD", "CHF"):
            assert FX_SERIES[currency]["quote_usd"] is False, f"{currency} should invert"

    def test_direct_pairs_are_quote_usd_true(self):
        for currency in ("EUR", "GBP", "AUD", "NZD"):
            assert FX_SERIES[currency]["quote_usd"] is True, f"{currency} should not invert"

    def test_correct_series_ids(self):
        assert FX_SERIES["EUR"]["series_id"] == "DEXUSEU"
        assert FX_SERIES["JPY"]["series_id"] == "DEXJPUS"
        assert FX_SERIES["CAD"]["series_id"] == "DEXCAUS"
        assert FX_SERIES["CHF"]["series_id"] == "DEXSZUS"
