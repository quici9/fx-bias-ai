# RPD — FX Bias AI Prediction System

**Requirements & Product Definition**

| Field | Value |
|---|---|
| Version | 2.1 |
| Ngày | 2026-03-19 |
| Trạng thái | Draft |
| Cập nhật từ | v2.0 — bổ sung price data source, hoàn thiện macro coverage, rollback mechanism, notification, correlation filter |

---

## 1. Tổng Quan Hệ Thống

### 1.1 Mô Tả

Hệ thống tự động thu thập, xử lý và phân tích dữ liệu đa nguồn để dự đoán bias tuần cho 8 đồng tiền chính trong thị trường Forex, đồng thời xếp hạng và chọn lọc các cặp tiền có xác suất bias cao nhất. Toàn bộ pipeline chạy tự động, không cần can thiệp thủ công, và liên tục học từ dữ liệu mới.

### 1.2 Mục Tiêu Cốt Lõi

| Mục tiêu | Mô tả |
|---|---|
| Bias Prediction | Dự đoán Bull / Bear / Neutral cho 8 đồng tiền mỗi tuần với xác suất cụ thể |
| Pair Selection | Xếp hạng các cặp tiền theo xác suất bias cao nhất, nhất quán, và không tương quan cao |
| Alert System | Cảnh báo tự động khi tín hiệu mâu thuẫn, extreme, hoặc có regime change |
| Continuous Learning | Model tự cập nhật định kỳ 4 tuần/lần khi có đủ dữ liệu confirmed |
| Notification | Push summary + HIGH alerts đến trader mỗi thứ Bảy sau khi pipeline hoàn thành |

### 1.3 Nguyên Tắc Thiết Kế

- **Free-only data sources** — không phụ thuộc API trả phí
- **Fully automated** — chạy hoàn toàn tự động qua scheduler
- **Explainable output** — mỗi prediction đi kèm lý do, không phải black box
- **Bias tuần, không phải ngày** — horizon dự đoán 5–7 ngày tới
- **Conservative by default** — khi uncertain, hệ thống cảnh báo thay vì predict sai
- **Minimal maintenance** — ưu tiên nguồn có official API, SLA ổn định, tránh scraping hoàn toàn
- **Resilient by design** — mỗi tầng dữ liệu có fallback; model có rollback; pipeline không crash khi một nguồn fail

---

## 2. Nguồn Dữ Liệu

> **Nguyên tắc phân tầng:** Tầng 1 là cốt lõi, không thể thiếu. Tầng 2, 3, 4 là bổ sung — nếu một nguồn fail, hệ thống vẫn chạy được với độ chính xác giảm nhẹ, không crash toàn bộ.

### 2.1 Tầng 1 — Positioning Data + Price Data (Cốt lõi, bắt buộc)

#### 2.1.1 CFTC COT Data — Nguồn positioning chính

**API:** CFTC Socrata REST API — free, no key, SLA ổn định nhất trong toàn hệ thống.

**Legacy COT Report:**

| Field | Mô tả |
|---|---|
| `noncomm_positions_long_all` | Long contracts của Non-Commercial traders |
| `noncomm_positions_short_all` | Short contracts của Non-Commercial traders |
| `open_interest_all` | Total open interest |
| `report_date_as_yyyy_mm_dd` | Report date |

**TFF Report (Traders in Financial Futures):**

| Field | Mô tả |
|---|---|
| `lev_money_positions_long_all` | Leveraged Funds long (hedge funds, CTAs) |
| `lev_money_positions_short_all` | Leveraged Funds short |
| `asset_mgr_positions_long_all` | Asset Managers long (institutional) |
| `asset_mgr_positions_short_all` | Asset Managers short |
| `dealer_positions_long_all` | Dealer/Intermediary long (market makers) |
| `dealer_positions_short_all` | Dealer/Intermediary short |

> **Lý do thêm TFF:** Phân tách Non-Commercial thành các nhóm có hành vi khác nhau. Leveraged Funds là speculative money thực sự di chuyển thị trường. Asset Managers là institutional long-term flow ít noise hơn. Dealers thường đứng ngược chiều thị trường — vị thế cực đoan của Dealers là contrarian signal quan trọng.

**Pairs:** EUR, GBP, JPY, AUD, CAD, CHF, NZD, USD Index
**Update:** Thứ Sáu 15:30 ET (reflect Tuesday close)
**Lịch sử:** Legacy từ 1986, TFF từ 2006 → training start từ 2006

---

#### 2.1.2 FX Weekly Price Data — Dùng để tạo training labels *(Mới v2.1)*

> **Mục đích:** Price data **CHỈ** dùng để tạo `BULL/BEAR/NEUTRAL` labels cho training và validate accuracy offline. **KHÔNG** dùng trong inference pipeline, không predict giá.

**Nguồn: FRED Exchange Rate Series** — cùng FRED client đã có, không cần thêm dependency.

| Pair | FRED Series | Ghi chú |
|---|---|---|
| EUR/USD | `DEXUSEU` | USD per EUR |
| GBP/USD | `DEXUSUK` | USD per GBP |
| USD/JPY | `DEXJPUS` | JPY per USD |
| AUD/USD | `DEXUSAL` | USD per AUD |
| USD/CAD | `DEXCAUS` | CAD per USD |
| USD/CHF | `DEXSZUS` | CHF per USD |
| NZD/USD | `DEXUSNZ` | USD per NZD |

**Cách dùng:**

```python
# training/build_labels.py
# Lấy Friday close mỗi tuần (resample daily → weekly, last)
# So sánh close[T+1] vs close[T] để xác định direction
# Combine với COT direction → BULL/BEAR/NEUTRAL label

def build_label(cot_direction: int, price_direction: int) -> str:
    if cot_direction > 0 and price_direction > 0:
        return 'BULL'
    elif cot_direction < 0 and price_direction < 0:
        return 'BEAR'
    else:
        return 'NEUTRAL'
```

**Class imbalance contingency:**

```
Sau khi build labels, kiểm tra class distribution:
  - Nếu NEUTRAL > 60% → thử relaxing target sang OR condition (COT OR price)
    và so sánh accuracy giữa AND vs OR definition
  - Dùng định nghĩa cho accuracy cao hơn trong walk-forward validation
  - Document lựa chọn trong model card
```

**Lưu vào:** `training/data/prices_2006_2026.csv` — một lần khi setup, không cần real-time.

---

### 2.2 Tầng 2 — Macro Differential Data (Bổ sung, quan trọng)

> **Nguyên tắc v2.1:** Tất cả macro data đi qua **2 API client duy nhất** — FRED và ECB. Phủ đủ 8 currencies. Không maintain Central Bank scrapers riêng lẻ.

> ⚠️ **Lưu ý trước khi code:** Verify tất cả FRED series IDs tại [fred.stlouisfed.org](https://fred.stlouisfed.org) trong Phase 1 — một số series có thể đã được rename hoặc discontinued.

#### FRED API (free, key miễn phí) — Nguồn chính cho mọi macro data

**Policy Rates:**

| Currency | FRED Series | Update |
|---|---|---|
| USD — Fed Funds Rate | `FEDFUNDS` | Monthly |
| GBP — BOE Bank Rate | `BOEBR` | Monthly |
| JPY — BOJ Policy Rate | `IRSTCB01JPM156N` | Monthly |
| AUD — RBA Cash Rate | `RBAArate` | Monthly |
| CAD — BOC Overnight Rate | `BOCRATE` | Monthly |
| CHF — SNB Policy Rate | `IRSTCB01CHM156N` | Monthly *(mới v2.1)* |
| NZD — RBNZ Cash Rate | `RBNZOCR` | Monthly *(mới v2.1)* |

**CPI YoY — Đủ 8 currencies:** *(mới v2.1: bổ sung AU, CA, UK, CH, NZ)*

| Currency | FRED Series | Update |
|---|---|---|
| USD | `CPIAUCSL` | Monthly |
| JPY | `JPNCPIALLMINMEI` | Monthly |
| AUD | `AUSCPIALLMINMEI` | Monthly |
| CAD | `CPALCY01CAM661N` | Monthly |
| GBP | `GBRCPIALLMINMEI` | Monthly |
| CHF | `CHECPIALLMINMEI` | Monthly |
| NZD | `NZLCPIALLMINMEI` | Monthly |

> EUR CPI (HICP) lấy từ ECB Data Portal — chính xác hơn FRED cho EUR.

**Yields & Market Data:**

| Data | FRED Series | Update |
|---|---|---|
| US GDP Growth | `A191RL1Q225SBEA` | Quarterly |
| US 10Y Yield | `DGS10` | Daily |
| DE 10Y Yield | `IRLTLT01DEM156N` | Monthly |
| UK 10Y Yield | `IRLTLT01GBM156N` | Monthly |
| JP 10Y Yield | `IRLTLT01JPM156N` | Monthly |
| VIX Index | `VIXCLS` | Daily |

#### ECB Data Portal (free, no key) — EUR-specific data

| Data | Mô tả |
|---|---|
| ECB Main Refinancing Rate | Policy rate chính xác nhất cho EUR |
| EU HICP CPI | Inflation measure ECB sử dụng |
| EU GDP Growth | Quarterly |

#### Publication Lag Rules — Bắt buộc enforce trong `feature_engineering.py`

```python
# CRITICAL: Không được dùng data chưa published tại thời điểm tuần T
# Vi phạm = look-ahead bias. Model train tốt nhưng live performance tệ.

PUBLICATION_LAG = {
    'cpi':          -2,   # Dùng CPI tháng T-2 (tháng T-1 chưa publish)
    'gdp':          -1,   # Dùng GDP quý trước (delay 4-6 tuần)
    'pmi':          -1,   # Dùng PMI tháng trước (publish đầu tháng hiện tại)
    'policy_rate':   0,   # Rate hiện tại OK (publish ngay sau meeting)
    'cot':          -3,   # COT reflect Tuesday, publish Friday (3-day lag)
    'price':         0,   # Friday close — available same day
}
```

> **Unit test bắt buộc trong Phase 2:** Kiểm tra từng feature không chứa future data. Không skip bước này.

---

### 2.3 Tầng 3 — Cross-Asset Context (Bổ sung)

**Tất cả từ CFTC Socrata và FRED — không có scraping.**

| Nguồn | Data | API |
|---|---|---|
| CFTC Socrata | Gold Futures COT | REST (cùng Tầng 1) |
| CFTC Socrata | Oil Futures COT | REST (cùng Tầng 1) |
| CFTC Socrata | S&P 500 Futures COT | REST (cùng Tầng 1) |
| FRED `VIXCLS` | VIX Index | FRED API (cùng Tầng 2) |
| FRED `DGS10` + series | US/DE/UK/JP 10Y Yields | FRED API (cùng Tầng 2) |

**Derived features:**
- Yield differential: `US10Y − DE10Y`, `US10Y − JP10Y`, `US10Y − GB10Y`
- VIX regime bucket: Low (<15), Normal (15–20), Elevated (20–30), Extreme (>30)
- Gold COT trend — inverse relationship với USD
- Oil COT trend — direct relationship với CAD

---

### 2.4 Tầng 4 — Seasonal & Calendar (Bổ sung, ít quan trọng nhất)

#### Built-in Calendar Features

| Feature | Nguồn | Cách tính |
|---|---|---|
| Week of year (1–52) | Python built-in | `datetime.isocalendar().week` |
| Month (1–12) | Python built-in | `datetime.month` |
| Quarter (1–4) | Python built-in | `(month - 1) // 3 + 1` |
| Days to next FOMC | MQL5 API → static JSON fallback | Xem bên dưới |
| Days to NFP | MQL5 API → static JSON fallback | Xem bên dưới |

#### Nguồn Calendar — MQL5 Economic Calendar API + Fallback

```
Primary:  MQL5 Economic Calendar API (free, GET request, JSON response)
          → Tự động cập nhật khi lịch thay đổi trong năm
          → Không cần scrape HTML

Fallback: static/calendar_{YEAR}.json — cập nhật thủ công tháng 1 hàng năm
          → Fed/BLS công bố lịch cả năm từ tháng 12 năm trước
          → 15 phút/năm khi MQL5 API unavailable

Alert khi dùng fallback:
  CALENDAR_SOURCE_FALLBACK — Severity: LOW
  → Kiểm tra thủ công nếu có thay đổi lịch gần đây
```

---

### 2.5 Nguồn Dữ Liệu — Không Sử Dụng

| Nguồn | Lý do loại |
|---|---|
| Tin tức hàng ngày / headlines | Nhiễu nhiều hơn signal |
| Social media sentiment | Không consistent, thường contrarian noise |
| Technical indicators (RSI, MACD) | Derivative của price — không thêm thông tin mới |
| Proprietary data feeds | Không phù hợp yêu cầu free-only |
| stooq.com / Yahoo Finance (real-time) | Không có SLA, block bot không báo trước |
| BOJ/RBA/RBNZ/SNB individual APIs | Format không chuẩn, scraping-based — thay bằng FRED |
| FedReserve.gov / BLS.gov scraping | HTML thay đổi hàng năm — thay bằng MQL5 API |

---

### 2.6 Data Source Health SLA

| Tier | Tiêu chí | Ví dụ |
|---|---|---|
| **TIER 1** — Không thể thay thế | Official API, uptime >99%, format stable >3 năm | CFTC Socrata, FRED |
| **TIER 2** — Có thể thay thế nếu cần | Official API, uptime >95%, có alternative rõ ràng | ECB, MQL5 Calendar |
| **TIER 3** — Thay thế ngay khi có vấn đề | Scraping-based, no SLA | *(Đã loại hết từ v2.0)* |

**Trigger để review:**
- Fail >2 tuần liên tiếp → tìm alternative ngay
- Format change làm pipeline break → đánh giá lại dependency
- Không update đúng schedule >3 lần/quý → downgrade hoặc loại

**`DATA_SOURCE_STALE` threshold:** Record mới nhất cũ hơn 14 ngày → trigger HIGH alert, dùng data tuần trước + flag WARNING trong output.

---

## 3. Feature Engineering

### 3.1 Nguyên Tắc

Không feed raw numbers. Feed **relationships, directions, và normalized values.**

### 3.2 Feature Set — 28 Features Per Currency Per Week

#### Group A — COT Features từ Legacy Report (12 features)

| # | Feature | Mô tả | Cách tính |
|---|---|---|---|
| 1 | `cot_index` | COT Index 52 tuần | `(Net − Min52) / (Max52 − Min52) × 100` |
| 2 | `cot_index_4w_change` | Thay đổi COT Index 4 tuần | `cot_index[t] − cot_index[t−4]` |
| 3 | `net_pct_change_1w` | % thay đổi Net Position tuần này | `(Net[t] − Net[t−1]) / |Net[t−1]| × 100` |
| 4 | `momentum_acceleration` | Tăng tốc / Giảm tốc | `delta[t] − delta[t−1]` (dương = tăng tốc) |
| 5 | `oi_delta_direction` | OI đang tăng hay giảm | `sign(OI[t] − OI[t−1])` |
| 6 | `oi_net_confluence` | OI × Net confluence | 4 regime: Strong / Covering / NewShort / Liquidation |
| 7 | `flip_flag` | Net Position đổi chiều | `1 nếu sign(Net[t]) ≠ sign(Net[t−1])` |
| 8 | `extreme_flag` | COT ở vùng extreme | `1 nếu cot_index < 10 hoặc > 90` |
| 9 | `usd_index_cot` | USD Index COT Index | Cùng công thức COT Index |
| 10 | `rank_in_8` | Rank sức mạnh trong 8 pairs | 1 (mạnh nhất) đến 8 (yếu nhất) |
| 11 | `spread_vs_usd` | COT Index spread so với USD | `cot_index − usd_index_cot` |
| 12 | `weeks_since_flip` | Số tuần kể từ flip gần nhất | Count tuần |

#### Group B — TFF OI Features (4 features)

| # | Feature | Mô tả | Cách tính |
|---|---|---|---|
| 13 | `lev_funds_net_index` | Leveraged Funds Net normalized 52w | `(LevNet − Min52) / (Max52 − Min52) × 100` |
| 14 | `asset_mgr_net_direction` | Institutional flow đang xoay chiều? | `sign(AssetMgr_Net[t] − AssetMgr_Net[t−4])` |
| 15 | `dealer_net_contrarian` | Dealer positioning — contrarian signal | `Dealer_Net normalized; cực âm = market long crowded` |
| 16 | `lev_vs_assetmgr_divergence` | Phân kỳ speculative vs institutional | `LevFunds_Net_norm − AssetMgr_Net_norm` |

> **Ý nghĩa Group B:** `lev_funds_net_index` signal sạch hơn `cot_index` vì loại bỏ noise từ Commercial hedgers. `dealer_net_contrarian` mạnh nhất khi kết hợp `extreme_flag` — cả hai trigger cùng lúc = reversal risk rất cao. `lev_vs_assetmgr_divergence` cao → uncertainty → tăng xác suất NEUTRAL.

#### Group C — Macro Features (8 features)

| # | Feature | Mô tả | Cách tính |
|---|---|---|---|
| 17 | `rate_diff_vs_usd` | Rate differential vs Fed | `CB_rate − Fed_rate` |
| 18 | `rate_diff_trend_3m` | Trend rate differential 3 tháng | `diff[t] − diff[t−12w]` |
| 19 | `rate_hike_expectation` | Kỳ vọng thay đổi rate | Proxy từ FRED Fed Funds Futures |
| 20 | `cpi_diff_vs_usd` | CPI differential vs US | `CPI_country − CPI_US` |
| 21 | `cpi_trend` | Trend CPI trong nước | `CPI[t] − CPI[t−3M]`: tăng / giảm / flat |
| 22 | `pmi_composite_diff` | PMI composite differential | `PMI_country − PMI_US` *(optional — xem ghi chú)* |
| 23 | `yield_10y_diff` | 10Y yield spread vs US | `yield_country − yield_US` |
| 24 | `vix_regime` | VIX regime bucket | 0=Low, 1=Normal, 2=Elevated, 3=Extreme |

> **Ghi chú `pmi_composite_diff`:** Feature **optional**. PMI free data không đồng đều về release date giữa các quốc gia. Đánh dấu `optional: true` trong `feature_metadata.json`. Model handle `NaN` gracefully — không fail khi thiếu.

#### Group D — Cross-Asset & Seasonal (4 features)

| # | Feature | Mô tả |
|---|---|---|
| 25 | `gold_cot_index` | Gold Futures COT Index (inverse USD signal) |
| 26 | `oil_cot_direction` | Oil COT trend (direct CAD signal, inverse USD) |
| 27 | `month` | Tháng trong năm (1–12) — seasonality |
| 28 | `quarter` | Quý (1–4) — quarterly flow patterns |

### 3.3 Target Variable

Label cho từng currency, từng tuần:

```
BULL    = COT Index tăng VÀ giá đồng tiền vs USD tăng tuần sau
BEAR    = COT Index giảm VÀ giá đồng tiền vs USD giảm tuần sau
NEUTRAL = Không thuộc BULL hoặc BEAR

→ Price data source: FRED Exchange Rate Series (Section 2.1.2)
→ 3-class classification problem
→ Target: tuần T+1 (future); Features: tuần T (current)
→ Label Confirmation Lag = 1 tuần (Section 5.1)
```

**Class imbalance contingency:** Nếu NEUTRAL >60% trong training set → test OR condition và chọn định nghĩa cho walk-forward accuracy cao hơn. Document lựa chọn trong model card.

---

## 4. Model Architecture

### 4.1 Primary Model — Random Forest Classifier

**Lý do chọn:**
- Xử lý tốt dataset nhỏ (~10,000 samples)
- Ít overfit hơn Gradient Boosting với data nhỏ
- Output probability distribution — không phải hard label
- Feature importance — explainable, không phải black box
- Không cần normalize features

**Hyperparameters (baseline):**

```python
RandomForestClassifier(
    n_estimators=200,
    max_depth=8,              # Giới hạn để tránh overfit
    min_samples_leaf=10,      # Test 10 vs 15 trong Phase 3, chọn cái tốt hơn
    max_features='sqrt',
    class_weight='balanced',  # Xử lý imbalanced labels
    random_state=42
)
```

### 4.2 Backup Model — Logistic Regression

Dùng để:
- Benchmark so sánh với Random Forest
- Fallback khi `FEATURE_VERSION_MISMATCH` alert trigger
- Explainability cao hơn khi cần audit

### 4.3 Không Sử Dụng

| Model | Lý do |
|---|---|
| LSTM / GRU | Cần >50,000 samples, overfit với 10K |
| XGBoost | Dễ overfit nếu không tune kỹ với data nhỏ |
| Neural Networks | Same as LSTM |
| Price prediction models | Out of scope — không dự đoán giá |

---

## 5. Training & Validation

### 5.1 Inference vs Retrain — Tách Biệt Hoàn Toàn

```
TUẦN T — Thứ Bảy 08:00 GMT+7:

  INFERENCE PIPELINE (chạy mỗi tuần — không bao giờ bị chặn):
    Input:  COT tuần T + macro + cross-asset (data mới nhất)
    Output: Bias prediction cho tuần T+1
    Model:  model.pkl hiện tại (không thay đổi)

  RETRAIN PIPELINE (chạy mỗi 4 tuần — sau inference):
    Input:  Training set đến tuần T−1 (labels đã confirmed)
    Lý do không dùng tuần T: Label tuần T cần COT tuần T+1 để xác nhận
    Output: model_candidate.pkl → validate → deploy nếu pass
```

**Enforce trong code:**

```python
# training/train_model.py
LABEL_CONFIRMATION_LAG = 1  # weeks — KHÔNG được thay đổi

training_cutoff = current_week - LABEL_CONFIRMATION_LAG
df_train = df[df['week'] <= training_cutoff]
# Không bao giờ train trên tuần T — label chưa confirmed
```

### 5.2 Walk-Forward Validation (Bắt buộc)

**KHÔNG dùng random train/test split vì time series.**

```
2006 ───────────────── 2020 │ 2021 ── 2023 │ 2024 ── nay
[ Training Set             ] [Validation ] [ Live Test ]

Walk-forward folds (monthly):
  Fold 1: Train 2006–2020, Test 2021-Q1
  Fold 2: Train 2006–2021-Q1, Test 2021-Q2
  ... (tiếp tục rolling)
  Fold N: Train 2006–2023, Test 2024

→ Kết quả mỗi fold log riêng vào data/history/model-metrics/
→ Average accuracy across folds = reported accuracy
```

> Training start từ 2006 (thay vì 2004 trong v1.0) vì TFF Report chỉ có từ 2006.

### 5.3 Baseline Comparison

Model phải beat tất cả baselines sau mới được deploy:

| Baseline | Mô tả | Expected accuracy |
|---|---|---|
| Random | Predict ngẫu nhiên | ~33% |
| Always BULL | Predict BULL tất cả | ~38% |
| COT Rule | Index >60=Bull, <40=Bear | ~60–62% |
| **Target model** | **Random Forest 28 features** | **>68%** |

### 5.4 Confidence Calibration

| Level | Điều kiện | Hành động |
|---|---|---|
| High Confidence | `max_probability > 0.65` | Trade signal đáng tin |
| Medium Confidence | `max_probability 0.50–0.65` | Cần xác nhận thêm |
| Low Confidence | `max_probability < 0.50` | UNCERTAIN → trigger `LOW_CONFIDENCE` alert |

**Calibration method:** Platt Scaling — `CalibratedClassifierCV(base_model, method='sigmoid')`

### 5.5 Retrain Schedule

| Action | Frequency | Trigger |
|---|---|---|
| Inference | Mỗi tuần (thứ Bảy) | Automatic — luôn chạy |
| Incremental retrain | Mỗi 4 tuần | Automatic — append + retrain + validate |
| Full retrain từ đầu | Mỗi 6 tháng | Scheduled hoặc `MODEL_DRIFT` alert |
| Emergency retrain | Ad-hoc | Accuracy giảm >10% vs baseline |

### 5.6 Model Rollback Policy *(Mới v2.1)*

```
Khi deploy model_candidate → model.pkl:
  1. Lưu model cũ: models/model_backup.pkl
  2. Lưu accuracy metrics: data/history/model-metrics/YYYY-WNN_pre_retrain.json

Trigger rollback tự động (kiểm tra mỗi tuần sau deploy):
  Điều kiện: Accuracy 4 tuần gần nhất < baseline_accuracy − 5%
  Action:
    → Restore models/model_backup.pkl → models/model.pkl
    → Trigger alert MODEL_ROLLBACK (severity: HIGH)
    → Push notification ngay lập tức (không đợi thứ Bảy)

Giữ tối đa 2 backup versions:
  model_backup.pkl      ← version trước
  model_backup_prev.pkl ← version trước nữa (xóa cái cũ hơn)
```

---

## 6. Output Specification

### 6.1 Weekly Bias Report

```json
{
  "meta": {
    "weekLabel": "2026-W12",
    "generatedAt": "2026-03-21T02:00:00Z",
    "modelVersion": "rf-v2.1",
    "featureVersion": "v2.1-28f",
    "overallConfidence": "HIGH",
    "dataSourceStatus": {
      "cot": "OK",
      "macro": "OK",
      "cross_asset": "OK",
      "calendar": "FALLBACK"
    }
  },
  "predictions": [
    {
      "currency": "USD",
      "bias": "BULL",
      "probability": { "bull": 0.78, "neutral": 0.15, "bear": 0.07 },
      "confidence": "HIGH",
      "rank": 1,
      "key_drivers": ["lev_funds_net_index_82", "rate_diff_leading", "cot_index_78"],
      "alerts": []
    },
    {
      "currency": "JPY",
      "bias": "BEAR",
      "probability": { "bull": 0.08, "neutral": 0.19, "bear": 0.73 },
      "confidence": "HIGH",
      "rank": 8,
      "key_drivers": ["cot_extreme_bear_4", "dealer_net_contrarian_high", "yield_diff_negative"],
      "alerts": ["EXTREME_POSITIONING"]
    },
    {
      "currency": "EUR",
      "bias": "NEUTRAL",
      "probability": { "bull": 0.41, "neutral": 0.35, "bear": 0.24 },
      "confidence": "LOW",
      "rank": 4,
      "key_drivers": ["cot_index_55", "lev_vs_assetmgr_divergence_high"],
      "alerts": ["LOW_CONFIDENCE", "MACRO_COT_CONFLICT"]
    }
  ],
  "pair_recommendations": {
    "strong_long": ["USD/JPY", "AUD/CHF", "GBP/NZD"],
    "strong_short": ["EUR/USD", "CHF/JPY"],
    "avoid": ["EUR/CHF", "AUD/NZD"]
  },
  "weekly_alerts": [
    {
      "type": "EXTREME_POSITIONING",
      "currency": "JPY",
      "message": "JPY COT Index = 4 — Extreme Bear. Historical: 76% reversal trong 3 tuần.",
      "severity": "HIGH"
    },
    {
      "type": "CALENDAR_SOURCE_FALLBACK",
      "message": "MQL5 API unavailable. Dùng static/calendar_2026.json. Kiểm tra thay đổi lịch.",
      "severity": "LOW"
    }
  ]
}
```

### 6.2 Alert Types

| Alert Type | Điều kiện kích hoạt | Severity |
|---|---|---|
| `EXTREME_POSITIONING` | COT Index < 10 hoặc > 90 | HIGH |
| `FLIP_DETECTED` | Net Position đổi dấu tuần này | HIGH |
| `MODEL_DRIFT` | Accuracy giảm >5% vs baseline | HIGH |
| `MODEL_ROLLBACK` | Model mới underperform → restore backup *(mới v2.1)* | HIGH |
| `MISSING_DATA` | Thiếu data source Tầng 1 tuần này | HIGH |
| `RISK_OFF_REGIME` | VIX > 25 — override COT bias cho JPY/CHF | HIGH |
| `DATA_SOURCE_STALE` | API trả về data có date > 14 ngày | HIGH |
| `FEATURE_VERSION_MISMATCH` | model.pkl train với feature version khác current | HIGH |
| `LOW_CONFIDENCE` | `max_probability < 0.50` | MEDIUM |
| `MACRO_COT_CONFLICT` | COT bias ngược chiều macro differential | MEDIUM |
| `MOMENTUM_DECEL` | Momentum giảm tốc 3 tuần liên tiếp | MEDIUM |
| `OI_DIVERGENCE` | Net tăng nhưng OI giảm, hoặc ngược lại | MEDIUM |
| `CALENDAR_SOURCE_FALLBACK` | MQL5 API fail, dùng static JSON | LOW |

**Handling khi `FEATURE_VERSION_MISMATCH`:** Dừng Random Forest, chạy Logistic Regression fallback, alert severity HIGH, flag output `"model": "fallback_lr"`.

### 6.3 Pair Selection Logic

```
Bước 1: Lọc pairs có confidence HIGH cho cả 2 đồng tiền

Bước 2: Tính directional spread
        spread = base_probability_bull − quote_probability_bull

Bước 3: Rank theo |spread| giảm dần (lớn nhất = signal mạnh nhất)

Bước 4: Loại bỏ pairs có bất kỳ alert HIGH nào

Bước 5 (Mới v2.1) — Correlation Filter:
  Loại bỏ pairs có currency correlation > 0.7:
    EUR/USD ↔ GBP/USD   → ~0.85  → giữ pair có spread cao hơn
    USD/JPY ↔ USD/CHF   → ~0.75  → giữ pair có confidence cao hơn
    AUD/USD ↔ NZD/USD   → ~0.88  → giữ pair có spread cao hơn
  Mục tiêu: Top 5 Strong Long có ít nhất 3 independent directional bets

Bước 6: Top 5 sau filter = Strong Long; Top 5 reversed = Strong Short

Bước 7: Pairs có LOW_CONFIDENCE ở cả 2 sides → Avoid list
```

> **Lý do Correlation Filter:** Nếu không có bước này, hệ thống có thể recommend USD/JPY + USD/EUR + USD/GBP cùng lúc — thực chất là 1 bet vào USD, risk không được diversify.

---

## 7. System Architecture

### 7.1 Infrastructure

| Component | Platform | Lý do |
|---|---|---|
| Scheduler | GitHub Actions | Free tier: 2,000 min/tháng — dùng <60 min/tháng |
| Compute | GitHub Actions runner (Ubuntu, 2-core, 7GB RAM) | Đủ cho ML inference |
| Storage | GitHub repository (JSON files) | Đơn giản, versioned, diffable |
| Model file | `models/model.pkl` trong repo | <5MB, không cần external storage |
| Notification | Telegram Bot (recommended) / GitHub Email | Push alerts đến trader |

### 7.2 GitHub Secrets — Setup Bắt Buộc Trước Phase 1 *(Mới v2.1)*

| Secret Name | Mô tả | Bắt buộc? |
|---|---|---|
| `FRED_API_KEY` | Free key tại fred.stlouisfed.org | ✅ Bắt buộc |
| `TELEGRAM_BOT_TOKEN` | Tạo qua @BotFather trên Telegram | ✅ Nếu dùng Telegram |
| `TELEGRAM_CHAT_ID` | Chat ID của trader | ✅ Nếu dùng Telegram |

**Setup:** GitHub repo → Settings → Secrets and variables → Actions → New repository secret.

### 7.3 Notification System *(Mới v2.1)*

**Mỗi thứ Bảy sau khi pipeline hoàn thành**, hệ thống push summary:

```
📊 FX Bias — 2026-W12

🟢 STRONG LONG:  USD/JPY | AUD/CHF | GBP/NZD
🔴 STRONG SHORT: EUR/USD | CHF/JPY
⚠️  AVOID:       EUR/CHF | AUD/NZD

🚨 ALERTS (HIGH):
  • JPY — EXTREME_POSITIONING (COT Index = 4)

📎 Full report: github.com/repo/data/bias-latest.json
```

**Notification options:**

```
Option A — Telegram Bot (recommended):
  → Bot token lưu trong GitHub Secrets
  → Push ngay sau Job 4 hoàn thành
  → Free, nhận được trên điện thoại ngay lập tức
  → ~20 dòng Python, không cần maintain

Option B — GitHub Actions Email:
  → Dùng actions/github-script gửi email
  → Free, không cần external service
  → Chỉ cho HIGH severity alerts, không push weekly summary

Rollback alert: Push NGAY LẬP TỨC khi MODEL_ROLLBACK trigger
               Không đợi đến thứ Bảy tiếp theo
```

### 7.4 Pipeline Overview

Chạy mỗi **thứ Bảy 08:00 GMT+7 (01:00 UTC):**

```
┌──────────────────────────────────────────────────────────────────────┐
│                      GITHUB ACTIONS PIPELINE                         │
├─────────────┬──────────────┬──────────────────┬──────────────────────┤
│   Job 1     │   Job 2      │   Job 3           │   Job 4              │
│ fetch_cot   │ fetch_macro  │ fetch_cross_asset │ predict_bias         │
│             │              │                   │                      │
│ CFTC Legacy │ FRED API     │ Gold/Oil/SP500 COT│ Load all data        │
│ CFTC TFF    │ ECB API      │ VIX, Yields       │ Feature engineering  │
│ → cot.json  │ → macro.json │ → cross.json      │ Check FVER mismatch  │
│             │              │                   │ Run model            │
│             │              │                   │ Correlation filter   │
│             │              │                   │ Generate alerts      │
│             │              │                   │ → bias.json          │
│             │              │                   │ Push notification    │
└─────────────┴──────────────┴──────────────────┴──────────────────────┘
                                                          │
                              ┌───────────────────────────┘
                              ▼
               IF (current_week % 4 == 0):
                 Job 5: retrain_model
                   → Build training set đến T−1
                   → Walk-forward validate
                   → Deploy nếu pass baseline
                   → Backup model cũ trước khi deploy
                   → Push retrain summary notification
```

### 7.5 File Structure

```
repo/
├── .github/
│   └── workflows/
│       ├── fetch-data.yml          ← Job 1, 2, 3
│       ├── predict-bias.yml        ← Job 4 + conditional Job 5
│       └── notify.yml              ← Reusable notification workflow
├── scripts/
│   ├── fetch_cot.py                ← CFTC Legacy + TFF
│   ├── fetch_macro.py              ← FRED + ECB
│   ├── fetch_cross_asset.py        ← Gold/Oil COT, VIX, Yields
│   ├── fetch_calendar.py           ← MQL5 API + static JSON fallback
│   ├── feature_engineering.py      ← 28 features + lag enforcement
│   ├── predict_bias.py             ← Inference + correlation filter
│   ├── generate_alerts.py          ← 13 alert types
│   ├── notify.py                   ← Telegram / email push
│   └── rollback_model.py           ← Model rollback logic
├── models/
│   ├── model.pkl                   ← Production model
│   ├── model_backup.pkl            ← Previous version (rollback target)
│   ├── model_backup_prev.pkl       ← 2 versions ago (xóa cũ hơn)
│   ├── calibrator.pkl              ← Platt scaling calibrator
│   └── feature_metadata.json       ← Feature names, versions, optional flags
├── training/
│   ├── train_model.py              ← Offline + incremental training
│   ├── validate_model.py           ← Walk-forward validation
│   ├── build_labels.py             ← Tạo BULL/BEAR/NEUTRAL từ COT + price
│   └── data/
│       ├── prices_2006_2026.csv    ← FRED FX weekly closes (build once)
│       └── features_2006_2026.csv  ← Full feature matrix (labeled)
├── static/
│   └── calendar_2026.json          ← Fallback FOMC/NFP dates
└── data/
    ├── cot-latest.json
    ├── macro-latest.json
    ├── cross-asset-latest.json
    ├── bias-latest.json             ← Main output
    └── history/
        ├── bias/                    ← Weekly bias (giữ 2 năm gần nhất)
        └── model-metrics/           ← Accuracy per fold + pre/post retrain
```

**Storage retention:** `data/history/bias/` giữ 2 năm gần nhất. File cũ hơn archive hoặc xóa mỗi tháng 1 hàng năm.

---

## 8. Development Phases

### Phase 1 — Data Foundation (Tuần 1–3)

**Mục tiêu:** Pipeline thu thập đầy đủ và ổn định

**Setup trước khi bắt đầu:**
- Tạo FRED API key tại fred.stlouisfed.org
- Setup GitHub Secrets: `FRED_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- Verify tất cả FRED series IDs trong bảng Section 2.2 tại fred.stlouisfed.org

**Tasks:**
- `fetch_cot.py` — CFTC Legacy + TFF Report, OI fields đầy đủ, historical từ 2006
- `fetch_macro.py` — FRED API: đủ 8 currencies (policy rate + CPI)
- `fetch_macro.py` — ECB Data Portal: EUR rate + HICP CPI
- `fetch_cross_asset.py` — Gold/Oil/SP500 COT từ CFTC; VIX, yields từ FRED
- `fetch_calendar.py` — MQL5 API + static JSON fallback
- `notify.py` — Telegram / email notification
- Validate data quality: missing values, outliers, format consistency
- **Stability gate: chạy 3 tuần liên tiếp không có lỗi trước khi qua Phase 2**

**Deliverable:** `data/` folder đầy đủ mỗi tuần, 3 tuần liên tiếp không lỗi

### Phase 2 — Feature Engineering & Training Data (Tuần 4–6)

**Mục tiêu:** Build dataset sạch, leak-free để train model

**Tasks:**
- `build_labels.py` — Download FRED price data, tạo BULL/BEAR/NEUTRAL labels
- Kiểm tra class distribution — nếu NEUTRAL >60%, test AND vs OR và chọn tốt hơn
- `feature_engineering.py` — Tính đủ 28 features
- **Implement `PUBLICATION_LAG` constants — mandatory, không skip**
- Align tất cả data sources theo weekly frequency
- Build `features_2006_2026.csv`: ~20 năm × 52 tuần × 8 pairs
- Exploratory analysis: feature correlation, class distribution
- **Unit test bắt buộc: kiểm tra không có future data leak trong bất kỳ feature nào**

**Deliverable:** `training/data/features_2006_2026.csv` — clean, aligned, labeled, leak-free

### Phase 3 — Model Training & Validation (Tuần 7–8)

**Mục tiêu:** Model đạt accuracy >68% với walk-forward validation

**Tasks:**
- `train_model.py` — Random Forest với walk-forward CV
- `validate_model.py` — So sánh với 4 baselines
- Calibrate probability output (Platt Scaling)
- Feature importance analysis — Group B TFF features contribute bao nhiêu?
- Tune: test `min_samples_leaf` = 10 vs 15, chọn cái tốt hơn
- Document model card: accuracy per fold, feature importance, class distribution, limitations

**Deliverable:** `models/model.pkl` với full accuracy report và model card

### Phase 4 — Inference Pipeline (Tuần 9–10)

**Mục tiêu:** Auto-predict mỗi thứ Bảy, retrain mỗi 4 tuần, rollback khi cần

**Tasks:**
- `predict_bias.py` — Check `FEATURE_VERSION_MISMATCH`, build features, run inference
- `generate_alerts.py` — 13 alert types đầy đủ
- Pair selection logic với correlation filter (Bước 5)
- `rollback_model.py` — Backup trước deploy, kiểm tra weekly, restore nếu cần
- GitHub Actions workflows đầy đủ
- Test `LABEL_CONFIRMATION_LAG` logic trong retrain
- **Integration test: chạy thủ công 2 tuần liên tiếp, verify toàn bộ output**
- Test notification: Telegram push đúng format

**Deliverable:** `bias-latest.json` tự động mỗi thứ Bảy; retrain + rollback hoạt động đúng

### Phase 5 — Monitoring & Iteration (Ongoing)

**Mục tiêu:** Hệ thống ổn định, tự phát hiện vấn đề

**Weekly (tự động):**
- Model drift detection: alert khi accuracy drop >5%
- Rollback check: accuracy 4 tuần gần nhất vs baseline
- `DATA_SOURCE_STALE` check: data cũ >14 ngày
- `FEATURE_VERSION_MISMATCH` check trước inference

**Monthly (tự động):**
- Accuracy report: accuracy theo tháng, by currency, by confidence level

**Quarterly (manual review):**
- Có cần full retrain từ đầu không?
- Feature importance có thay đổi so với baseline không?
- Class distribution có drift không?

**Annually (tháng 1, manual — 15 phút):**
- Cập nhật `static/calendar_{YEAR}.json`
- Verify FRED series IDs còn active
- Review Data Source Health SLA

---

## 9. Constraints & Limitations

### 9.1 Ràng Buộc Kỹ Thuật

| Constraint | Chi tiết |
|---|---|
| Data size | ~10,000 samples sau augmentation — giới hạn complexity model |
| Macro data frequency | CPI, GDP là monthly → interpolate sang weekly, giảm precision |
| Rate expectations | Fed Futures không có free API → dùng proxy FRED |
| TFF history | TFF từ 2006 → training start từ 2006 (Legacy từ 1986 nhưng không dùng để đồng bộ) |
| GitHub Actions | Max 6 giờ/job, 2,000 min/tháng free tier |
| Label confirmation lag | Label tuần T chỉ confirmed sau COT tuần T+1 → retrain dùng data đến T−1 |
| Price data | Dùng FRED Exchange Rate series — daily, resample thành weekly Friday close |

### 9.2 Giới Hạn Dự Đoán

- Dự đoán **bias định hướng (direction)**, không phải giá hay pip target
- Accuracy ~68–76% trong điều kiện bình thường
- Accuracy giảm mạnh trong sự kiện bất ngờ (Black Swan, central bank intervention)
- Horizon 1 tuần — không ngoại suy sang tháng hay quý
- **Không thay thế judgment của trader** — công cụ hỗ trợ quyết định

### 9.3 Known Failure Modes

| Scenario | Tác động | Mitigation |
|---|---|---|
| Central bank surprise intervention | Model không predict được | `RISK_OFF_REGIME` khi VIX spike |
| Geopolitical shock | Positioning flip nhanh hơn model học | `MISSING_DATA` + freeze prediction |
| Market regime change | Accuracy giảm dần | Monthly monitoring + quarterly review |
| CFTC delay (holiday) | Thiếu data tuần đó | Dùng tuần trước, flag WARNING |
| MQL5 API unavailable | Calendar features thiếu | Fallback static JSON |
| API trả về data stale | Silent wrong features | `DATA_SOURCE_STALE` alert |
| Model mới underperform | Live accuracy xấu hơn | Rollback tự động + `MODEL_ROLLBACK` alert |
| FRED series discontinued | Feature bị NaN | Verify series IDs tháng 1 hàng năm |

---

## 10. Success Metrics

### 10.1 Technical Metrics

| Metric | Target | Minimum Acceptable |
|---|---|---|
| Walk-forward accuracy (3-class) | >72% | >65% |
| Beat COT-only baseline | +8% | +5% |
| High-confidence signal accuracy | >78% | >70% |
| Alert false positive rate | <15% | <25% |
| Pipeline uptime | >95% | >90% |
| Data freshness | <24h sau CFTC publish | <48h |
| Rollback rate | <1 lần/6 tháng | <1 lần/3 tháng |

### 10.2 Trading Utility Metrics

| Metric | Mô tả |
|---|---|
| Strong signal win rate | Khi confidence HIGH, directional accuracy trong backtest |
| Independent bet ratio | Tỷ lệ Strong Long pairs không tương quan >0.7 với nhau |
| Avoid signal value | Tỷ lệ pairs trong Avoid list thực sự sideways/noise tuần đó |
| Alert precision | Tỷ lệ HIGH alerts dẫn đến market event đáng chú ý |

---

## 11. Tech Stack

| Component | Technology | Lý do |
|---|---|---|
| Data collection | Python 3.11 + `requests` | Đơn giản, đủ dùng |
| Feature engineering | `pandas` + `numpy` | Standard cho tabular data |
| ML Model | `scikit-learn` RandomForest | Phù hợp data size, well-tested |
| Calibration | `scikit-learn` CalibratedClassifierCV | Platt scaling |
| Model serialization | `joblib` (.pkl) | Fast, compatible |
| Scheduler | GitHub Actions | Free, reliable |
| Storage | JSON files in Git repo | Đơn giản, versioned, diffable |
| Notification | `requests` → Telegram Bot API | Free, mobile-friendly, ~20 dòng code |
| Monitoring | Python logging + GitHub Actions annotations | Không cần external service |

---

## 12. Changelog

| Version | Ngày | Thay đổi chính |
|---|---|---|
| v1.0 | 2026-03-19 | Initial release |
| v2.0 | 2026-03-19 | Thêm TFF OI features; Thay Central Bank scrapers bằng FRED; Loại stooq/Yahoo Finance; Thêm MQL5 Calendar API; Publication Lag Rules; Tách Inference/Retrain; `LABEL_CONFIRMATION_LAG`; 3 alerts mới; Timeline 10 tuần; Data Source Health SLA |
| v2.1 | 2026-03-19 | **[Blocker fix]** Thêm FRED FX price series cho training labels; **[Blocker fix]** Hoàn thiện FRED macro coverage cho CHF/NZD/AUD/CAD/GBP; Class imbalance contingency; Model rollback policy + `MODEL_ROLLBACK` alert; Telegram notification system; GitHub Secrets documentation; Correlation filter trong pair selection (Bước 5); Storage retention policy; Training start từ 2006 (đồng bộ TFF history) |

---

*Document này là living document — cập nhật khi có thay đổi requirement hoặc sau mỗi phase review.*
