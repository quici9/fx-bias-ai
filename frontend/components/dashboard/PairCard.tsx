"use client";

import { useState } from "react";
import { Badge } from "@/components/shared/Badge";
import type { PairRecommendation, PairColumnType } from "@/lib/types";

// Re-export so legacy imports like `import { PairColumnType } from "@/components/dashboard/PairCard"` still work
export type { PairColumnType };

// ─── Column frame styles ───────────────────────────────────────────────────────

const COLUMN_FRAME: Record<
  PairColumnType,
  { border: string; bg: string; bgHover: string; label: string }
> = {
  long: {
    border: "var(--accent-bull)",
    bg: "rgba(16, 185, 129, 0.04)",
    bgHover: "rgba(16, 185, 129, 0.08)",
    label: "LONG",
  },
  short: {
    border: "var(--accent-bear)",
    bg: "rgba(239, 68, 68, 0.04)",
    bgHover: "rgba(239, 68, 68, 0.08)",
    label: "SHORT",
  },
  avoid: {
    border: "var(--accent-neutral)",
    bg: "rgba(107, 114, 128, 0.04)",
    bgHover: "rgba(107, 114, 128, 0.08)",
    label: "AVOID",
  },
};

// ─── Props ────────────────────────────────────────────────────────────────────

interface PairCardProps {
  pair: PairRecommendation;
  type: PairColumnType;
  onSelect?: (pair: PairRecommendation) => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function PairCard({ pair, type, onSelect }: PairCardProps) {
  const [hovered, setHovered] = useState(false);
  const frame = COLUMN_FRAME[type];

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`${pair.pair} ${type} recommendation, ${pair.confidence} confidence`}
      onClick={() => onSelect?.(pair)}
      onKeyDown={(e) => e.key === "Enter" && onSelect?.(pair)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 10,
        padding: "14px 16px",
        background: hovered ? frame.bgHover : frame.bg,
        border: "1px solid var(--border)",
        borderLeft: `4px solid ${frame.border}`,
        borderRadius: "var(--card-radius-sm)",
        cursor: onSelect ? "pointer" : "default",
        transition: "background var(--transition-fast), box-shadow var(--transition-fast)",
        boxShadow: hovered ? "0 4px 16px rgba(0,0,0,0.25)" : "none",
      }}
    >
      {/* Pair name + confidence */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontWeight: 700,
            fontSize: "var(--text-base)",
            color: "var(--text-primary)",
            letterSpacing: "0.02em",
          }}
        >
          {pair.pair}
        </span>
        <Badge variant="confidence" value={pair.confidence} size="sm" />
      </div>

      {/* Base / Quote currencies */}
      <div style={{ display: "flex", gap: 8, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
        <span>
          Base:{" "}
          <span style={{ color: "var(--text-secondary)", fontWeight: 600 }}>
            {pair.base_currency}
          </span>
        </span>
        <span style={{ color: "var(--border-strong)" }}>·</span>
        <span>
          Quote:{" "}
          <span style={{ color: "var(--text-secondary)", fontWeight: 600 }}>
            {pair.quote_currency}
          </span>
        </span>
      </div>

      {/* Spread score */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          fontSize: "var(--text-xs)",
          color: "var(--text-muted)",
        }}
      >
        <span>Spread Score</span>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            color: frame.border,
            fontWeight: 700,
          }}
        >
          {pair.spread.toFixed(2)}
        </span>
      </div>
    </div>
  );
}
