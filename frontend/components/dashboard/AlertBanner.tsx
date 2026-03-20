"use client";

import { useState } from "react";
import { StatusDot } from "@/components/shared/StatusDot";
import { Badge } from "@/components/shared/Badge";
import type { Alert } from "@/lib/types";

// ─── Alert type labels ────────────────────────────────────────────────────────

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

// ─── Props ────────────────────────────────────────────────────────────────────

interface AlertBannerProps {
  alerts: Alert[]; // HIGH severity only
}

// ─── Component ────────────────────────────────────────────────────────────────

export function AlertBanner({ alerts }: AlertBannerProps) {
  const [dismissed, setDismissed] = useState(false);

  if (alerts.length === 0 || dismissed) return null;

  return (
    <div
      role="alert"
      aria-live="assertive"
      style={{
        background: "var(--severity-high-bg)",
        border: "1px solid var(--severity-high)",
        borderLeft: "4px solid var(--severity-high)",
        borderRadius: "var(--card-radius-sm)",
        padding: "14px 16px",
        marginBottom: 24,
        animation: "fadeIn 0.2s ease",
      }}
    >
      {/* Header row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            fontSize: "var(--text-xs)",
            fontWeight: 700,
            color: "var(--severity-high)",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
          }}
        >
          <StatusDot status="error" pulse />
          {alerts.length} High Priority Alert{alerts.length > 1 ? "s" : ""}
        </div>

        <button
          onClick={() => setDismissed(true)}
          aria-label="Dismiss alerts"
          style={{
            background: "none",
            border: "none",
            color: "var(--text-muted)",
            cursor: "pointer",
            fontSize: "var(--text-sm)",
            padding: "2px 6px",
            borderRadius: 4,
            lineHeight: 1,
          }}
        >
          ✕
        </button>
      </div>

      {/* Alert rows */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {alerts.map((alert, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
              fontSize: "var(--text-sm)",
              color: "var(--text-primary)",
            }}
          >
            {/* Type chip */}
            <Badge
              variant="severity"
              value={alert.severity}
              size="sm"
            />

            {/* Alert type label */}
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-xs)",
                color: "var(--severity-high)",
                background: "rgba(239,68,68,0.12)",
                padding: "2px 6px",
                borderRadius: 4,
                whiteSpace: "nowrap",
              }}
            >
              {ALERT_TYPE_LABELS[alert.type] ?? alert.type}
            </span>

            {/* Currency tag */}
            {alert.currency && (
              <span
                style={{
                  fontWeight: 700,
                  color: "var(--text-primary)",
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-xs)",
                  background: "rgba(255,255,255,0.06)",
                  padding: "2px 6px",
                  borderRadius: 4,
                  whiteSpace: "nowrap",
                }}
              >
                {alert.currency}
              </span>
            )}

            {/* Message */}
            <span style={{ color: "var(--text-secondary)", flex: 1 }}>
              {alert.message}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
