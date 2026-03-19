"""
Feature schema loader and validator for FX Bias AI pipeline.

Loads `models/feature_metadata.json`, validates its integrity,
and provides lookup utilities for feature definitions.

Reference: Task List S-05d, System Design Section 4.6
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_METADATA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "models", "feature_metadata.json"
)
EXPECTED_FEATURE_VERSION = "v2.1-28f"
EXPECTED_TOTAL_FEATURES = 28


def load_feature_metadata(
    path: Optional[str] = None,
) -> dict:
    """
    Load and validate feature_metadata.json.

    Args:
        path: Path to feature_metadata.json. Defaults to models/feature_metadata.json.

    Returns:
        Parsed and validated feature metadata dict

    Raises:
        FileNotFoundError: If the metadata file does not exist
        ValueError: If the metadata is invalid or version mismatches
    """
    if path is None:
        path = os.path.normpath(DEFAULT_METADATA_PATH)

    if not os.path.exists(path):
        raise FileNotFoundError(f"Feature metadata not found: {path}")

    with open(path, "r") as f:
        metadata = json.load(f)

    _validate_metadata_structure(metadata)
    _validate_feature_count(metadata)

    logger.info(
        "Feature metadata loaded: version=%s, features=%d",
        metadata["version"],
        metadata["total_features"],
    )

    return metadata


def check_version_compatibility(
    metadata: dict,
    expected_version: str = EXPECTED_FEATURE_VERSION,
) -> dict:
    """
    Check if the feature metadata version matches expectations.

    Args:
        metadata: Loaded feature metadata dict
        expected_version: Expected version string

    Returns:
        dict with keys: compatible, current_version, expected_version
    """
    current_version = metadata.get("version", "UNKNOWN")
    compatible = current_version == expected_version

    if not compatible:
        logger.warning(
            "Feature version mismatch: current=%s, expected=%s",
            current_version,
            expected_version,
        )

    return {
        "compatible": compatible,
        "current_version": current_version,
        "expected_version": expected_version,
    }


def get_feature_names(metadata: dict) -> list[str]:
    """Extract ordered list of all feature names."""
    names = []
    for group in metadata["groups"]:
        for feature in group["features"]:
            names.append(feature["name"])
    return names


def get_optional_features(metadata: dict) -> list[str]:
    """Extract list of optional feature names (NaN-tolerant)."""
    return [
        feature["name"]
        for group in metadata["groups"]
        for feature in group["features"]
        if feature.get("optional", False)
    ]


def get_feature_by_name(metadata: dict, name: str) -> Optional[dict]:
    """Look up a single feature definition by name."""
    for group in metadata["groups"]:
        for feature in group["features"]:
            if feature["name"] == name:
                return feature
    return None


def get_features_by_source(metadata: dict, source: str) -> list[dict]:
    """Return all features from a specific data source."""
    return [
        feature
        for group in metadata["groups"]
        for feature in group["features"]
        if feature["source"] == source
    ]


def _validate_metadata_structure(metadata: dict) -> None:
    """Validate required top-level keys exist."""
    required_keys = ["version", "total_features", "groups"]
    missing = [key for key in required_keys if key not in metadata]

    if missing:
        raise ValueError(
            f"Feature metadata missing required keys: {missing}"
        )

    if not isinstance(metadata["groups"], list) or len(metadata["groups"]) == 0:
        raise ValueError("Feature metadata 'groups' must be a non-empty array")


def _validate_feature_count(metadata: dict) -> None:
    """Validate total feature count matches declared total."""
    actual_count = sum(
        len(group["features"]) for group in metadata["groups"]
    )
    declared_count = metadata["total_features"]

    if actual_count != declared_count:
        raise ValueError(
            f"Feature count mismatch: declared={declared_count}, "
            f"actual={actual_count}"
        )

    feature_ids = [
        feature["id"]
        for group in metadata["groups"]
        for feature in group["features"]
    ]

    expected_ids = list(range(1, declared_count + 1))
    if sorted(feature_ids) != expected_ids:
        raise ValueError(
            f"Feature IDs must be sequential 1-{declared_count}. "
            f"Got: {sorted(feature_ids)}"
        )
