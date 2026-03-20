"use client";

import type { VixRegime } from "@/lib/types";

// ─── Types ────────────────────────────────────────────────────────────────────

interface VixGaugeProps {
  value: number;
  regime: VixRegime;
  delta1w?: number;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const REGIME_CONFIG: Record<VixRegime, { color: string; label: string; range: string }> = {
  LOW: { color: "var(--accent-bull)", label: "Low Volatility", range: "< 15" },
  NORMAL: { color: "var(--brand)", label: "Normal", range: "15–25" },
  ELEVATED: { color: "var(--severity-medium)", label: "Elevated", range: "25–40" },
  EXTREME: { color: "var(--severity-high)", label: "Extreme", range: "> 40" },
};

// VIX gauge fills from 0–60 range, clamped
function valueToPercent(value: number): number {
  return Math.min(Math.max(value / 60, 0), 1) * 100;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function VixGauge({ value, regime, delta1w }: VixGaugeProps) {
  const config = REGIME_CONFIG[regime];
  const fillPercent = valueToPercent(value);
  const deltaSign = delta1w !== undefined ? (delta1w > 0 ? "+" : "") : "";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span
          style={{
            fontSize: "var(--text-2xl)",
            fontWeight: 700,
            color: config.color,
            fontFamily: "var(--font-mono)",
          }}
        >
          {value.toFixed(1)}
        </span>
        {delta1w !== undefined && (
          <span
            style={{
              fontSize: "var(--text-xs)",
              color: delta1w > 0 ? "var(--severity-high)" : "var(--accent-bull)",
              fontWeight: 500,
            }}
          >
            {deltaSign}{delta1w.toFixed(1)} 1w
          </span>
        )}
      </div>

      {/* Bar gauge */}
      <div
        style={{
          height: 8,
          background: "var(--bg-card-hover)",
          borderRadius: 4,
          overflow: "hidden",
          border: "1px solid var(--border)",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${fillPercent}%`,
            background: config.color,
            borderRadius: 4,
            transition: "width var(--transition-slow)",
          }}
        />
      </div>

      {/* Regime label */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span
          style={{
            fontSize: "var(--text-xs)",
            fontWeight: 600,
            color: config.color,
            textTransform: "uppercase",
            letterSpacing: "0.05em",
          }}
        >
          {config.label}
        </span>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
          VIX {config.range}
        </span>
      </div>
    </div>
  );
}
