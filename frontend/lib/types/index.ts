// TypeScript interfaces — mirrors JSON schema contracts from System Design Section 4.
// Sync with backend schemas when any field changes (bump featureVersion).

// ─── Alert Types ─────────────────────────────────────────────────────────────

export type AlertType =
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

export type Severity = "HIGH" | "MEDIUM" | "LOW";
export type Confidence = "HIGH" | "MEDIUM" | "LOW";
export type Bias = "BULL" | "BEAR" | "NEUTRAL";
export type Currency = "USD" | "EUR" | "GBP" | "JPY" | "AUD" | "CAD" | "CHF" | "NZD";
export type DataSourceStatus = "OK" | "STALE" | "FAILED" | "FALLBACK";
export type VixRegime = "LOW" | "NORMAL" | "ELEVATED" | "EXTREME";
export type TrendDirection = "RISING" | "FALLING" | "STABLE";
export type YieldDirection = "WIDENING" | "NARROWING" | "STABLE";
export type CommodityTrend = "RISING" | "FALLING" | "FLAT";

export interface Alert {
  type: AlertType;
  currency?: string;
  message: string;
  severity: Severity;
  context?: Record<string, unknown>;
}

// ─── Bias Report (bias-latest.json) ──────────────────────────────────────────

export interface CurrencyPrediction {
  currency: Currency;
  bias: Bias;
  probability: {
    bull: number;
    neutral: number;
    bear: number;
  };
  confidence: Confidence;
  rank: number; // 1–8
  key_drivers: string[];
  alerts: AlertType[];
  historical_accuracy_12w?: number;
}

export interface PairRecommendation {
  pair: string; // "USD/JPY"
  spread: number;
  base_currency: string;
  quote_currency: string;
  confidence: Confidence;
}

export interface BiasReport {
  meta: {
    weekLabel: string;
    generatedAt: string;
    modelVersion: string;
    featureVersion: string;
    overallConfidence: Confidence;
    dataSourceStatus: {
      cot: DataSourceStatus;
      macro: DataSourceStatus;
      cross_asset: DataSourceStatus;
      calendar: DataSourceStatus;
    };
    pipelineRuntime: number;
  };
  predictions: CurrencyPrediction[];
  pair_recommendations: {
    strong_long: PairRecommendation[];
    strong_short: PairRecommendation[];
    avoid: PairRecommendation[];
  };
  weekly_alerts: Alert[];
}

// ─── COT Report (cot-latest.json) ────────────────────────────────────────────

export interface CotLegacyRecord {
  currency: string;
  noncomm_long: number;
  noncomm_short: number;
  open_interest: number;
  net: number;
  net_delta_1w: number;
  cot_index_52w: number;
  extreme_flag: boolean;
  flip_flag: boolean;
}

export interface CotTffRecord {
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

export interface CotReport {
  reportDate: string;
  publishDate: string;
  source: "CFTC_LEGACY_TFF";
  legacy: CotLegacyRecord[];
  tff: CotTffRecord[];
  cot_indices: {
    [currency: string]: {
      index: number;
      trend_12w: number[];
    };
  };
}

// ─── Macro Report (macro-latest.json) ────────────────────────────────────────

export interface MacroSeriesRecord {
  currency: string;
  value: number;
  diff_vs_usd: number;
  trend_3m: TrendDirection;
  last_update: string;
  publication_lag_applied: number;
  freshness_days: number;
  is_stale: boolean;
}

export interface YieldRecord {
  country: string;
  yield: number;
  spread_vs_us: number;
  delta_1w: number;
  direction: YieldDirection;
  last_update: string;
}

export interface MacroReport {
  fetchDate: string;
  policy_rates: MacroSeriesRecord[];
  cpi_yoy: MacroSeriesRecord[];
  yields_10y: YieldRecord[];
  vix: {
    value: number;
    regime: VixRegime;
    delta_1w: number;
  };
}

// ─── Cross-Asset Report (cross-asset-latest.json) ────────────────────────────

export interface CommodityCotRecord {
  cot_index: number;
  trend_12w: number[];
  trend_direction: CommodityTrend;
  fx_impact: string;
}

export interface YieldDifferential {
  pair: string;
  spread: number;
  delta_4w: number;
  direction: YieldDirection;
}

export interface CrossAssetReport {
  fetchDate: string;
  commodities: {
    gold: CommodityCotRecord;
    oil: CommodityCotRecord;
    sp500: CommodityCotRecord;
  };
  yield_differentials: YieldDifferential[];
}

// ─── Model Metrics (model-metrics/YYYY-WNN.json) ──────────────────────────────

export type ModelAction =
  | "INFERENCE_ONLY"
  | "RETRAIN_DEPLOYED"
  | "RETRAIN_REJECTED"
  | "ROLLBACK";

export interface ModelMetrics {
  week: string;
  modelVersion: string;
  featureVersion: string;
  action: ModelAction;
  accuracy: {
    current_week: number;
    rolling_4w: number;
    rolling_12w: number;
    by_currency: Record<string, number>;
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
  retrain?: {
    pre_accuracy: number;
    post_accuracy: number;
    deployed: boolean;
    reason_rejected?: string;
  };
  rollback?: {
    from_version: string;
    to_version: string;
    trigger_accuracy: number;
  };
}

// ─── Feature Metadata (feature_metadata.json) ────────────────────────────────

export type FeatureSource =
  | "CFTC_LEGACY"
  | "CFTC_TFF"
  | "FRED"
  | "ECB"
  | "CALENDAR"
  | "DERIVED";

export interface FeatureDefinition {
  id: number;
  name: string;
  description: string;
  formula: string;
  optional: boolean;
  source: FeatureSource;
  publication_lag?: number;
}

export interface FeatureGroup {
  name: string;
  features: FeatureDefinition[];
}

export interface FeatureMetadata {
  version: string;
  total_features: number;
  groups: FeatureGroup[];
}
