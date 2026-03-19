"""
Unit tests for backend/utils/feature_schema.py

Validates feature metadata loading, version checking, and feature queries.
"""

import json
import os
import pytest

from backend.utils.feature_schema import (
    EXPECTED_FEATURE_VERSION,
    EXPECTED_TOTAL_FEATURES,
    check_version_compatibility,
    get_feature_by_name,
    get_feature_names,
    get_features_by_source,
    get_optional_features,
    load_feature_metadata,
)


@pytest.fixture
def metadata_path():
    """Return path to the actual feature_metadata.json."""
    return os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "models", "feature_metadata.json"
    )


@pytest.fixture
def metadata(metadata_path):
    """Load the actual feature metadata."""
    return load_feature_metadata(metadata_path)


class TestLoadFeatureMetadata:
    """Verify feature metadata loading and validation."""

    def test_should_load_successfully(self, metadata_path):
        metadata = load_feature_metadata(metadata_path)
        assert metadata is not None
        assert "version" in metadata
        assert "total_features" in metadata
        assert "groups" in metadata

    def test_should_have_correct_version(self, metadata):
        assert metadata["version"] == EXPECTED_FEATURE_VERSION

    def test_should_have_28_total_features(self, metadata):
        assert metadata["total_features"] == EXPECTED_TOTAL_FEATURES

    def test_should_have_4_groups(self, metadata):
        assert len(metadata["groups"]) == 4

    def test_should_raise_for_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            load_feature_metadata("/nonexistent/path.json")

    def test_should_raise_for_invalid_structure(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text(json.dumps({"version": "test"}))

        with pytest.raises(ValueError, match="missing required keys"):
            load_feature_metadata(str(bad_file))

    def test_should_raise_for_wrong_feature_count(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_data = {
            "version": "test",
            "total_features": 5,
            "groups": [
                {
                    "name": "Test",
                    "features": [
                        {
                            "id": 1,
                            "name": "test",
                            "description": "test",
                            "formula": "test",
                            "optional": False,
                            "source": "DERIVED",
                        }
                    ],
                }
            ],
        }
        bad_file.write_text(json.dumps(bad_data))

        with pytest.raises(ValueError, match="Feature count mismatch"):
            load_feature_metadata(str(bad_file))


class TestCheckVersionCompatibility:
    """Verify version compatibility checking."""

    def test_should_be_compatible_with_correct_version(self, metadata):
        result = check_version_compatibility(metadata)
        assert result["compatible"] is True

    def test_should_be_incompatible_with_wrong_version(self, metadata):
        result = check_version_compatibility(metadata, expected_version="v1.0-10f")
        assert result["compatible"] is False

    def test_should_include_version_info(self, metadata):
        result = check_version_compatibility(metadata)
        assert result["current_version"] == EXPECTED_FEATURE_VERSION
        assert result["expected_version"] == EXPECTED_FEATURE_VERSION


class TestGetFeatureNames:
    """Verify feature name extraction."""

    def test_should_return_28_names(self, metadata):
        names = get_feature_names(metadata)
        assert len(names) == 28

    def test_should_start_with_cot_index(self, metadata):
        names = get_feature_names(metadata)
        assert names[0] == "cot_index"

    def test_should_end_with_quarter(self, metadata):
        names = get_feature_names(metadata)
        assert names[-1] == "quarter"

    def test_should_have_unique_names(self, metadata):
        names = get_feature_names(metadata)
        assert len(names) == len(set(names))


class TestGetOptionalFeatures:
    """Verify optional feature identification."""

    def test_should_return_pmi_as_optional(self, metadata):
        optional = get_optional_features(metadata)
        assert "pmi_composite_diff" in optional

    def test_should_not_include_cot_index(self, metadata):
        optional = get_optional_features(metadata)
        assert "cot_index" not in optional


class TestGetFeatureByName:
    """Verify single feature lookup."""

    def test_should_find_existing_feature(self, metadata):
        feature = get_feature_by_name(metadata, "cot_index")
        assert feature is not None
        assert feature["id"] == 1

    def test_should_return_none_for_unknown_feature(self, metadata):
        result = get_feature_by_name(metadata, "nonexistent")
        assert result is None


class TestGetFeaturesBySource:
    """Verify source-based filtering."""

    def test_should_find_cftc_legacy_features(self, metadata):
        features = get_features_by_source(metadata, "CFTC_LEGACY")
        assert len(features) >= 10  # Group A has 10+ legacy features

    def test_should_find_fred_features(self, metadata):
        features = get_features_by_source(metadata, "FRED")
        assert len(features) >= 5  # Group C macro features

    def test_should_return_empty_for_unknown_source(self, metadata):
        features = get_features_by_source(metadata, "UNKNOWN")
        assert features == []
