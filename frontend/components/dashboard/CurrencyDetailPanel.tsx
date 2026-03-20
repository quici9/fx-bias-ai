"use client";

import { SlidePanel } from "@/components/shared/SlidePanel";
import { Badge } from "@/components/shared/Badge";
import { Sparkline } from "@/components/shared/Sparkline";
import type { CurrencyPrediction, Alert } from "@/lib/types";

// ─── Helpers ──────────────────────────────────────────────────────────────────

const ALERT_TYPE_LABELS: Record<string, string> = {
  EXTREME_POSITIONING: "Extreme Positioning",
  FLIP_DETECTED: "Flip Detected",
  MODEL_DRIFT: "Model Drift",
  MODEL_ROLLBACK: "Model Rollback",
  MISSING_DATA: "Missing Data",
  RISK_OFF_REGIME: "Risk-Off Regime",
  DATA_SOURCE_STALE: "Data Stale",
  FEATURE_VERSION_MISMATCH: "Version Mismatch",
  LOW_CONFIDENCE: "Low Confidence",
  MACRO_COT_CONFLICT: "Macro/COT Conflict",
  MOMENTUM_DECEL: "Momentum Decel",
  OI_DIVERGENCE: "OI Divergence",
  CALENDAR_SOURCE_FALLBACK: "Calendar Fallback",
};

function ProbabilityBar({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: "var(--text-xs)",
        }}
      >
        <span style={{ color: "var(--text-muted)" }}>{label}</span>
        <span style={{ color, fontFamily: "var(--font-mono)", fontWeight: 700 }}>
          {(value * 100).toFixed(0)}%
        </span>
      </div>
      <div
        style={{
          height: 8,
          background: "rgba(255,255,255,0.06)",
          borderRadius: 4,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${(value * 100).toFixed(1)}%`,
            height: "100%",
            background: color,
            borderRadius: 4,
            transition: "width 0.4s ease",
          }}
        />
      </div>
    </div>
  );
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface CurrencyDetailPanelProps {
  prediction: CurrencyPrediction | null;
  allAlerts: Alert[];
  cotTrend?: number[]; // 12-week sparkline from cotReport
  onClose: () => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function CurrencyDetailPanel({
  prediction,
  allAlerts,
  cotTrend,
  onClose,
}: CurrencyDetailPanelProps) {
  const isOpen = prediction !== null;

  // Filter alerts relevant to this currency
  const currencyAlerts = allAlerts.filter(
    (a) => !a.currency || a.currency === prediction?.currency
  );

  return (
    <SlidePanel
      open={prediction !== null}
      onClose={onClose}
      title={prediction ? `${prediction.currency} — Detail` : ""}
    >
      {prediction && (
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {/* Header */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-2xl)",
                  fontWeight: 700,
                  color: "var(--text-primary)",
                }}
              >
                {prediction.currency}
              </span>
              <Badge variant="bias" value={prediction.bias} />
              <Badge variant="confidence" value={prediction.confidence} size="sm" />
            </div>
            <span
              style={{
                fontSize: "var(--text-xs)",
                color: "var(--text-muted)",
                fontFamily: "var(--font-mono)",
              }}
            >
              Rank #{prediction.rank}
            </span>
          </div>

          {/* Probability bars */}
          <div
            style={{
              background: "var(--bg-secondary)",
              borderRadius: "var(--card-radius-sm)",
              padding: 16,
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            <span
              style={{
                fontSize: "var(--text-xs)",
                fontWeight: 700,
                color: "var(--text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
              }}
            >
              Probability Distribution
            </span>
            <ProbabilityBar
              label="BULL"
              value={prediction.probability.bull}
              color="var(--accent-bull)"
            />
            <ProbabilityBar
              label="NEUTRAL"
              value={prediction.probability.neutral}
              color="var(--accent-neutral)"
            />
            <ProbabilityBar
              label="BEAR"
              value={prediction.probability.bear}
              color="var(--accent-bear)"
            />
          </div>

          {/* Key drivers */}
          <div>
            <span
              style={{
                fontSize: "var(--text-xs)",
                fontWeight: 700,
                color: "var(--text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                display: "block",
                marginBottom: 10,
              }}
            >
              Key Drivers
            </span>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {prediction.key_drivers.map((driver, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "8px 12px",
                    background: "rgba(255,255,255,0.03)",
                    borderRadius: 6,
                    border: "1px solid var(--border)",
                  }}
                >
                  <span
                    style={{
                      width: 18,
                      height: 18,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      background: "rgba(255,255,255,0.07)",
                      borderRadius: "50%",
                      fontSize: "var(--text-xs)",
                      color: "var(--text-muted)",
                      fontFamily: "var(--font-mono)",
                      flexShrink: 0,
                    }}
                  >
                    {i + 1}
                  </span>
                  <span style={{ fontSize: "var(--text-sm)", color: "var(--text-primary)" }}>
                    {driver}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* COT Trend sparkline */}
          {cotTrend && cotTrend.length > 0 && (
            <div>
              <span
                style={{
                  fontSize: "var(--text-xs)",
                  fontWeight: 700,
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  display: "block",
                  marginBottom: 10,
                }}
              >
                COT Index — 12w Trend
              </span>
              <div
                style={{
                  background: "var(--bg-secondary)",
                  borderRadius: "var(--card-radius-sm)",
                  padding: 12,
                }}
              >
                <Sparkline data={cotTrend} height={60} />
              </div>
            </div>
          )}

          {/* 12w Accuracy */}
          {prediction.historical_accuracy_12w != null && (
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "12px 16px",
                background: "var(--bg-secondary)",
                borderRadius: "var(--card-radius-sm)",
                border: "1px solid var(--border)",
              }}
            >
              <span style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>
                12-week historical accuracy
              </span>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontWeight: 700,
                  fontSize: "var(--text-base)",
                  color:
                    prediction.historical_accuracy_12w >= 0.7
                      ? "var(--accent-bull)"
                      : prediction.historical_accuracy_12w >= 0.6
                        ? "var(--severity-medium)"
                        : "var(--accent-bear)",
                }}
              >
                {(prediction.historical_accuracy_12w * 100).toFixed(0)}%
              </span>
            </div>
          )}

          {/* Active alerts */}
          {currencyAlerts.length > 0 && (
            <div>
              <span
                style={{
                  fontSize: "var(--text-xs)",
                  fontWeight: 700,
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  display: "block",
                  marginBottom: 10,
                }}
              >
                Active Alerts ({currencyAlerts.length})
              </span>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {currencyAlerts.map((alert, i) => (
                  <div
                    key={i}
                    style={{
                      padding: "10px 12px",
                      background:
                        alert.severity === "HIGH"
                          ? "var(--severity-high-bg)"
                          : alert.severity === "MEDIUM"
                            ? "var(--severity-medium-bg)"
                            : "var(--severity-low-bg)",
                      border: `1px solid ${
                        alert.severity === "HIGH"
                          ? "rgba(239,68,68,0.3)"
                          : alert.severity === "MEDIUM"
                            ? "rgba(245,158,11,0.3)"
                            : "rgba(107,114,128,0.3)"
                      }`,
                      borderRadius: 6,
                      display: "flex",
                      flexDirection: "column",
                      gap: 4,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <Badge variant="severity" value={alert.severity} size="sm" />
                      <span
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "var(--text-xs)",
                          color: "var(--text-secondary)",
                          fontWeight: 600,
                        }}
                      >
                        {ALERT_TYPE_LABELS[alert.type] ?? alert.type}
                      </span>
                    </div>
                    <span style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>
                      {alert.message}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* View in Data Audit link */}
          <div style={{ paddingTop: 8, borderTop: "1px solid var(--border)" }}>
            <a
              href="/audit?tab=features"
              style={{
                fontSize: "var(--text-sm)",
                color: "var(--accent-bull)",
                textDecoration: "none",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "8px 0",
              }}
            >
              View in Data Audit →
            </a>
          </div>
        </div>
      )}
    </SlidePanel>
  );
}
