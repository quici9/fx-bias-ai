"use client";

import { PairCard, type PairColumnType } from "@/components/dashboard/PairCard";
import type { PairRecommendation } from "@/lib/types";

// ─── Column config ────────────────────────────────────────────────────────────

const COLUMNS: Array<{
  key: string;
  type: PairColumnType;
  label: string;
  accentVar: string;
  borderVar: string;
}> = [
  { key: "strong_long",  type: "long",  label: "Strong Long",  accentVar: "var(--accent-bull)", borderVar: "var(--accent-bull-muted)" },
  { key: "strong_short", type: "short", label: "Strong Short", accentVar: "var(--accent-bear)", borderVar: "var(--accent-bear-muted)" },
  { key: "avoid",        type: "avoid", label: "Avoid",        accentVar: "var(--accent-neutral)", borderVar: "rgba(107,114,128,0.3)" },
];

// ─── Props ────────────────────────────────────────────────────────────────────

interface PairRecommendationGridProps {
  strongLong: PairRecommendation[];
  strongShort: PairRecommendation[];
  avoid: PairRecommendation[];
  onPairSelect?: (pair: PairRecommendation) => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function PairRecommendationGrid({
  strongLong,
  strongShort,
  avoid,
  onPairSelect,
}: PairRecommendationGridProps) {
  const DATA: Record<string, PairRecommendation[]> = {
    strong_long: strongLong,
    strong_short: strongShort,
    avoid,
  };

  return (
    <section aria-label="Pair recommendations">
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
        Pair Recommendations
      </h2>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: 16,
        }}
      >
        {COLUMNS.map(({ key, type, label, accentVar, borderVar }) => (
          <div key={key} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {/* Column header */}
            <div
              style={{
                fontSize: "var(--text-xs)",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                color: accentVar,
                paddingBottom: 8,
                borderBottom: `2px solid ${borderVar}`,
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <span>{label}</span>
              <span
                style={{
                  background: "rgba(255,255,255,0.06)",
                  borderRadius: 10,
                  padding: "1px 7px",
                  fontSize: "var(--text-xs)",
                  color: "var(--text-muted)",
                  fontWeight: 600,
                }}
              >
                {DATA[key].length}
              </span>
            </div>

            {/* Cards */}
            {DATA[key].map((pair) => (
              <PairCard
                key={pair.pair}
                pair={pair}
                type={type}
                onSelect={onPairSelect}
              />
            ))}

            {DATA[key].length === 0 && (
              <div
                style={{
                  fontSize: "var(--text-sm)",
                  color: "var(--text-muted)",
                  padding: "16px 0",
                  fontStyle: "italic",
                }}
              >
                None this week
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
