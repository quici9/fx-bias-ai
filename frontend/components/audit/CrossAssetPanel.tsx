"use client";

import { useEffect } from "react";
import { type ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/shared/DataTable";
import { Sparkline } from "@/components/shared/Sparkline";
import { VixGauge } from "@/components/shared/VixGauge";
import { useAuditStore } from "@/lib/store/auditStore";
import { fetchMacroData } from "@/lib/fetchers/fetchMacroData";
import type { YieldDifferential } from "@/lib/types";

// ─── Yield diff columns ───────────────────────────────────────────────────────

const YIELD_DIFF_COLS: ColumnDef<YieldDifferential>[] = [
  {
    accessorKey: "pair",
    header: "Pair",
    cell: ({ getValue }) => (
      <span style={{ fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--text-primary)" }}>
        {getValue<string>()}
      </span>
    ),
  },
  {
    accessorKey: "spread",
    header: "Spread (%)",
    cell: ({ getValue }) => {
      const v = getValue<number>();
      return (
        <span style={{
          fontFamily: "var(--font-mono)",
          fontWeight: 600,
          color: v > 0 ? "var(--accent-bull)" : v < 0 ? "var(--accent-bear)" : "var(--text-muted)",
        }}>
          {v > 0 ? "+" : ""}{v.toFixed(2)}%
        </span>
      );
    },
  },
  {
    accessorKey: "delta_4w",
    header: "Δ4w",
    cell: ({ getValue }) => {
      const v = getValue<number>();
      return (
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-xs)",
          color: v > 0 ? "var(--accent-bull)" : v < 0 ? "var(--accent-bear)" : "var(--text-muted)",
        }}>
          {v > 0 ? "+" : ""}{v.toFixed(2)}
        </span>
      );
    },
  },
  {
    accessorKey: "direction",
    header: "Direction",
    cell: ({ getValue }) => {
      const v = getValue<string>();
      const color =
        v === "WIDENING" ? "var(--accent-bull)" : v === "NARROWING" ? "var(--accent-bear)" : "var(--text-muted)";
      return (
        <span style={{ color, fontWeight: 600, fontSize: "var(--text-xs)" }}>
          {v === "WIDENING" ? "↑ " : v === "NARROWING" ? "↓ " : "→ "}
          {v}
        </span>
      );
    },
  },
];

// ─── Component ────────────────────────────────────────────────────────────────

const COMMODITY_LABELS: Record<string, { label: string; fxNote: string }> = {
  gold: { label: "Gold Futures", fxNote: "AUD+, CHF+" },
  oil: { label: "Crude Oil Futures", fxNote: "CAD+, NOK+" },
  sp500: { label: "S&P 500 Futures", fxNote: "Risk-On → JPY−, CHF−" },
};

export function CrossAssetPanel() {
  const {
    crossAssetReport,
    crossAssetLoadState,
    crossAssetError,
    macroReport,
    macroLoadState,
    setCrossAssetReport,
    setCrossAssetLoadState,
    setCrossAssetError,
    setMacroReport,
    setMacroLoadState,
    setMacroError,
  } = useAuditStore();

  // Load cross-asset data
  useEffect(() => {
    if (crossAssetLoadState === "idle") {
      setCrossAssetLoadState("loading");
      import("@/lib/fetchers/fetchCrossAssetData")
        .then((m) => m.fetchCrossAssetData())
        .then(setCrossAssetReport)
        .catch((err: unknown) => {
          setCrossAssetError(err instanceof Error ? err.message : "Failed to load cross-asset data");
        });
    }
  }, [crossAssetLoadState, setCrossAssetReport, setCrossAssetLoadState, setCrossAssetError]);

  // Load macro data for VIX (shared store)
  useEffect(() => {
    if (macroLoadState === "idle") {
      setMacroLoadState("loading");
      fetchMacroData()
        .then(setMacroReport)
        .catch((err: unknown) => {
          setMacroError(err instanceof Error ? err.message : "Failed to load macro data");
        });
    }
  }, [macroLoadState, setMacroReport, setMacroLoadState, setMacroError]);

  const isLoading = crossAssetLoadState === "loading";
  const hasError = crossAssetLoadState === "error" || !crossAssetReport;

  if (isLoading) {
    return (
      <div className="card" style={{ color: "var(--text-muted)", fontSize: "var(--text-sm)", textAlign: "center", padding: 40 }}>
        Loading cross-asset data…
      </div>
    );
  }

  if (hasError) {
    return (
      <div className="card" style={{ color: "var(--severity-high)", fontSize: "var(--text-sm)", textAlign: "center", padding: 40 }}>
        {crossAssetError ?? "Cross-asset data unavailable"}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      {/* Fetch date */}
      <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
        Fetched: <strong style={{ color: "var(--text-secondary)" }}>{crossAssetReport.fetchDate}</strong>
      </p>

      {/* Commodities COT section */}
      <div>
        <h3 style={{ margin: "0 0 14px", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Commodities — COT Positioning
        </h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
          {(Object.entries(crossAssetReport.commodities) as [keyof typeof crossAssetReport.commodities, typeof crossAssetReport.commodities[keyof typeof crossAssetReport.commodities]][]).map(([key, commodity]) => {
            const meta = COMMODITY_LABELS[key] ?? { label: key, fxNote: "" };
            const isRising = commodity.trend_direction === "RISING";
            const isFalling = commodity.trend_direction === "FALLING";
            const indexColor = isRising ? "var(--accent-bull)" : isFalling ? "var(--accent-bear)" : "var(--text-muted)";
            return (
              <div
                key={key}
                className="card"
                style={{
                  padding: "16px",
                  borderLeft: `3px solid ${indexColor}`,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                  <div>
                    <p style={{ margin: 0, fontWeight: 700, fontSize: "var(--text-sm)", color: "var(--text-primary)" }}>{meta.label}</p>
                    <p style={{ margin: "2px 0 0", fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>{meta.fxNote}</p>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <p style={{ margin: 0, fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: "var(--text-xl)", color: indexColor }}>
                      {commodity.cot_index}
                    </p>
                    <p style={{ margin: "2px 0 0", fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>COT Index</p>
                  </div>
                </div>
                <Sparkline data={commodity.trend_12w} height={36} />
                <div style={{ marginTop: 8, display: "flex", gap: 6, alignItems: "center" }}>
                  <span style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                    fontSize: "var(--text-xs)",
                    fontWeight: 600,
                    color: indexColor,
                  }}>
                    {isRising ? "↑" : isFalling ? "↓" : "→"} {commodity.trend_direction}
                  </span>
                  <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>FX impact: {commodity.fx_impact}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* VIX Gauge (from macro) */}
      {macroReport && (
        <div className="card" style={{ padding: 20, maxWidth: 440 }}>
          <h3 style={{ margin: "0 0 16px", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            VIX — Volatility Regime
          </h3>
          <VixGauge value={macroReport.vix.value} regime={macroReport.vix.regime} delta1w={macroReport.vix.delta_1w} />
        </div>
      )}

      {/* Yield Differentials */}
      <div>
        <h3 style={{ margin: "0 0 10px", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Yield Differentials
        </h3>
        <DataTable data={crossAssetReport.yield_differentials} columns={YIELD_DIFF_COLS} />
      </div>
    </div>
  );
}
