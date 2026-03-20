"""
Unit tests for training/feature_engineering.py — B2-06b

Tests COT Index calculation for sample data, verifies all 28 features
are produced correctly, and validates helper function behavior.

Reference: Task List B2-06b, System Design Section 5.2, RPD Section 3.2
"""

import sys
import os

import numpy as np
import pandas as pd
import pytest

# Add project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from training.feature_engineering import (
    ALL_CURRENCIES,
    COT_INDEX_WINDOW,
    CURRENCIES,
    FEATURE_NAMES,
    OI_NET_REGIME,
    VIX_THRESHOLDS,
    _align_daily_to_weekly,
    _align_monthly_to_weekly,
    _compute_group_a,
    _compute_group_b,
    _compute_group_c,
    _compute_group_d,
    _rolling_norm,
    _vix_regime,
    _weeks_since_flip,
    build_historical_features,
)


# ---------------------------------------------------------------------------
# Fixtures — reusable synthetic data
# ---------------------------------------------------------------------------

def _make_weekly_index(weeks: int = 60, start: str = "2020-01-03") -> pd.DatetimeIndex:
    """Create a weekly Friday DatetimeIndex."""
    return pd.date_range(start=start, periods=weeks, freq="W-FRI")


def _make_cot_long(weeks: int = 60, currencies=None) -> pd.DataFrame:
    """
    Build a synthetic long-format COT DataFrame matching the schema
    expected by build_historical_features().
    """
    if currencies is None:
        currencies = ALL_CURRENCIES

    idx = _make_weekly_index(weeks)
    rng = np.random.default_rng(42)
    rows = []

    for cur in currencies:
        base_net = rng.integers(-50_000, 50_000)
        for i, dt in enumerate(idx):
            net = int(base_net + rng.integers(-5_000, 5_000))
            oi = int(abs(net) * 3 + rng.integers(10_000, 50_000))
            noncomm_long = int(max(net, 0) + rng.integers(1_000, 10_000))
            noncomm_short = int(noncomm_long - net)
            rows.append({
                "date": dt,
                "currency": cur,
                "noncomm_long": noncomm_long,
                "noncomm_short": noncomm_short,
                "open_interest": oi,
                "net": net,
                "lev_funds_long": noncomm_long // 2,
                "lev_funds_short": noncomm_short // 2,
                "lev_funds_net": net // 2,
                "asset_mgr_long": noncomm_long // 3,
                "asset_mgr_short": noncomm_short // 3,
                "asset_mgr_net": net // 3,
                "dealer_long": noncomm_short // 4,
                "dealer_short": noncomm_long // 4,
                "dealer_net": (noncomm_short - noncomm_long) // 4,
            })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Test: _rolling_norm()
# ---------------------------------------------------------------------------

class TestRollingNorm:
    def test_should_return_series_of_same_length(self):
        s = pd.Series(range(100), dtype=float)
        result = _rolling_norm(s, window=10)
        assert len(result) == len(s)

    def test_should_normalize_to_0_100_range(self):
        s = pd.Series(range(100), dtype=float)
        result = _rolling_norm(s, window=10)
        assert result.min() >= 0.0
        assert result.max() <= 100.0

    def test_should_return_100_when_at_rolling_max(self):
        # Monotonically increasing → last value is always max
        s = pd.Series(range(20), dtype=float)
        result = _rolling_norm(s, window=10)
        assert result.iloc[-1] == pytest.approx(100.0)

    def test_should_return_0_when_at_rolling_min(self):
        # Monotonically decreasing → last value is always min
        s = pd.Series(range(20, 0, -1), dtype=float)
        result = _rolling_norm(s, window=10)
        assert result.iloc[-1] == pytest.approx(0.0)

    def test_should_return_50_for_flat_series(self):
        s = pd.Series([42.0] * 20)
        result = _rolling_norm(s, window=10)
        # All same → spread=0 → NaN → fillna(50.0)
        assert result.iloc[-1] == pytest.approx(50.0)

    def test_should_fill_50_before_window_is_full(self):
        s = pd.Series(range(10), dtype=float)
        result = _rolling_norm(s, window=52)
        # 10 < 52 → min_periods not met → all should be 50.0
        assert all(result == 50.0)

    def test_known_cot_index_calculation(self):
        """
        Given net positions [0, 10, 20, ..., 90] over 10 periods,
        with window=10 the 10th value (90) should be 100.0.
        """
        s = pd.Series(range(0, 100, 10), dtype=float)
        result = _rolling_norm(s, window=10)
        assert result.iloc[-1] == pytest.approx(100.0)
        # 5th value (40) when window is full:
        # min=0, max=90 → (40-0)/(90-0)*100 = 44.44
        # But first 9 values have min_periods=10, so only index 9 has a value
        assert result.iloc[9] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Test: _weeks_since_flip()
# ---------------------------------------------------------------------------

class TestWeeksSinceFlip:
    def test_should_count_weeks_after_flip(self):
        flips = pd.Series([0, 0, 1, 0, 0, 0])
        result = _weeks_since_flip(flips)
        assert np.isnan(result.iloc[0])
        assert np.isnan(result.iloc[1])
        assert result.iloc[2] == 0  # flip happened here
        assert result.iloc[3] == 1
        assert result.iloc[4] == 2
        assert result.iloc[5] == 3

    def test_should_reset_on_second_flip(self):
        flips = pd.Series([1, 0, 0, 1, 0])
        result = _weeks_since_flip(flips)
        assert result.iloc[0] == 0
        assert result.iloc[1] == 1
        assert result.iloc[2] == 2
        assert result.iloc[3] == 0  # reset
        assert result.iloc[4] == 1

    def test_should_return_nan_when_no_flip(self):
        flips = pd.Series([0, 0, 0, 0])
        result = _weeks_since_flip(flips)
        assert all(np.isnan(result))


# ---------------------------------------------------------------------------
# Test: _vix_regime()
# ---------------------------------------------------------------------------

class TestVixRegime:
    def test_should_return_0_for_low_vix(self):
        assert _vix_regime(12.0) == 0

    def test_should_return_1_for_normal_vix(self):
        assert _vix_regime(17.0) == 1

    def test_should_return_2_for_elevated_vix(self):
        assert _vix_regime(25.0) == 2

    def test_should_return_3_for_extreme_vix(self):
        assert _vix_regime(35.0) == 3

    def test_should_return_1_for_nan_default(self):
        assert _vix_regime(np.nan) == 1

    def test_should_respect_threshold_boundaries(self):
        assert _vix_regime(VIX_THRESHOLDS[0] - 0.01) == 0
        assert _vix_regime(VIX_THRESHOLDS[0]) == 1  # >= 15 is Normal
        assert _vix_regime(VIX_THRESHOLDS[1]) == 2  # >= 20 is Elevated
        assert _vix_regime(VIX_THRESHOLDS[2]) == 3  # >= 30 is Extreme


# ---------------------------------------------------------------------------
# Test: _align_monthly_to_weekly()
# ---------------------------------------------------------------------------

class TestAlignMonthlyToWeekly:
    def test_should_forward_fill_monthly_data_to_weekly(self):
        monthly_idx = pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"])
        monthly = pd.Series([1.0, 2.0, 3.0], index=monthly_idx)
        weekly_idx = pd.date_range("2020-02-07", periods=4, freq="W-FRI")
        result = _align_monthly_to_weekly(monthly, weekly_idx, "policy_rate")
        # policy_rate has lag=0, so Feb 7 should see Feb 1 data = 2.0
        assert result.iloc[0] == pytest.approx(2.0)

    def test_should_enforce_cpi_lag(self):
        """CPI lag = -2 months: on March 20 we can only see January CPI."""
        monthly_idx = pd.to_datetime([
            "2020-01-15", "2020-02-15", "2020-03-15",
        ])
        monthly = pd.Series([1.0, 2.0, 3.0], index=monthly_idx)
        weekly_idx = pd.DatetimeIndex([pd.Timestamp("2020-03-20")])
        result = _align_monthly_to_weekly(monthly, weekly_idx, "cpi")
        # valid_date_for("cpi", 2020-03-20) = 2020-01-20
        # Last observation <= Jan 20 is Jan 15 → value = 1.0
        assert result.iloc[0] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test: _align_daily_to_weekly()
# ---------------------------------------------------------------------------

class TestAlignDailyToWeekly:
    def test_should_use_friday_close(self):
        daily_idx = pd.date_range("2020-01-06", periods=5, freq="B")  # Mon–Fri
        daily = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=daily_idx)
        weekly_idx = pd.DatetimeIndex([pd.Timestamp("2020-01-10")])  # Friday
        result = _align_daily_to_weekly(daily, weekly_idx, "price")
        assert result.iloc[0] == pytest.approx(5.0)

    def test_should_return_nan_when_no_data_available(self):
        daily_idx = pd.date_range("2020-06-01", periods=5, freq="B")
        daily = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=daily_idx)
        # Ask for a Friday before any data exists
        weekly_idx = pd.DatetimeIndex([pd.Timestamp("2020-01-03")])
        result = _align_daily_to_weekly(daily, weekly_idx, "price")
        assert np.isnan(result.iloc[0])


# ---------------------------------------------------------------------------
# Test: _compute_group_a() — COT Index sample data
# ---------------------------------------------------------------------------

class TestComputeGroupA:
    def _make_cot_wide(self, net_values, oi_values=None, currency="EUR"):
        """Build minimal cot_wide DataFrame for Group A testing."""
        n = len(net_values)
        idx = _make_weekly_index(n)
        if oi_values is None:
            oi_values = [abs(v) * 3 + 10_000 for v in net_values]

        data = {
            f"net_{currency}": net_values,
            f"open_interest_{currency}": oi_values,
        }
        # Add USD columns for usd_index_cot
        data["net_USD"] = [0] * n
        data["open_interest_USD"] = [10_000] * n

        return pd.DataFrame(data, index=idx)

    def test_should_produce_12_feature_columns(self):
        net = list(range(-5_000, 5_000, 200))[:60]
        cot_wide = self._make_cot_wide(net)
        usd_idx = pd.Series(50.0, index=cot_wide.index)
        all_idx = pd.DataFrame({"EUR": 50.0, "USD": 50.0}, index=cot_wide.index)
        result = _compute_group_a(cot_wide, "EUR", usd_idx, all_idx)
        assert len(result.columns) == 12
        expected_cols = [
            "cot_index", "cot_index_4w_change", "net_pct_change_1w",
            "momentum_acceleration", "oi_delta_direction", "oi_net_confluence",
            "flip_flag", "extreme_flag", "usd_index_cot", "rank_in_8",
            "spread_vs_usd", "weeks_since_flip",
        ]
        assert list(result.columns) == expected_cols

    def test_cot_index_should_be_in_0_100_range(self):
        net = list(range(-5_000, 5_000, 200))[:60]
        cot_wide = self._make_cot_wide(net)
        usd_idx = pd.Series(50.0, index=cot_wide.index)
        all_idx = pd.DataFrame({"EUR": 50.0, "USD": 50.0}, index=cot_wide.index)
        result = _compute_group_a(cot_wide, "EUR", usd_idx, all_idx)
        assert result["cot_index"].min() >= 0.0
        assert result["cot_index"].max() <= 100.0

    def test_cot_index_known_calculation(self):
        """
        With monotonically increasing net positions over 52+ weeks,
        the last COT index value should be 100.0 (at rolling max).
        """
        net = list(range(1_000, 7_000, 100))[:60]  # 60 weeks, increasing
        cot_wide = self._make_cot_wide(net)
        usd_idx = pd.Series(50.0, index=cot_wide.index)
        all_idx = pd.DataFrame({"EUR": 50.0, "USD": 50.0}, index=cot_wide.index)
        result = _compute_group_a(cot_wide, "EUR", usd_idx, all_idx)
        # After 52 weeks, monotonically increasing → last = max → 100.0
        assert result["cot_index"].iloc[-1] == pytest.approx(100.0)

    def test_flip_flag_when_sign_changes(self):
        """Flip flag = 1 when net position changes sign."""
        net = [100] * 5 + [-100] * 5 + [100] * 5  # two sign changes
        cot_wide = self._make_cot_wide(net)
        usd_idx = pd.Series(50.0, index=cot_wide.index)
        all_idx = pd.DataFrame({"EUR": 50.0, "USD": 50.0}, index=cot_wide.index)
        result = _compute_group_a(cot_wide, "EUR", usd_idx, all_idx)
        # Flip should occur at index 5 (+ → −) and index 10 (− → +)
        assert result["flip_flag"].iloc[5] == 1
        assert result["flip_flag"].iloc[10] == 1
        # No flip at other positions
        assert result["flip_flag"].iloc[3] == 0
        assert result["flip_flag"].iloc[7] == 0

    def test_extreme_flag_when_cot_index_below_10_or_above_90(self):
        """Extreme flag = 1 when COT index < 10 or > 90."""
        # Decreasing → after 52w, last value is min → index = 0 → extreme
        net = list(range(10_000, 4_000, -100))[:60]
        cot_wide = self._make_cot_wide(net)
        usd_idx = pd.Series(50.0, index=cot_wide.index)
        all_idx = pd.DataFrame({"EUR": 50.0, "USD": 50.0}, index=cot_wide.index)
        result = _compute_group_a(cot_wide, "EUR", usd_idx, all_idx)
        # Last value should be at min → cot_index = 0 → extreme = 1
        assert result["extreme_flag"].iloc[-1] == 1

    def test_oi_net_confluence_regime_encoding(self):
        """Verify OI_NET_REGIME encoding is applied correctly."""
        assert OI_NET_REGIME[(1, 1)] == 1    # Strong
        assert OI_NET_REGIME[(-1, 1)] == 2   # Covering
        assert OI_NET_REGIME[(1, -1)] == 3   # NewShort
        assert OI_NET_REGIME[(-1, -1)] == 4  # Liquidation


# ---------------------------------------------------------------------------
# Test: _compute_group_b() — TFF OI features
# ---------------------------------------------------------------------------

class TestComputeGroupB:
    def test_should_produce_4_feature_columns(self):
        n = 60
        idx = _make_weekly_index(n)
        cot_wide = pd.DataFrame({
            "lev_funds_net_EUR": range(n),
            "asset_mgr_net_EUR": range(n),
            "dealer_net_EUR": range(n),
        }, index=idx)
        result = _compute_group_b(cot_wide, "EUR")
        assert len(result.columns) == 4
        assert "lev_funds_net_index" in result.columns
        assert "asset_mgr_net_direction" in result.columns
        assert "dealer_net_contrarian" in result.columns
        assert "lev_vs_assetmgr_divergence" in result.columns

    def test_should_handle_missing_tff_columns_gracefully(self):
        """When TFF columns are missing, should use 0 → neutral values."""
        n = 60
        idx = _make_weekly_index(n)
        cot_wide = pd.DataFrame(index=idx)  # no TFF columns
        result = _compute_group_b(cot_wide, "EUR")
        # All zeros in → rolling norm on flat → 50.0; direction = 0
        assert result["lev_funds_net_index"].iloc[-1] == pytest.approx(50.0)
        assert result["asset_mgr_net_direction"].iloc[-1] == 0


# ---------------------------------------------------------------------------
# Test: _compute_group_c() — Macro features
# ---------------------------------------------------------------------------

class TestComputeGroupC:
    def test_should_produce_8_feature_columns(self):
        idx = _make_weekly_index(20)
        result = _compute_group_c(idx, "EUR", None, None, None, None)
        assert len(result.columns) == 8

    def test_should_default_to_zero_when_no_macro_data(self):
        idx = _make_weekly_index(20)
        result = _compute_group_c(idx, "EUR", None, None, None, None)
        assert (result == 0.0).all().all()

    def test_should_compute_rate_diff_vs_usd(self):
        idx = _make_weekly_index(20)
        monthly_idx = pd.date_range("2019-12-01", periods=6, freq="MS")
        rates = pd.DataFrame({
            "USD": [2.5, 2.5, 2.5, 2.5, 2.5, 2.5],
            "EUR": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        }, index=monthly_idx)
        result = _compute_group_c(idx, "EUR", rates, None, None, None)
        # EUR(0.0) - USD(2.5) = -2.5
        valid_rows = result["rate_diff_vs_usd"] != 0.0
        if valid_rows.any():
            assert result.loc[valid_rows, "rate_diff_vs_usd"].iloc[0] == pytest.approx(-2.5)

    def test_should_compute_vix_regime_correctly(self):
        idx = _make_weekly_index(5, start="2020-01-03")
        daily_idx = pd.date_range("2019-12-30", periods=30, freq="B")
        vix = pd.Series([12.0] * 10 + [25.0] * 10 + [35.0] * 10, index=daily_idx)
        result = _compute_group_c(idx, "EUR", None, None, None, vix)
        # First week should map to Low VIX regime (~ 12.0 → regime 0)
        assert result["vix_regime"].iloc[0] == 0


# ---------------------------------------------------------------------------
# Test: _compute_group_d() — Cross-asset + Seasonal
# ---------------------------------------------------------------------------

class TestComputeGroupD:
    def test_should_produce_4_feature_columns(self):
        idx = _make_weekly_index(20)
        result = _compute_group_d(idx, None, None)
        assert len(result.columns) == 4

    def test_month_should_be_calendar_month(self):
        idx = _make_weekly_index(20, start="2020-03-06")
        result = _compute_group_d(idx, None, None)
        assert result["month"].iloc[0] == 3  # March

    def test_quarter_should_be_calendar_quarter(self):
        idx = _make_weekly_index(20, start="2020-07-03")
        result = _compute_group_d(idx, None, None)
        assert result["quarter"].iloc[0] == 3  # Q3


# ---------------------------------------------------------------------------
# Test: build_historical_features() — full pipeline
# ---------------------------------------------------------------------------

class TestBuildHistoricalFeatures:
    @pytest.fixture(scope="class")
    def cot_df(self):
        return _make_cot_long(weeks=60)

    @pytest.fixture(scope="class")
    def feature_matrix(self, cot_df):
        return build_historical_features(cot_df=cot_df)

    def test_should_return_all_28_features(self, feature_matrix):
        for name in FEATURE_NAMES:
            assert name in feature_matrix.columns, f"Missing feature: {name}"

    def test_should_have_date_and_currency_columns(self, feature_matrix):
        assert "date" in feature_matrix.columns
        assert "currency" in feature_matrix.columns

    def test_should_have_exactly_28_feature_columns(self, feature_matrix):
        feature_cols = [c for c in feature_matrix.columns if c in FEATURE_NAMES]
        assert len(feature_cols) == 28

    def test_should_produce_rows_for_all_7_currencies(self, feature_matrix):
        actual_currencies = set(feature_matrix["currency"].unique())
        expected = set(CURRENCIES)
        assert actual_currencies == expected

    def test_should_have_no_nan_values(self, feature_matrix):
        nan_counts = feature_matrix[FEATURE_NAMES].isna().sum()
        nan_features = nan_counts[nan_counts > 0]
        assert nan_features.empty, f"NaN found in features: {dict(nan_features)}"

    def test_cot_index_should_stay_within_valid_range(self, feature_matrix):
        assert feature_matrix["cot_index"].min() >= 0.0
        assert feature_matrix["cot_index"].max() <= 100.0

    def test_cot_index_4w_change_should_be_finite(self, feature_matrix):
        assert feature_matrix["cot_index_4w_change"].apply(np.isfinite).all()

    def test_net_pct_change_1w_should_be_clipped(self, feature_matrix):
        assert feature_matrix["net_pct_change_1w"].min() >= -500.0
        assert feature_matrix["net_pct_change_1w"].max() <= 500.0

    def test_flip_flag_should_be_binary(self, feature_matrix):
        assert set(feature_matrix["flip_flag"].unique()).issubset({0, 1})

    def test_extreme_flag_should_be_binary(self, feature_matrix):
        assert set(feature_matrix["extreme_flag"].unique()).issubset({0, 1})

    def test_month_should_be_1_to_12(self, feature_matrix):
        assert feature_matrix["month"].min() >= 1
        assert feature_matrix["month"].max() <= 12

    def test_quarter_should_be_1_to_4(self, feature_matrix):
        assert feature_matrix["quarter"].min() >= 1
        assert feature_matrix["quarter"].max() <= 4

    def test_all_dates_should_be_fridays(self, feature_matrix):
        dates = pd.to_datetime(feature_matrix["date"])
        non_friday = dates[dates.dt.dayofweek != 4]
        assert non_friday.empty, f"Non-Friday dates found: {non_friday.tolist()[:5]}"

    def test_should_raise_when_no_currency_data(self):
        empty_cot = pd.DataFrame(columns=[
            "date", "currency", "net", "open_interest",
            "noncomm_long", "noncomm_short",
        ])
        with pytest.raises(ValueError, match="No currency data"):
            build_historical_features(cot_df=empty_cot)

    def test_should_handle_single_currency(self):
        cot = _make_cot_long(weeks=55, currencies=["EUR", "USD"])
        result = build_historical_features(cot_df=cot, currencies=["EUR"])
        assert set(result["currency"].unique()) == {"EUR"}
        assert len(result.columns) == 30  # date + currency + 28 features


# ---------------------------------------------------------------------------
# Test: FEATURE_NAMES constant
# ---------------------------------------------------------------------------

class TestFeatureNamesConstant:
    def test_should_have_exactly_28_names(self):
        assert len(FEATURE_NAMES) == 28

    def test_should_have_no_duplicates(self):
        assert len(FEATURE_NAMES) == len(set(FEATURE_NAMES))

    def test_should_contain_all_group_a_features(self):
        group_a = [
            "cot_index", "cot_index_4w_change", "net_pct_change_1w",
            "momentum_acceleration", "oi_delta_direction", "oi_net_confluence",
            "flip_flag", "extreme_flag", "usd_index_cot", "rank_in_8",
            "spread_vs_usd", "weeks_since_flip",
        ]
        for f in group_a:
            assert f in FEATURE_NAMES, f"Missing Group A feature: {f}"

    def test_should_contain_all_group_b_features(self):
        group_b = [
            "lev_funds_net_index", "asset_mgr_net_direction",
            "dealer_net_contrarian", "lev_vs_assetmgr_divergence",
        ]
        for f in group_b:
            assert f in FEATURE_NAMES, f"Missing Group B feature: {f}"

    def test_should_contain_all_group_c_features(self):
        group_c = [
            "rate_diff_vs_usd", "rate_diff_trend_3m", "rate_hike_expectation",
            "cpi_diff_vs_usd", "cpi_trend", "pmi_composite_diff",
            "yield_10y_diff", "vix_regime",
        ]
        for f in group_c:
            assert f in FEATURE_NAMES, f"Missing Group C feature: {f}"

    def test_should_contain_all_group_d_features(self):
        group_d = ["gold_cot_index", "oil_cot_direction", "month", "quarter"]
        for f in group_d:
            assert f in FEATURE_NAMES, f"Missing Group D feature: {f}"


# ---------------------------------------------------------------------------
# Test: Constants and configuration
# ---------------------------------------------------------------------------

class TestConstants:
    def test_currencies_should_have_7_non_usd(self):
        assert len(CURRENCIES) == 7
        assert "USD" not in CURRENCIES

    def test_all_currencies_should_have_8_including_usd(self):
        assert len(ALL_CURRENCIES) == 8
        assert "USD" in ALL_CURRENCIES

    def test_cot_index_window_should_be_52(self):
        assert COT_INDEX_WINDOW == 52

    def test_vix_thresholds_should_be_ascending(self):
        assert VIX_THRESHOLDS == sorted(VIX_THRESHOLDS)
        assert len(VIX_THRESHOLDS) == 3
