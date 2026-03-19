# Task List — FX Bias AI Prediction System

**Version:** 1.0
**Ngày:** 2026-03-19
**Dựa trên:** System Design v1.0 · RPD v2.1 · UI/UX v1.0
**Trạng thái:** Active

---

## Hướng Dẫn Đọc

| Ký hiệu | Ý nghĩa |
|---|---|
| `[ ]` | Chưa làm |
| `[x]` | Hoàn thành |
| `[~]` | Đang làm |
| `[!]` | Bị block bởi task khác |
| 🔴 | Critical — block toàn bộ phase nếu thiếu |
| 🟡 | High — quan trọng nhưng có workaround tạm |
| 🟢 | Medium / Low — nice to have hoặc polish |
| `→ [ID]` | Blocked by task ID này |

---

## SETUP — Quyết Định & Khởi Tạo Repo

> Hoàn thành toàn bộ SETUP trước khi bắt đầu bất kỳ phase nào.

### S-01 — Quyết Định Kỹ Thuật (Open Questions)

- [ ] 🔴 **S-01a** — Chọn hosting: GitHub Pages hay Vercel → ghi vào `DECISIONS.md`
- [ ] 🔴 **S-01b** — Chọn chart library: `recharts` hay `lightweight-charts` → ghi vào `DECISIONS.md`
- [ ] 🟡 **S-01c** — Chọn model storage: direct commit hay Git LFS → kiểm tra kích thước model sau Phase B3
- [ ] 🟡 **S-01d** — Xác nhận historical retention: 2 năm bias history, 12 entries model-metrics
- [ ] 🟡 **S-01e** — Confirm notification channel: Telegram (recommended)
- [ ] 🟢 **S-01f** — Confirm frontend render mode: Static export (`next export`)

### S-02 — Repository Setup

- [ ] 🔴 **S-02a** — Tạo GitHub repository với cấu trúc thư mục theo System Design Section 9.3
- [ ] 🔴 **S-02b** — Tạo `backend/`, `frontend/`, `models/`, `data/`, `data/history/bias/`, `data/history/model-metrics/`, `static/` folders
- [ ] 🔴 **S-02c** — Tạo `.gitignore`: exclude `*.pyc`, `__pycache__`, `node_modules`, `*.tmp`, `.env`
- [ ] 🔴 **S-02d** — Tạo `requirements.txt`: `requests>=2.31`, `pandas>=2.1`, `numpy>=1.26`, `scikit-learn>=1.4`, `joblib>=1.3`, `jsonschema>=4.21`, `python-dateutil>=2.8`
- [ ] 🟡 **S-02e** — Tạo `DECISIONS.md` để log architectural decisions
- [ ] 🟢 **S-02f** — Setup branch protection: `main` yêu cầu pipeline pass trước khi merge

### S-03 — GitHub Secrets & External Accounts

- [ ] 🔴 **S-03a** — Đăng ký FRED API key tại `fred.stlouisfed.org` (free)
- [ ] 🔴 **S-03b** — Thêm `FRED_API_KEY` vào GitHub Secrets
- [ ] 🔴 **S-03c** — Tạo Telegram Bot qua `@BotFather`, lấy `BOT_TOKEN` và `CHAT_ID`
- [ ] 🔴 **S-03d** — Thêm `TELEGRAM_BOT_TOKEN` và `TELEGRAM_CHAT_ID` vào GitHub Secrets
- [ ] 🟡 **S-03e** — Verify FRED API key hoạt động: test fetch 1 series (`FEDFUNDS`)

### S-04 — Tạo JSON Schema Files

- [ ] 🔴 **S-04a** — Tạo `schemas/bias-report.schema.json` từ Section 4.1 System Design
- [ ] 🔴 **S-04b** — Tạo `schemas/cot-report.schema.json` từ Section 4.2
- [ ] 🔴 **S-04c** — Tạo `schemas/macro-report.schema.json` từ Section 4.3
- [ ] 🔴 **S-04d** — Tạo `schemas/cross-asset-report.schema.json` từ Section 4.4
- [ ] 🔴 **S-04e** — Tạo `schemas/model-metrics.schema.json` từ Section 4.5
- [ ] 🔴 **S-04f** — Tạo `models/feature_metadata.json` đầy đủ 28 features từ Section 4.6 RPD v2.1

### S-05 — Shared Utilities (viết trước tất cả scripts)

- [ ] 🔴 **S-05a** — Viết `backend/utils/lag_rules.py` với `PUBLICATION_LAG` dict + `get_valid_date_for()` từ System Design Section 5.2
- [ ] 🔴 **S-05b** — Viết unit test cho `lag_rules.py`: assert CPI lag = T-2, policy_rate lag = 0
- [ ] 🔴 **S-05c** — Viết `backend/utils/data_validator.py`: freshness check (>14 ngày = STALE), format validation, emit_alert()
- [ ] 🔴 **S-05d** — Viết `backend/utils/feature_schema.py`: load/validate `feature_metadata.json`, version check
- [ ] 🔴 **S-05e** — Implement `write_output()` atomic write utility (write temp → rename) từ System Design Section 5.1

---

## Phase B1 — Data Foundation (Tuần 1–3)

> **Gate:** Pipeline chạy 3 tuần liên tiếp không lỗi trước khi vào B2.

### B1-01 — fetch_cot.py

- [ ] 🔴 **B1-01a** — Implement CFTC Socrata API client: build query URL, handle pagination, retry on 429/500
- [ ] 🔴 **B1-01b** — Fetch **Legacy COT** fields: `noncomm_long`, `noncomm_short`, `open_interest_all`, `report_date` cho 8 currencies
- [ ] 🔴 **B1-01c** — Fetch **TFF Report** fields: `lev_money_long/short`, `asset_mgr_long/short`, `dealer_long/short` cho 8 currencies
- [ ] 🔴 **B1-01d** — Validate: date = last Friday, tất cả 8 currencies present, không có null trong required fields
- [ ] 🔴 **B1-01e** — Tính pre-computed values: `net`, `net_delta_1w`, `cot_index_52w`, `extreme_flag`, `flip_flag` cho Legacy; `lev_funds_net`, `asset_mgr_net`, `dealer_net`, `lev_vs_assetmgr_divergence` cho TFF
- [ ] 🔴 **B1-01f** — Tính `cot_indices`: 52w index + `trend_12w[]` array cho mỗi currency (dùng cho sparkline)
- [ ] 🔴 **B1-01g** — Validate output với `schemas/cot-report.schema.json` trước khi write
- [ ] 🔴 **B1-01h** — Write `data/cot-latest.json` dùng atomic write
- [ ] 🟡 **B1-01i** — Emit `MISSING_DATA` alert nếu Tầng 1 fail; emit `DATA_SOURCE_STALE` nếu date cũ > 14 ngày

### B1-02 — fetch_macro.py

- [ ] 🔴 **B1-02a** — Implement FRED API client: base URL + API key từ env, retry logic, rate limit handling
- [ ] 🔴 **B1-02b** — Fetch **policy rates** từ FRED: `FEDFUNDS`, `BOEBR`, `IRSTCB01JPM156N`, `RBAArate`, `BOCRATE`, `IRSTCB01CHM156N`, `RBNZOCR`
- [ ] 🔴 **B1-02c** — Fetch **CPI YoY** từ FRED: `CPIAUCSL`, `JPNCPIALLMINMEI`, `AUSCPIALLMINMEI`, `CPALCY01CAM661N`, `GBRCPIALLMINMEI`, `CHECPIALLMINMEI`, `NZLCPIALLMINMEI`
- [ ] 🔴 **B1-02d** — Fetch **10Y yields** từ FRED: `DGS10` (US), `IRLTLT01DEM156N` (DE), `IRLTLT01GBM156N` (UK), `IRLTLT01JPM156N` (JP)
- [ ] 🔴 **B1-02e** — Fetch **VIX** từ FRED `VIXCLS`, tính `regime` bucket
- [ ] 🔴 **B1-02f** — Implement ECB Data Portal client (no key): fetch ECB rate + HICP CPI cho EUR
- [ ] 🔴 **B1-02g** — Apply `PUBLICATION_LAG` rules cho mỗi series type khi select record
- [ ] 🔴 **B1-02h** — Tính derived fields: `diff_vs_usd`, `trend_3m`, `freshness_days`, `is_stale`, `spread_vs_us`, yield `direction`
- [ ] 🔴 **B1-02i** — Validate output với `schemas/macro-report.schema.json`
- [ ] 🔴 **B1-02j** — Write `data/macro-latest.json` dùng atomic write
- [ ] 🟡 **B1-02k** — Emit `DATA_SOURCE_STALE` nếu bất kỳ series nào có `freshness_days > 14`
- [ ] 🟢 **B1-02l** — Verify tất cả FRED series IDs còn active (test script riêng, chạy 1 lần khi setup) → `→ [S-03e]`

### B1-03 — fetch_cross_asset.py

- [ ] 🔴 **B1-03a** — Fetch **Gold Futures COT** từ CFTC Socrata (dùng lại client từ B1-01a): `cot_index`, `trend_12w[]`, `trend_direction`
- [ ] 🔴 **B1-03b** — Fetch **Oil Futures COT** từ CFTC Socrata: cùng fields như gold
- [ ] 🔴 **B1-03c** — Fetch **S&P 500 Futures COT** từ CFTC Socrata: cùng fields
- [ ] 🔴 **B1-03d** — Reuse VIX + yields từ `macro-latest.json` (không fetch lại): tính `yield_differentials` (US-DE, US-JP, US-GB)
- [ ] 🔴 **B1-03e** — Validate output với `schemas/cross-asset-report.schema.json`
- [ ] 🔴 **B1-03f** — Write `data/cross-asset-latest.json` dùng atomic write

### B1-04 — fetch_calendar.py

- [ ] 🟡 **B1-04a** — Implement MQL5 Economic Calendar API client: GET request, parse FOMC + NFP events, tính `days_to_next_fomc` và `days_to_next_nfp`
- [ ] 🟡 **B1-04b** — Tạo `static/calendar_2026.json` với FOMC và NFP dates cho năm 2026 (manual, 15 phút)
- [ ] 🟡 **B1-04c** — Implement fallback logic: nếu MQL5 fail → dùng `static/calendar_{YEAR}.json` + emit `CALENDAR_SOURCE_FALLBACK`
- [ ] 🟢 **B1-04d** — Unit test: verify fallback hoạt động khi MQL5 timeout

### B1-05 — notify.py

- [ ] 🔴 **B1-05a** — Implement Telegram Bot API client: `POST /sendMessage` với parse_mode=Markdown
- [ ] 🔴 **B1-05b** — Implement `format_weekly_message()`: Top 3 Long/Short/Avoid + HIGH alerts + dashboard link (format từ System Design Section 7.2)
- [ ] 🔴 **B1-05c** — Implement `format_rollback_alert()`: immediate push khi `MODEL_ROLLBACK` trigger
- [ ] 🟡 **B1-05d** — Xử lý lỗi Telegram gracefully: nếu fail → log lỗi, pipeline tiếp tục (không crash)
- [ ] 🟢 **B1-05e** — Test manual: gửi test message xác nhận format đúng

### B1-06 — GitHub Actions: fetch-data.yml

- [ ] 🔴 **B1-06a** — Tạo `.github/workflows/fetch-data.yml` với matrix strategy: `[fetch_cot, fetch_macro, fetch_cross_asset]`
- [ ] 🔴 **B1-06b** — Cấu hình `fail-fast: false` — Job khác tiếp tục khi 1 job fail
- [ ] 🔴 **B1-06c** — Setup `actions/upload-artifact` để pass JSON files giữa jobs
- [ ] 🔴 **B1-06d** — Cấu hình `FRED_API_KEY` từ GitHub Secrets vào env
- [ ] 🟡 **B1-06e** — Thêm timeout per job: 10 min cho cot, 15 min cho macro, 5 min cho cross_asset

### B1-07 — Stability Gate

- [ ] 🔴 **B1-07a** — Chạy pipeline thủ công lần 1: verify tất cả 4 JSON files được tạo đúng format
- [ ] 🔴 **B1-07b** — Chạy pipeline thủ công lần 2 (tuần sau): verify data update đúng
- [ ] 🔴 **B1-07c** — Chạy pipeline thủ công lần 3 (tuần sau nữa): verify 3 tuần liên tiếp không lỗi
- [ ] 🟡 **B1-07d** — Kiểm tra tất cả FRED series IDs trả về data (không có series bị discontinued)

---

## Phase B2 — Feature Engineering & Training Data (Tuần 4–6)

> **Gate:** `training/data/features_2006_2026.csv` clean, aligned, labeled, pass look-ahead test.

### B2-01 — build_labels.py

- [x] 🔴 **B2-01a** — Download FRED FX price series historical: `DEXUSEU`, `DEXUSUK`, `DEXJPUS`, `DEXUSAL`, `DEXCAUS`, `DEXSZUS`, `DEXUSNZ` (2006–nay)
- [x] 🔴 **B2-01b** — Resample daily → weekly (Friday close): xử lý missing ngày holiday
- [x] 🔴 **B2-01c** — Implement `build_label()`: BULL/BEAR/NEUTRAL logic từ RPD Section 3.3 (AND condition: COT direction AND price direction)
- [x] 🔴 **B2-01d** — Enforce `LABEL_CONFIRMATION_LAG = 1`: chỉ label đến tuần T-1
- [x] 🔴 **B2-01e** — Save `training/data/prices_2006_2026.csv`
- [x] 🟡 **B2-01f** — Kiểm tra class distribution: log % BULL/BEAR/NEUTRAL
- [x] 🟡 **B2-01g** — Nếu NEUTRAL >60%: implement OR condition variant, so sánh accuracy 2 definitions, document lựa chọn trong `DECISIONS.md`

### B2-02 — Download Historical COT Data

- [ ] 🔴 **B2-02a** — Download CFTC Legacy bulk files 2006–nay từ `cftc.gov` (annual zip files)
- [ ] 🔴 **B2-02b** — Download CFTC TFF bulk files 2006–nay (TFF available từ 2006)
- [ ] 🔴 **B2-02c** — Parse và standardize format: align với schema của `cot-latest.json`
- [ ] 🔴 **B2-02d** — Save `training/data/cot_historical_2006_2026.csv`

### B2-03 — feature_engineering.py

- [ ] 🔴 **B2-03a** — Implement Group A features (12): `cot_index`, `cot_index_4w_change`, `net_pct_change_1w`, `momentum_acceleration`, `oi_delta_direction`, `oi_net_confluence`, `flip_flag`, `extreme_flag`, `usd_index_cot`, `rank_in_8`, `spread_vs_usd`, `weeks_since_flip`
- [ ] 🔴 **B2-03b** — Implement Group B features (4): `lev_funds_net_index`, `asset_mgr_net_direction`, `dealer_net_contrarian`, `lev_vs_assetmgr_divergence`
- [ ] 🔴 **B2-03c** — Implement Group C features (8): `rate_diff_vs_usd`, `rate_diff_trend_3m`, `rate_hike_expectation`, `cpi_diff_vs_usd`, `cpi_trend`, `pmi_composite_diff` (optional), `yield_10y_diff`, `vix_regime`
- [ ] 🔴 **B2-03d** — Implement Group D features (4): `gold_cot_index`, `oil_cot_direction`, `month`, `quarter`
- [ ] 🔴 **B2-03e** — Integrate `lag_rules.py` vào tất cả macro feature calculations — không được bypass
- [ ] 🔴 **B2-03f** — Handle `NaN` gracefully cho optional features (`pmi_composite_diff`): không raise exception, fill với 0 hoặc median
- [ ] 🔴 **B2-03g** — Implement `build_current_week()`: build feature matrix (8 currencies × 28 features) từ latest JSON files

### B2-04 — Build Training Dataset

- [ ] 🔴 **B2-04a** — Align tất cả data sources theo weekly frequency (2006-W01 → 2026-W12)
- [ ] 🔴 **B2-04b** — Apply feature engineering cho toàn bộ historical period
- [ ] 🔴 **B2-04c** — Join với labels từ `build_labels.py`
- [ ] 🔴 **B2-04d** — Save `training/data/features_2006_2026.csv`: ~20 năm × 52 tuần × 8 currencies = ~8,320 rows × 29 columns (28 features + label)
- [ ] 🟡 **B2-04e** — Exploratory analysis: feature correlation matrix, class distribution per currency, missing values summary

### B2-05 — Look-Ahead Bias Tests (Critical)

- [ ] 🔴 **B2-05a** — Viết `tests/validation/test_no_lookahead.py` từ System Design Section 12.1
- [ ] 🔴 **B2-05b** — Run test cho reference date = `2020-07-24` (W30 2020): verify mỗi feature không dùng data sau ngày này
- [ ] 🔴 **B2-05c** — Run test cho 3 reference dates khác nhau (2015, 2018, 2022): đảm bảo lag rules nhất quán
- [ ] 🔴 **B2-05d** — **Không được pass B2 nếu bất kỳ test nào fail**

### B2-06 — Unit Tests — Feature Engineering

- [ ] 🟡 **B2-06a** — `tests/unit/test_lag_rules.py`: test assertions từ System Design (CPI lag = T-2, etc.)
- [ ] 🟡 **B2-06b** — `tests/unit/test_feature_engineering.py`: tính COT Index cho sample data, verify kết quả đúng
- [x] 🟡 **B2-06c** — `tests/unit/test_label_builder.py`: test BULL/BEAR/NEUTRAL cho các combinations
- [ ] 🟢 **B2-06d** — `tests/integration/test_full_pipeline.py`: end-to-end với mock data (không gọi real APIs)

---

## Phase B3 — Model Training & Validation (Tuần 7–8)

> **Gate:** `models/model.pkl` đạt accuracy >68% walk-forward, beat COT-only baseline +5%.

### B3-01 — train_model.py

- [ ] 🔴 **B3-01a** — Implement walk-forward validation loop: Fold 1 (train 2006–2020, test 2021-Q1) đến Fold N (train 2006–2023, test 2024)
- [ ] 🔴 **B3-01b** — Khởi tạo `RandomForestClassifier` với hyperparameters baseline từ RPD Section 4.1
- [ ] 🔴 **B3-01c** — Enforce `LABEL_CONFIRMATION_LAG = 1` trong code: `df_train = df[df['week'] <= training_cutoff]`
- [ ] 🔴 **B3-01d** — Train với `class_weight='balanced'` — xử lý imbalanced labels
- [ ] 🔴 **B3-01e** — Apply Platt Scaling calibration: `CalibratedClassifierCV(base_model, method='sigmoid')`
- [ ] 🔴 **B3-01f** — Save `models/model.pkl` và `models/calibrator.pkl` dùng `joblib.dump()`
- [ ] 🔴 **B3-01g** — Ghi accuracy per fold vào `data/history/model-metrics/initial_training.json`

### B3-02 — validate_model.py

- [ ] 🔴 **B3-02a** — Implement 4 baseline models: Random, Always BULL, COT Rule (Index >60=Bull, <40=Bear), Logistic Regression
- [ ] 🔴 **B3-02b** — So sánh Random Forest vs tất cả baselines: phải beat COT-only ≥ +5% để pass
- [ ] 🔴 **B3-02c** — Tính accuracy by currency, by confidence level (HIGH/MEDIUM/LOW)
- [ ] 🔴 **B3-02d** — Log kết quả vào model card: `models/model_card.md`
- [ ] 🟡 **B3-02e** — Tune `min_samples_leaf`: test 10 vs 15, chọn cái cho accuracy cao hơn, document trong `DECISIONS.md`
- [ ] 🟡 **B3-02f** — Feature importance analysis: log top 10 features, confirm Group B TFF features contribute positive
- [ ] 🟢 **B3-02g** — Plot accuracy per fold (lưu vào `models/validation_chart.png` nếu cần)

### B3-03 — Logistic Regression Fallback

- [ ] 🟡 **B3-03a** — Train Logistic Regression trên cùng training set
- [ ] 🟡 **B3-03b** — Save `models/model_lr_fallback.pkl`
- [ ] 🟡 **B3-03c** — Verify Logistic Regression hoạt động khi load trong `predict_bias.py` với flag `use_fallback=True`

---

## Phase B4 — Inference Pipeline (Tuần 9–10)

> **Gate:** `bias-latest.json` được tạo tự động mỗi thứ Bảy đúng format, Telegram nhận được, retrain+rollback hoạt động đúng.

### B4-01 — predict_bias.py

- [ ] 🔴 **B4-01a** — Implement main flow từ System Design Section 5.3: load model → check version → build features → inference → calibrate → classify confidence
- [ ] 🔴 **B4-01b** — Implement `FEATURE_VERSION_MISMATCH` check: so sánh `model.feature_version` với `feature_metadata.json`
- [ ] 🔴 **B4-01c** — Implement pair selection Steps 1–7 từ RPD Section 6.3 (bao gồm correlation filter Step 5)
- [ ] 🔴 **B4-01d** — Implement correlation filter với `CURRENCY_CORRELATION` matrix từ System Design Section 5.4
- [ ] 🔴 **B4-01e** — Assemble final `BiasReport` object: meta + predictions + pair_recommendations
- [ ] 🔴 **B4-01f** — Validate output với `schemas/bias-report.schema.json` trước khi write
- [ ] 🔴 **B4-01g** — Write `data/bias-latest.json` (compact JSON, không indent)
- [ ] 🔴 **B4-01h** — Append `data/history/bias/YYYY-WNN.json`

### B4-02 — generate_alerts.py

- [ ] 🔴 **B4-02a** — Implement `EXTREME_POSITIONING` alert: COT Index < 10 hoặc > 90
- [ ] 🔴 **B4-02b** — Implement `FLIP_DETECTED` alert: `flip_flag == 1`
- [ ] 🔴 **B4-02c** — Implement `MODEL_DRIFT` alert: accuracy 4w < baseline − 5%
- [ ] 🔴 **B4-02d** — Implement `MISSING_DATA` alert: Tầng 1 fail
- [ ] 🔴 **B4-02e** — Implement `RISK_OFF_REGIME` alert: VIX > 25
- [ ] 🔴 **B4-02f** — Implement `DATA_SOURCE_STALE` alert: freshness_days > 14
- [ ] 🔴 **B4-02g** — Implement `FEATURE_VERSION_MISMATCH` alert
- [ ] 🔴 **B4-02h** — Implement `LOW_CONFIDENCE` alert: max_probability < 0.50
- [ ] 🔴 **B4-02i** — Implement `MACRO_COT_CONFLICT` alert: COT bias ngược chiều macro differential
- [ ] 🟡 **B4-02j** — Implement `MOMENTUM_DECEL` alert: `momentum_acceleration` âm 3 tuần liên tiếp
- [ ] 🟡 **B4-02k** — Implement `OI_DIVERGENCE` alert: net tăng nhưng OI giảm (hoặc ngược)
- [ ] 🟡 **B4-02l** — Implement `CALENDAR_SOURCE_FALLBACK` alert
- [ ] 🟡 **B4-02m** — Implement `MODEL_ROLLBACK` alert
- [ ] 🟡 **B4-02n** — Unit test: `tests/unit/test_alert_generation.py` cho tất cả 13 conditions

### B4-03 — rollback_model.py

- [ ] 🟡 **B4-03a** — Implement `backup_current_model()`: copy `model.pkl` → `model_backup.pkl`; `model_backup.pkl` → `model_backup_prev.pkl`; xóa cũ hơn
- [ ] 🟡 **B4-03b** — Implement `deploy_candidate()`: backup → copy `model_candidate.pkl` → `model.pkl`
- [ ] 🟡 **B4-03c** — Implement `check_rollback_condition()`: tính accuracy_4w từ history, so sánh vs baseline − 5%
- [ ] 🟡 **B4-03d** — Implement `execute_rollback()`: restore `model_backup.pkl` → `model.pkl`, emit `MODEL_ROLLBACK` alert, gọi `notify.py` ngay lập tức
- [ ] 🟡 **B4-03e** — Log rollback event vào `data/history/model-metrics/rollback_YYYY-WNN.json`

### B4-04 — GitHub Actions: predict-bias.yml

- [ ] 🔴 **B4-04a** — Tạo `.github/workflows/predict-bias.yml` với cron `0 1 * * 6` (Saturday 01:00 UTC) + `workflow_dispatch`
- [ ] 🔴 **B4-04b** — Cấu hình job dependencies: `predict` needs `fetch-data`; `retrain` needs `predict`; `notify` needs `predict` + `retrain` với `if: always()`
- [ ] 🔴 **B4-04c** — Implement conditional retrain: `IF (current_week % 4 == 0)` → chạy Job 5
- [ ] 🔴 **B4-04d** — Cấu hình git commit + push sau khi generate `bias-latest.json`
- [ ] 🟡 **B4-04e** — Thêm timeout per step: feature_engineering < 5 min, predict < 5 min, train < 30 min
- [ ] 🟢 **B4-04f** — Thêm `fail-fast: false` cho notify job: luôn notify kể cả khi có lỗi

### B4-05 — Integration Tests

- [ ] 🔴 **B4-05a** — `tests/integration/test_cftc_api.py`: live API call + validate response format
- [ ] 🔴 **B4-05b** — `tests/integration/test_fred_api.py`: verify tất cả series IDs active + return data
- [ ] 🔴 **B4-05c** — `tests/integration/test_full_pipeline.py`: end-to-end với mock data → verify `bias-latest.json` output

### B4-06 — Manual Testing Checklist

- [ ] 🔴 **B4-06a** — Trigger pipeline thủ công, verify `bias-latest.json` được commit đúng format
- [ ] 🔴 **B4-06b** — Verify Telegram message nhận được trong 5 phút
- [ ] 🟡 **B4-06c** — Test rollback: tạm thời override accuracy threshold → verify `model_backup.pkl` được restore
- [ ] 🟡 **B4-06d** — Test `FEATURE_VERSION_MISMATCH`: thay đổi version trong `feature_metadata.json` → verify Logistic Regression fallback chạy
- [ ] 🟡 **B4-06e** — Chạy thủ công 2 tuần liên tiếp: verify history files được append đúng

---

## Phase B5 — Monitoring & Iteration (Ongoing)

### B5-01 — Monitoring Logic

- [ ] 🟡 **B5-01a** — Implement weekly accuracy calculation: compare predictions T-4..T-1 vs actual outcomes
- [ ] 🟡 **B5-01b** — Implement `MODEL_DRIFT` detection: accuracy 4w < baseline − 5% → alert
- [ ] 🟡 **B5-01c** — Implement monthly accuracy report: tự động aggregate metrics, commit vào `data/history/model-metrics/monthly_YYYY-MM.json`
- [ ] 🟢 **B5-01d** — Implement quarterly review checklist trong `docs/quarterly_review_template.md`

### B5-02 — Annual Maintenance Tasks (Lên lịch tháng 1 hàng năm)

- [ ] 🟡 **B5-02a** — Cập nhật `static/calendar_{YEAR}.json` với FOMC + NFP dates năm mới
- [ ] 🟡 **B5-02b** — Verify tất cả FRED series IDs còn active (chạy `test_fred_api.py`)
- [ ] 🟢 **B5-02c** — Review Data Source Health SLA: có nguồn nào cần downgrade không?
- [ ] 🟢 **B5-02d** — Quarterly model review: feature importance drift, class distribution drift

---

## Phase F1 — Frontend: App Shell + Mock (Parallel với B1)

> Có thể bắt đầu ngay — không cần backend complete.

### F1-01 — Project Setup

- [ ] 🔴 **F1-01a** — Khởi tạo Next.js 15 project với TypeScript strict trong `frontend/`
- [ ] 🔴 **F1-01b** — Cài dependencies: `tailwindcss@4`, `zustand`, `lucide-react`, `clsx`, `recharts`, `@tanstack/table`
- [ ] 🔴 **F1-01c** — Setup CSS variables từ UI/UX Design Section 5.1: colors, typography, spacing
- [ ] 🔴 **F1-01d** — Tạo `lib/types/index.ts` với tất cả TypeScript interfaces từ System Design Section 4 (mirror JSON schemas)
- [ ] 🟡 **F1-01e** — Setup Jest + `@testing-library/react`
- [ ] 🟢 **F1-01f** — Setup Tailwind CSS custom config với design tokens

### F1-02 — Mock Data

- [ ] 🔴 **F1-02a** — Tạo `frontend/public/data/bias-latest.json` mock từ sample output trong RPD Section 6.1 (8 currencies đầy đủ)
- [ ] 🔴 **F1-02b** — Tạo mock `cot-latest.json`, `macro-latest.json`, `cross-asset-latest.json` với data hợp lý
- [ ] 🔴 **F1-02c** — Tạo mock `model-metrics/2026-W12.json` với accuracy data
- [ ] 🟡 **F1-02d** — Tạo 3 mock historical weeks: `2026-W11.json`, `2026-W10.json`, `2026-W09.json` cho test week navigation

### F1-03 — Zustand Store

- [ ] 🔴 **F1-03a** — Implement `biasStore.ts` với đầy đủ state/actions/derived values từ System Design Section 6.2
- [ ] 🔴 **F1-03b** — Implement `auditStore.ts`: state cho cotData, macroData, crossData, modelMetrics
- [ ] 🔴 **F1-03c** — Implement `uiStore.ts`: selectedWeek, panel open/close states, theme (dark/light)
- [ ] 🟡 **F1-03d** — `tests/stores/biasStore.test.ts`: test load, cache, week navigation, highAlerts()

### F1-04 — Data Fetching

- [ ] 🔴 **F1-04a** — Implement `lib/fetchers/fetchBiasData.ts` với in-memory cache (TTL 1h) từ System Design Section 6.3
- [ ] 🔴 **F1-04b** — Implement `lib/fetchers/fetchCotData.ts`, `fetchMacroData.ts`, `fetchHistorical.ts`
- [ ] 🟡 **F1-04c** — Implement runtime type guard `isBiasReport()` + schema version check
- [ ] 🟡 **F1-04d** — Implement error states: loading / empty / error / stale (Section 8.2 System Design)

### F1-05 — App Shell

- [ ] 🔴 **F1-05a** — Implement `Sidebar.tsx`: navigation links (Dashboard, Data Audit, Performance, Settings) + version info footer + active state indicator
- [ ] 🔴 **F1-05b** — Implement `Header.tsx`: week label + pipeline status dots (COT/Macro/Cross/Calendar) + data freshness text + theme toggle
- [ ] 🔴 **F1-05c** — Implement `WeekPicker.tsx`: dropdown 8 tuần gần nhất + "LATEST" / "HISTORICAL" badges
- [ ] 🔴 **F1-05d** — Implement root `layout.tsx` với Sidebar + Header + page content area
- [ ] 🟡 **F1-05e** — Sidebar collapsible: icon-only mode khi collapsed (64px width)
- [ ] 🟢 **F1-05f** — Keyboard shortcut `1` → Dashboard, `2` → Data Audit

### F1-06 — Shared Components (Critical)

- [ ] 🔴 **F1-06a** — `Badge.tsx`: variants `high|medium|low|bull|bear|neutral` từ design system Section 5.4
- [ ] 🔴 **F1-06b** — `StatusDot.tsx`: `ok|warn|error` với màu tương ứng
- [ ] 🔴 **F1-06c** — `Sparkline.tsx`: inline 12-week trend với color gradient bull/neutral/bear
- [ ] 🔴 **F1-06d** — `DataTable.tsx` (TanStack Table): sortable columns, conditional formatting (green/red text, yellow background rows), tabular-nums font
- [ ] 🔴 **F1-06e** — `TabBar.tsx`: horizontal tabs với active indicator
- [ ] 🔴 **F1-06f** — `SlidePanel.tsx`: slide-over từ bên phải, width 480px, Esc để close
- [ ] 🟡 **F1-06g** — `VixGauge.tsx`: horizontal gauge với 4 zones + current value marker
- [ ] 🟡 **F1-06h** — `AccuracyLineChart.tsx`: line chart với target line + minimum line (Recharts)
- [ ] 🟡 **F1-06i** — `FeatureImportanceChart.tsx`: horizontal bar chart sorted descending

---

## Phase F2 — Frontend: Dashboard Page

> Dependencies: F1 complete + `bias-latest.json` schema finalized (S-04a).

### F2-01 — Alert Banner

- [ ] 🔴 **F2-01a** — Implement `AlertBanner.tsx`: chỉ render khi có HIGH alerts, dismiss button (collapse không xóa), subtle red tint background + left border
- [ ] 🔴 **F2-01b** — Render mỗi alert: type badge chip + currency + message
- [ ] 🟡 **F2-01c** — Animation: subtle pulse trên alert icon, 1 lần khi load
- [ ] 🟢 **F2-01d** — `tests/components/AlertBanner.test.tsx`: render với/không có HIGH alerts

### F2-02 — Pair Recommendation Grid

- [ ] 🔴 **F2-02a** — Implement `PairRecommendationGrid.tsx`: 3-column layout (Strong Long / Strong Short / Avoid) với responsive collapse
- [ ] 🔴 **F2-02b** — Implement `PairCard.tsx`: pair name + confidence badge + spread score + base/quote bias summary + alert chip nếu có
- [ ] 🔴 **F2-02c** — Visual encoding: left border color (emerald/red/gray) + background tint per column type
- [ ] 🟡 **F2-02d** — Hover state: card elevation + expand key drivers
- [ ] 🟡 **F2-02e** — Click → mở `SlidePanel` với full prediction detail (probability bars + all drivers + active alerts + 12w accuracy)
- [ ] 🟢 **F2-02f** — `tests/components/PairCard.test.tsx`

### F2-03 — Currency Strength Chart

- [ ] 🔴 **F2-03a** — Implement `CurrencyStrengthChart.tsx`: horizontal bar per currency, sorted by rank (1 = top)
- [ ] 🔴 **F2-03b** — Bar direction: BULL fill left→right (emerald), BEAR fill right→left (red), NEUTRAL center-out (gray)
- [ ] 🔴 **F2-03c** — Inline: rank number + currency label + bias label + probability % + alert icons
- [ ] 🔴 **F2-03d** — Alternate row background: `#0f1117` vs `#141520`
- [ ] 🟡 **F2-03e** — Hover tooltip: mini probability distribution pie (BULL/NEUTRAL/BEAR)
- [ ] 🟡 **F2-03f** — Click row → mở currency detail `SlidePanel`
- [ ] 🟢 **F2-03g** — `tests/components/CurrencyStrengthChart.test.tsx`

### F2-04 — Alert Detail Section

- [ ] 🟡 **F2-04a** — Implement `AlertDetailSection.tsx`: collapsed by default, show count badge "N Alerts"
- [ ] 🟡 **F2-04b** — Expanded: alert detail cards sorted HIGH → MEDIUM → LOW
- [ ] 🟡 **F2-04c** — Alert card: severity badge + type + currency + message + context data (Lev Funds net, Dealer net, VIX)
- [ ] 🟡 **F2-04d** — Filter chips: toggle visibility theo severity

### F2-05 — Currency Detail Slide Panel

- [ ] 🟡 **F2-05a** — Implement `CurrencyDetailPanel.tsx`: probability distribution bars, key drivers list, active alerts, 12w accuracy history, "View in Data Audit" link
- [ ] 🟡 **F2-05b** — Probability bars: BULL/NEUTRAL/BEAR với label + percentage
- [ ] 🟢 **F2-05c** — Prediction history: `[✅✅❌✅]` format cho last 4 weeks

---

## Phase F3 — Frontend: Data Audit Page

> Dependencies: F1 complete + all JSON schemas finalized (S-04).

### F3-01 — COT Data Tab

- [ ] 🟡 **F3-01a** — Implement `CotDataPanel.tsx` với report date + source attribution header
- [ ] 🟡 **F3-01b** — Currency selector: `[ALL ▾]` dropdown
- [ ] 🟡 **F3-01c** — Legacy Report table: `DataTable` với columns Currency/Net Long/Net Short/OI/Net/Δ1w + conditional format (green/red net, yellow extreme row, alert row annotation)
- [ ] 🟡 **F3-01d** — TFF Report table: columns Currency/Lev Funds/Asset Mgr/Dealer/Divergence
- [ ] 🟡 **F3-01e** — COT Index Sparkline section: `Sparkline` per currency với value + alert badge
- [ ] 🟢 **F3-01f** — `tests/components/DataTable.test.tsx`: sort, filter, conditional format

### F3-02 — Macro Data Tab

- [ ] 🟡 **F3-02a** — Implement `MacroDataPanel.tsx`
- [ ] 🟡 **F3-02b** — Policy Rates table: Currency/Rate/Δ vs USD/Trend 3M/Last Update + publication lag note
- [ ] 🟡 **F3-02c** — CPI YoY table: Currency/CPI/Δ vs US/Trend/Last Update + "⚠️ Lag: T-2 months" badge
- [ ] 🟡 **F3-02d** — Yields & Market table: Indicator/Value/Δ1w/Regime (VIX regime badge)
- [ ] 🟡 **F3-02e** — Data Freshness Monitor: Source/Last Record/Age/Status với color coding (green <7d, amber 7-14d, red >14d)

### F3-03 — Cross-Asset Tab

- [ ] 🟡 **F3-03a** — Implement `CrossAssetPanel.tsx`
- [ ] 🟡 **F3-03b** — Commodities COT table: Asset/COT Index/Trend 12w (sparkline)/FX Impact label
- [ ] 🟡 **F3-03c** — Yield Differentials table: Pair/Spread/Δ4w/Direction badge
- [ ] 🟡 **F3-03d** — VIX Regime Gauge: `VixGauge` component với current value marker + zone labels

### F3-04 — Feature Inspector Tab

- [ ] 🟡 **F3-04a** — Implement `FeatureInspector.tsx` với currency selector
- [ ] 🟡 **F3-04b** — Feature table: # / Feature name / Value / Z-Score / Flag — grouped by Group A/B/C/D headers
- [ ] 🟡 **F3-04c** — Z-Score highlight: `|Z| > 2` → yellow background
- [ ] 🟡 **F3-04d** — NaN handling: hiện badge "MISSING" màu amber, không ẩn
- [ ] 🟡 **F3-04e** — Feature Importance chart: `FeatureImportanceChart` horizontal bars sorted descending

### F3-05 — Model Diagnostics Tab

- [ ] 🟡 **F3-05a** — Implement `ModelDiagnostics.tsx`
- [ ] 🟡 **F3-05b** — Model Summary card: version, features, last retrain date, next retrain, backup version, status badge
- [ ] 🟡 **F3-05c** — Accuracy Trend chart: `AccuracyLineChart` 12 tuần với target line (72%) + minimum line (65%)
- [ ] 🟡 **F3-05d** — Accuracy by Currency: horizontal bars per currency với ✅/⚠️ vs target
- [ ] 🟡 **F3-05e** — Baseline Comparison table: 4 baselines vs current model
- [ ] 🟡 **F3-05f** — Retrain History table: Week/Action/Pre/Post accuracy/Status

---

## Phase F4 — Frontend: Integration với Real Data

> Dependencies: Backend Phase B4 complete (real `bias-latest.json` available).

### F4-01 — Connect Real JSON

- [ ] 🔴 **F4-01a** — Swap mock JSON → real JSON từ repo (update fetch URLs)
- [ ] 🔴 **F4-01b** — Test toàn bộ Dashboard với real data từ backend
- [ ] 🔴 **F4-01c** — Test Data Audit với real `cot-latest.json`, `macro-latest.json`
- [ ] 🔴 **F4-01d** — Verify week navigation: fetch `data/history/bias/YYYY-WNN.json` đúng

### F4-02 — Schema Version Compatibility

- [ ] 🟡 **F4-02a** — Implement `featureVersion` check: nếu schema mismatch → render amber banner "Dashboard may show stale data"
- [ ] 🟡 **F4-02b** — Test với intentionally mismatched version → verify banner hiện đúng

### F4-03 — Manual Integration Test Checklist

- [ ] 🔴 **F4-03a** — Dashboard load và hiển thị đúng bias-latest.json
- [ ] 🔴 **F4-03b** — Week navigation: chọn tuần trước → data + header badge thay đổi
- [ ] 🔴 **F4-03c** — Alert banner hiện/ẩn đúng theo HIGH alerts trong JSON
- [ ] 🔴 **F4-03d** — Slide-over panel mở khi click currency
- [ ] 🔴 **F4-03e** — Data Audit tabs render đúng từ real JSON files
- [ ] 🟡 **F4-03f** — Accuracy chart trong Model Diagnostics render đúng từ model-metrics
- [ ] 🟡 **F4-03g** — Mobile: dashboard glanceable trên 375px screen (pair cards, currency bars)
- [ ] 🟡 **F4-03h** — Keyboard shortcuts hoạt động: `1`, `2`, `←`, `→`, `Esc`

---

## Phase F5 — Frontend: Polish (Phase 5+ / Ongoing)

### F5-01 — Animations & Transitions

- [ ] 🟢 **F5-01a** — Page load staggered animation: sections fade-in với delay
- [ ] 🟢 **F5-01b** — Alert banner pulse animation (1 lần)
- [ ] 🟢 **F5-01c** — Card hover elevation transition (shadow + border)
- [ ] 🟢 **F5-01d** — Respect `prefers-reduced-motion`: tắt tất cả animations

### F5-02 — Responsive Polish

- [ ] 🟢 **F5-02a** — Laptop (1024–1279px): collapsed sidebar, 2-column pair recommendations
- [ ] 🟢 **F5-02b** — Tablet (768–1023px): bottom navigation thay sidebar
- [ ] 🟢 **F5-02c** — Mobile (<768px): horizontal scroll pair cards, simplified currency list (no sparklines), accordion alerts

### F5-03 — Data Export

- [ ] 🟢 **F5-03a** — "Export as PDF" button trên Dashboard → 1-page weekly summary
- [ ] 🟢 **F5-03b** — "Download JSON" button trong Data Audit per section

### F5-04 — Accessibility

- [ ] 🟢 **F5-04a** — Verify WCAG AA contrast ratio cho tất cả text
- [ ] 🟢 **F5-04b** — BULL/BEAR encoding: text label + arrow + color (không chỉ màu)
- [ ] 🟢 **F5-04c** — ARIA labels cho charts + table headers
- [ ] 🟢 **F5-04d** — Focus visible trên tất cả interactive elements

### F5-05 — Performance Audit

- [ ] 🟢 **F5-05a** — Lighthouse: FCP < 1.5s, TTI < 2s
- [ ] 🟢 **F5-05b** — Total JSON payload < 200KB
- [ ] 🟢 **F5-05c** — Lazy load Data Audit page components

---

## Deployment

### D-01 — Frontend Deployment

- [ ] 🔴 **D-01a** — Tạo `.github/workflows/build-frontend.yml`: `npm ci` → `npm run build` → `next export` → deploy `out/` → GitHub Pages
- [ ] 🔴 **D-01b** — Cấu hình `next.config.js`: `output: 'export'`, `basePath` nếu dùng GitHub Pages subdirectory
- [ ] 🔴 **D-01c** — Verify frontend deploy và serve đúng JSON files từ `data/`
- [ ] 🟡 **D-01d** — Cấu hình custom domain nếu cần

### D-02 — End-to-End Production Smoke Test

- [ ] 🔴 **D-02a** — Pipeline thứ Bảy chạy → `bias-latest.json` commit → GitHub Pages serve file mới → Frontend hiển thị data mới
- [ ] 🔴 **D-02b** — Telegram nhận message đúng format sau pipeline
- [ ] 🔴 **D-02c** — Toàn bộ manual testing checklist từ B4-06 pass trên production

---

## Tổng Quan Tiến Độ

| Phase | Số Tasks | Critical | High | Medium/Low | Dependencies |
|---|---|---|---|---|---|
| SETUP | 22 | 16 | 5 | 1 | — |
| B1 — Data Foundation | 31 | 22 | 7 | 2 | SETUP |
| B2 — Feature Engineering | 22 | 16 | 4 | 2 | B1 |
| B3 — Model Training | 12 | 7 | 4 | 1 | B2 |
| B4 — Inference Pipeline | 26 | 14 | 10 | 2 | B3 |
| B5 — Monitoring | 7 | 0 | 4 | 3 | B4 |
| F1 — App Shell + Mock | 29 | 18 | 8 | 3 | SETUP (parallel) |
| F2 — Dashboard | 18 | 9 | 7 | 2 | F1 |
| F3 — Data Audit | 22 | 0 | 22 | 0 | F1 |
| F4 — Integration | 10 | 7 | 3 | 0 | F1 + B4 |
| F5 — Polish | 13 | 0 | 0 | 13 | F4 |
| Deployment | 5 | 4 | 1 | 0 | F1 + B4 |
| **Total** | **217** | **113** | **75** | **29** | |

---

## Thứ Tự Ưu Tiên Khởi Động

Nếu bắt đầu hôm nay, làm theo thứ tự này để unblock nhanh nhất:

1. **SETUP hoàn toàn** — S-01 đến S-05 (quyết định, repo, secrets, schemas, utils)
2. **B1 song song F1** — Backend data foundation đồng thời với Frontend app shell + mock
3. **B2** khi B1 stable gate pass
4. **B3** khi B2 pass look-ahead test
5. **F2 + F3** song song với B3 (frontend không cần real data)
6. **B4 + F4** — Integration: backend inference + connect frontend
7. **Deployment** → Production
8. **B5 + F5** — Monitoring + Polish

---

## Changelog

| Version | Ngày | Thay đổi |
|---|---|---|
| v1.0 | 2026-03-19 | Initial task list từ System Design v1.0 |

---

*Cập nhật status task sau mỗi buổi làm việc. Review toàn bộ list vào cuối mỗi phase.*
