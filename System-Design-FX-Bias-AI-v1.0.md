# System Design — FX Bias AI Prediction System

**Version:** 1.0
**Ngày:** 2026-03-19
**RPD Reference:** v2.1
**UI/UX Reference:** v1.0
**Trạng thái:** Draft

---

## 0. Mục Lục

1. [Tổng Quan Kiến Trúc](#1-tổng-quan-kiến-trúc)
2. [Component Breakdown](#2-component-breakdown)
3. [Data Flow](#3-data-flow)
4. [JSON Schema Contracts](#4-json-schema-contracts)
5. [Backend Pipeline Design](#5-backend-pipeline-design)
6. [Frontend Architecture](#6-frontend-architecture)
7. [Integration Layer](#7-integration-layer)
8. [Error Handling & Resilience](#8-error-handling--resilience)
9. [Deployment Architecture](#9-deployment-architecture)
10. [Security](#10-security)
11. [Performance](#11-performance)
12. [Testing Strategy](#12-testing-strategy)
13. [Dependency Map](#13-dependency-map)

---

## 1. Tổng Quan Kiến Trúc

### 1.1 Kiểu Kiến Trúc: Static-First Pipeline

Hệ thống này **không phải một web server truyền thống**. Không có backend API server, không có database, không có real-time requests từ client. Toàn bộ dựa trên mô hình:

```
[Scheduled Job] → [Process Data] → [Write JSON files] → [Static Frontend reads JSON]
```

Đây là lựa chọn có chủ đích: zero infrastructure cost, zero server maintenance, phù hợp với single-user workflow và update frequency 1 lần/tuần.

### 1.2 System Context Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          EXTERNAL DATA SOURCES                          │
│                                                                         │
│   ┌──────────────┐  ┌──────────────┐  ┌────────────┐  ┌────────────┐  │
│   │ CFTC Socrata │  │  FRED API    │  │ ECB Portal │  │ MQL5 API   │  │
│   │ (Legacy+TFF) │  │  (Free key)  │  │ (No key)   │  │ (Calendar) │  │
│   └──────┬───────┘  └──────┬───────┘  └─────┬──────┘  └─────┬──────┘  │
└──────────┼──────────────────┼────────────────┼───────────────┼─────────┘
           │                  │                │               │
           ▼                  ▼                ▼               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     GITHUB ACTIONS (Backend Pipeline)                   │
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐ │
│  │   Job 1     │  │   Job 2     │  │   Job 3     │  │    Job 4      │ │
│  │ fetch_cot   │  │ fetch_macro │  │ fetch_cross │  │ predict_bias  │ │
│  │             │  │             │  │ _asset      │  │ + retrain     │ │
│  │ cot.json ◄──┘  macro.json◄──┘  cross.json◄──┘  bias.json ◄────┘ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └───────────────┘ │
│                                          │                              │
│                                   Job 5: notify                        │
│                                   (Telegram push)                      │
└──────────────────────────────────────────┬──────────────────────────────┘
                                           │
                              ┌────────────▼───────────┐
                              │    GitHub Repository    │
                              │    (Static File Store)  │
                              │                         │
                              │  data/bias-latest.json  │
                              │  data/cot-latest.json   │
                              │  data/macro-latest.json │
                              │  data/cross-latest.json │
                              │  data/history/bias/     │
                              │  models/model.pkl       │
                              └────────────┬────────────┘
                                           │
                              ┌────────────▼───────────┐
                              │   GitHub Pages/Vercel   │
                              │   (Static Hosting)      │
                              │                         │
                              │   Next.js Frontend      │
                              │   reads JSON via fetch  │
                              └────────────┬────────────┘
                                           │
                              ┌────────────▼───────────┐
                              │      TRADER             │
                              │  Desktop: Web Dashboard │
                              │  Mobile: Telegram Bot   │
                              └─────────────────────────┘
```

### 1.3 Phân Tách Rõ Ràng: Backend vs Frontend

| Dimension | Backend (GitHub Actions) | Frontend (Next.js) |
|---|---|---|
| **Ngôn ngữ** | Python 3.11 | TypeScript strict |
| **Chạy khi nào** | Thứ Bảy 01:00 UTC (scheduled) | Khi trader mở browser |
| **Output** | JSON files vào repo | Rendered UI |
| **Dependency** | CFTC, FRED, ECB, scikit-learn | JSON files từ repo |
| **State** | Stateless (mỗi lần chạy độc lập) | In-memory (Zustand) |
| **Deploy** | Tự chạy, không cần trigger | GitHub Pages / Vercel |

---

## 2. Component Breakdown

### 2.1 Backend Components

```
backend/
├── Data Collectors (4 scripts)
│   ├── fetch_cot.py           — CFTC Legacy + TFF
│   ├── fetch_macro.py         — FRED + ECB
│   ├── fetch_cross_asset.py   — Gold/Oil/SP500 COT, VIX, Yields
│   └── fetch_calendar.py      — MQL5 + static JSON fallback
│
├── Processing (2 scripts)
│   ├── feature_engineering.py — 28 features + lag enforcement
│   └── build_labels.py        — BULL/BEAR/NEUTRAL từ COT + FRED price
│
├── ML Core (4 scripts)
│   ├── train_model.py         — Walk-forward training
│   ├── validate_model.py      — Baseline comparison + drift check
│   ├── predict_bias.py        — Inference + pair selection + correlation filter
│   └── rollback_model.py      — Backup, deploy, restore logic
│
├── Output (2 scripts)
│   ├── generate_alerts.py     — 13 alert types
│   └── notify.py              — Telegram / email push
│
└── Shared (1 module)
    └── utils/
        ├── lag_rules.py       — PUBLICATION_LAG constants
        ├── feature_schema.py  — Feature metadata + version
        └── data_validator.py  — Freshness checks, format validation
```

### 2.2 Frontend Components

```
frontend/
├── App Shell
│   ├── Sidebar               — Navigation + version info
│   ├── Header                — Week picker + pipeline status + theme
│   └── Layout                — Page wrapper
│
├── Dashboard Page
│   ├── AlertBanner           — HIGH alerts với dismiss
│   ├── PairRecommendationGrid— 3 cột: Long / Short / Avoid
│   ├── CurrencyStrengthChart — Horizontal bars sorted by rank
│   └── AlertDetailSection    — Expandable cards
│
├── Data Audit Page
│   ├── CotDataPanel          — Legacy + TFF tables + sparklines
│   ├── MacroDataPanel        — Rates, CPI, Yields + freshness monitor
│   ├── CrossAssetPanel       — Commodities COT, yield diffs, VIX gauge
│   ├── FeatureInspector      — 28-feature table + importance chart
│   └── ModelDiagnostics      — Accuracy trend, baselines, retrain history
│
├── Shared Components (13)
│   ├── AlertBanner, PairCard, CurrencyBar
│   ├── DataTable, Sparkline, Badge, StatusDot
│   ├── WeekPicker, SlidePanel, TabBar
│   ├── FeatureImportanceChart, AccuracyLineChart, VixGauge
│
└── State (Zustand store)
    ├── biasData              — bias-latest.json
    ├── cotData               — cot-latest.json
    ├── macroData             — macro-latest.json
    ├── crossData             — cross-asset-latest.json
    ├── modelMetrics          — model-metrics/
    └── selectedWeek          — week navigation state
```

### 2.3 Infrastructure Components

| Component | Tool | Role |
|---|---|---|
| Scheduler | GitHub Actions cron | Trigger pipeline mỗi thứ Bảy |
| Compute | GitHub Actions runner (Ubuntu) | Chạy Python scripts + ML |
| File Storage | GitHub repository | Lưu JSON outputs + model.pkl |
| Static Hosting | GitHub Pages hoặc Vercel | Serve frontend |
| Secrets Store | GitHub Secrets | FRED key, Telegram tokens |
| Notification | Telegram Bot API | Push alerts đến trader |
| Model Storage | Git LFS hoặc direct commit | model.pkl < 5MB |

---

## 3. Data Flow

### 3.1 Weekly Production Flow (Thứ Bảy)

```
01:00 UTC — GitHub Actions trigger

┌────────────────────────────────────────────────────────────────┐
│ PHASE 1: DATA COLLECTION (parallel jobs, ~10 min total)        │
│                                                                │
│  Job 1: fetch_cot.py                                           │
│    GET cftc.gov/socrata → Legacy fields + TFF fields           │
│    Validate: date = last Friday, all 8 currencies present      │
│    Output: data/cot-latest.json                                │
│    Error: DATA_SOURCE_STALE hoặc MISSING_DATA alert            │
│                                                                │
│  Job 2: fetch_macro.py                                         │
│    GET fred.stlouisfed.org → policy rates + CPI + yields       │
│    GET sdw-wsgs.ecb.europa.eu → ECB rate + HICP                │
│    Validate: freshness check per series                        │
│    Output: data/macro-latest.json                              │
│                                                                │
│  Job 3: fetch_cross_asset.py                                   │
│    GET cftc.gov/socrata → Gold/Oil/SP500 COT                   │
│    GET fred.stlouisfed.org → VIX + yields (đã có từ Job 2)    │
│    Output: data/cross-asset-latest.json                        │
└────────────────────────────────────────────────────────────────┘
           │ (Jobs 1,2,3 complete)
           ▼
┌────────────────────────────────────────────────────────────────┐
│ PHASE 2: INFERENCE (sequential, ~5 min)                        │
│                                                                │
│  Job 4a: feature_engineering.py                                │
│    Load cot.json + macro.json + cross.json                     │
│    Apply PUBLICATION_LAG rules                                 │
│    Calculate 28 features per currency                          │
│    Check FEATURE_VERSION_MISMATCH                              │
│    Output: features_current_week.json (temp, không commit)     │
│                                                                │
│  Job 4b: predict_bias.py                                       │
│    Load model.pkl + calibrator.pkl                             │
│    Run RandomForest inference → probability[3] per currency    │
│    Apply Platt scaling calibration                             │
│    Classify confidence levels                                  │
│    Run correlation filter (Bước 5 pair selection)              │
│    Output: pair_recommendations                                │
│                                                                │
│  Job 4c: generate_alerts.py                                    │
│    Check 13 alert conditions                                   │
│    Classify severity: HIGH / MEDIUM / LOW                      │
│    Build weekly_alerts[]                                       │
│                                                                │
│  Job 4d: assemble output                                       │
│    Merge predictions + pairs + alerts → bias-latest.json       │
│    Append to data/history/bias/YYYY-WNN.json                   │
│    Commit + push to repo                                       │
└────────────────────────────────────────────────────────────────┘
           │
           ▼
┌────────────────────────────────────────────────────────────────┐
│ PHASE 3: RETRAIN (conditional, mỗi 4 tuần, ~15 min)           │
│                                                                │
│  IF (current_week % 4 == 0):                                   │
│    Job 5a: build training set đến tuần T-1                     │
│    Job 5b: train_model.py → model_candidate.pkl                │
│    Job 5c: validate_model.py → compare vs 4 baselines          │
│    IF (accuracy > baseline + 5%):                              │
│      Backup model.pkl → model_backup.pkl                       │
│      Deploy model_candidate.pkl → model.pkl                    │
│      Log metrics → data/history/model-metrics/                 │
│    ELSE:                                                       │
│      Discard candidate, keep current model                     │
│      Alert: MODEL_RETRAIN_FAILED (MEDIUM)                      │
└────────────────────────────────────────────────────────────────┘
           │
           ▼
┌────────────────────────────────────────────────────────────────┐
│ PHASE 4: NOTIFICATION (cuối cùng, ~1 min)                      │
│                                                                │
│  Job 6: notify.py                                              │
│    Load bias-latest.json                                       │
│    Format Telegram message (summary + HIGH alerts)             │
│    POST telegram.org/bot{TOKEN}/sendMessage                    │
│    Include link to web dashboard                               │
└────────────────────────────────────────────────────────────────┘

Total estimated runtime: ~30 min (well within 6h Actions limit)
GitHub Actions minutes used: ~30/2000 per month = 1.5%
```

### 3.2 Rollback Flow (Triggered khi accuracy drop)

```
Weekly accuracy check (sau mỗi inference):
  
  Tính accuracy 4 tuần gần nhất:
    Compare prediction[T-4..T-1] vs actual[T-4..T-1]
    actual = label build từ FRED price + COT tuần sau

  IF (accuracy_4w < baseline_accuracy - 5%):
    1. Copy model.pkl → model_backup_prev.pkl  (cũ nhất)
    2. Copy model_backup.pkl → model.pkl       (restore)
    3. Delete model_backup_prev.pkl nếu có cũ hơn
    4. Generate alert: MODEL_ROLLBACK (HIGH)
    5. notify.py → Telegram NGAY (không đợi thứ Bảy)
    6. Log: data/history/model-metrics/rollback_YYYY-WNN.json
```

### 3.3 Frontend Data Flow

```
Browser load
     │
     ▼
Next.js App boots
     │
     ├─── fetch('/data/bias-latest.json')     ──► biasStore
     ├─── fetch('/data/cot-latest.json')       ──► cotStore
     ├─── fetch('/data/macro-latest.json')     ──► macroStore
     ├─── fetch('/data/cross-asset-latest.json')──► crossStore
     └─── fetch('/data/history/model-metrics/')──► metricsStore
          (list last 12 entries)
                    │
                    ▼
           Zustand hydrated
                    │
     ┌──────────────┴──────────────┐
     ▼                             ▼
Dashboard renders           Data Audit ready
  - AlertBanner               - COT tables
  - PairGrid                  - Macro tables
  - CurrencyBars              - Feature inspector
  - AlertDetail               - Model diagnostics

Week navigation:
  User selects W11 (not latest)
     │
     ▼
  fetch('/data/history/bias/2026-W11.json')
  fetch('/data/history/cot/2026-W11.json')   (nếu có)
     │
     ▼
  Replace biasStore + cotStore với historical data
  Dashboard re-renders với header badge "HISTORICAL"
```

---

## 4. JSON Schema Contracts

> Đây là **interface contract** giữa backend (Python) và frontend (TypeScript). Cả hai phải tuân thủ schema này. Thay đổi schema = bump `featureVersion` + thông báo cả 2 bên.

### 4.1 `bias-latest.json` — Primary Output

```typescript
interface BiasReport {
  meta: {
    weekLabel: string;              // "2026-W12"
    generatedAt: string;            // ISO 8601
    modelVersion: string;           // "rf-v2.1"
    featureVersion: string;         // "v2.1-28f"
    overallConfidence: "HIGH" | "MEDIUM" | "LOW";
    dataSourceStatus: {
      cot: "OK" | "STALE" | "FAILED";
      macro: "OK" | "STALE" | "FAILED";
      cross_asset: "OK" | "STALE" | "FAILED";
      calendar: "OK" | "FALLBACK" | "FAILED";
    };
    pipelineRuntime: number;        // seconds
  };

  predictions: CurrencyPrediction[];

  pair_recommendations: {
    strong_long: PairRecommendation[];
    strong_short: PairRecommendation[];
    avoid: PairRecommendation[];
  };

  weekly_alerts: Alert[];
}

interface CurrencyPrediction {
  currency: "USD" | "EUR" | "GBP" | "JPY" | "AUD" | "CAD" | "CHF" | "NZD";
  bias: "BULL" | "BEAR" | "NEUTRAL";
  probability: {
    bull: number;     // 0–1
    neutral: number;  // 0–1
    bear: number;     // 0–1
  };
  confidence: "HIGH" | "MEDIUM" | "LOW";
  rank: number;       // 1–8
  key_drivers: string[];            // top 3 feature names
  alerts: AlertType[];              // alert types active for this currency
  historical_accuracy_12w?: number; // optional, 0–1
}

interface PairRecommendation {
  pair: string;          // "USD/JPY"
  spread: number;        // directional spread score
  base_currency: string;
  quote_currency: string;
  confidence: "HIGH" | "MEDIUM" | "LOW";
}

interface Alert {
  type: AlertType;
  currency?: string;     // undefined for system-level alerts
  message: string;
  severity: "HIGH" | "MEDIUM" | "LOW";
  context?: Record<string, unknown>;  // extra data for UI display
}

type AlertType =
  | "EXTREME_POSITIONING"
  | "FLIP_DETECTED"
  | "MODEL_DRIFT"
  | "MODEL_ROLLBACK"
  | "MISSING_DATA"
  | "RISK_OFF_REGIME"
  | "DATA_SOURCE_STALE"
  | "FEATURE_VERSION_MISMATCH"
  | "LOW_CONFIDENCE"
  | "MACRO_COT_CONFLICT"
  | "MOMENTUM_DECEL"
  | "OI_DIVERGENCE"
  | "CALENDAR_SOURCE_FALLBACK";
```

### 4.2 `cot-latest.json` — COT Raw Data

```typescript
interface CotReport {
  reportDate: string;          // "2026-03-17" (Tuesday close date)
  publishDate: string;         // "2026-03-21" (Friday publish date)
  source: "CFTC_LEGACY_TFF";

  legacy: CotLegacyRecord[];
  tff: CotTffRecord[];

  cot_indices: {               // pre-computed 52w indices
    [currency: string]: {
      index: number;           // 0–100
      trend_12w: number[];     // last 12 values for sparkline
    };
  };
}

interface CotLegacyRecord {
  currency: string;
  noncomm_long: number;
  noncomm_short: number;
  open_interest: number;
  net: number;                 // long - short
  net_delta_1w: number;        // vs last week
  cot_index_52w: number;       // 0–100
  extreme_flag: boolean;
  flip_flag: boolean;
}

interface CotTffRecord {
  currency: string;
  lev_funds_long: number;
  lev_funds_short: number;
  lev_funds_net: number;
  asset_mgr_long: number;
  asset_mgr_short: number;
  asset_mgr_net: number;
  dealer_long: number;
  dealer_short: number;
  dealer_net: number;
  lev_vs_assetmgr_divergence: number;
}
```

### 4.3 `macro-latest.json` — Macro Data

```typescript
interface MacroReport {
  fetchDate: string;           // ISO date

  policy_rates: MacroSeriesRecord[];
  cpi_yoy: MacroSeriesRecord[];
  yields_10y: YieldRecord[];
  vix: {
    value: number;
    regime: "LOW" | "NORMAL" | "ELEVATED" | "EXTREME";
    delta_1w: number;
  };
}

interface MacroSeriesRecord {
  currency: string;
  value: number;
  diff_vs_usd: number;
  trend_3m: "RISING" | "FALLING" | "STABLE";
  last_update: string;         // ISO date of source record
  publication_lag_applied: number;  // months lag applied
  freshness_days: number;      // days since last_update
  is_stale: boolean;           // > 14 days threshold
}

interface YieldRecord {
  country: string;
  yield: number;
  spread_vs_us: number;
  delta_1w: number;
  direction: "WIDENING" | "NARROWING" | "STABLE";
  last_update: string;
}
```

### 4.4 `cross-asset-latest.json` — Cross-Asset Data

```typescript
interface CrossAssetReport {
  fetchDate: string;

  commodities: {
    gold: CommodityCotRecord;
    oil: CommodityCotRecord;
    sp500: CommodityCotRecord;
  };

  yield_differentials: YieldDifferential[];
}

interface CommodityCotRecord {
  cot_index: number;           // 0–100
  trend_12w: number[];         // for sparkline
  trend_direction: "RISING" | "FALLING" | "FLAT";
  fx_impact: string;           // "Inverse USD" | "Direct CAD" | "Risk-on proxy"
}

interface YieldDifferential {
  pair: string;                // "US-DE"
  spread: number;
  delta_4w: number;
  direction: "WIDENING" | "NARROWING" | "STABLE";
}
```

### 4.5 `model-metrics/YYYY-WNN.json` — Model Performance

```typescript
interface ModelMetrics {
  week: string;                // "2026-W12"
  modelVersion: string;
  featureVersion: string;
  action: "INFERENCE_ONLY" | "RETRAIN_DEPLOYED" | "RETRAIN_REJECTED" | "ROLLBACK";

  accuracy: {
    current_week: number;
    rolling_4w: number;
    rolling_12w: number;
    by_currency: { [currency: string]: number };
    by_confidence: {
      HIGH: number;
      MEDIUM: number;
      LOW: number;
    };
  };

  baselines: {
    random: number;
    always_bull: number;
    cot_rule_only: number;
    vs_cot_rule_delta: number;
  };

  retrain?: {                  // chỉ khi action = RETRAIN_*
    pre_accuracy: number;
    post_accuracy: number;
    deployed: boolean;
    reason_rejected?: string;
  };

  rollback?: {                 // chỉ khi action = ROLLBACK
    from_version: string;
    to_version: string;
    trigger_accuracy: number;
  };
}
```

### 4.6 `feature_metadata.json` — Feature Registry

```typescript
interface FeatureMetadata {
  version: string;             // "v2.1-28f"
  total_features: number;      // 28
  groups: FeatureGroup[];
}

interface FeatureGroup {
  name: string;                // "Group A — COT Features"
  features: FeatureDefinition[];
}

interface FeatureDefinition {
  id: number;                  // 1–28
  name: string;                // "cot_index"
  description: string;
  formula: string;             // human-readable
  optional: boolean;           // true = NaN OK
  source: "CFTC_LEGACY" | "CFTC_TFF" | "FRED" | "ECB" | "CALENDAR" | "DERIVED";
  publication_lag?: number;    // months (from PUBLICATION_LAG dict)
}
```

---

## 5. Backend Pipeline Design

### 5.1 Script Interface Conventions

Mỗi script phải tuân theo convention sau để đảm bảo composability:

```python
# Convention cho tất cả scripts

# 1. Exit codes
EXIT_SUCCESS = 0
EXIT_PARTIAL = 1   # Có data nhưng thiếu một phần — warning, không fail
EXIT_FAILED  = 2   # Không có data usable — fail job

# 2. Logging format (parse được bởi GitHub Actions)
import logging
logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    level=logging.INFO
)

# 3. Output file convention
# Mỗi script chỉ write vào 1 output file
# Không modify file của script khác
# Atomic write: write temp → rename

import json, tempfile, os

def write_output(data: dict, path: str):
    """Atomic write — không corrupt nếu process bị kill giữa chừng"""
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    os.rename(tmp, path)

# 4. Error reporting — mọi exception phải tạo alert
def emit_alert(alert_type: str, message: str, severity: str):
    """Ghi alert vào alerts-pending.json để generate_alerts.py tổng hợp"""
    ...
```

### 5.2 Feature Engineering — Lag Enforcement

```python
# utils/lag_rules.py — Nguồn duy nhất của truth về publication lag

from datetime import date
from dateutil.relativedelta import relativedelta

PUBLICATION_LAG = {
    'cpi':          {'unit': 'month', 'lag': -2},
    'gdp':          {'unit': 'quarter', 'lag': -1},
    'pmi':          {'unit': 'month', 'lag': -1},
    'policy_rate':  {'unit': 'month', 'lag': 0},
    'cot':          {'unit': 'day', 'lag': -3},
    'price':        {'unit': 'day', 'lag': 0},
    'yield_10y':    {'unit': 'day', 'lag': 0},
}

def get_valid_date_for(series_type: str, as_of: date) -> date:
    """
    Trả về ngày mà data series_type được phép dùng
    tại thời điểm as_of mà không bị look-ahead bias.
    """
    rule = PUBLICATION_LAG[series_type]
    if rule['unit'] == 'month':
        return as_of + relativedelta(months=rule['lag'])
    elif rule['unit'] == 'quarter':
        return as_of + relativedelta(months=rule['lag'] * 3)
    elif rule['unit'] == 'day':
        from datetime import timedelta
        return as_of + timedelta(days=rule['lag'])

# Test (chạy trong Phase 2 để verify):
assert get_valid_date_for('cpi', date(2026, 3, 21)) == date(2026, 1, 21)
assert get_valid_date_for('policy_rate', date(2026, 3, 21)) == date(2026, 3, 21)
```

### 5.3 Prediction Pipeline — Step by Step

```python
# scripts/predict_bias.py — High-level flow

def run_prediction_pipeline():

    # Step 1: Load + validate feature metadata
    feature_meta = load_json('models/feature_metadata.json')
    model = joblib.load('models/model.pkl')
    calibrator = joblib.load('models/calibrator.pkl')

    # Step 2: Check version compatibility
    if model.feature_version != feature_meta['version']:
        emit_alert('FEATURE_VERSION_MISMATCH', ..., 'HIGH')
        model = load_fallback_logistic_regression()

    # Step 3: Build feature matrix (8 currencies × 28 features)
    features_df = feature_engineering.build_current_week()
    # features_df shape: (8, 28)

    # Step 4: Inference
    raw_probs = model.predict_proba(features_df)         # (8, 3)
    cal_probs = calibrator.predict_proba(features_df)    # (8, 3) — calibrated

    # Step 5: Assign confidence levels
    predictions = []
    for i, currency in enumerate(CURRENCIES):
        max_prob = cal_probs[i].max()
        confidence = (
            'HIGH'   if max_prob > 0.65 else
            'MEDIUM' if max_prob > 0.50 else
            'LOW'
        )
        predictions.append(build_prediction(currency, cal_probs[i], confidence))

    # Step 6: Pair selection (Section 6.3 RPD)
    pairs = pair_selection_with_correlation_filter(predictions)

    # Step 7: Assemble output
    return assemble_bias_report(predictions, pairs)
```

### 5.4 Pair Selection — Correlation Filter Implementation

```python
# Correlation matrix — cố định, không tính real-time
CURRENCY_CORRELATION = {
    ('EUR', 'GBP'):  0.85,
    ('USD', 'CHF'):  0.75,  # inverse: USD/CHF và USD/JPY
    ('AUD', 'NZD'):  0.88,
    ('AUD', 'CAD'):  0.65,
}

CORRELATION_THRESHOLD = 0.70

def pair_selection_with_correlation_filter(predictions: list) -> dict:
    """
    Bước 1-7 từ RPD Section 6.3
    """
    # Bước 1: Chỉ giữ HIGH confidence ở cả 2 currencies
    eligible = [(p1, p2) for p1, p2 in all_pairs(predictions)
                if p1.confidence == 'HIGH' and p2.confidence == 'HIGH']

    # Bước 2: Tính directional spread
    for pair in eligible:
        pair.spread = pair.base.probability['bull'] - pair.quote.probability['bull']

    # Bước 3: Sort by |spread|
    eligible.sort(key=lambda p: abs(p.spread), reverse=True)

    # Bước 4: Loại pairs có HIGH alert
    eligible = [p for p in eligible if not has_high_alert(p)]

    # Bước 5: Correlation filter
    selected = []
    for candidate in eligible:
        # Kiểm tra correlation với các pair đã chọn
        correlated = False
        for existing in selected:
            if get_correlation(candidate, existing) > CORRELATION_THRESHOLD:
                correlated = True
                break
        if not correlated:
            selected.append(candidate)

    # Bước 6 & 7: Top 5 Long, Top 5 Short, Low confidence → Avoid
    strong_long  = [p for p in selected if p.spread > 0][:5]
    strong_short = [p for p in selected if p.spread < 0][:5]
    avoid = [p for p in all_pairs(predictions)
             if p.base.confidence == 'LOW' and p.quote.confidence == 'LOW']

    return {'strong_long': strong_long, 'strong_short': strong_short, 'avoid': avoid}
```

---

## 6. Frontend Architecture

### 6.1 Next.js App Structure

```
app/
├── layout.tsx                — Root layout: Sidebar + Header + theme
├── page.tsx                  — Redirect → /dashboard
├── dashboard/
│   └── page.tsx              — Dashboard page (Server Component → Client hydration)
├── audit/
│   └── page.tsx              — Data Audit page
├── performance/
│   └── page.tsx              — Phase 5+ placeholder
└── settings/
    └── page.tsx              — Phase 5+ placeholder

components/
├── shell/
│   ├── Sidebar.tsx
│   ├── Header.tsx
│   └── WeekPicker.tsx
├── dashboard/
│   ├── AlertBanner.tsx
│   ├── PairRecommendationGrid.tsx
│   ├── PairCard.tsx
│   ├── CurrencyStrengthChart.tsx
│   └── AlertDetailSection.tsx
├── audit/
│   ├── CotDataPanel.tsx
│   ├── MacroDataPanel.tsx
│   ├── CrossAssetPanel.tsx
│   ├── FeatureInspector.tsx
│   └── ModelDiagnostics.tsx
└── shared/
    ├── Badge.tsx, StatusDot.tsx, Sparkline.tsx
    ├── DataTable.tsx, SlidePanel.tsx, TabBar.tsx
    ├── FeatureImportanceChart.tsx, AccuracyLineChart.tsx
    └── VixGauge.tsx

lib/
├── store/
│   ├── biasStore.ts          — Zustand slice cho bias data
│   ├── auditStore.ts         — Zustand slice cho COT/macro/cross data
│   └── uiStore.ts            — Week selection, panel states, theme
├── fetchers/
│   ├── fetchBiasData.ts
│   ├── fetchCotData.ts
│   ├── fetchMacroData.ts
│   └── fetchHistorical.ts
└── types/
    └── index.ts              — TypeScript interfaces (mirror JSON Schema)
```

### 6.2 State Management (Zustand)

```typescript
// lib/store/biasStore.ts

interface BiasStore {
  // Data
  currentReport: BiasReport | null;
  historicalReports: Map<string, BiasReport>;  // weekLabel → report
  selectedWeek: string;                         // "2026-W12" | "LATEST"
  isLoading: boolean;
  error: string | null;

  // Actions
  loadCurrentWeek: () => Promise<void>;
  loadWeek: (weekLabel: string) => Promise<void>;
  setSelectedWeek: (week: string) => void;
  refresh: () => Promise<void>;

  // Derived (computed)
  highAlerts: () => Alert[];
  sortedPredictions: () => CurrencyPrediction[];  // by rank
}

// Loading strategy: eager load current week, lazy load historical
const useBiasStore = create<BiasStore>((set, get) => ({
  currentReport: null,
  historicalReports: new Map(),
  selectedWeek: 'LATEST',
  isLoading: false,
  error: null,

  loadCurrentWeek: async () => {
    set({ isLoading: true });
    try {
      const data = await fetchBiasData('/data/bias-latest.json');
      set({ currentReport: data, isLoading: false });
    } catch (e) {
      set({ error: String(e), isLoading: false });
    }
  },

  loadWeek: async (weekLabel) => {
    // Check cache first
    if (get().historicalReports.has(weekLabel)) {
      set({ selectedWeek: weekLabel });
      return;
    }
    const data = await fetchBiasData(`/data/history/bias/${weekLabel}.json`);
    set(state => ({
      historicalReports: new Map(state.historicalReports).set(weekLabel, data),
      selectedWeek: weekLabel,
    }));
  },

  highAlerts: () => (get().currentReport?.weekly_alerts ?? [])
    .filter(a => a.severity === 'HIGH'),

  sortedPredictions: () => (get().currentReport?.predictions ?? [])
    .sort((a, b) => a.rank - b.rank),
}));
```

### 6.3 Data Fetching Strategy

```typescript
// lib/fetchers/fetchBiasData.ts

// Caching: In-memory per session, không dùng localStorage (unsupported)
const cache = new Map<string, { data: unknown; fetchedAt: number }>();
const CACHE_TTL = 60 * 60 * 1000; // 1 hour

export async function fetchBiasData(url: string): Promise<BiasReport> {
  const cached = cache.get(url);
  if (cached && Date.now() - cached.fetchedAt < CACHE_TTL) {
    return cached.data as BiasReport;
  }

  const response = await fetch(url, {
    // GitHub Pages / Vercel serving static files
    headers: { 'Cache-Control': 'no-cache' },  // force revalidate
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status}`);
  }

  const data = await response.json();
  cache.set(url, { data, fetchedAt: Date.now() });
  return data as BiasReport;
}
```

### 6.4 Type Safety — Python → TypeScript Sync

Để đảm bảo backend Python output luôn khớp với frontend TypeScript types, dùng **schema validation ở cả 2 đầu**:

```python
# Backend: validate output trước khi write (scripts/predict_bias.py)
from jsonschema import validate

BIAS_SCHEMA = json.load(open('schemas/bias-report.schema.json'))

def validate_output(report: dict):
    try:
        validate(instance=report, schema=BIAS_SCHEMA)
    except ValidationError as e:
        emit_alert('SCHEMA_VALIDATION_FAILED', str(e), 'HIGH')
        raise
```

```typescript
// Frontend: runtime type guard
function isBiasReport(data: unknown): data is BiasReport {
  return (
    typeof data === 'object' && data !== null &&
    'meta' in data && 'predictions' in data &&
    'pair_recommendations' in data
  );
}
```

---

## 7. Integration Layer

### 7.1 Backend → Frontend Contract

```
Backend writes:                      Frontend reads:
─────────────────────────────────────────────────────
data/bias-latest.json          →     Dashboard + all pages
data/cot-latest.json           →     Data Audit / COT tab
data/macro-latest.json         →     Data Audit / Macro tab
data/cross-asset-latest.json   →     Data Audit / Cross-Asset tab
data/history/bias/YYYY-WNN.json→     Week navigation
data/history/model-metrics/    →     Data Audit / Model Diagnostics
models/feature_metadata.json   →     Data Audit / Feature Inspector
```

**Versioning rule:** Khi thay đổi JSON schema:
1. Bump `featureVersion` trong `bias-latest.json`
2. Backend validate output với JSON Schema trước khi commit
3. Frontend check `featureVersion` compatibility trước khi render
4. Nếu incompatible → hiện "Schema mismatch — please refresh or check backend"

### 7.2 Telegram Notification Contract

```python
# notify.py — Message format

def format_weekly_message(report: BiasReport) -> str:
    high_alerts = [a for a in report.weekly_alerts if a.severity == 'HIGH']

    lines = [
        f"📊 *FX Bias — {report.meta.weekLabel}*",
        f"Confidence: {report.meta.overallConfidence}",
        "",
        "🟢 *LONG:* " + " | ".join(
            p.pair for p in report.pair_recommendations.strong_long[:3]
        ),
        "🔴 *SHORT:* " + " | ".join(
            p.pair for p in report.pair_recommendations.strong_short[:3]
        ),
        "⚪ *AVOID:* " + " | ".join(
            p.pair for p in report.pair_recommendations.avoid[:2]
        ),
    ]

    if high_alerts:
        lines += ["", "🚨 *HIGH ALERTS:*"]
        for alert in high_alerts:
            currency = f"[{alert.currency}] " if alert.currency else ""
            lines.append(f"• {currency}{alert.type}")

    lines.append("")
    lines.append(f"📎 [Full Report]({DASHBOARD_URL})")

    return "\n".join(lines)

# Rollback alert (sent immediately, not weekly)
def format_rollback_alert(rollback_info: dict) -> str:
    return (
        f"⚠️ *MODEL ROLLBACK — {rollback_info['week']}*\n"
        f"Accuracy dropped to {rollback_info['trigger_accuracy']:.1%}\n"
        f"Restored: {rollback_info['to_version']}\n"
        f"Action required: Review recent data quality"
    )
```

### 7.3 GitHub Actions Workflow Coordination

```yaml
# .github/workflows/predict-bias.yml — Key orchestration

name: Weekly Prediction Pipeline
on:
  schedule:
    - cron: '0 1 * * 6'   # Saturday 01:00 UTC
  workflow_dispatch:        # Manual trigger for testing

jobs:
  fetch-data:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        job: [fetch_cot, fetch_macro, fetch_cross_asset]
      fail-fast: false      # Tiếp tục ngay cả khi 1 job fail
    steps:
      - uses: actions/checkout@v4
      - run: python scripts/${{ matrix.job }}.py
      - uses: actions/upload-artifact@v4
        with:
          name: ${{ matrix.job }}-output
          path: data/

  predict:
    needs: fetch-data       # Chỉ chạy sau khi tất cả fetch jobs done
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
      - run: python scripts/predict_bias.py
      - run: python scripts/generate_alerts.py
      - name: Commit outputs
        run: |
          git config user.name "fx-bias-bot"
          git add data/bias-latest.json data/history/
          git commit -m "chore: weekly bias update ${{ env.WEEK_LABEL }}"
          git push

  retrain:
    needs: predict
    if: ${{ github.event_name == 'schedule' }}  # Không retrain khi manual trigger
    runs-on: ubuntu-latest
    steps:
      - name: Check if retrain week
        id: check
        run: |
          WEEK=$(date +%V)
          echo "should_retrain=$(( WEEK % 4 == 0 ))" >> $GITHUB_OUTPUT
      - if: ${{ steps.check.outputs.should_retrain == '1' }}
        run: python training/train_model.py

  notify:
    needs: [predict, retrain]
    if: always()            # Notify kể cả khi có lỗi
    runs-on: ubuntu-latest
    steps:
      - run: python scripts/notify.py
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          PIPELINE_STATUS: ${{ needs.predict.result }}
```

---

## 8. Error Handling & Resilience

### 8.1 Failure Matrix — Backend

| Failure Scenario | Impact | System Response | Alert |
|---|---|---|---|
| CFTC API down | Không có COT data | Dùng tuần trước + flag WARNING | `MISSING_DATA` (HIGH) |
| FRED API down | Thiếu macro features | Dùng cached macro + flag STALE | `DATA_SOURCE_STALE` (HIGH) |
| ECB API down | Thiếu EUR macro | FRED fallback cho EUR rate | `DATA_SOURCE_STALE` (MEDIUM) |
| MQL5 calendar fail | Thiếu FOMC/NFP days | Dùng static JSON fallback | `CALENDAR_SOURCE_FALLBACK` (LOW) |
| Feature version mismatch | Model incompatible | Chạy Logistic Regression thay | `FEATURE_VERSION_MISMATCH` (HIGH) |
| Model.pkl corrupt | Inference fail | Restore model_backup.pkl | `MISSING_DATA` (HIGH) |
| GitHub Actions timeout | Pipeline không xong | Partial output, retry manual | Email từ GitHub |
| Telegram API fail | Không notify | Log lỗi, pipeline vẫn OK | GitHub Actions annotation |

### 8.2 Failure Matrix — Frontend

| Failure Scenario | UI Response |
|---|---|
| `bias-latest.json` not found | Red banner: "Data unavailable — pipeline may be delayed" + retry button |
| JSON parse error | Red banner: "Data format error" + link to raw JSON |
| Historical week not found | Toast: "No data for selected week" + reset to latest |
| Slow fetch (>5s) | Skeleton shimmer loading state |
| Partial data (some files missing) | Render available sections, grey out missing tabs with "Unavailable" |
| Schema version mismatch | Amber banner: "Dashboard may show stale data" |

### 8.3 Graceful Degradation Priority

```
Tier 1 (must work):    bias-latest.json → Dashboard renders
Tier 2 (important):    cot-latest.json  → COT tab renders
Tier 3 (nice to have): macro/cross/metrics → remaining tabs
```

Dashboard luôn render được nếu có `bias-latest.json`. Các tab trong Data Audit là independent — lỗi 1 tab không ảnh hưởng tab khác.

---

## 9. Deployment Architecture

### 9.1 Environments

| Environment | Mô tả | URL |
|---|---|---|
| Production | Auto-deploy từ `main` branch | `https://your-repo.github.io` |
| Staging | Feature branch preview | Vercel preview URL (optional) |
| Local dev | `npm run dev` với mock JSON | `localhost:3000` |

### 9.2 Deployment Flow

```
Developer push code:
  git push origin main
        │
        ▼
  GitHub Actions: build-frontend.yml
    - npm ci
    - npm run build
    - npx next export → out/
    - Deploy out/ → GitHub Pages
        │
        ▼
  GitHub Pages serves:
    Static HTML/JS/CSS
    + data/*.json (cùng repo)

Backend pipeline (tách biệt):
  Cron Saturday 01:00 UTC
  → Writes JSON files vào repo
  → git push
  → GitHub Pages tự serve JSON mới nhất
```

### 9.3 Repository Structure — Full

```
repo/
├── .github/
│   └── workflows/
│       ├── fetch-data.yml
│       ├── predict-bias.yml
│       ├── build-frontend.yml
│       └── notify.yml
│
├── backend/                  ← Python backend
│   ├── scripts/
│   ├── training/
│   ├── utils/
│   ├── schemas/              ← JSON Schema files cho validation
│   └── static/
│       └── calendar_2026.json
│
├── frontend/                 ← Next.js frontend
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── public/
│
├── models/                   ← Shared (backend writes, frontend references)
│   ├── model.pkl
│   ├── model_backup.pkl
│   ├── calibrator.pkl
│   └── feature_metadata.json
│
└── data/                     ← Shared (backend writes, frontend reads)
    ├── bias-latest.json
    ├── cot-latest.json
    ├── macro-latest.json
    ├── cross-asset-latest.json
    └── history/
        ├── bias/
        └── model-metrics/
```

---

## 10. Security

### 10.1 Secrets Management

| Secret | Lưu ở | Scope |
|---|---|---|
| `FRED_API_KEY` | GitHub Secrets | Backend only — không expose ra frontend |
| `TELEGRAM_BOT_TOKEN` | GitHub Secrets | Backend only |
| `TELEGRAM_CHAT_ID` | GitHub Secrets | Backend only |

**Frontend không có secrets.** Frontend chỉ đọc public JSON files. Không có API keys trong browser code.

### 10.2 Data Privacy

- Toàn bộ dữ liệu là **public market data** — không có thông tin nhạy cảm cá nhân
- JSON files trong repo là public nếu repo public — đây là chủ ý (trader review được lịch sử)
- Nếu muốn private: set repo to private, dùng GitHub Pages với authentication

### 10.3 Supply Chain

- Không có external runtime dependencies cho backend (chỉ Python stdlib + requests + scikit-learn + pandas)
- Frontend dependencies: Next.js ecosystem — pin versions trong `package-lock.json`
- CFTC/FRED data: public government data, không có ToS restrictions cho automated access

---

## 11. Performance

### 11.1 Backend Performance Budget

| Task | Expected Time | Hard Limit |
|---|---|---|
| fetch_cot.py | 2–3 min | 10 min |
| fetch_macro.py | 3–5 min | 15 min |
| fetch_cross_asset.py | 1–2 min | 5 min |
| feature_engineering.py | < 1 min | 5 min |
| predict_bias.py | < 1 min | 5 min |
| train_model.py (4-weekly) | 10–15 min | 30 min |
| **Total pipeline** | **~30 min** | **6 hours (Actions limit)** |

GitHub Actions free tier: 2,000 min/month. Pipeline dùng ~30 min/tuần × 4 = **120 min/tháng = 6% quota**.

### 11.2 Frontend Performance Budget

| Metric | Target | Method |
|---|---|---|
| First Contentful Paint | < 1.5s | Static generation (SSG) |
| Total JSON payload | < 200KB | Tất cả JSON files gộp lại |
| bias-latest.json size | < 20KB | 8 currencies × compact JSON |
| Dashboard TTI | < 2s | Lazy load Data Audit |
| Chart render (8 bars) | < 100ms | Recharts / lightweight-charts |
| Week navigation switch | < 500ms | In-memory cache sau lần đầu |

### 11.3 JSON Size Optimization

```python
# Compact JSON — loại bỏ whitespace trong production output
json.dumps(report, separators=(',', ':'))  # ~30% smaller than indent=2

# Estimated sizes:
# bias-latest.json: ~8KB compact (8 predictions + alerts + pairs)
# cot-latest.json:  ~15KB compact
# macro-latest.json: ~12KB compact
# cross-asset.json: ~5KB compact
# Total initial load: ~40KB — rất nhỏ
```

---

## 12. Testing Strategy

### 12.1 Backend Tests

```
tests/
├── unit/
│   ├── test_lag_rules.py         — Publication lag calculations
│   ├── test_feature_engineering.py — 28 features tính đúng không
│   ├── test_label_builder.py     — BULL/BEAR/NEUTRAL logic
│   ├── test_pair_selection.py    — Correlation filter
│   └── test_alert_generation.py  — 13 alert conditions
│
├── integration/
│   ├── test_cftc_api.py          — Live API call + response validation
│   ├── test_fred_api.py          — Live API call + series IDs active
│   └── test_full_pipeline.py     — End-to-end với mock data
│
└── validation/
    └── test_no_lookahead.py      — Critical: kiểm tra không có data leak
        # Test: với training set đến ngày X,
        #       không feature nào chứa info sau ngày X
```

**Critical test — Look-ahead bias detection:**

```python
def test_no_lookahead_bias():
    """
    Build feature matrix cho tuần 2020-W30.
    Verify không có field nào trong row này chứa data published
    sau ngày Friday 2020-W30.
    """
    reference_date = date(2020, 7, 24)  # Friday W30 2020
    features = build_features_for_week(reference_date)

    for feature_name, value in features.items():
        source_date = get_source_date(feature_name, reference_date)
        assert source_date <= reference_date, (
            f"LOOK-AHEAD BIAS: {feature_name} uses data from {source_date} "
            f"which is after reference date {reference_date}"
        )
```

### 12.2 Frontend Tests

```
__tests__/
├── components/
│   ├── AlertBanner.test.tsx      — Render với/không có HIGH alerts
│   ├── PairCard.test.tsx         — Long/Short/Avoid variants
│   ├── CurrencyStrengthChart.test.tsx
│   └── DataTable.test.tsx        — Sort, filter, conditional format
│
├── stores/
│   └── biasStore.test.ts         — Load, cache, week navigation
│
└── integration/
    └── dashboard.test.tsx        — Full page render với mock JSON
```

### 12.3 Manual Testing Checklist (Phase 4)

```
□ Pipeline chạy thứ Bảy đúng 01:00 UTC
□ bias-latest.json được commit vào repo
□ Telegram message nhận được trong 5 phút sau pipeline
□ Web dashboard load và hiển thị đúng data
□ Week navigation hoạt động (chọn tuần trước, data đổi)
□ Alert banner hiện khi có HIGH alerts, ẩn khi không có
□ Slide-over panel mở khi click currency
□ Data Audit — COT tab hiển thị đúng data từ cot-latest.json
□ Model Diagnostics — accuracy chart render đúng
□ Rollback test: manually giảm accuracy → verify rollback trigger
□ FEATURE_VERSION_MISMATCH test: thay đổi feature_metadata.json → verify fallback
□ Mobile: dashboard glanceable trên 375px screen
□ Keyboard shortcuts (1, 2, ←, →, Esc) hoạt động
```

---

## 13. Dependency Map

### 13.1 Backend Dependencies

```
Python 3.11
├── requests           2.31+   — HTTP client cho tất cả APIs
├── pandas             2.1+    — Data manipulation
├── numpy              1.26+   — Numerical operations
├── scikit-learn       1.4+    — RandomForest, calibration, metrics
├── joblib             1.3+    — Model serialization
├── jsonschema         4.21+   — Output validation
├── python-dateutil    2.8+    — Date arithmetic cho lag rules
└── (stdlib only)
    ├── json, os, logging, datetime, pathlib
    └── typing, dataclasses
```

### 13.2 Frontend Dependencies

```
Next.js 15          — Framework
TypeScript 5+       — Language
Tailwind CSS 4      — Styling

# Data visualization
recharts            — Charts (accuracy trend, feature importance)
lightweight-charts  — Sparklines (nếu cần high performance)

# Data handling
@tanstack/table     — DataTable (sort, filter, virtual scroll)
zustand             — State management

# UI primitives
lucide-react        — Icons
clsx                — Conditional classNames

# Dev tools
jest + @testing-library/react   — Unit tests
playwright                       — E2E tests (optional, Phase 5+)
```

### 13.3 External Service Dependencies

```
CFTC Socrata API          — TIER 1, no auth required
FRED API                  — TIER 1, free API key
ECB Data Portal           — TIER 2, no auth required
MQL5 Economic Calendar    — TIER 2, free
GitHub Actions            — Infrastructure
GitHub Pages / Vercel     — Hosting
Telegram Bot API          — Notification
```

---

## 14. Open Questions & Decisions

| # | Question | Recommended Decision | Owner | By When |
|---|---|---|---|---|
| 1 | GitHub Pages vs Vercel cho hosting? | GitHub Pages đơn giản hơn, same repo. Vercel nếu cần preview deploys | Developer | Phase F1 |
| 2 | `recharts` vs `lightweight-charts` cho sparklines? | `recharts` đủ dùng, consistent với other charts | Developer | Phase F2 |
| 3 | `model.pkl` lưu trong repo hay Git LFS? | Direct commit nếu <5MB. Git LFS nếu model grow | Developer | Phase 3 |
| 4 | Historical data retention: giữ bao nhiêu tuần? | 2 năm (104 tuần) bias history, 12 entries model-metrics | Developer | Phase 4 |
| 5 | Telegram vs email notification? | Telegram — nhận ngay trên mobile, setup dễ hơn | Developer | Phase 1 |
| 6 | Frontend static export hay SSR? | Static export (`next export`) — không cần server | Developer | Phase F1 |

---

## 15. Changelog

| Version | Ngày | Thay đổi |
|---|---|---|
| v1.0 | 2026-03-19 | Initial system design — tổng hợp từ RPD v2.1 + UI/UX v1.0 |

---

*Tài liệu này là companion cho RPD v2.1 và UI/UX Design v1.0. Cập nhật sau mỗi phase review hoặc khi có architectural decision thay đổi.*
