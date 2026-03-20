"""
backend/utils/model_loader.py — B3-03c

Model loading utility for predict_bias.py.

Supports two models:
  Primary : models/model.pkl         — CalibratedClassifierCV (Random Forest)
  Fallback: models/model_lr_fallback.pkl — LR bundle {model, scaler, features}

Usage in predict_bias.py:
    from backend.utils.model_loader import load_model

    predictor = load_model(use_fallback=False)   # primary RF
    predictor = load_model(use_fallback=True)    # LR fallback

    label   = predictor.predict(X)          # e.g. ["BULL", "BEAR", "NEUTRAL"]
    proba   = predictor.predict_proba(X)    # shape (n, 3)
    classes = predictor.classes_            # ["BEAR", "BULL", "NEUTRAL"]
"""

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MODEL_PATH = _REPO_ROOT / "models" / "model.pkl"
_LR_FALLBACK_PATH = _REPO_ROOT / "models" / "model_lr_fallback.pkl"


# ---------------------------------------------------------------------------
# Wrapper — uniform interface regardless of model type
# ---------------------------------------------------------------------------

class ModelPredictor:
    """
    Thin wrapper providing a consistent predict / predict_proba interface
    for both the RF primary model and the LR fallback bundle.

    The LR bundle (saved by validate_model.py) is:
        {"model": CalibratedClassifierCV, "scaler": StandardScaler, "features": [...]}

    The wrapper applies scaler.transform() automatically before predicting
    when a scaler is present (LR path), so callers always pass raw X.
    """

    def __init__(
        self,
        model,
        scaler=None,
        features: list = None,
        model_type: str = "rf",
    ):
        self._model = model
        self._scaler = scaler
        self._features = features
        self.model_type = model_type  # "rf" | "lr"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def classes_(self) -> np.ndarray:
        return self._model.classes_

    def predict(self, X: np.ndarray) -> np.ndarray:
        X_ready = self._prepare(X)
        return self._model.predict(X_ready)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        X_ready = self._prepare(X)
        return self._model.predict_proba(X_ready)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prepare(self, X: np.ndarray) -> np.ndarray:
        if self._scaler is not None:
            return self._scaler.transform(X)
        return X

    def __repr__(self) -> str:
        return (
            f"ModelPredictor(type={self.model_type}, "
            f"classes={list(self.classes_)}, "
            f"scaler={'yes' if self._scaler else 'no'})"
        )


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_model(use_fallback: bool = False) -> ModelPredictor:
    """
    Load the primary RF model or the LR fallback.

    Args:
        use_fallback: If True, load models/model_lr_fallback.pkl.
                      If False (default), load models/model.pkl.

    Returns:
        ModelPredictor with uniform predict() / predict_proba() interface.

    Raises:
        FileNotFoundError: if the requested model file does not exist.
        ValueError: if the LR bundle is missing expected keys.
    """
    if use_fallback:
        return _load_lr_fallback()
    return _load_primary()


def _load_primary() -> ModelPredictor:
    if not _MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Primary model not found: {_MODEL_PATH}\n"
            "Run training/train_model.py (B3-01) first."
        )
    import joblib  # lazy — not available in test environments without sklearn
    model = joblib.load(_MODEL_PATH)
    logger.info(f"Loaded primary model: {_MODEL_PATH.name}")
    return ModelPredictor(model=model, model_type="rf")


def _load_lr_fallback() -> ModelPredictor:
    if not _LR_FALLBACK_PATH.exists():
        raise FileNotFoundError(
            f"LR fallback not found: {_LR_FALLBACK_PATH}\n"
            "Run training/validate_model.py (B3-02/B3-03) first."
        )
    import joblib  # lazy — not available in test environments without sklearn
    bundle = joblib.load(_LR_FALLBACK_PATH)

    # Validate bundle structure
    required_keys = {"model", "scaler", "features"}
    missing = required_keys - set(bundle.keys())
    if missing:
        raise ValueError(
            f"LR fallback bundle is missing keys: {missing}. "
            "Re-run training/validate_model.py to regenerate."
        )

    logger.info(f"Loaded LR fallback: {_LR_FALLBACK_PATH.name}  "
                f"(features: {len(bundle['features'])})")

    return ModelPredictor(
        model=bundle["model"],
        scaler=bundle["scaler"],
        features=bundle["features"],
        model_type="lr",
    )
