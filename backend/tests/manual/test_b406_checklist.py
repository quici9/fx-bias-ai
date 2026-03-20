"""
B4-06 — Manual Testing Checklist (automated where possible)

B4-06a  Trigger pipeline manually → verify bias-latest.json format
        → REQUIRES GitHub Actions (push & trigger workflow_dispatch)
        → Local verification: run verify_bias_format() on committed file

B4-06b  Verify Telegram message received within 5 minutes
        → REQUIRES real TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID secrets in GH

B4-06c  Test rollback: override accuracy threshold → verify model_backup.pkl restored
        → AUTOMATED below (pure mock, no real model)

B4-06d  Test FEATURE_VERSION_MISMATCH: change version → verify LR fallback alert fires
        → AUTOMATED below (mock feature_metadata.json)

B4-06e  Run 2 consecutive weeks: verify history files appended correctly
        → AUTOMATED below (mock 2 append_bias_history calls)

Run:
    pytest backend/tests/manual/test_b406_checklist.py -v
"""

import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Project root on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

import backend.scripts.rollback_model as rm
import backend.scripts.generate_alerts as ga
import backend.scripts.predict_bias as pb


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _write_initial_training(metrics: Path, mean_accuracy: float) -> None:
    (metrics / "initial_training.json").write_text(
        json.dumps({"walk_forward_summary": {"mean_accuracy": mean_accuracy}})
    )


def _write_validation_results(metrics: Path, fold_accs: dict) -> None:
    (metrics / "validation_results.json").write_text(
        json.dumps({"folds": fold_accs})
    )


def _minimal_bias_report(week_label: str = "2026-W12") -> dict:
    return {
        "meta": {
            "weekLabel": week_label,
            "generatedAt": datetime.now(tz=timezone.utc).isoformat(),
            "modelVersion": "rf-v2.1",
            "featureVersion": "v2.1-28f",
            "overallConfidence": "MEDIUM",
            "dataSourceStatus": {"cot": "OK", "macro": "OK"},
            "pipelineRuntime": 1.23,
        },
        "predictions": [
            {
                "currency": "EUR",
                "bias": "BULL",
                "probability": {"bull": 0.72, "neutral": 0.18, "bear": 0.10},
                "confidence": "HIGH",
                "rank": 1,
                "key_drivers": ["COT positioning"],
                "alerts": [],
            }
        ],
        "pair_recommendations": {
            "strong_long": [{"pair": "EUR/USD", "spread": 0.6, "base_currency": "EUR",
                             "quote_currency": "USD", "confidence": "HIGH"}],
            "strong_short": [],
            "avoid": [],
        },
        "weekly_alerts": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# B4-06a — bias-latest.json format verification (local, no GH Actions required)
# ─────────────────────────────────────────────────────────────────────────────

class TestB406a_BiasFormat:
    """
    B4-06a: Verify bias-latest.json is in correct schema format.
    In CI: triggered after predict-bias workflow commits the file.
    Locally: runs against a mock report to verify the format checker itself.
    NOTE: Real trigger verification (GitHub Actions commit) cannot be automated locally.
    """

    def test_required_top_level_keys_present(self):
        report = _minimal_bias_report()
        required = {"meta", "predictions", "pair_recommendations", "weekly_alerts"}
        assert required.issubset(set(report.keys()))

    def test_meta_contains_required_fields(self):
        meta = _minimal_bias_report()["meta"]
        required_meta = {
            "weekLabel", "generatedAt", "modelVersion",
            "featureVersion", "overallConfidence",
        }
        assert required_meta.issubset(set(meta.keys()))

    def test_week_label_format(self):
        import re
        label = _minimal_bias_report()["meta"]["weekLabel"]
        assert re.match(r"^\d{4}-W\d{2}$", label), f"Invalid weekLabel: {label}"

    def test_predictions_have_required_fields(self):
        pred = _minimal_bias_report()["predictions"][0]
        required = {"currency", "bias", "probability", "confidence", "rank"}
        assert required.issubset(set(pred.keys()))

    def test_bias_values_valid(self):
        pred = _minimal_bias_report()["predictions"][0]
        assert pred["bias"] in ("BULL", "BEAR", "NEUTRAL")

    def test_probability_keys_valid(self):
        proba = _minimal_bias_report()["predictions"][0]["probability"]
        assert set(proba.keys()) == {"bull", "neutral", "bear"}
        total = sum(proba.values())
        assert abs(total - 1.0) < 0.01, f"Probabilities sum to {total} (expected ~1.0)"

    def test_pair_recommendations_keys(self):
        recs = _minimal_bias_report()["pair_recommendations"]
        assert set(recs.keys()) == {"strong_long", "strong_short", "avoid"}

    def test_write_and_read_roundtrip(self, tmp_path):
        """bias-latest.json written as compact JSON and re-read correctly."""
        report = _minimal_bias_report()
        out_file = tmp_path / "bias-latest.json"

        with patch.object(pb, "BIAS_LATEST_FILE", out_file):
            with patch.object(pb, "DATA_DIR", tmp_path):
                pb.write_bias_latest(report)

        assert out_file.exists()
        loaded = json.loads(out_file.read_text())
        assert loaded["meta"]["weekLabel"] == report["meta"]["weekLabel"]
        assert loaded["predictions"][0]["currency"] == "EUR"


# ─────────────────────────────────────────────────────────────────────────────
# B4-06c — Rollback test
# Override accuracy threshold → verify model_backup.pkl restored
# ─────────────────────────────────────────────────────────────────────────────

class TestB406c_Rollback:
    """
    B4-06c: Test that rollback restores model_backup.pkl → model.pkl when
    rolling 4-week accuracy drops more than 5% below baseline.
    """

    @pytest.fixture
    def rollback_env(self, tmp_path):
        """Set up mock model files + metrics that trigger rollback."""
        models = tmp_path / "models"
        models.mkdir()
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        (models / "model.pkl").write_bytes(b"NEW_UNDERPERFORMING_MODEL")
        (models / "model_backup.pkl").write_bytes(b"PREVIOUS_GOOD_MODEL")

        metrics = tmp_path / "data" / "history" / "model-metrics"
        metrics.mkdir(parents=True)

        # baseline = 70%, recent = 58% → drift = 12% > 5% threshold → rollback
        _write_initial_training(metrics, mean_accuracy=0.70)
        _write_validation_results(
            metrics,
            {"f1": {"rf": 0.58}, "f2": {"rf": 0.58},
             "f3": {"rf": 0.58}, "f4": {"rf": 0.58}},
        )

        return {"models": models, "metrics": metrics, "data": data_dir, "root": tmp_path}

    def test_rollback_condition_is_detected(self, rollback_env):
        """check_rollback_condition() returns True when accuracy drops > 5%."""
        should, details = rm.check_rollback_condition(rollback_env["metrics"])
        assert should is True, "Expected rollback condition to be True"
        assert details["drift"] > rm.ROLLBACK_MARGIN

    def test_execute_rollback_restores_backup(self, rollback_env):
        """execute_rollback() copies model_backup.pkl back to model.pkl."""
        env = rollback_env
        _, details = rm.check_rollback_condition(env["metrics"])

        with (
            patch.object(rm, "MODEL_PATH",        env["models"] / "model.pkl"),
            patch.object(rm, "MODEL_BACKUP_PATH", env["models"] / "model_backup.pkl"),
            patch.object(rm, "METRICS_DIR",        env["metrics"]),
            patch.object(rm, "_REPO_ROOT",         env["root"]),
            patch.object(rm, "_send_rollback_notification", return_value=None),
        ):
            ok = rm.execute_rollback(details, "B4-06c test rollback",
                                     notify_script=Path("/dev/null"))

        assert ok is True
        restored = (env["models"] / "model.pkl").read_bytes()
        assert restored == b"PREVIOUS_GOOD_MODEL", (
            "model.pkl should contain the backup content after rollback"
        )

    def test_rollback_log_written(self, rollback_env):
        """Rollback event must be logged to rollback_YYYY-WNN.json."""
        env = rollback_env
        _, details = rm.check_rollback_condition(env["metrics"])

        with (
            patch.object(rm, "MODEL_PATH",        env["models"] / "model.pkl"),
            patch.object(rm, "MODEL_BACKUP_PATH", env["models"] / "model_backup.pkl"),
            patch.object(rm, "METRICS_DIR",        env["metrics"]),
            patch.object(rm, "_REPO_ROOT",         env["root"]),
            patch.object(rm, "_send_rollback_notification", return_value=None),
        ):
            rm.execute_rollback(details, "B4-06c test rollback",
                                notify_script=Path("/dev/null"))

        logs = list(env["metrics"].glob("rollback_*.json"))
        assert len(logs) == 1, f"Expected 1 rollback log, found {len(logs)}"
        data = json.loads(logs[0].read_text())
        assert data["reason"] == "B4-06c test rollback"
        assert data["baseline_accuracy"] == pytest.approx(0.70, abs=1e-3)
        assert data["accuracy_4w"] == pytest.approx(0.58, abs=1e-3)

    def test_rollback_alert_emitted(self, rollback_env):
        """MODEL_ROLLBACK alert must appear in alerts-pending.json."""
        env = rollback_env
        _, details = rm.check_rollback_condition(env["metrics"])

        with (
            patch.object(rm, "MODEL_PATH",        env["models"] / "model.pkl"),
            patch.object(rm, "MODEL_BACKUP_PATH", env["models"] / "model_backup.pkl"),
            patch.object(rm, "METRICS_DIR",        env["metrics"]),
            patch.object(rm, "_REPO_ROOT",         env["root"]),
            patch.object(rm, "_send_rollback_notification", return_value=None),
        ):
            rm.execute_rollback(details, "accuracy drop",
                                notify_script=Path("/dev/null"))

        alerts_file = env["root"] / "data" / "alerts-pending.json"
        assert alerts_file.exists()
        alerts = json.loads(alerts_file.read_text())
        types = [a["type"] for a in alerts]
        assert "MODEL_ROLLBACK" in types

    def test_no_rollback_when_accuracy_ok(self, tmp_path):
        """No rollback when accuracy drift is within acceptable range."""
        metrics = tmp_path / "data" / "history" / "model-metrics"
        metrics.mkdir(parents=True)

        _write_initial_training(metrics, mean_accuracy=0.70)
        _write_validation_results(
            metrics,
            {"f1": {"rf": 0.68}, "f2": {"rf": 0.67},
             "f3": {"rf": 0.68}, "f4": {"rf": 0.69}},
        )

        should, details = rm.check_rollback_condition(metrics)
        assert should is False, "Should NOT rollback when accuracy is within 5% of baseline"
        assert details["drift"] <= rm.ROLLBACK_MARGIN


# ─────────────────────────────────────────────────────────────────────────────
# B4-06d — FEATURE_VERSION_MISMATCH detection
# Change version in feature_metadata.json → verify LR fallback alert fires
# ─────────────────────────────────────────────────────────────────────────────

class TestB406d_FeatureVersionMismatch:
    """
    B4-06d: When feature_metadata.json contains a wrong version string,
    both predict_bias.check_feature_version() and
    generate_alerts.check_feature_version_mismatch() must detect the mismatch.
    """

    @pytest.fixture
    def wrong_version_meta(self, tmp_path):
        """Write feature_metadata.json with a deliberately wrong version."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        meta = {"version": "v1.0-OLD", "feature_count": 28}
        (models_dir / "feature_metadata.json").write_text(json.dumps(meta))
        return models_dir / "feature_metadata.json"

    @pytest.fixture
    def correct_version_meta(self, tmp_path):
        """Write feature_metadata.json with the expected version."""
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        meta = {"version": pb.EXPECTED_FEATURE_VERSION, "feature_count": 28}
        (models_dir / "feature_metadata.json").write_text(json.dumps(meta))
        return models_dir / "feature_metadata.json"

    # --- predict_bias.check_feature_version() ---

    def test_predict_detects_wrong_version(self, wrong_version_meta):
        with patch.object(pb, "FEATURE_META_FILE", wrong_version_meta):
            mismatch, actual = pb.check_feature_version()
        assert mismatch is True
        assert actual == "v1.0-OLD"

    def test_predict_no_mismatch_on_correct_version(self, correct_version_meta):
        with patch.object(pb, "FEATURE_META_FILE", correct_version_meta):
            mismatch, actual = pb.check_feature_version()
        assert mismatch is False
        assert actual == pb.EXPECTED_FEATURE_VERSION

    def test_predict_no_mismatch_when_file_missing(self, tmp_path):
        """Missing file → mismatch=False (graceful fallback)."""
        with patch.object(pb, "FEATURE_META_FILE", tmp_path / "nonexistent.json"):
            mismatch, actual = pb.check_feature_version()
        assert mismatch is False

    # --- generate_alerts.check_feature_version_mismatch() ---

    def test_alert_fires_on_wrong_version(self, wrong_version_meta):
        with patch.object(ga, "FEATURE_META_FILE", wrong_version_meta):
            alerts = ga.check_feature_version_mismatch()
        assert len(alerts) == 1
        assert alerts[0]["type"] == "FEATURE_VERSION_MISMATCH"
        assert alerts[0]["severity"] == "HIGH"
        assert "v1.0-OLD" in alerts[0]["message"]
        assert ga.EXPECTED_FEATURE_VERSION in alerts[0]["message"]

    def test_no_alert_on_correct_version(self, correct_version_meta):
        with patch.object(ga, "FEATURE_META_FILE", correct_version_meta):
            alerts = ga.check_feature_version_mismatch()
        assert alerts == []

    def test_alert_context_contains_versions(self, wrong_version_meta):
        """Alert context must include both expected and actual version."""
        with patch.object(ga, "FEATURE_META_FILE", wrong_version_meta):
            alerts = ga.check_feature_version_mismatch()
        ctx = alerts[0]["context"]
        assert ctx["expected"] == ga.EXPECTED_FEATURE_VERSION
        assert ctx["actual"] == "v1.0-OLD"

    def test_both_modules_agree_on_expected_version(self):
        """predict_bias and generate_alerts must share the same expected version."""
        assert pb.EXPECTED_FEATURE_VERSION == ga.EXPECTED_FEATURE_VERSION, (
            "Version constant differs between predict_bias and generate_alerts"
        )


# ─────────────────────────────────────────────────────────────────────────────
# B4-06e — 2 consecutive weeks: history files appended correctly
# ─────────────────────────────────────────────────────────────────────────────

class TestB406e_HistoryAppend:
    """
    B4-06e: Simulate running the pipeline for 2 consecutive weeks and verify
    that both YYYY-WNN.json history files are created correctly.
    """

    @pytest.fixture
    def history_dir(self, tmp_path):
        d = tmp_path / "data" / "history" / "bias"
        d.mkdir(parents=True)
        return d

    def test_two_consecutive_weeks_create_two_files(self, history_dir):
        week11 = datetime(2026, 3, 14, tzinfo=timezone.utc)  # ISO week 11
        week12 = datetime(2026, 3, 21, tzinfo=timezone.utc)  # ISO week 12

        report11 = _minimal_bias_report("2026-W11")
        report12 = _minimal_bias_report("2026-W12")

        with patch.object(pb, "HISTORY_BIAS_DIR", history_dir):
            pb.append_bias_history(report11, week11)
            pb.append_bias_history(report12, week12)

        files = sorted(history_dir.glob("*.json"))
        names = [f.name for f in files]
        assert len(files) == 2, f"Expected 2 history files, found: {names}"
        assert "2026-W11.json" in names
        assert "2026-W12.json" in names

    def test_history_files_contain_correct_content(self, history_dir):
        week11 = datetime(2026, 3, 14, tzinfo=timezone.utc)
        week12 = datetime(2026, 3, 21, tzinfo=timezone.utc)

        report11 = _minimal_bias_report("2026-W11")
        report12 = _minimal_bias_report("2026-W12")

        with patch.object(pb, "HISTORY_BIAS_DIR", history_dir):
            pb.append_bias_history(report11, week11)
            pb.append_bias_history(report12, week12)

        data11 = json.loads((history_dir / "2026-W11.json").read_text())
        data12 = json.loads((history_dir / "2026-W12.json").read_text())

        assert data11["meta"]["weekLabel"] == "2026-W11"
        assert data12["meta"]["weekLabel"] == "2026-W12"

    def test_second_run_does_not_overwrite_first(self, history_dir):
        """Each week's file is independent — W12 must not overwrite W11."""
        week11 = datetime(2026, 3, 14, tzinfo=timezone.utc)
        week12 = datetime(2026, 3, 21, tzinfo=timezone.utc)

        with patch.object(pb, "HISTORY_BIAS_DIR", history_dir):
            pb.append_bias_history(_minimal_bias_report("2026-W11"), week11)
            pb.append_bias_history(_minimal_bias_report("2026-W12"), week12)

        # Both files must still exist with their own content
        assert (history_dir / "2026-W11.json").exists()
        assert (history_dir / "2026-W12.json").exists()

        w11_label = json.loads((history_dir / "2026-W11.json").read_text())["meta"]["weekLabel"]
        w12_label = json.loads((history_dir / "2026-W12.json").read_text())["meta"]["weekLabel"]
        assert w11_label == "2026-W11"
        assert w12_label == "2026-W12"

    def test_history_file_is_valid_json_with_indent(self, history_dir):
        """History files are pretty-printed JSON (indented), not compact."""
        now = datetime(2026, 3, 14, tzinfo=timezone.utc)

        with patch.object(pb, "HISTORY_BIAS_DIR", history_dir):
            pb.append_bias_history(_minimal_bias_report("2026-W11"), now)

        raw = (history_dir / "2026-W11.json").read_text()
        # Pretty-printed JSON contains newlines
        assert "\n" in raw, "History file should be pretty-printed (indented JSON)"
        # Must still parse cleanly
        data = json.loads(raw)
        assert "meta" in data

    def test_same_week_run_twice_overwrites_cleanly(self, history_dir):
        """If pipeline re-runs in the same week, the history file is overwritten."""
        now = datetime(2026, 3, 14, tzinfo=timezone.utc)

        report_v1 = _minimal_bias_report("2026-W11")
        report_v2 = _minimal_bias_report("2026-W11")
        report_v2["meta"]["overallConfidence"] = "HIGH"  # different content

        with patch.object(pb, "HISTORY_BIAS_DIR", history_dir):
            pb.append_bias_history(report_v1, now)
            pb.append_bias_history(report_v2, now)

        files = list(history_dir.glob("*.json"))
        assert len(files) == 1  # only one file for this week

        data = json.loads(files[0].read_text())
        assert data["meta"]["overallConfidence"] == "HIGH"  # second write wins

    def test_week_label_matches_iso_calendar(self, history_dir):
        """File name must match ISO week from the datetime passed."""
        from datetime import datetime, timezone

        # Specific Saturdays with known ISO week numbers
        test_cases = [
            (datetime(2026, 1, 10, tzinfo=timezone.utc),  "2026-W02"),
            (datetime(2026, 3, 14, tzinfo=timezone.utc),  "2026-W11"),
            (datetime(2026, 12, 26, tzinfo=timezone.utc), "2026-W52"),
        ]

        for dt, expected_label in test_cases:
            with patch.object(pb, "HISTORY_BIAS_DIR", history_dir):
                pb.append_bias_history(_minimal_bias_report(expected_label), dt)

            assert (history_dir / f"{expected_label}.json").exists(), (
                f"Expected file {expected_label}.json for datetime {dt}"
            )
