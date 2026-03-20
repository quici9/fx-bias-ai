"use client";

import { SlidePanel } from "@/components/shared/SlidePanel";
import { Badge } from "@/components/shared/Badge";
import type { PairRecommendation, CurrencyPrediction, Alert, PairColumnType } from "@/lib/types";

// ─── Helpers ──────────────────────────────────────────────────────────────────

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

const DIRECTION_STYLE: Record<string, { color: string; bg: string; label: string }> = {
  long:  { color: "var(--accent-bull)",    bg: "rgba(16,185,129,0.08)",  label: "LONG" },
  short: { color: "var(--accent-bear)",    bg: "rgba(239,68,68,0.08)",   label: "SHORT" },
  avoid: { color: "var(--accent-neutral)", bg: "rgba(107,114,128,0.08)", label: "AVOID" },
};

// ─── Props ────────────────────────────────────────────────────────────────────

interface PairDetailPanelProps {
  pair: PairRecommendation | null;
  /** Column type determines the bias direction */
  columnType: PairColumnType | null;
  /** Full predictions map to look up base/quote currency prediction details */
  predictions: CurrencyPrediction[];
  /** All weekly alerts to filter relevant ones */
  allAlerts: Alert[];
  onClose: () => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function PairDetailPanel({
  pair,
  columnType,
  predictions,
  allAlerts,
  onClose,
}: PairDetailPanelProps) {
  if (!pair || !columnType) {
    return (
      <SlidePanel open={false} onClose={onClose} title="">
        {null}
      </SlidePanel>
    );
  }

  const style = DIRECTION_STYLE[columnType];

  // Look up prediction details for base and quote currencies
  const basePred = predictions.find((p) => p.currency === pair.base_currency);
  const quotePred = predictions.find((p) => p.currency === pair.quote_currency);

  // Filter relevant alerts (either global or affecting base/quote currency)
  const relevantAlerts = allAlerts.filter(
    (a) => !a.currency || a.currency === pair.base_currency || a.currency === pair.quote_currency
  );

  return (
    <SlidePanel
      open={pair !== null}
      onClose={onClose}
      title={`${pair.pair}`}
      subtitle={`${style.label} — Spread Score ${pair.spread.toFixed(2)}`}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

        {/* Direction badge + confidence */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span
            style={{
              padding: "4px 12px",
              borderRadius: 6,
              background: style.bg,
              color: style.color,
              fontWeight: 700,
              fontSize: "var(--text-sm)",
              fontFamily: "var(--font-mono)",
              letterSpacing: "0.06em",
              border: `1px solid ${style.color}40`,
            }}
          >
            {style.label}
          </span>
          <Badge variant="confidence" value={pair.confidence} />
        </div>

        {/* Base currency prediction detail */}
        {basePred && (
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
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span
                style={{
                  fontSize: "var(--text-xs)",
                  fontWeight: 700,
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                }}
              >
                Base — {basePred.currency}
              </span>
              <div style={{ display: "flex", gap: 6 }}>
                <Badge variant="bias" value={basePred.bias} size="sm" />
                <Badge variant="confidence" value={basePred.confidence} size="sm" />
              </div>
            </div>
            <ProbabilityBar label="BULL" value={basePred.probability.bull} color="var(--accent-bull)" />
            <ProbabilityBar label="NEUTRAL" value={basePred.probability.neutral} color="var(--accent-neutral)" />
            <ProbabilityBar label="BEAR" value={basePred.probability.bear} color="var(--accent-bear)" />
            {basePred.key_drivers.length > 0 && (
              <div>
                <span
                  style={{
                    fontSize: "var(--text-xs)",
                    color: "var(--text-muted)",
                    display: "block",
                    marginBottom: 6,
                  }}
                >
                  Key Drivers
                </span>
                {basePred.key_drivers.slice(0, 3).map((d, i) => (
                  <div
                    key={i}
                    style={{
                      fontSize: "var(--text-xs)",
                      color: "var(--text-secondary)",
                      padding: "4px 0",
                      borderTop: i > 0 ? "1px solid var(--border)" : undefined,
                    }}
                  >
                    {i + 1}. {d}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Quote currency prediction detail */}
        {quotePred && (
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
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span
                style={{
                  fontSize: "var(--text-xs)",
                  fontWeight: 700,
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                }}
              >
                Quote — {quotePred.currency}
              </span>
              <div style={{ display: "flex", gap: 6 }}>
                <Badge variant="bias" value={quotePred.bias} size="sm" />
                <Badge variant="confidence" value={quotePred.confidence} size="sm" />
              </div>
            </div>
            <ProbabilityBar label="BULL" value={quotePred.probability.bull} color="var(--accent-bull)" />
            <ProbabilityBar label="NEUTRAL" value={quotePred.probability.neutral} color="var(--accent-neutral)" />
            <ProbabilityBar label="BEAR" value={quotePred.probability.bear} color="var(--accent-bear)" />
            {quotePred.key_drivers.length > 0 && (
              <div>
                <span
                  style={{
                    fontSize: "var(--text-xs)",
                    color: "var(--text-muted)",
                    display: "block",
                    marginBottom: 6,
                  }}
                >
                  Key Drivers
                </span>
                {quotePred.key_drivers.slice(0, 3).map((d, i) => (
                  <div
                    key={i}
                    style={{
                      fontSize: "var(--text-xs)",
                      color: "var(--text-secondary)",
                      padding: "4px 0",
                      borderTop: i > 0 ? "1px solid var(--border)" : undefined,
                    }}
                  >
                    {i + 1}. {d}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 12w accuracy for base currency */}
        {basePred?.historical_accuracy_12w != null && (
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
              {basePred.currency} — 12w historical accuracy
            </span>
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontWeight: 700,
                fontSize: "var(--text-base)",
                color:
                  basePred.historical_accuracy_12w >= 0.7
                    ? "var(--accent-bull)"
                    : basePred.historical_accuracy_12w >= 0.6
                      ? "var(--severity-medium)"
                      : "var(--accent-bear)",
              }}
            >
              {(basePred.historical_accuracy_12w * 100).toFixed(0)}%
            </span>
          </div>
        )}

        {/* Relevant alerts */}
        {relevantAlerts.length > 0 && (
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
              Active Alerts ({relevantAlerts.length})
            </span>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {relevantAlerts.map((alert, i) => (
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
                    {alert.currency && (
                      <span
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "var(--text-xs)",
                          fontWeight: 700,
                          color: "var(--text-secondary)",
                        }}
                      >
                        {alert.currency}
                      </span>
                    )}
                  </div>
                  <span style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>
                    {alert.message}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </SlidePanel>
  );
}
