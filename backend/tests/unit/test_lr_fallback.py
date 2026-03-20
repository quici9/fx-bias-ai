"""
Unit tests — B3-03c: LR Fallback via predict_bias.py (model_loader)

Verifies that:
  1. load_model(use_fallback=False) routes to primary RF model
  2. load_model(use_fallback=True)  routes to LR fallback bundle
  3. ModelPredictor.predict() returns valid label strings
  4. ModelPredictor.predict_proba() returns valid probability matrix
  5. LR path applies scaler.transform() before predict
  6. RF path does NOT apply scaler transform
  7. FileNotFoundError raised when model files are absent
  8. ValueError raised when LR bundle is malformed

All tests use mocks — no real .pkl files required.

Reference: Task List B3-03c
"""

import sys
import os
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backend.utils.model_loader import ModelPredictor, load_model


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CLASSES = np.array(["BEAR", "BULL", "NEUTRAL"])
N_SAMPLES = 5
N_FEATURES = 29  # 28 features + currency_enc


def _make_mock_model(classes=CLASSES) -> MagicMock:
    """Fake CalibratedClassifierCV-like model."""
    model = MagicMock()
    model.classes_ = classes
    model.predict.return_value = np.array(["BULL", "BEAR", "NEUTRAL", "BULL", "BEAR"])
    model.predict_proba.return_value = np.array([
        [0.10, 0.75, 0.15],
        [0.70, 0.10, 0.20],
        [0.15, 0.20, 0.65],
        [0.05, 0.80, 0.15],
        [0.65, 0.15, 0.20],
    ])
    return model


def _make_mock_scaler() -> MagicMock:
    """Fake StandardScaler that returns input unchanged."""
    scaler = MagicMock()
    scaler.transform.side_effect = lambda X: X * 1.0   # identity, but records calls
    return scaler


def _sample_X() -> np.ndarray:
    return np.random.default_rng(0).random((N_SAMPLES, N_FEATURES)).astype(np.float32)


# ---------------------------------------------------------------------------
# ModelPredictor — RF path (no scaler)
# ---------------------------------------------------------------------------

class TestModelPredictorRF:
    def setup_method(self):
        self.mock_model = _make_mock_model()
        self.predictor = ModelPredictor(model=self.mock_model, model_type="rf")
        self.X = _sample_X()

    def test_classes_exposed(self):
        assert list(self.predictor.classes_) == ["BEAR", "BULL", "NEUTRAL"]

    def test_model_type_rf(self):
        assert self.predictor.model_type == "rf"

    def test_predict_returns_label_strings(self):
        result = self.predictor.predict(self.X)
        assert len(result) == N_SAMPLES
        assert all(label in {"BULL", "BEAR", "NEUTRAL"} for label in result)

    def test_predict_delegates_to_model(self):
        self.predictor.predict(self.X)
        self.mock_model.predict.assert_called_once()

    def test_predict_proba_shape(self):
        proba = self.predictor.predict_proba(self.X)
        assert proba.shape == (N_SAMPLES, 3)

    def test_predict_proba_rows_sum_to_one(self):
        proba = self.predictor.predict_proba(self.X)
        row_sums = proba.sum(axis=1)
        np.testing.assert_allclose(row_sums, 1.0, atol=1e-5)

    def test_no_scaler_transform_called(self):
        """RF path must NOT apply a scaler (raw X passed directly)."""
        self.predictor.predict(self.X)
        # _scaler is None — no transform calls to verify; just confirm X passes through
        call_args = self.mock_model.predict.call_args[0][0]
        np.testing.assert_array_equal(call_args, self.X)

    def test_repr_contains_type(self):
        r = repr(self.predictor)
        assert "rf" in r
        assert "scaler=no" in r


# ---------------------------------------------------------------------------
# ModelPredictor — LR path (with scaler)
# ---------------------------------------------------------------------------

class TestModelPredictorLR:
    def setup_method(self):
        self.mock_model = _make_mock_model()
        self.mock_scaler = _make_mock_scaler()
        self.predictor = ModelPredictor(
            model=self.mock_model,
            scaler=self.mock_scaler,
            features=["f1", "f2"],
            model_type="lr",
        )
        self.X = _sample_X()

    def test_model_type_lr(self):
        assert self.predictor.model_type == "lr"

    def test_predict_applies_scaler(self):
        """LR path must call scaler.transform() before predict()."""
        self.predictor.predict(self.X)
        self.mock_scaler.transform.assert_called_once()

    def test_predict_proba_applies_scaler(self):
        self.predictor.predict_proba(self.X)
        self.mock_scaler.transform.assert_called_once()

    def test_predict_passes_scaled_X_to_model(self):
        """Scaled X (output of transform) must be what the model receives."""
        scaled = self.X * 1.0
        self.mock_scaler.transform.return_value = scaled
        self.predictor.predict(self.X)
        call_args = self.mock_model.predict.call_args[0][0]
        np.testing.assert_array_equal(call_args, scaled)

    def test_predict_returns_valid_labels(self):
        result = self.predictor.predict(self.X)
        assert all(label in {"BULL", "BEAR", "NEUTRAL"} for label in result)

    def test_predict_proba_shape(self):
        proba = self.predictor.predict_proba(self.X)
        assert proba.shape == (N_SAMPLES, 3)

    def test_repr_contains_scaler_yes(self):
        assert "scaler=yes" in repr(self.predictor)


# ---------------------------------------------------------------------------
# load_model() — routing
# ---------------------------------------------------------------------------

class TestLoadModelRouting:
    """Verify load_model() routes to correct file based on use_fallback flag."""

    def _make_lr_bundle(self):
        return {
            "model": _make_mock_model(),
            "scaler": _make_mock_scaler(),
            "features": ["f1", "f2", "currency_enc"],
        }

    @patch("backend.utils.model_loader._MODEL_PATH")
    def test_use_fallback_false_loads_primary(self, mock_path):
        mock_path.exists.return_value = True
        with patch("builtins.__import__", wraps=_import_joblib_load(_make_mock_model())):
            predictor = load_model(use_fallback=False)
        assert predictor.model_type == "rf"

    @patch("backend.utils.model_loader._LR_FALLBACK_PATH")
    def test_use_fallback_true_loads_lr(self, mock_path):
        mock_path.exists.return_value = True
        with patch("builtins.__import__", wraps=_import_joblib_load(self._make_lr_bundle())):
            predictor = load_model(use_fallback=True)
        assert predictor.model_type == "lr"

    @patch("backend.utils.model_loader._LR_FALLBACK_PATH")
    def test_lr_predictor_has_scaler(self, mock_path):
        mock_path.exists.return_value = True
        with patch("builtins.__import__", wraps=_import_joblib_load(self._make_lr_bundle())):
            predictor = load_model(use_fallback=True)
        assert predictor._scaler is not None

    @patch("backend.utils.model_loader._MODEL_PATH")
    def test_rf_predictor_has_no_scaler(self, mock_path):
        mock_path.exists.return_value = True
        with patch("builtins.__import__", wraps=_import_joblib_load(_make_mock_model())):
            predictor = load_model(use_fallback=False)
        assert predictor._scaler is None


def _import_joblib_load(return_value):
    """
    Helper: returns a __import__ wrapper that intercepts 'import joblib'
    and injects a mock with joblib.load returning return_value.
    """
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _fake_import(name, *args, **kwargs):
        if name == "joblib":
            mock_joblib = MagicMock()
            mock_joblib.load.return_value = return_value
            return mock_joblib
        return real_import(name, *args, **kwargs)

    return _fake_import


# ---------------------------------------------------------------------------
# load_model() — error handling (no joblib needed — errors before import)
# ---------------------------------------------------------------------------

class TestLoadModelErrors:
    @patch("backend.utils.model_loader._MODEL_PATH")
    def test_primary_not_found_raises_filenotfounderror(self, mock_path):
        mock_path.exists.return_value = False
        with pytest.raises(FileNotFoundError, match="Primary model not found"):
            load_model(use_fallback=False)

    @patch("backend.utils.model_loader._LR_FALLBACK_PATH")
    def test_lr_not_found_raises_filenotfounderror(self, mock_path):
        mock_path.exists.return_value = False
        with pytest.raises(FileNotFoundError, match="LR fallback not found"):
            load_model(use_fallback=True)

    @patch("backend.utils.model_loader._LR_FALLBACK_PATH")
    def test_malformed_bundle_missing_scaler_raises_valueerror(self, mock_path):
        mock_path.exists.return_value = True
        bad_bundle = {"model": _make_mock_model()}  # missing scaler + features
        with patch("builtins.__import__", wraps=_import_joblib_load(bad_bundle)):
            with pytest.raises(ValueError, match="missing keys"):
                load_model(use_fallback=True)

    @patch("backend.utils.model_loader._LR_FALLBACK_PATH")
    def test_malformed_bundle_missing_model_raises_valueerror(self, mock_path):
        mock_path.exists.return_value = True
        bad_bundle = {"scaler": _make_mock_scaler(), "features": ["f1"]}
        with patch("builtins.__import__", wraps=_import_joblib_load(bad_bundle)):
            with pytest.raises(ValueError, match="missing keys"):
                load_model(use_fallback=True)


# ---------------------------------------------------------------------------
# End-to-end: load LR fallback → predict full pipeline
# ---------------------------------------------------------------------------

class TestLRFallbackEndToEnd:
    """
    Simulates predict_bias.py usage with use_fallback=True.
    Verifies the complete chain: load → predict → proba → confidence.
    """

    @patch("backend.utils.model_loader._LR_FALLBACK_PATH")
    def test_full_inference_pipeline_lr(self, mock_path):
        mock_path.exists.return_value = True
        mock_model = _make_mock_model()
        mock_scaler = _make_mock_scaler()
        bundle = {
            "model": mock_model,
            "scaler": mock_scaler,
            "features": [f"feat_{i}" for i in range(N_FEATURES)],
        }

        with patch("builtins.__import__", wraps=_import_joblib_load(bundle)):
            predictor = load_model(use_fallback=True)

        X = _sample_X()
        labels = predictor.predict(X)
        proba = predictor.predict_proba(X)

        # Labels are valid strings
        assert len(labels) == N_SAMPLES
        assert all(label in {"BULL", "BEAR", "NEUTRAL"} for label in labels)

        # Proba is a valid probability matrix
        assert proba.shape == (N_SAMPLES, len(CLASSES))
        row_sums = proba.sum(axis=1)
        np.testing.assert_allclose(row_sums, 1.0, atol=1e-5)

        # Confidence computation (as in predict_bias.py)
        max_proba = proba.max(axis=1)
        confidence_levels = np.where(
            max_proba >= 0.70, "HIGH",
            np.where(max_proba >= 0.55, "MEDIUM", "LOW")
        )
        assert all(c in {"HIGH", "MEDIUM", "LOW"} for c in confidence_levels)

        # Scaler was applied
        mock_scaler.transform.assert_called()

    @patch("backend.utils.model_loader._MODEL_PATH")
    def test_full_inference_pipeline_rf(self, mock_path):
        mock_path.exists.return_value = True
        mock_model = _make_mock_model()

        with patch("builtins.__import__", wraps=_import_joblib_load(mock_model)):
            predictor = load_model(use_fallback=False)

        X = _sample_X()
        labels = predictor.predict(X)
        proba = predictor.predict_proba(X)

        assert len(labels) == N_SAMPLES
        assert proba.shape == (N_SAMPLES, len(CLASSES))
        assert predictor.model_type == "rf"
