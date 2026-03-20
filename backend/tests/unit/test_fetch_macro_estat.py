"""Unit tests for e-Stat Japan CPI functions in fetch_macro.py."""
import os
import pytest
from datetime import date
from unittest.mock import MagicMock, patch

# Provide dummy keys so module-level constants don't raise on import
os.environ.setdefault("FRED_API_KEY", "test_fred_key")
os.environ.setdefault("ESTAT_API_KEY", "test_estat_key")

from backend.scripts.fetch_macro import compute_yoy_from_level, fetch_estat_japan_cpi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _estat_response(*time_value_pairs):
    """Build a minimal e-Stat JSON response from (time, value) tuples."""
    return {
        "GET_STATS_DATA": {
            "STATISTICAL_DATA": {
                "DATA_INF": {
                    "VALUE": [
                        {"@time": t, "@cat01": "0001", "$": v}
                        for t, v in time_value_pairs
                    ]
                }
            }
        }
    }


def _mock_get(json_body, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.raise_for_status = MagicMock()
    return resp


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

    def test_skips_missing_and_suppressed_values(self):
        body = _estat_response(
            ("202401", "107.2"),
            ("202402", "－"),    # full-width dash (suppressed)
            ("202403", "***"),   # suppressed
            ("202404", ""),      # empty
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
        """e-Stat sometimes pads @time to 10 chars: '2024010000'."""
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
        """Match should succeed even if past date is offset by a few days."""
        obs = [
            {"date": "2024-03-01", "value": "108.0"},
            # 12 months ago is 2023-03-01; provide 2023-02-16 (13 days off → within 15d window)
            {"date": "2023-02-16", "value": "104.0"},
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
        result = compute_yoy_from_level(obs)
        assert result == []

    def test_skips_bad_values_gracefully(self):
        obs = [
            {"date": "2024-01-01", "value": "bad"},
            {"date": "2023-01-01", "value": "103.5"},
        ]
        result = compute_yoy_from_level(obs)
        assert result == []
