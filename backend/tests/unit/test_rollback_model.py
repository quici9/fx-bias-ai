"""
Unit tests for B4-03 — rollback_model.py

Tests:
  B4-03a  backup_current_model()
  B4-03b  deploy_candidate()
  B4-03c  check_rollback_condition()
  B4-03d  execute_rollback()
  B4-03e  _log_rollback_event()
"""

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — temp directory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_models(tmp_path):
    """Return a tmp models dir with mock .pkl files."""
    models = tmp_path / "models"
    models.mkdir()
    (models / "model.pkl").write_bytes(b"MODEL_CURRENT")
    return models


@pytest.fixture
def tmp_metrics(tmp_path):
    """Return a tmp metrics dir with initial_training + validation_results."""
    metrics = tmp_path / "history" / "model-metrics"
    metrics.mkdir(parents=True)
    return metrics


def _write_initial_training(metrics: Path, mean_accuracy: float):
    data = {"walk_forward_summary": {"mean_accuracy": mean_accuracy}}
    (metrics / "initial_training.json").write_text(json.dumps(data))


def _write_validation_results(metrics: Path, fold_accs: dict):
    """fold_accs: {"fold1": {"rf": 0.65}, ...}"""
    data = {"folds": fold_accs}
    (metrics / "validation_results.json").write_text(json.dumps(data))


# ---------------------------------------------------------------------------
# B4-03a — backup_current_model
# ---------------------------------------------------------------------------


class TestBackupCurrentModel:
    def test_backup_creates_model_backup(self, tmp_models):
        import backend.scripts.rollback_model as rm

        with (
            patch.object(rm, "MODEL_PATH", tmp_models / "model.pkl"),
            patch.object(rm, "MODEL_BACKUP_PATH", tmp_models / "model_backup.pkl"),
            patch.object(rm, "MODEL_BACKUP_PREV", tmp_models / "model_backup_prev.pkl"),
            patch.object(rm, "MODELS_DIR", tmp_models),
        ):
            result = rm.backup_current_model()

        assert result is True
        assert (tmp_models / "model_backup.pkl").read_bytes() == b"MODEL_CURRENT"

    def test_backup_rotates_existing_backup(self, tmp_models):
        import backend.scripts.rollback_model as rm

        (tmp_models / "model_backup.pkl").write_bytes(b"MODEL_PREV")

        with (
            patch.object(rm, "MODEL_PATH", tmp_models / "model.pkl"),
            patch.object(rm, "MODEL_BACKUP_PATH", tmp_models / "model_backup.pkl"),
            patch.object(rm, "MODEL_BACKUP_PREV", tmp_models / "model_backup_prev.pkl"),
            patch.object(rm, "MODELS_DIR", tmp_models),
        ):
            rm.backup_current_model()

        assert (tmp_models / "model_backup_prev.pkl").read_bytes() == b"MODEL_PREV"
        assert (tmp_models / "model_backup.pkl").read_bytes() == b"MODEL_CURRENT"

    def test_backup_returns_false_if_no_model(self, tmp_path):
        import backend.scripts.rollback_model as rm

        missing = tmp_path / "models"
        missing.mkdir()

        with (
            patch.object(rm, "MODEL_PATH", missing / "model.pkl"),
            patch.object(rm, "MODEL_BACKUP_PATH", missing / "model_backup.pkl"),
            patch.object(rm, "MODEL_BACKUP_PREV", missing / "model_backup_prev.pkl"),
            patch.object(rm, "MODELS_DIR", missing),
        ):
            result = rm.backup_current_model()

        assert result is False


# ---------------------------------------------------------------------------
# B4-03b — deploy_candidate
# ---------------------------------------------------------------------------


class TestDeployCandidate:
    def test_deploy_promotes_candidate(self, tmp_models):
        import backend.scripts.rollback_model as rm

        (tmp_models / "model_candidate.pkl").write_bytes(b"MODEL_CANDIDATE")

        with (
            patch.object(rm, "MODEL_PATH", tmp_models / "model.pkl"),
            patch.object(rm, "MODEL_BACKUP_PATH", tmp_models / "model_backup.pkl"),
            patch.object(rm, "MODEL_BACKUP_PREV", tmp_models / "model_backup_prev.pkl"),
            patch.object(rm, "MODEL_CANDIDATE", tmp_models / "model_candidate.pkl"),
            patch.object(rm, "MODELS_DIR", tmp_models),
        ):
            result = rm.deploy_candidate()

        assert result is True
        assert (tmp_models / "model.pkl").read_bytes() == b"MODEL_CANDIDATE"
        # Old model.pkl should be backed up
        assert (tmp_models / "model_backup.pkl").read_bytes() == b"MODEL_CURRENT"

    def test_deploy_returns_false_if_no_candidate(self, tmp_models):
        import backend.scripts.rollback_model as rm

        with (
            patch.object(rm, "MODEL_PATH", tmp_models / "model.pkl"),
            patch.object(rm, "MODEL_BACKUP_PATH", tmp_models / "model_backup.pkl"),
            patch.object(rm, "MODEL_BACKUP_PREV", tmp_models / "model_backup_prev.pkl"),
            patch.object(rm, "MODEL_CANDIDATE", tmp_models / "model_candidate.pkl"),
            patch.object(rm, "MODELS_DIR", tmp_models),
        ):
            result = rm.deploy_candidate()

        assert result is False


# ---------------------------------------------------------------------------
# B4-03c — check_rollback_condition
# ---------------------------------------------------------------------------


class TestCheckRollbackCondition:
    def test_no_rollback_when_accuracy_ok(self, tmp_metrics):
        import backend.scripts.rollback_model as rm

        _write_initial_training(tmp_metrics, mean_accuracy=0.70)
        _write_validation_results(
            tmp_metrics,
            {"f1": {"rf": 0.68}, "f2": {"rf": 0.66}, "f3": {"rf": 0.67}, "f4": {"rf": 0.69}},
        )

        should_rollback, details = rm.check_rollback_condition(tmp_metrics)

        assert should_rollback is False
        assert details["baseline_accuracy"] == pytest.approx(0.70, abs=1e-4)
        assert details["accuracy_4w"] is not None
        assert details["drift"] < rm.ROLLBACK_MARGIN

    def test_rollback_triggered_when_drift_exceeds_margin(self, tmp_metrics):
        import backend.scripts.rollback_model as rm

        _write_initial_training(tmp_metrics, mean_accuracy=0.70)
        # accuracy_4w ≈ 0.60 → drift = 0.10 > 0.05
        _write_validation_results(
            tmp_metrics,
            {"f1": {"rf": 0.60}, "f2": {"rf": 0.60}, "f3": {"rf": 0.60}, "f4": {"rf": 0.60}},
        )

        should_rollback, details = rm.check_rollback_condition(tmp_metrics)

        assert should_rollback is True
        assert details["drift"] == pytest.approx(0.10, abs=1e-4)

    def test_exactly_at_margin_no_rollback(self, tmp_metrics):
        import backend.scripts.rollback_model as rm

        _write_initial_training(tmp_metrics, mean_accuracy=0.70)
        # accuracy_4w = 0.65 → drift = 0.05 (not strictly greater)
        _write_validation_results(
            tmp_metrics,
            {"f1": {"rf": 0.65}, "f2": {"rf": 0.65}, "f3": {"rf": 0.65}, "f4": {"rf": 0.65}},
        )

        should_rollback, details = rm.check_rollback_condition(tmp_metrics)

        assert should_rollback is False

    def test_missing_initial_training_returns_false(self, tmp_metrics):
        import backend.scripts.rollback_model as rm

        _write_validation_results(tmp_metrics, {"f1": {"rf": 0.60}})

        should_rollback, details = rm.check_rollback_condition(tmp_metrics)

        assert should_rollback is False
        assert details["baseline_accuracy"] is None

    def test_missing_validation_returns_false(self, tmp_metrics):
        import backend.scripts.rollback_model as rm

        _write_initial_training(tmp_metrics, mean_accuracy=0.70)

        should_rollback, details = rm.check_rollback_condition(tmp_metrics)

        assert should_rollback is False

    def test_only_last_4_folds_used(self, tmp_metrics):
        """6 folds present — only last 4 should be averaged."""
        import backend.scripts.rollback_model as rm

        _write_initial_training(tmp_metrics, mean_accuracy=0.70)
        # first 2 folds are 0.40 (very low), last 4 are 0.68
        folds = {
            "f1": {"rf": 0.40},
            "f2": {"rf": 0.40},
            "f3": {"rf": 0.68},
            "f4": {"rf": 0.68},
            "f5": {"rf": 0.68},
            "f6": {"rf": 0.68},
        }
        _write_validation_results(tmp_metrics, folds)

        should_rollback, details = rm.check_rollback_condition(tmp_metrics)

        assert details["folds_used"] == 4
        assert details["accuracy_4w"] == pytest.approx(0.68, abs=1e-4)
        assert should_rollback is False


# ---------------------------------------------------------------------------
# B4-03e — _log_rollback_event
# ---------------------------------------------------------------------------


class TestLogRollbackEvent:
    def test_creates_rollback_file(self, tmp_metrics):
        import backend.scripts.rollback_model as rm

        details = {
            "baseline_accuracy": 0.70,
            "accuracy_4w": 0.60,
            "drift": 0.10,
            "threshold": 0.05,
            "folds_used": 4,
        }
        log_path = rm._log_rollback_event(details, "test reason", metrics_dir=tmp_metrics)

        assert log_path.exists()
        data = json.loads(log_path.read_text())
        assert data["reason"] == "test reason"
        assert data["baseline_accuracy"] == pytest.approx(0.70, abs=1e-4)
        assert data["accuracy_4w"] == pytest.approx(0.60, abs=1e-4)
        assert "week_label" in data
        assert "timestamp_utc" in data

    def test_filename_format(self, tmp_metrics):
        import backend.scripts.rollback_model as rm
        from datetime import datetime, timezone

        now = datetime.now(tz=timezone.utc)
        iso = now.isocalendar()
        expected_name = f"rollback_{iso[0]}-W{iso[1]:02d}.json"

        log_path = rm._log_rollback_event({}, "test", metrics_dir=tmp_metrics)

        assert log_path.name == expected_name


# ---------------------------------------------------------------------------
# B4-03d — execute_rollback
# ---------------------------------------------------------------------------


class TestExecuteRollback:
    def test_restores_backup_to_model(self, tmp_models, tmp_metrics):
        import backend.scripts.rollback_model as rm

        (tmp_models / "model_backup.pkl").write_bytes(b"MODEL_BACKUP")

        details = {
            "baseline_accuracy": 0.70,
            "accuracy_4w": 0.60,
            "drift": 0.10,
            "threshold": 0.05,
            "folds_used": 4,
        }

        alerts_file = tmp_models.parent / "data" / "alerts-pending.json"

        with (
            patch.object(rm, "MODEL_PATH", tmp_models / "model.pkl"),
            patch.object(rm, "MODEL_BACKUP_PATH", tmp_models / "model_backup.pkl"),
            patch.object(rm, "METRICS_DIR", tmp_metrics),
            patch.object(rm, "_REPO_ROOT", tmp_models.parent),
            patch.object(rm, "_send_rollback_notification", return_value=None),
        ):
            result = rm.execute_rollback(details, "test rollback", notify_script=Path("/dev/null"))

        assert result is True
        assert (tmp_models / "model.pkl").read_bytes() == b"MODEL_BACKUP"

    def test_returns_false_if_no_backup(self, tmp_models, tmp_metrics):
        import backend.scripts.rollback_model as rm

        details = {"baseline_accuracy": 0.70, "accuracy_4w": 0.60, "drift": 0.10,
                   "threshold": 0.05, "folds_used": 4}

        with (
            patch.object(rm, "MODEL_PATH", tmp_models / "model.pkl"),
            patch.object(rm, "MODEL_BACKUP_PATH", tmp_models / "model_backup.pkl"),
        ):
            result = rm.execute_rollback(details, "test")

        assert result is False

    def test_alert_written_to_alerts_pending(self, tmp_models, tmp_metrics, tmp_path):
        import backend.scripts.rollback_model as rm

        (tmp_models / "model_backup.pkl").write_bytes(b"BACKUP")
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        details = {"baseline_accuracy": 0.70, "accuracy_4w": 0.60, "drift": 0.10,
                   "threshold": 0.05, "folds_used": 4}

        with (
            patch.object(rm, "MODEL_PATH", tmp_models / "model.pkl"),
            patch.object(rm, "MODEL_BACKUP_PATH", tmp_models / "model_backup.pkl"),
            patch.object(rm, "METRICS_DIR", tmp_metrics),
            patch.object(rm, "_REPO_ROOT", tmp_path),
            patch.object(rm, "_send_rollback_notification", return_value=None),
        ):
            rm.execute_rollback(details, "accuracy drop", notify_script=Path("/dev/null"))

        alerts_file = tmp_path / "data" / "alerts-pending.json"
        assert alerts_file.exists()
        alerts = json.loads(alerts_file.read_text())
        types = [a["type"] for a in alerts]
        assert "MODEL_ROLLBACK" in types

    def test_existing_alerts_preserved(self, tmp_models, tmp_metrics, tmp_path):
        import backend.scripts.rollback_model as rm

        (tmp_models / "model_backup.pkl").write_bytes(b"BACKUP")
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Pre-existing alert
        existing = [{"type": "RISK_OFF_REGIME", "message": "VIX high", "severity": "HIGH"}]
        (data_dir / "alerts-pending.json").write_text(json.dumps(existing))

        details = {"baseline_accuracy": 0.70, "accuracy_4w": 0.60, "drift": 0.10,
                   "threshold": 0.05, "folds_used": 4}

        with (
            patch.object(rm, "MODEL_PATH", tmp_models / "model.pkl"),
            patch.object(rm, "MODEL_BACKUP_PATH", tmp_models / "model_backup.pkl"),
            patch.object(rm, "METRICS_DIR", tmp_metrics),
            patch.object(rm, "_REPO_ROOT", tmp_path),
            patch.object(rm, "_send_rollback_notification", return_value=None),
        ):
            rm.execute_rollback(details, "drift", notify_script=Path("/dev/null"))

        alerts = json.loads((data_dir / "alerts-pending.json").read_text())
        types = [a["type"] for a in alerts]
        assert "RISK_OFF_REGIME" in types
        assert "MODEL_ROLLBACK" in types


# ---------------------------------------------------------------------------
# main() — integration path
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_no_rollback(self, tmp_metrics):
        import backend.scripts.rollback_model as rm

        _write_initial_training(tmp_metrics, 0.70)
        _write_validation_results(tmp_metrics, {"f1": {"rf": 0.68}, "f2": {"rf": 0.68}})

        with patch.object(rm, "METRICS_DIR", tmp_metrics):
            rc = rm.main()

        assert rc == rm.EXIT_SUCCESS

    def test_main_triggers_rollback(self, tmp_models, tmp_metrics):
        import backend.scripts.rollback_model as rm

        _write_initial_training(tmp_metrics, 0.70)
        _write_validation_results(tmp_metrics, {"f1": {"rf": 0.50}, "f2": {"rf": 0.50}})
        (tmp_models / "model_backup.pkl").write_bytes(b"BACKUP")

        data_dir = tmp_models.parent / "data"
        data_dir.mkdir(exist_ok=True)

        with (
            patch.object(rm, "METRICS_DIR", tmp_metrics),
            patch.object(rm, "MODEL_PATH", tmp_models / "model.pkl"),
            patch.object(rm, "MODEL_BACKUP_PATH", tmp_models / "model_backup.pkl"),
            patch.object(rm, "_REPO_ROOT", tmp_models.parent),
            patch.object(rm, "_send_rollback_notification", return_value=None),
        ):
            rc = rm.main()

        assert rc == rm.EXIT_SUCCESS
        assert (tmp_models / "model.pkl").read_bytes() == b"BACKUP"
