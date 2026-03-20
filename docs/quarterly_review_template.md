# Quarterly Model Review — Checklist

**Quarter:** <!-- e.g. 2026-Q1 -->
**Reviewer:** <!-- name -->
**Date:** <!-- YYYY-MM-DD -->

---

## 1. Accuracy Review

- [ ] Open `data/history/model-metrics/weekly_accuracy.json`
- [ ] Review `rolling_4w_accuracy` vs `baseline_accuracy`
- [ ] Check each monthly report (`monthly_YYYY-MM.json`) for the quarter
- [ ] Flag any month where `monthly_accuracy < baseline_accuracy - 0.05`
- [ ] Note currencies with consistently low per-currency accuracy

**Summary:**

| Month | Accuracy | Baseline | Delta | Notes |
|-------|----------|----------|-------|-------|
|       |          |          |       |       |

---

## 2. Drift & Rollback Events

- [ ] Search `data/history/model-metrics/` for `rollback_*.json` files this quarter
- [ ] Review each rollback: reason, drift magnitude, recovery
- [ ] Confirm `check_model_drift` / `check_rollback_condition` fired correctly

**Rollback events this quarter:** <!-- count or "none" -->

---

## 3. Data Quality

- [ ] Run `test_fred_series.py` (via `workflow_dispatch` on GitHub Actions)
  - All POLICY_RATE_SERIES pass ✅
  - All CPI_SERIES pass ✅
  - YIELD_10Y_SERIES pass ✅
- [ ] Verify `data/cot-latest.json` freshness (≤ 7 days old)
- [ ] Verify `data/macro-latest.json` freshness (≤ 14 days old)
- [ ] Check `DATA_SOURCE_STALE` alerts frequency in past 13 weeks

**Issues found:**

---

## 4. Model Retrain

- [ ] Confirm retrain ran every 4 weeks (weeks divisible by 4)
- [ ] Review `data/history/model-metrics/validation_results.json` for latest folds
- [ ] Compare `initial_training.json` walk-forward mean vs current validation folds
- [ ] Consider forced retrain if accuracy trend is declining

**Last retrain date / week:**

---

## 5. Calendar & Feature Maintenance

- [ ] Review `backend/static/calendar_YYYY.json` — does the year need updating?
- [ ] Check `AVAILABLE_WEEKS` in `predict_bias.py` includes all completed weeks
- [ ] Verify feature version in `models/feature_metadata.json` matches `EXPECTED_FEATURE_VERSION`
- [ ] Check for any new COT report format changes (CFTC releases)

---

## 6. Alert Review

- [ ] Count `EXTREME_POSITIONING` alerts this quarter — any persistent extremes?
- [ ] Count `FLIP_DETECTED` alerts — consistent with price action?
- [ ] Count `MACRO_COT_CONFLICT` alerts — model struggling with certain currencies?
- [ ] Review `LOW_CONFIDENCE` frequency — model uncertain too often?

---

## 7. Action Items

| Priority | Action | Owner | Deadline |
|----------|--------|-------|----------|
|          |        |       |          |

---

## 8. Sign-off

- [ ] All checks above reviewed
- [ ] Action items assigned
- [ ] Next quarterly review scheduled for: <!-- YYYY-MM-DD -->
