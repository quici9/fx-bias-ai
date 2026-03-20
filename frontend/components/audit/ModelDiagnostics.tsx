"use client";

import { useEffect } from "react";
import { Badge } from "@/components/shared/Badge";
import { AccuracyLineChart, type AccuracyDataPoint } from "@/components/shared/AccuracyLineChart";
import { useAuditStore } from "@/lib/store/auditStore";

// ─── Mock model metrics history (used as fallback when no real data loaded) ──

const MOCK_HISTORY: AccuracyDataPoint[] = [
  { week: "W10", accuracy: 0.71 },
  { week: "W11", accuracy: 0.68 },
  { week: "W12", accuracy: 0.73 },
  { week: "W13", accuracy: 0.69 },
  { week: "W14", accuracy: 0.74 },
  { week: "W15", accuracy: 0.72 },
  { week: "W16", accuracy: 0.70 },
  { week: "W17", accuracy: 0.76 },
  { week: "W18", accuracy: 0.74 },
  { week: "W19", accuracy: 0.71 },
  { week: "W20", accuracy: 0.75 },
  { week: "W21", accuracy: 0.73 },
];

const MOCK_METRICS = {
  version: "v1.2.0",
  featureVersion: "1.0",
  lastRetrain: "2026-W12",
  nextRetrain: "2026-W16",
  backupVersion: "v1.1.3",
  status: "ACTIVE" as const,
  rolling4w: 0.736,
  rolling12w: 0.724,
  byCurrency: {
    USD: 0.81, EUR: 0.74, GBP: 0.69, JPY: 0.77,
    AUD: 0.68, CAD: 0.71, CHF: 0.73, NZD: 0.66,
  },
  baselines: {
    random: 0.333,
    always_bull: 0.412,
    cot_rule_only: 0.644,
    vs_cot_rule_delta: 0.092,
  },
  retrainHistory: [
    { week: "2026-W12", action: "INFERENCE_ONLY",   pre: 0.724, post: null,  deployed: false, status: "SKIPPED" },
    { week: "2026-W08", action: "RETRAIN_DEPLOYED",  pre: 0.698, post: 0.724, deployed: true,  status: "DEPLOYED" },
    { week: "2026-W04", action: "RETRAIN_REJECTED",  pre: 0.701, post: 0.695, deployed: false, status: "REJECTED" },
    { week: "2025-W52", action: "RETRAIN_DEPLOYED",  pre: 0.688, post: 0.701, deployed: true,  status: "DEPLOYED" },
  ],
};

const TARGET_ACC = 0.72;
const MIN_ACC = 0.65;

// ─── Currency accuracy bar ────────────────────────────────────────────────────

interface CurrencyAccuracyBarProps {
  currency: string;
  accuracy: number;
}

function CurrencyAccuracyBar({ currency, accuracy }: CurrencyAccuracyBarProps) {
  const meetsTarget = accuracy >= TARGET_ACC;
  const color = accuracy >= TARGET_ACC
    ? "var(--accent-bull)"
    : accuracy >= MIN_ACC
    ? "var(--severity-medium)"
    : "var(--severity-high)";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <span style={{ width: 36, fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: "var(--text-sm)", color: "var(--text-primary)" }}>
        {currency}
      </span>
      <div style={{ flex: 1, height: 10, background: "var(--bg-card-hover)", borderRadius: 4, overflow: "hidden" }}>
        <div style={{
          height: "100%",
          width: `${(accuracy / 1) * 100}%`,
          background: color,
          borderRadius: 4,
          transition: "width var(--transition-slow)",
        }} />
      </div>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", color, fontWeight: 600, width: 48, textAlign: "right" }}>
        {(accuracy * 100).toFixed(1)}%
      </span>
      <span style={{ fontSize: "var(--text-base)" }}>{meetsTarget ? "✅" : accuracy >= MIN_ACC ? "⚠️" : "❌"}</span>
    </div>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ModelDiagnostics() {
  const { modelMetrics, modelMetricsHistory, modelMetricsLoadState, modelMetricsError } = useAuditStore();

  // Build chart data from history or fallback mock
  const chartData: AccuracyDataPoint[] =
    modelMetricsHistory.length > 0
      ? modelMetricsHistory
          .slice()
          .reverse()
          .map((m) => ({
            week: m.week.replace(/^\d{4}-/, ""),
            accuracy: m.accuracy.rolling_4w,
          }))
      : MOCK_HISTORY;

  const metrics = modelMetrics ?? MOCK_METRICS;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {modelMetricsLoadState === "error" && (
        <div style={{
          background: "var(--severity-high)1A",
          border: "1px solid var(--severity-high)",
          borderRadius: "var(--card-radius-sm)",
          padding: "10px 14px",
          fontSize: "var(--text-sm)",
          color: "var(--severity-high)",
        }}>
          {modelMetricsError ?? "Model metrics unavailable — showing mock data"}
        </div>
      )}

      {/* Model Summary card */}
      <div className="card" style={{ padding: 20 }}>
        <h3 style={{ margin: "0 0 16px", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Model Summary
        </h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 16 }}>
          {[
            { label: "Model Version", value: MOCK_METRICS.version },
            { label: "Feature Version", value: MOCK_METRICS.featureVersion },
            { label: "Last Retrain", value: MOCK_METRICS.lastRetrain },
            { label: "Next Retrain", value: MOCK_METRICS.nextRetrain },
            { label: "Backup Version", value: MOCK_METRICS.backupVersion },
          ].map((item) => (
            <div key={item.label}>
              <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{item.label}</p>
              <p style={{ margin: "4px 0 0", fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", color: "var(--text-primary)", fontWeight: 600 }}>{item.value}</p>
            </div>
          ))}
          <div>
            <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Status</p>
            <div style={{ marginTop: 4 }}>
              <Badge variant="bull" size="sm">ACTIVE</Badge>
            </div>
          </div>
        </div>

        <div style={{ marginTop: 16, display: "flex", gap: 24, flexWrap: "wrap" }}>
          <div>
            <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>Rolling 4W</p>
            <p style={{ margin: "2px 0 0", fontFamily: "var(--font-mono)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--accent-bull)" }}>
              {(MOCK_METRICS.rolling4w * 100).toFixed(1)}%
            </p>
          </div>
          <div>
            <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>Rolling 12W</p>
            <p style={{ margin: "2px 0 0", fontFamily: "var(--font-mono)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--brand)" }}>
              {(MOCK_METRICS.rolling12w * 100).toFixed(1)}%
            </p>
          </div>
          <div>
            <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>vs COT-Rule Baseline</p>
            <p style={{ margin: "2px 0 0", fontFamily: "var(--font-mono)", fontSize: "var(--text-xl)", fontWeight: 700, color: "var(--accent-bull)" }}>
              +{(MOCK_METRICS.baselines.vs_cot_rule_delta * 100).toFixed(1)}%
            </p>
          </div>
        </div>
      </div>

      {/* Accuracy Trend Chart */}
      <div className="card" style={{ padding: 20 }}>
        <h3 style={{ margin: "0 0 16px", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Accuracy Trend — 12 Weeks
        </h3>
        <AccuracyLineChart
          data={chartData}
          targetAccuracy={TARGET_ACC}
          minAccuracy={MIN_ACC}
          height={200}
        />
      </div>

      {/* Accuracy by Currency */}
      <div className="card" style={{ padding: 20 }}>
        <h3 style={{ margin: "0 0 16px", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Accuracy by Currency
        </h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {Object.entries(MOCK_METRICS.byCurrency).map(([ccy, acc]) => (
            <CurrencyAccuracyBar key={ccy} currency={ccy} accuracy={acc} />
          ))}
        </div>
      </div>

      {/* Baseline Comparison */}
      <div className="card" style={{ padding: 20 }}>
        <h3 style={{ margin: "0 0 14px", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Baseline Comparison
        </h3>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "var(--bg-card-hover)" }}>
                {["Model / Baseline", "Accuracy", "vs RF"].map((h) => (
                  <th key={h} style={{ padding: "10px 12px", textAlign: "left", fontSize: "var(--text-xs)", fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr style={{ background: "var(--brand)1A" }}>
                <td style={{ padding: "10px 12px", fontWeight: 700, color: "var(--brand)", borderBottom: "1px solid var(--border-muted)" }}>Random Forest (current)</td>
                <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--brand)", borderBottom: "1px solid var(--border-muted)" }}>{(MOCK_METRICS.rolling4w * 100).toFixed(1)}%</td>
                <td style={{ padding: "10px 12px", color: "var(--text-muted)", fontSize: "var(--text-xs)", borderBottom: "1px solid var(--border-muted)" }}>—</td>
              </tr>
              {[
                { label: "Random (baseline)", acc: MOCK_METRICS.baselines.random },
                { label: "Always BULL", acc: MOCK_METRICS.baselines.always_bull },
                { label: "COT Rule Only", acc: MOCK_METRICS.baselines.cot_rule_only },
              ].map(({ label, acc }) => {
                const delta = MOCK_METRICS.rolling4w - acc;
                return (
                  <tr key={label} style={{ background: "var(--bg-card)" }}>
                    <td style={{ padding: "10px 12px", color: "var(--text-secondary)", fontSize: "var(--text-sm)", borderBottom: "1px solid var(--border-muted)" }}>{label}</td>
                    <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", color: "var(--text-secondary)", borderBottom: "1px solid var(--border-muted)" }}>{(acc * 100).toFixed(1)}%</td>
                    <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", color: delta > 0 ? "var(--accent-bull)" : "var(--accent-bear)", fontWeight: 600, borderBottom: "1px solid var(--border-muted)" }}>
                      {delta > 0 ? "+" : ""}{(delta * 100).toFixed(1)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Retrain History */}
      <div className="card" style={{ padding: 20 }}>
        <h3 style={{ margin: "0 0 14px", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Retrain History
        </h3>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapsibse: "collapse" } as React.CSSProperties}>
            <thead>
              <tr style={{ background: "var(--bg-card-hover)" }}>
                {["Week", "Action", "Pre Acc.", "Post Acc.", "Status"].map((h) => (
                  <th key={h} style={{ padding: "10px 12px", textAlign: "left", fontSize: "var(--text-xs)", fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {MOCK_METRICS.retrainHistory.map((row) => (
                <tr key={row.week} style={{ background: "var(--bg-card)" }}>
                  <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", color: "var(--text-secondary)", borderBottom: "1px solid var(--border-muted)" }}>{row.week}</td>
                  <td style={{ padding: "10px 12px", fontSize: "var(--text-xs)", color: "var(--text-muted)", borderBottom: "1px solid var(--border-muted)" }}>{row.action}</td>
                  <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", color: "var(--text-secondary)", borderBottom: "1px solid var(--border-muted)" }}>
                    {(row.pre * 100).toFixed(1)}%
                  </td>
                  <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)", borderBottom: "1px solid var(--border-muted)" }}>
                    {row.post !== null ? (
                      <span style={{ color: (row.post ?? 0) > row.pre ? "var(--accent-bull)" : "var(--accent-bear)", fontWeight: 600 }}>
                        {(row.post! * 100).toFixed(1)}%
                        <span style={{ marginLeft: 4, fontSize: "var(--text-xs)" }}>
                          ({row.post! > row.pre ? "+" : ""}{((row.post! - row.pre) * 100).toFixed(1)}%)
                        </span>
                      </span>
                    ) : (
                      <span style={{ color: "var(--text-muted)" }}>—</span>
                    )}
                  </td>
                  <td style={{ padding: "10px 12px", borderBottom: "1px solid var(--border-muted)" }}>
                    <Badge
                      variant={row.status === "DEPLOYED" ? "bull" : row.status === "REJECTED" ? "bear" : "neutral"}
                      size="sm"
                    >
                      {row.status}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
