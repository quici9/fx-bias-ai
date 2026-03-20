"""
Integration test: end-to-end pipeline with mock data — B2-06d

Validates the full pipeline flow:
  1. Synthetic COT data (long format) → feature engineering → 28 features
  2. Synthetic prices → label building → BULL/BEAR/NEUTRAL
  3. Feature + label merge → final dataset shape/structure
  4. No real API calls — all data is synthetic

Reference: Task List B2-06d, System Design Section 12.1
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
    FX_SERIES,
    LABEL_CONFIRMATION_LAG,
    adjust_for_quoting,
    build_label,
    build_labels_for_currency,
    get_price_direction,
    resample_to_weekly_friday,
)
from training.feature_engineering import (
    ALL_CURRENCIES,
    CURRENCIES,
    FEATURE_NAMES,
    build_historical_features,
)
from training.build_dataset import (
    align_cot_to_fridays,
)


# ---------------------------------------------------------------------------
# Synthetic data generators
# ---------------------------------------------------------------------------

PIPELINE_WEEKS = 70  # > 52 to ensure rolling windows are filled
PIPELINE_START = "2020-01-03"  # Friday
RNG = np.random.default_rng(123)


def _make_friday_index(start: str = PIPELINE_START, weeks: int = PIPELINE_WEEKS):
    return pd.date_range(start=start, periods=weeks, freq="W-FRI")


def _make_synthetic_cot(
    weeks: int = PIPELINE_WEEKS,
    currencies=None,
) -> pd.DataFrame:
    """Build realistic synthetic COT long-format DataFrame."""
    if currencies is None:
        currencies = ALL_CURRENCIES

    idx = _make_friday_index(weeks=weeks)
    rows = []

    for cur in currencies:
        base = RNG.integers(-40_000, 40_000)
        for dt in idx:
            net = int(base + RNG.integers(-3_000, 3_000))
            oi = int(abs(net) * 2.5 + RNG.integers(20_000, 80_000))
            long_ = int(max(net, 0) + RNG.integers(1_000, 10_000))
            short_ = int(long_ - net)
            rows.append({
                "date": dt,
                "currency": cur,
                "noncomm_long": long_,
                "noncomm_short": short_,
                "open_interest": oi,
                "net": net,
                "lev_funds_long": long_ // 2,
                "lev_funds_short": short_ // 2,
                "lev_funds_net": net // 2,
                "asset_mgr_long": long_ // 3,
                "asset_mgr_short": short_ // 3,
                "asset_mgr_net": net // 3,
                "dealer_long": short_ // 4,
                "dealer_short": long_ // 4,
                "dealer_net": (short_ - long_) // 4,
            })
            base = net  # random walk

    return pd.DataFrame(rows)


def _make_synthetic_prices(weeks: int = PIPELINE_WEEKS) -> pd.DataFrame:
    """Build synthetic weekly FX price DataFrame (7 currencies)."""
    idx = _make_friday_index(weeks=weeks)

    prices = {}
    base_levels = {
        "EUR": 1.10, "GBP": 1.25, "JPY": 140.0,
        "AUD": 0.65, "CAD": 1.36, "CHF": 0.92, "NZD": 0.60,
    }
    for cur, base in base_levels.items():
        noise = RNG.normal(0, 0.005, weeks)
        prices[cur] = base * np.cumprod(1 + noise)

    return pd.DataFrame(prices, index=idx)


def _make_synthetic_macro():
    """Build synthetic macro DataFrames (rates, cpi, yields, vix)."""
    monthly_idx = pd.date_range("2019-06-01", periods=20, freq="MS")

    rates = pd.DataFrame({
        "USD": [2.5] * 20,
        "EUR": [0.0] * 20,
        "GBP": [0.75] * 20,
        "JPY": [-0.1] * 20,
        "AUD": [0.25] * 20,
        "CAD": [1.75] * 20,
        "CHF": [-0.75] * 20,
        "NZD": [1.0] * 20,
    }, index=monthly_idx)

    cpi = pd.DataFrame({
        "USD": [2.0 + RNG.normal(0, 0.3) for _ in range(20)],
        "EUR": [1.5 + RNG.normal(0, 0.2) for _ in range(20)],
        "GBP": [2.0 + RNG.normal(0, 0.2) for _ in range(20)],
        "JPY": [0.5 + RNG.normal(0, 0.1) for _ in range(20)],
        "AUD": [2.5 + RNG.normal(0, 0.2) for _ in range(20)],
        "CAD": [2.0 + RNG.normal(0, 0.2) for _ in range(20)],
        "CHF": [0.3 + RNG.normal(0, 0.1) for _ in range(20)],
        "NZD": [1.8 + RNG.normal(0, 0.2) for _ in range(20)],
    }, index=monthly_idx)

    daily_idx = pd.date_range("2019-12-01", periods=360, freq="B")
    yields = pd.DataFrame({
        "US": [1.5 + RNG.normal(0, 0.05) for _ in range(360)],
        "DE": [-0.3 + RNG.normal(0, 0.03) for _ in range(360)],
        "GB": [0.7 + RNG.normal(0, 0.04) for _ in range(360)],
        "JP": [0.0 + RNG.normal(0, 0.01) for _ in range(360)],
    }, index=daily_idx)

    vix = pd.Series(
        [18.0 + RNG.normal(0, 3.0) for _ in range(360)],
        index=daily_idx,
    )

    return {"rates": rates, "cpi": cpi, "yields": yields, "vix": vix}


# ---------------------------------------------------------------------------
# Test: COT data alignment (Tuesday → Friday)
# ---------------------------------------------------------------------------

class TestCotFridayAlignment:
    def test_should_shift_tuesday_to_friday(self):
        """COT reports on Tuesday → shift +3 days to Friday."""
        tues_dates = pd.date_range("2020-01-07", periods=5, freq="W-TUE")
        cot = pd.DataFrame({
            "date": tues_dates,
            "currency": "EUR",
            "net": range(5),
        })
        result = align_cot_to_fridays(cot)
        assert all(dt.weekday() == 4 for dt in result["date"])  # all Fridays

    def test_should_preserve_all_data_columns(self):
        cot = pd.DataFrame({
            "date": pd.date_range("2020-01-07", periods=3, freq="W-TUE"),
            "currency": ["EUR", "GBP", "JPY"],
            "net": [100, 200, 300],
            "open_interest": [1000, 2000, 3000],
        })
        result = align_cot_to_fridays(cot)
        assert list(result["net"]) == [100, 200, 300]
        assert list(result["open_interest"]) == [1000, 2000, 3000]


# ---------------------------------------------------------------------------
# Test: Label building end-to-end
# ---------------------------------------------------------------------------

class TestLabelPipeline:
    def test_should_produce_valid_labels_for_all_currencies(self):
        prices = _make_synthetic_prices()
        cot = _make_synthetic_cot()

        for cur in CURRENCIES:
            cot_cur = cot[cot["currency"] == cur].set_index("date")["net"].sort_index()
            config = FX_SERIES[cur]
            labels = build_labels_for_currency(
                weekly_price=prices[cur],
                cot_net=cot_cur,
                quote_usd=config["quote_usd"],
                reference_date=prices.index[-2].date(),
            )
            assert len(labels) > 0, f"No labels for {cur}"
            assert set(labels.unique()).issubset({"BULL", "BEAR", "NEUTRAL"})

    def test_should_enforce_confirmation_lag(self):
        prices = _make_synthetic_prices()
        cot = _make_synthetic_cot()
        ref_date = prices.index[-1].date()

        cot_eur = cot[cot["currency"] == "EUR"].set_index("date")["net"].sort_index()
        labels = build_labels_for_currency(
            weekly_price=prices["EUR"],
            cot_net=cot_eur,
            quote_usd=True,
            reference_date=ref_date,
        )
        cutoff = pd.Timestamp(ref_date) - pd.Timedelta(weeks=LABEL_CONFIRMATION_LAG)
        assert all(dt <= cutoff for dt in labels.index)


# ---------------------------------------------------------------------------
# Test: Feature engineering end-to-end
# ---------------------------------------------------------------------------

class TestFeatureEngineeringPipeline:
    @pytest.fixture(scope="class")
    def feature_result(self):
        cot = _make_synthetic_cot()
        macro = _make_synthetic_macro()
        return build_historical_features(
            cot_df=cot,
            macro_rates=macro["rates"],
            macro_cpi=macro["cpi"],
            yields_df=macro["yields"],
            vix_series=macro["vix"],
        )

    def test_should_return_dataframe_with_correct_shape(self, feature_result):
        # 7 currencies × N weeks
        assert feature_result.shape[1] == 30  # date + currency + 28 features
        assert "date" in feature_result.columns
        assert "currency" in feature_result.columns

    def test_should_contain_all_28_features(self, feature_result):
        for name in FEATURE_NAMES:
            assert name in feature_result.columns, f"Missing: {name}"

    def test_should_include_all_7_currencies(self, feature_result):
        assert set(feature_result["currency"].unique()) == set(CURRENCIES)

    def test_should_have_no_nan_in_features(self, feature_result):
        nan_count = feature_result[FEATURE_NAMES].isna().sum().sum()
        assert nan_count == 0, f"Found {nan_count} NaN values in features"

    def test_should_have_all_fridays(self, feature_result):
        dates = pd.to_datetime(feature_result["date"])
        non_friday = dates[dates.dt.dayofweek != 4]
        assert non_friday.empty

    def test_cot_index_should_stay_in_valid_range(self, feature_result):
        assert feature_result["cot_index"].min() >= 0.0
        assert feature_result["cot_index"].max() <= 100.0

    def test_macro_features_should_be_nonzero(self, feature_result):
        """With macro data provided, at least some macro features should vary."""
        rate_diff = feature_result["rate_diff_vs_usd"]
        # Not all should be zero if macro data was provided
        assert rate_diff.abs().sum() > 0

    def test_vix_regime_should_be_valid_bucket(self, feature_result):
        assert feature_result["vix_regime"].isin([0, 1, 2, 3]).all()


# ---------------------------------------------------------------------------
# Test: Full pipeline merge (features + labels)
# ---------------------------------------------------------------------------

class TestFullPipelineMerge:
    @pytest.fixture(scope="class")
    def merged_dataset(self):
        """Simulate the full build_dataset.py pipeline with mock data."""
        cot = _make_synthetic_cot()
        prices = _make_synthetic_prices()
        macro = _make_synthetic_macro()

        # Step 1: Build features
        features = build_historical_features(
            cot_df=cot,
            macro_rates=macro["rates"],
            macro_cpi=macro["cpi"],
            yields_df=macro["yields"],
            vix_series=macro["vix"],
        )

        # Step 2: Build labels
        label_rows = []
        for cur in CURRENCIES:
            cot_cur = cot[cot["currency"] == cur].set_index("date")["net"].sort_index()
            config = FX_SERIES[cur]
            labels = build_labels_for_currency(
                weekly_price=prices[cur],
                cot_net=cot_cur,
                quote_usd=config["quote_usd"],
            )
            for dt, lbl in labels.items():
                label_rows.append({"date": dt, "currency": cur, "label": lbl})

        labels_df = pd.DataFrame(label_rows)
        labels_df["date"] = pd.to_datetime(labels_df["date"])

        # Step 3: Merge
        merged = features.merge(labels_df, on=["date", "currency"], how="inner")
        merged = merged.dropna(subset=["label"])
        merged = merged.sort_values(["date", "currency"]).reset_index(drop=True)

        return merged

    def test_should_have_date_currency_features_label(self, merged_dataset):
        expected_cols = {"date", "currency", "label"}
        assert expected_cols.issubset(set(merged_dataset.columns))
        for f in FEATURE_NAMES:
            assert f in merged_dataset.columns

    def test_should_have_valid_labels_only(self, merged_dataset):
        assert set(merged_dataset["label"].unique()).issubset(
            {"BULL", "BEAR", "NEUTRAL"}
        )

    def test_should_have_no_nan_labels(self, merged_dataset):
        assert merged_dataset["label"].isna().sum() == 0

    def test_should_have_no_nan_features(self, merged_dataset):
        nan_sum = merged_dataset[FEATURE_NAMES].isna().sum().sum()
        assert nan_sum == 0

    def test_should_produce_multiple_rows(self, merged_dataset):
        """At least 7 currencies × some weeks."""
        assert len(merged_dataset) >= 7 * 10

    def test_should_have_consistent_feature_count(self, merged_dataset):
        n_feat = len([c for c in merged_dataset.columns if c in FEATURE_NAMES])
        assert n_feat == 28

    def test_column_order_should_be_canonical(self, merged_dataset):
        """date, currency, then 28 features, then label."""
        cols = list(merged_dataset.columns)
        assert cols[0] == "date"
        assert cols[1] == "currency"
        # Features should precede label; label is last
        assert cols[-1] == "label"

    def test_no_duplicate_date_currency_pairs(self, merged_dataset):
        dups = merged_dataset.duplicated(subset=["date", "currency"])
        assert dups.sum() == 0

    def test_all_dates_are_fridays(self, merged_dataset):
        dates = pd.to_datetime(merged_dataset["date"])
        non_friday = dates[dates.dt.dayofweek != 4]
        assert non_friday.empty, f"Non-Friday dates: {non_friday.tolist()[:5]}"

    def test_feature_value_ranges_are_reasonable(self, merged_dataset):
        """Sanity check — features should not have extreme outlier values."""
        assert merged_dataset["cot_index"].between(0, 100).all()
        assert merged_dataset["net_pct_change_1w"].between(-500, 500).all()
        assert merged_dataset["month"].between(1, 12).all()
        assert merged_dataset["quarter"].between(1, 4).all()
        assert merged_dataset["flip_flag"].isin([0, 1]).all()
        assert merged_dataset["extreme_flag"].isin([0, 1]).all()
