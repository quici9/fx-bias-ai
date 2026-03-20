"""Unit tests for e-Stat Japan CPI functions in fetch_macro.py."""
import os
import pytest
from datetime import date
from unittest.mock import MagicMock, patch

# Provide dummy keys so module-level constants don't raise on import
os.environ.setdefault("FRED_API_KEY", "test_fred_key")
os.environ.setdefault("ESTAT_API_KEY", "test_estat_key")

from backend.scripts.fetch_macro import (
    _find_all_items_cat_code,
    compute_yoy_from_level,
    fetch_estat_japan_cpi,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _class_inf(entries: list[dict]) -> dict:
    """Build a CLASS_INF structure with cat01 entries."""
    return {
        "CLASS_INF": {
            "CLASS_OBJ": {
                "@id": "cat01",
                "CLASS": entries,
            }
        }
    }


def _estat_response(*time_value_pairs, cat01_code="0001", with_meta=True):
    """Build a minimal e-Stat JSON response from (time, value) tuples."""
    stat_data: dict = {
        "DATA_INF": {
            "VALUE": [
                {"@time": t, "@cat01": cat01_code, "$": v}
                for t, v in time_value_pairs
            ]
        }
    }
    if with_meta:
        stat_data.update(_class_inf([
            {"@code": cat01_code, "@name": "総合"},
            {"@code": "0002", "@name": "生鮮食品を除く総合"},
        ]))
    return {"GET_STATS_DATA": {"STATISTICAL_DATA": stat_data}}


def _mock_get(json_body, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# _find_all_items_cat_code
# ---------------------------------------------------------------------------

class TestFindAllItemsCatCode:
    def test_finds_exact_sogocode(self):
        stat_data = _class_inf([
            {"@code": "0001", "@name": "総合"},
            {"@code": "0002", "@name": "生鮮食品を除く総合"},
        ])
        assert _find_all_items_cat_code(stat_data) == "0001"

    def test_prefers_exact_over_loose_match(self):
        stat_data = _class_inf([
            {"@code": "0099", "@name": "エネルギーを除く総合"},
            {"@code": "0001", "@name": "総合"},
        ])
        assert _find_all_items_cat_code(stat_data) == "0001"

    def test_loose_match_when_no_exact(self):
        stat_data = _class_inf([
            {"@code": "0099", "@name": "食料及び総合指数"},
            {"@code": "0002", "@name": "生鮮食品を除く総合"},
        ])
        # "食料及び総合指数" contains 総合 and no 除く → loose match
        assert _find_all_items_cat_code(stat_data) == "0099"

    def test_returns_none_when_not_found(self):
        stat_data = _class_inf([
            {"@code": "0002", "@name": "食料"},
            {"@code": "0003", "@name": "住居"},
        ])
        assert _find_all_items_cat_code(stat_data) is None

    def test_handles_class_obj_as_list(self):
        stat_data = {
            "CLASS_INF": {
                "CLASS_OBJ": [
                    {"@id": "tab", "CLASS": [{"@code": "T1", "@name": "指数"}]},
                    {"@id": "cat01", "CLASS": [{"@code": "A001", "@name": "総合"}]},
                ]
            }
        }
        assert _find_all_items_cat_code(stat_data) == "A001"

    def test_handles_class_as_single_dict(self):
        stat_data = {
            "CLASS_INF": {
                "CLASS_OBJ": {
                    "@id": "cat01",
                    "CLASS": {"@code": "X01", "@name": "総合"},
                }
            }
        }
        assert _find_all_items_cat_code(stat_data) == "X01"

    def test_returns_none_when_no_class_inf(self):
        assert _find_all_items_cat_code({}) is None


# ---------------------------------------------------------------------------
# fetch_estat_japan_cpi
# ---------------------------------------------------------------------------

class TestFetchEstatJapanCPI:
    def test_parses_observations_and_sorts_desc(self):
        body = _estat_response(
            ("202301", "103.5"),
            ("202302", "103.8"),
            ("202401", "107.2"),
            ("202402", "107.5"),
        )
        with patch("backend.scripts.fetch_macro.requests.get", return_value=_mock_get(body)):
            obs = fetch_estat_japan_cpi()

        assert len(obs) == 4
        assert obs[0]["date"] == "2024-02-01"
        assert obs[-1]["date"] == "2023-01-01"
        assert obs[0]["value"] == "107.5"

    def test_date_format_yyyy_mm_01(self):
        body = _estat_response(("202406", "108.3"))
        with patch("backend.scripts.fetch_macro.requests.get", return_value=_mock_get(body)):
            obs = fetch_estat_japan_cpi()
        assert obs[0]["date"] == "2024-06-01"

    def test_filters_to_sogo_category_only(self):
        """Non-総合 entries (different cat01) should be excluded."""
        stat_data = {
            "CLASS_INF": {
                "CLASS_OBJ": {
                    "@id": "cat01",
                    "CLASS": [
                        {"@code": "A001", "@name": "総合"},
                        {"@code": "A002", "@name": "食料"},
                    ],
                }
            },
            "DATA_INF": {
                "VALUE": [
                    {"@time": "202401", "@cat01": "A001", "$": "107.2"},  # 総合 ✓
                    {"@time": "202401", "@cat01": "A002", "$": "115.0"},  # 食料 ✗
                ]
            },
        }
        body = {"GET_STATS_DATA": {"STATISTICAL_DATA": stat_data}}
        with patch("backend.scripts.fetch_macro.requests.get", return_value=_mock_get(body)):
            obs = fetch_estat_japan_cpi()
        assert len(obs) == 1
        assert obs[0]["value"] == "107.2"

    def test_skips_missing_and_suppressed_values(self):
        body = _estat_response(
            ("202401", "107.2"),
            ("202402", "－"),
            ("202403", "***"),
            ("202404", ""),
            ("202405", "108.0"),
        )
        with patch("backend.scripts.fetch_macro.requests.get", return_value=_mock_get(body)):
            obs = fetch_estat_japan_cpi()
        assert len(obs) == 2
        dates = [o["date"] for o in obs]
        assert "2024-02-01" not in dates
        assert "2024-03-01" not in dates
        assert "2024-04-01" not in dates

    def test_handles_10char_time_format(self):
        body = _estat_response(("2024010000", "107.2"))
        with patch("backend.scripts.fetch_macro.requests.get", return_value=_mock_get(body)):
            obs = fetch_estat_japan_cpi()
        assert obs[0]["date"] == "2024-01-01"

    def test_raises_without_api_key(self):
        with patch("backend.scripts.fetch_macro.ESTAT_API_KEY", ""):
            with pytest.raises(ValueError, match="ESTAT_API_KEY"):
                fetch_estat_japan_cpi()

    def test_raises_on_empty_value_list(self):
        body = {"GET_STATS_DATA": {"STATISTICAL_DATA": {"DATA_INF": {"VALUE": []}}}}
        with patch("backend.scripts.fetch_macro.requests.get", return_value=_mock_get(body)):
            with pytest.raises(ValueError, match="empty VALUE list"):
                fetch_estat_japan_cpi()

    def test_raises_when_sogo_filtered_out_completely(self):
        """If metadata found a code but no VALUES match it, raise."""
        stat_data = {
            "CLASS_INF": {
                "CLASS_OBJ": {
                    "@id": "cat01",
                    "CLASS": {"@code": "A001", "@name": "総合"},
                }
            },
            "DATA_INF": {
                "VALUE": [
                    {"@time": "202401", "@cat01": "WRONG", "$": "107.0"},
                ]
            },
        }
        body = {"GET_STATS_DATA": {"STATISTICAL_DATA": stat_data}}
        with patch("backend.scripts.fetch_macro.requests.get", return_value=_mock_get(body)):
            with pytest.raises(ValueError, match="no observations for 総合"):
                fetch_estat_japan_cpi()

    def test_retries_on_server_error_then_succeeds(self):
        good_body = _estat_response(("202401", "107.2"))
        error_resp = _mock_get({}, status_code=500)
        ok_resp = _mock_get(good_body, status_code=200)

        with patch("backend.scripts.fetch_macro.requests.get", side_effect=[error_resp, ok_resp]):
            with patch("backend.scripts.fetch_macro.time.sleep"):
                obs = fetch_estat_japan_cpi()
        assert len(obs) == 1


# ---------------------------------------------------------------------------
# compute_yoy_from_level
# ---------------------------------------------------------------------------

class TestComputeYoyFromLevel:
    def test_basic_yoy(self):
        obs = [
            {"date": "2024-02-01", "value": "107.5"},
            {"date": "2024-01-01", "value": "107.2"},
            {"date": "2023-02-01", "value": "103.8"},
            {"date": "2023-01-01", "value": "103.5"},
        ]
        result = compute_yoy_from_level(obs)
        assert len(result) == 2
        assert result[0]["date"] == "2024-02-01"
        expected = round((107.5 / 103.8 - 1) * 100, 2)
        assert float(result[0]["value"]) == pytest.approx(expected, abs=0.01)

    def test_sorted_descending(self):
        obs = [
            {"date": "2024-03-01", "value": "108.0"},
            {"date": "2024-02-01", "value": "107.5"},
            {"date": "2023-03-01", "value": "104.2"},
            {"date": "2023-02-01", "value": "103.8"},
        ]
        result = compute_yoy_from_level(obs)
        assert len(result) == 2
        assert result[0]["date"] > result[1]["date"]

    def test_returns_empty_when_no_year_ago(self):
        obs = [{"date": "2024-02-01", "value": "107.5"}]
        assert compute_yoy_from_level(obs) == []

    def test_15_day_window_tolerance(self):
        obs = [
            {"date": "2024-03-01", "value": "108.0"},
            {"date": "2023-02-16", "value": "104.0"},  # 13 days off → within ±15d
        ]
        result = compute_yoy_from_level(obs)
        assert len(result) == 1
        expected = round((108.0 / 104.0 - 1) * 100, 2)
        assert float(result[0]["value"]) == pytest.approx(expected, abs=0.01)

    def test_skips_zero_base(self):
        obs = [
            {"date": "2024-01-01", "value": "107.0"},
            {"date": "2023-01-01", "value": "0"},
        ]
        assert compute_yoy_from_level(obs) == []

    def test_skips_bad_values_gracefully(self):
        obs = [
            {"date": "2024-01-01", "value": "bad"},
            {"date": "2023-01-01", "value": "103.5"},
        ]
        assert compute_yoy_from_level(obs) == []
