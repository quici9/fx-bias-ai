"""
Unit tests for backend/utils/data_validator.py

Validates freshness checks, format validation, and alert emission.
"""

import json
import os
import pytest
from datetime import date
from unittest.mock import patch

from backend.utils.data_validator import (
    STALE_THRESHOLD_DAYS,
    check_freshness,
    emit_alert,
    validate_date_format,
    validate_json_format,
    validate_week_label,
)


class TestCheckFreshness:
    """Verify data freshness checking logic."""

    REFERENCE_DATE = date(2026, 3, 21)

    def test_should_return_ok_when_data_is_fresh(self):
        last_update = date(2026, 3, 15)  # 6 days old
        result = check_freshness(last_update, as_of=self.REFERENCE_DATE)

        assert result["is_stale"] is False
        assert result["status"] == "OK"
        assert result["freshness_days"] == 6

    def test_should_return_stale_when_data_exceeds_threshold(self):
        last_update = date(2026, 3, 1)  # 20 days old
        result = check_freshness(last_update, as_of=self.REFERENCE_DATE)

        assert result["is_stale"] is True
        assert result["status"] == "STALE"
        assert result["freshness_days"] == 20

    def test_should_use_14_day_default_threshold(self):
        # Exactly 14 days — should be OK (not strictly greater)
        last_update = date(2026, 3, 7)
        result = check_freshness(last_update, as_of=self.REFERENCE_DATE)

        assert result["freshness_days"] == 14
        assert result["is_stale"] is False

    def test_should_become_stale_at_15_days(self):
        last_update = date(2026, 3, 6)
        result = check_freshness(last_update, as_of=self.REFERENCE_DATE)

        assert result["freshness_days"] == 15
        assert result["is_stale"] is True

    def test_should_respect_custom_threshold(self):
        last_update = date(2026, 3, 18)  # 3 days
        result = check_freshness(
            last_update, as_of=self.REFERENCE_DATE, threshold_days=2
        )

        assert result["is_stale"] is True


class TestValidateJsonFormat:
    """Verify JSON format validation."""

    def test_should_pass_when_all_keys_present(self):
        data = {"meta": {}, "predictions": [], "alerts": []}
        result = validate_json_format(data, ["meta", "predictions", "alerts"])

        assert result["valid"] is True
        assert result["missing_keys"] == []

    def test_should_fail_when_keys_missing(self):
        data = {"meta": {}}
        result = validate_json_format(data, ["meta", "predictions", "alerts"])

        assert result["valid"] is False
        assert "predictions" in result["missing_keys"]
        assert "alerts" in result["missing_keys"]


class TestValidateDateFormat:
    """Verify ISO date string validation."""

    def test_should_accept_valid_iso_date(self):
        assert validate_date_format("2026-03-21") is True

    def test_should_reject_invalid_date(self):
        assert validate_date_format("2026-13-01") is False

    def test_should_reject_non_string(self):
        assert validate_date_format(None) is False

    def test_should_reject_empty_string(self):
        assert validate_date_format("") is False


class TestValidateWeekLabel:
    """Verify ISO week label format validation."""

    def test_should_accept_valid_week_label(self):
        assert validate_week_label("2026-W12") is True

    def test_should_accept_week_01(self):
        assert validate_week_label("2026-W01") is True

    def test_should_accept_week_53(self):
        assert validate_week_label("2026-W53") is True

    def test_should_reject_week_00(self):
        assert validate_week_label("2026-W00") is False

    def test_should_reject_invalid_format(self):
        assert validate_week_label("2026-12") is False
        assert validate_week_label("W12") is False

    def test_should_reject_non_string(self):
        assert validate_week_label(None) is False


class TestEmitAlert:
    """Verify alert creation and file output."""

    def test_should_create_alert_with_required_fields(self, tmp_path):
        alerts_file = str(tmp_path / "alerts.json")

        with patch("backend.utils.data_validator.ALERTS_PENDING_FILE", alerts_file):
            alert = emit_alert("DATA_SOURCE_STALE", "COT data is 20 days old", "HIGH")

        assert alert["type"] == "DATA_SOURCE_STALE"
        assert alert["message"] == "COT data is 20 days old"
        assert alert["severity"] == "HIGH"
        assert "currency" not in alert

    def test_should_include_optional_currency(self, tmp_path):
        alerts_file = str(tmp_path / "alerts.json")

        with patch("backend.utils.data_validator.ALERTS_PENDING_FILE", alerts_file):
            alert = emit_alert(
                "EXTREME_POSITIONING", "EUR extreme long", "MEDIUM", currency="EUR"
            )

        assert alert["currency"] == "EUR"

    def test_should_append_to_existing_alerts_file(self, tmp_path):
        alerts_file = str(tmp_path / "alerts.json")

        with patch("backend.utils.data_validator.ALERTS_PENDING_FILE", alerts_file):
            emit_alert("FLIP_DETECTED", "GBP flipped", "HIGH")
            emit_alert("MODEL_DRIFT", "Accuracy dropping", "MEDIUM")

        with open(alerts_file) as f:
            alerts = json.load(f)

        assert len(alerts) == 2

    def test_should_raise_for_invalid_severity(self, tmp_path):
        alerts_file = str(tmp_path / "alerts.json")

        with patch("backend.utils.data_validator.ALERTS_PENDING_FILE", alerts_file):
            with pytest.raises(ValueError, match="Invalid severity"):
                emit_alert("FLIP_DETECTED", "test", "CRITICAL")
