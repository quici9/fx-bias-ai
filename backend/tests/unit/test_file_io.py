"""
Unit tests for backend/utils/file_io.py

Validates atomic write and logging utilities.
"""

import json
import os
import pytest

from backend.utils.file_io import (
    EXIT_FAILED,
    EXIT_PARTIAL,
    EXIT_SUCCESS,
    write_output,
)


class TestWriteOutput:
    """Verify atomic write behavior."""

    def test_should_write_valid_json(self, tmp_path):
        output_file = str(tmp_path / "test.json")
        data = {"key": "value", "count": 42}

        write_output(data, output_file)

        with open(output_file) as f:
            loaded = json.load(f)

        assert loaded == data

    def test_should_not_leave_temp_file_on_success(self, tmp_path):
        output_file = str(tmp_path / "test.json")
        write_output({"test": True}, output_file)

        assert not os.path.exists(output_file + ".tmp")

    def test_should_create_parent_directories(self, tmp_path):
        output_file = str(tmp_path / "nested" / "dir" / "test.json")
        write_output({"test": True}, output_file)

        assert os.path.exists(output_file)

    def test_should_overwrite_existing_file(self, tmp_path):
        output_file = str(tmp_path / "test.json")

        write_output({"version": 1}, output_file)
        write_output({"version": 2}, output_file)

        with open(output_file) as f:
            loaded = json.load(f)

        assert loaded["version"] == 2

    def test_should_handle_dates_with_default_str(self, tmp_path):
        from datetime import date, datetime

        output_file = str(tmp_path / "test.json")
        data = {"date": date(2026, 3, 21), "timestamp": datetime(2026, 3, 21, 12, 0)}

        write_output(data, output_file)

        with open(output_file) as f:
            loaded = json.load(f)

        assert loaded["date"] == "2026-03-21"


class TestExitCodes:
    """Verify exit code constants."""

    def test_should_have_correct_exit_values(self):
        assert EXIT_SUCCESS == 0
        assert EXIT_PARTIAL == 1
        assert EXIT_FAILED == 2
