"use client";

import { useState } from "react";
import { Badge } from "@/components/shared/Badge";
import { FeatureImportanceChart } from "@/components/shared/FeatureImportanceChart";
import { useBiasStore, selectActiveReport } from "@/lib/store/biasStore";

// ─── Types ────────────────────────────────────────────────────────────────────

type Currency = "USD" | "EUR" | "GBP" | "JPY" | "AUD" | "CAD" | "CHF" | "NZD";

// ─── Mock feature data per currency ──────────────────────────────────────────
// In real implementation this would come from fetched feature matrix

interface FeatureRow {
  id: number;
  name: string;
  group: string;
  value: number | null;
  zScore: number | null;
  flag: boolean;
  optional: boolean;
}

function generateMockFeatures(currency: Currency): FeatureRow[] {
  // Deterministic mock values based on currency index
  const seed = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"].indexOf(currency);
  const r = (base: number, range: number) => base + (seed * range * 0.17) % range - range / 2;

  return [
    // Group A — COT Legacy
    { id: 1,  name: "cot_index",              group: "A", value: Math.round(r(55, 80)),     zScore: r(0.2, 3),    flag: false, optional: false },
    { id: 2,  name: "cot_index_4w_change",    group: "A", value: r(2, 20),                  zScore: r(0.1, 2.5),  flag: false, optional: false },
    { id: 3,  name: "net_pct_change_1w",      group: "A", value: r(0.5, 8),                 zScore: r(-0.3, 2),   flag: false, optional: false },
    { id: 4,  name: "momentum_acceleration",  group: "A", value: r(-0.1, 1),                zScore: r(0.4, 3.2),  flag: Math.abs(r(0.4, 3.2)) > 2, optional: false },
    { id: 5,  name: "oi_delta_direction",     group: "A", value: Math.round(r(0, 1) > 0 ? 1 : -1), zScore: r(0, 1.5), flag: false, optional: false },
    { id: 6,  name: "oi_net_confluence",      group: "A", value: Math.round(r(0, 1) > 0 ? 1 : 0), zScore: r(0.1, 1), flag: false, optional: false },
    { id: 7,  name: "flip_flag",              group: "A", value: seed === 2 ? 1 : 0,        zScore: null,         flag: seed === 2, optional: false },
    { id: 8,  name: "extreme_flag",           group: "A", value: seed === 5 ? 1 : 0,        zScore: null,         flag: seed === 5, optional: false },
    { id: 9,  name: "usd_index_cot",          group: "A", value: Math.round(r(50, 40)),     zScore: r(-0.2, 2),   flag: false, optional: false },
    { id: 10, name: "rank_in_8",              group: "A", value: seed + 1,                  zScore: r(0, 1.5),    flag: false, optional: false },
    { id: 11, name: "spread_vs_usd",          group: "A", value: r(5000, 50000),            zScore: r(0.3, 2.8),  flag: Math.abs(r(0.3, 2.8)) > 2, optional: false },
    { id: 12, name: "weeks_since_flip",       group: "A", value: Math.round(Math.abs(r(6, 24))), zScore: r(0.1, 1.5), flag: false, optional: false },
    // Group B — COT TFF
    { id: 13, name: "lev_funds_net_index",    group: "B", value: Math.round(r(48, 70)),     zScore: r(-0.5, 2.5), flag: Math.abs(r(-0.5, 2.5)) > 2, optional: false },
    { id: 14, name: "asset_mgr_net_direction", group: "B", value: Math.round(r(0, 1) > 0 ? 1 : -1), zScore: r(0, 1), flag: false, optional: false },
    { id: 15, name: "dealer_net_contrarian",  group: "B", value: Math.round(r(0, 1) > 0 ? 1 : -1), zScore: r(0.1, 1.5), flag: false, optional: false },
    { id: 16, name: "lev_vs_assetmgr_divergence", group: "B", value: r(2000, 80000),       zScore: r(0.5, 3.5),  flag: Math.abs(r(0.5, 3.5)) > 2, optional: false },
    // Group C — Macro
    { id: 17, name: "rate_diff_vs_usd",       group: "C", value: r(-1, 5),                 zScore: r(0.2, 2.5),  flag: false, optional: false },
    { id: 18, name: "rate_diff_trend_3m",     group: "C", value: Math.round(r(0, 1) > 0 ? 1 : -1), zScore: null, flag: false, optional: false },
    { id: 19, name: "rate_hike_expectation",  group: "C", value: r(0, 1),                  zScore: r(-0.1, 1.5), flag: false, optional: false },
    { id: 20, name: "cpi_diff_vs_usd",        group: "C", value: r(-1, 3),                 zScore: r(0.3, 2),    flag: false, optional: false },
    { id: 21, name: "cpi_trend",              group: "C", value: Math.round(r(0, 1) > 0 ? 1 : -1), zScore: null, flag: false, optional: false },
    { id: 22, name: "pmi_composite_diff",     group: "C", value: null,                     zScore: null,         flag: false, optional: true },
    { id: 23, name: "yield_10y_diff",         group: "C", value: r(-1, 4),                 zScore: r(0.1, 2.2),  flag: false, optional: false },
    { id: 24, name: "vix_regime",             group: "C", value: 1,                        zScore: r(-0.2, 1.5), flag: false, optional: false },
    // Group D — Cross-Asset / Calendar
    { id: 25, name: "gold_cot_index",         group: "D", value: 71,                       zScore: r(0.8, 2.5),  flag: false, optional: false },
    { id: 26, name: "oil_cot_direction",      group: "D", value: -1,                       zScore: r(-0.5, 2),   flag: false, optional: false },
    { id: 27, name: "month",                  group: "D", value: 3,                        zScore: null,         flag: false, optional: false },
    { id: 28, name: "quarter",                group: "D", value: 1,                        zScore: null,         flag: false, optional: false },
  ];
}

const GROUP_LABELS: Record<string, string> = {
  A: "Group A — COT Legacy Positioning",
  B: "Group B — COT TFF Disaggregated",
  C: "Group C — Macro & Rates",
  D: "Group D — Cross-Asset & Calendar",
};

const MOCK_IMPORTANCES = [
  { name: "cot_index", importance: 0.142 },
  { name: "lev_funds_net_index", importance: 0.118 },
  { name: "spread_vs_usd", importance: 0.097 },
  { name: "rate_diff_vs_usd", importance: 0.089 },
  { name: "momentum_acceleration", importance: 0.071 },
  { name: "cot_index_4w_change", importance: 0.065 },
  { name: "lev_vs_assetmgr_divergence", importance: 0.060 },
  { name: "yield_10y_diff", importance: 0.052 },
  { name: "weeks_since_flip", importance: 0.048 },
  { name: "gold_cot_index", importance: 0.043 },
];

const CURRENCIES: Currency[] = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"];

// ─── Component ────────────────────────────────────────────────────────────────

export function FeatureInspector() {
  const [selectedCurrency, setSelectedCurrency] = useState<Currency>("USD");
  const activeReport = useBiasStore(selectActiveReport);
  const features = generateMockFeatures(selectedCurrency);
  const groups = ["A", "B", "C", "D"];

  // Get live rank from bias report if available
  const livePrediction = activeReport?.predictions.find((p) => p.currency === selectedCurrency);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      {/* Header — currency selector */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div>
          <label htmlFor="feature-currency-select" style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", marginRight: 8 }}>
            Currency
          </label>
          <select
            id="feature-currency-select"
            value={selectedCurrency}
            onChange={(e) => setSelectedCurrency(e.target.value as Currency)}
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: "var(--card-radius-sm)",
              color: "var(--text-primary)",
              fontSize: "var(--text-sm)",
              padding: "6px 10px",
              cursor: "pointer",
            }}
          >
            {CURRENCIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        {livePrediction && (
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>Live bias:</span>
            <Badge variant="bias" value={livePrediction.bias} size="sm" />
            <Badge variant="confidence" value={livePrediction.confidence} size="sm" />
            <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>Rank #{livePrediction.rank}</span>
          </div>
        )}

        <div style={{ marginLeft: "auto" }}>
          <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
            28 features · {features.filter((f) => f.value === null).length} missing
          </span>
        </div>
      </div>

      {/* Feature table grouped by Group A/B/C/D */}
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        {groups.map((group) => {
          const groupFeatures = features.filter((f) => f.group === group);
          return (
            <div key={group}>
              <h3 style={{
                margin: "0 0 10px",
                fontSize: "var(--text-sm)",
                fontWeight: 600,
                color: "var(--brand)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                paddingBottom: 6,
                borderBottom: "1px solid var(--border)",
              }}>
                {GROUP_LABELS[group]}
              </h3>
              <div style={{ overflowX: "auto", borderRadius: "var(--card-radius-sm)", border: "1px solid var(--border)" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ background: "var(--bg-card)" }}>
                      {["#", "Feature", "Value", "Z-Score", "Flag"].map((h) => (
                        <th key={h} style={{
                          padding: "10px 12px",
                          textAlign: "left",
                          fontSize: "var(--text-xs)",
                          fontWeight: 600,
                          letterSpacing: "0.05em",
                          textTransform: "uppercase",
                          color: "var(--text-muted)",
                          borderBottom: "1px solid var(--border)",
                        }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {groupFeatures.map((feat) => {
                      const isHighZ = feat.zScore !== null && Math.abs(feat.zScore) > 2;
                      return (
                        <tr
                          key={feat.id}
                          style={{
                            background: isHighZ ? "var(--severity-medium)11" : "var(--bg-card)",
                          }}
                        >
                          <td style={{ padding: "9px 12px", fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", color: "var(--text-muted)", borderBottom: "1px solid var(--border-muted)", width: 36 }}>
                            {feat.id}
                          </td>
                          <td style={{ padding: "9px 12px", fontSize: "var(--text-sm)", color: "var(--text-primary)", borderBottom: "1px solid var(--border-muted)", fontFamily: "var(--font-mono)" }}>
                            {feat.name}
                            {feat.optional && (
                              <span style={{ marginLeft: 6, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>opt</span>
                            )}
                          </td>
                          <td style={{ padding: "9px 12px", fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", color: "var(--text-secondary)", borderBottom: "1px solid var(--border-muted)" }}>
                            {feat.value === null ? (
                              <Badge variant="severity" value="MEDIUM" size="sm">MISSING</Badge>
                            ) : (
                              typeof feat.value === "number"
                                ? (Number.isInteger(feat.value) ? feat.value : feat.value.toFixed(4))
                                : feat.value
                            )}
                          </td>
                          <td style={{ padding: "9px 12px", fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", borderBottom: "1px solid var(--border-muted)" }}>
                            {feat.zScore === null ? (
                              <span style={{ color: "var(--text-muted)" }}>—</span>
                            ) : (
                              <span style={{ color: isHighZ ? "var(--severity-medium)" : "var(--text-secondary)", fontWeight: isHighZ ? 700 : 400 }}>
                                {feat.zScore > 0 ? "+" : ""}{feat.zScore.toFixed(2)}
                                {isHighZ && " ⚠"}
                              </span>
                            )}
                          </td>
                          <td style={{ padding: "9px 12px", borderBottom: "1px solid var(--border-muted)" }}>
                            {feat.flag ? (
                              <Badge variant="severity" value="HIGH" size="sm">FLAGGED</Badge>
                            ) : (
                              <span style={{ color: "var(--text-muted)", fontSize: "var(--text-xs)" }}>—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })}
      </div>

      {/* Feature Importance Chart */}
      <div className="card" style={{ padding: 20 }}>
        <h3 style={{ margin: "0 0 16px", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Feature Importance — Top 10
        </h3>
        <FeatureImportanceChart data={MOCK_IMPORTANCES} height={220} />
      </div>
    </div>
  );
}
