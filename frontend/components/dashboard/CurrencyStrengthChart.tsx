"use client";

import { useState } from "react";
import { Badge } from "@/components/shared/Badge";
import { StatusDot } from "@/components/shared/StatusDot";
import type { CurrencyPrediction } from "@/lib/types";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getRowBg(index: number): string {
  return index % 2 === 0 ? "var(--bg-card)" : "#141520";
}

function biasArrow(bias: string): string {
  if (bias === "BULL") return "↑";
  if (bias === "BEAR") return "↓";
  return "→";
}

function biasColor(bias: string): string {
  if (bias === "BULL") return "var(--accent-bull)";
  if (bias === "BEAR") return "var(--accent-bear)";
  return "var(--accent-neutral)";
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface CurrencyStrengthChartProps {
  predictions: CurrencyPrediction[];
  onCurrencyClick?: (prediction: CurrencyPrediction) => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function CurrencyStrengthChart({
  predictions,
  onCurrencyClick,
}: CurrencyStrengthChartProps) {
  const [hoveredCurrency, setHoveredCurrency] = useState<string | null>(null);

  // Sort by rank ascending (rank 1 = strongest bull at top)
  const sorted = [...predictions].sort((a, b) => a.rank - b.rank);

  return (
    <section aria-label="Currency strength ranking">
      <h2
        style={{
          margin: "0 0 16px",
          fontSize: "var(--text-base)",
          fontWeight: 600,
          color: "var(--text-secondary)",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
        }}
      >
        Currency Strength
      </h2>

      <div
        style={{
          border: "1px solid var(--border)",
          borderRadius: "var(--card-radius-sm)",
          overflow: "hidden",
        }}
      >
        {sorted.map((pred, index) => {
          const isHovered = hoveredCurrency === pred.currency;
          const maxProb = Math.max(pred.probability.bull, pred.probability.bear, pred.probability.neutral);
          const hasAlerts = pred.alerts.length > 0;

          return (
            <div
              key={pred.currency}
              role={onCurrencyClick ? "button" : undefined}
              tabIndex={onCurrencyClick ? 0 : undefined}
              aria-label={`${pred.currency}: ${pred.bias} bias, rank ${pred.rank}`}
              onClick={() => onCurrencyClick?.(pred)}
              onKeyDown={(e) => e.key === "Enter" && onCurrencyClick?.(pred)}
              onMouseEnter={() => setHoveredCurrency(pred.currency)}
              onMouseLeave={() => setHoveredCurrency(null)}
              style={{
                display: "grid",
                gridTemplateColumns: "28px 56px 100px 1fr 80px 70px 48px",
                alignItems: "center",
                gap: 12,
                padding: "10px 16px",
                background: isHovered ? "var(--bg-card-hover)" : getRowBg(index),
                cursor: onCurrencyClick ? "pointer" : "default",
                transition: "background var(--transition-fast)",
                borderBottom: index < sorted.length - 1 ? "1px solid var(--border)" : "none",
              }}
            >
              {/* Rank */}
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-xs)",
                  color: "var(--text-muted)",
                  textAlign: "right",
                }}
              >
                #{pred.rank}
              </span>

              {/* Currency + arrow */}
              <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontWeight: 700,
                    fontSize: "var(--text-sm)",
                    color: "var(--text-primary)",
                  }}
                >
                  {pred.currency}
                </span>
                <span
                  style={{
                    fontSize: "var(--text-sm)",
                    color: biasColor(pred.bias),
                    fontWeight: 700,
                  }}
                >
                  {biasArrow(pred.bias)}
                </span>
              </div>

              {/* Bias badge */}
              <Badge variant="bias" value={pred.bias} size="sm" />

              {/* Probability bar */}
              <div style={{ display: "flex", gap: 2, height: 8, borderRadius: 4, overflow: "hidden" }}>
                {pred.bias === "BULL" && (
                  <>
                    <div style={{ flex: pred.probability.bull, background: "var(--accent-bull)", minWidth: 2 }} />
                    <div style={{ flex: pred.probability.neutral, background: "var(--accent-neutral)", minWidth: 1, opacity: 0.5 }} />
                    <div style={{ flex: pred.probability.bear, background: "var(--accent-bear)", minWidth: 1, opacity: 0.4 }} />
                  </>
                )}
                {pred.bias === "BEAR" && (
                  <>
                    <div style={{ flex: pred.probability.bull, background: "var(--accent-bull)", minWidth: 1, opacity: 0.4 }} />
                    <div style={{ flex: pred.probability.neutral, background: "var(--accent-neutral)", minWidth: 1, opacity: 0.5 }} />
                    <div style={{ flex: pred.probability.bear, background: "var(--accent-bear)", minWidth: 2 }} />
                  </>
                )}
                {pred.bias === "NEUTRAL" && (
                  <>
                    <div style={{ flex: pred.probability.bull, background: "var(--accent-bull)", minWidth: 1, opacity: 0.4 }} />
                    <div style={{ flex: pred.probability.neutral, background: "var(--accent-neutral)", minWidth: 2 }} />
                    <div style={{ flex: pred.probability.bear, background: "var(--accent-bear)", minWidth: 1, opacity: 0.4 }} />
                  </>
                )}
              </div>

              {/* Max probability % */}
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-xs)",
                  color: biasColor(pred.bias),
                  fontWeight: 700,
                  textAlign: "right",
                }}
              >
                {(maxProb * 100).toFixed(0)}%
              </span>

              {/* Confidence */}
              <Badge variant="confidence" value={pred.confidence} size="sm" />

              {/* Alert indicator */}
              <div style={{ display: "flex", justifyContent: "center" }}>
                {hasAlerts && <StatusDot status="warn" aria-label="Active alerts" />}
              </div>
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div
        style={{
          display: "flex",
          gap: 16,
          marginTop: 8,
          fontSize: "var(--text-xs)",
          color: "var(--text-muted)",
          paddingLeft: 4,
        }}
      >
        <span>
          <span style={{ color: "var(--accent-bull)", marginRight: 4 }}>↑ Bull</span>
          bullish bias
        </span>
        <span>
          <span style={{ color: "var(--accent-bear)", marginRight: 4 }}>↓ Bear</span>
          bearish bias
        </span>
        <span>
          <span style={{ color: "var(--accent-neutral)", marginRight: 4 }}>→ Neutral</span>
          no clear direction
        </span>
        <span style={{ marginLeft: "auto" }}>click row for detail</span>
      </div>
    </section>
  );
}
