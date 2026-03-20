"use client";

import { useState } from "react";
import { Badge } from "@/components/shared/Badge";
import type { Alert, Severity } from "@/lib/types";

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

const SEVERITY_ORDER: Record<Severity, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };

// ─── Props ────────────────────────────────────────────────────────────────────

interface AlertDetailSectionProps {
  alerts: Alert[]; // all severities
}

// ─── Component ────────────────────────────────────────────────────────────────

export function AlertDetailSection({ alerts }: AlertDetailSectionProps) {
  const [expanded, setExpanded] = useState(false);
  const [filter, setFilter] = useState<Severity | "ALL">("ALL");

  if (alerts.length === 0) return null;

  const counts = {
    HIGH: alerts.filter((a) => a.severity === "HIGH").length,
    MEDIUM: alerts.filter((a) => a.severity === "MEDIUM").length,
    LOW: alerts.filter((a) => a.severity === "LOW").length,
  };

  const filtered =
    filter === "ALL"
      ? [...alerts].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity])
      : alerts.filter((a) => a.severity === filter);

  return (
    <section
      aria-label={`Alert details — ${alerts.length} alerts`}
      style={{
        border: "1px solid var(--border)",
        borderRadius: "var(--card-radius-sm)",
        overflow: "hidden",
      }}
    >
      {/* Collapsible header */}
      <button
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        style={{
          width: "100%",
          background: "var(--bg-card)",
          border: "none",
          cursor: "pointer",
          padding: "12px 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          transition: "background var(--transition-fast)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span
            style={{
              fontSize: "var(--text-sm)",
              fontWeight: 600,
              color: "var(--text-secondary)",
              textTransform: "uppercase",
              letterSpacing: "0.06em",
            }}
          >
            Alert Details
          </span>

          {/* Count badges */}
          {counts.HIGH > 0 && (
            <span
              style={{
                background: "var(--severity-high-bg)",
                color: "var(--severity-high)",
                border: "1px solid rgba(239,68,68,0.3)",
                borderRadius: 10,
                padding: "1px 8px",
                fontSize: "var(--text-xs)",
                fontWeight: 700,
              }}
            >
              {counts.HIGH} HIGH
            </span>
          )}
          {counts.MEDIUM > 0 && (
            <span
              style={{
                background: "var(--severity-medium-bg)",
                color: "var(--severity-medium)",
                border: "1px solid rgba(245,158,11,0.3)",
                borderRadius: 10,
                padding: "1px 8px",
                fontSize: "var(--text-xs)",
                fontWeight: 700,
              }}
            >
              {counts.MEDIUM} MED
            </span>
          )}
          {counts.LOW > 0 && (
            <span
              style={{
                background: "var(--severity-low-bg)",
                color: "var(--severity-low)",
                border: "1px solid rgba(107,114,128,0.3)",
                borderRadius: 10,
                padding: "1px 8px",
                fontSize: "var(--text-xs)",
                fontWeight: 700,
              }}
            >
              {counts.LOW} LOW
            </span>
          )}
        </div>

        <span style={{ color: "var(--text-muted)", fontSize: "var(--text-sm)", transform: expanded ? "rotate(180deg)" : "rotate(0deg)", transition: "transform var(--transition-fast)" }}>
          ▼
        </span>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div style={{ borderTop: "1px solid var(--border)" }}>
          {/* Filter chips */}
          <div style={{ display: "flex", gap: 8, padding: "10px 16px", borderBottom: "1px solid var(--border)", background: "var(--bg-secondary)" }}>
            {(["ALL", "HIGH", "MEDIUM", "LOW"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setFilter(s)}
                style={{
                  background: filter === s ? "rgba(255,255,255,0.1)" : "transparent",
                  border: "1px solid",
                  borderColor: filter === s ? "var(--border-strong)" : "var(--border)",
                  borderRadius: 20,
                  padding: "3px 12px",
                  fontSize: "var(--text-xs)",
                  fontWeight: 600,
                  color: filter === s ? "var(--text-primary)" : "var(--text-muted)",
                  cursor: "pointer",
                  transition: "all var(--transition-fast)",
                }}
              >
                {s === "ALL" ? `All (${alerts.length})` : `${s} (${counts[s]})`}
              </button>
            ))}
          </div>

          {/* Alert cards */}
          <div style={{ display: "flex", flexDirection: "column" }}>
            {filtered.map((alert, i) => (
              <AlertCard key={i} alert={alert} index={i} total={filtered.length} />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

// ─── AlertCard subcomponent ───────────────────────────────────────────────────

function AlertCard({ alert, index, total }: { alert: Alert; index: number; total: number }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "auto auto 1fr",
        alignItems: "flex-start",
        gap: 12,
        padding: "14px 16px",
        borderBottom: index < total - 1 ? "1px solid var(--border)" : "none",
        background: index % 2 === 0 ? "var(--bg-card)" : "#141520",
      }}
    >
      {/* Severity badge */}
      <Badge variant="severity" value={alert.severity} size="sm" />

      {/* Type + currency */}
      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-xs)",
            color: "var(--text-secondary)",
            fontWeight: 600,
            whiteSpace: "nowrap",
          }}
        >
          {ALERT_TYPE_LABELS[alert.type] ?? alert.type}
        </span>
        {alert.currency && (
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-xs)",
              color: "var(--text-muted)",
            }}
          >
            {alert.currency}
          </span>
        )}
      </div>

      {/* Message + context */}
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: "var(--text-sm)", color: "var(--text-primary)", lineHeight: 1.5 }}>
          {alert.message}
        </span>
        {alert.context && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 2 }}>
            {Object.entries(alert.context).map(([k, v]) => (
              <span
                key={k}
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-xs)",
                  color: "var(--text-muted)",
                  background: "rgba(255,255,255,0.04)",
                  border: "1px solid var(--border)",
                  borderRadius: 4,
                  padding: "2px 6px",
                }}
              >
                {k}: {typeof v === "number" ? v.toLocaleString() : String(v)}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
