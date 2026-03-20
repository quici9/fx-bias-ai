"use client";

import { useEffect } from "react";
import { type ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/shared/DataTable";
import { Badge } from "@/components/shared/Badge";
import { VixGauge } from "@/components/shared/VixGauge";
import { useAuditStore } from "@/lib/store/auditStore";
import { fetchMacroData } from "@/lib/fetchers/fetchMacroData";
import type { MacroSeriesRecord, YieldRecord, TrendDirection } from "@/lib/types";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function trendArrow(trend: TrendDirection): string {
  return trend === "RISING" ? "↑" : trend === "FALLING" ? "↓" : "→";
}

function trendColor(trend: TrendDirection): string {
  return trend === "RISING"
    ? "var(--accent-bull)"
    : trend === "FALLING"
    ? "var(--accent-bear)"
    : "var(--text-muted)";
}

function freshnessColor(days: number): string {
  if (days <= 7) return "var(--accent-bull)";
  if (days <= 14) return "var(--severity-medium)";
  return "var(--severity-high)";
}

function freshnessLabel(days: number): string {
  if (days <= 7) return "Fresh";
  if (days <= 14) return "Aging";
  return "Stale";
}

// ─── Policy Rates columns ─────────────────────────────────────────────────────

const RATE_COLS: ColumnDef<MacroSeriesRecord>[] = [
  {
    accessorKey: "currency",
    header: "Currency",
    cell: ({ getValue }) => (
      <span style={{ fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--text-primary)" }}>
        {getValue<string>()}
      </span>
    ),
  },
  {
    accessorKey: "value",
    header: "Rate (%)",
    cell: ({ getValue }) => (
      <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>
        {getValue<number>().toFixed(2)}%
      </span>
    ),
  },
  {
    accessorKey: "diff_vs_usd",
    header: "Δ vs USD",
    cell: ({ getValue }) => {
      const v = getValue<number>();
      return (
        <span style={{
          fontFamily: "var(--font-mono)",
          color: v > 0 ? "var(--accent-bull)" : v < 0 ? "var(--accent-bear)" : "var(--text-muted)",
        }}>
          {v > 0 ? "+" : ""}{v.toFixed(2)}%
        </span>
      );
    },
  },
  {
    accessorKey: "trend_3m",
    header: "Trend 3M",
    cell: ({ getValue }) => {
      const v = getValue<TrendDirection>();
      return (
        <span style={{ color: trendColor(v), fontWeight: 600 }}>
          {trendArrow(v)} {v}
        </span>
      );
    },
  },
  {
    accessorKey: "last_update",
    header: "Last Update",
    cell: ({ getValue }) => (
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
        {getValue<string>()}
      </span>
    ),
  },
  {
    accessorKey: "freshness_days",
    header: "Age",
    cell: ({ getValue }) => {
      const d = getValue<number>();
      return (
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", color: freshnessColor(d) }}>
          {d}d
        </span>
      );
    },
  },
];

// ─── CPI YoY columns (same shape + lag note) ─────────────────────────────────

const CPI_COLS: ColumnDef<MacroSeriesRecord>[] = [
  {
    accessorKey: "currency",
    header: "Currency",
    cell: ({ getValue }) => (
      <span style={{ fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--text-primary)" }}>
        {getValue<string>()}
      </span>
    ),
  },
  {
    accessorKey: "value",
    header: "CPI YoY (%)",
    cell: ({ getValue }) => (
      <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>
        {getValue<number>().toFixed(1)}%
      </span>
    ),
  },
  {
    accessorKey: "diff_vs_usd",
    header: "Δ vs US",
    cell: ({ getValue }) => {
      const v = getValue<number>();
      return (
        <span style={{
          fontFamily: "var(--font-mono)",
          color: v > 0 ? "var(--accent-bull)" : v < 0 ? "var(--accent-bear)" : "var(--text-muted)",
        }}>
          {v > 0 ? "+" : ""}{v.toFixed(1)}%
        </span>
      );
    },
  },
  {
    accessorKey: "trend_3m",
    header: "Trend",
    cell: ({ getValue }) => {
      const v = getValue<TrendDirection>();
      return (
        <span style={{ color: trendColor(v), fontWeight: 600 }}>
          {trendArrow(v)} {v}
        </span>
      );
    },
  },
  {
    accessorKey: "last_update",
    header: "Last Update",
    cell: ({ getValue }) => (
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
        {getValue<string>()}
      </span>
    ),
  },
  {
    accessorKey: "publication_lag_applied",
    header: "Lag",
    cell: ({ getValue }) => {
      const lag = getValue<number>();
      return lag > 0 ? (
        <Badge variant="medium" size="sm">T-{Math.round(lag / 30)}M</Badge>
      ) : null;
    },
  },
];

// ─── 10Y Yields columns ───────────────────────────────────────────────────────

const YIELD_COLS: ColumnDef<YieldRecord>[] = [
  {
    accessorKey: "country",
    header: "Country",
    cell: ({ getValue }) => (
      <span style={{ fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--text-primary)" }}>
        {getValue<string>()}
      </span>
    ),
  },
  {
    accessorKey: "yield",
    header: "10Y Yield",
    cell: ({ getValue }) => (
      <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>
        {getValue<number>().toFixed(2)}%
      </span>
    ),
  },
  {
    accessorKey: "spread_vs_us",
    header: "Spread vs US",
    cell: ({ getValue }) => {
      const v = getValue<number>();
      return (
        <span style={{
          fontFamily: "var(--font-mono)",
          color: v > 0 ? "var(--accent-bull)" : v < 0 ? "var(--accent-bear)" : "var(--text-muted)",
        }}>
          {v > 0 ? "+" : ""}{v.toFixed(2)}%
        </span>
      );
    },
  },
  {
    accessorKey: "delta_1w",
    header: "Δ1w",
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
      const color = v === "WIDENING" ? "var(--accent-bull)" : v === "NARROWING" ? "var(--accent-bear)" : "var(--text-muted)";
      return <span style={{ color, fontWeight: 600, fontSize: "var(--text-xs)" }}>{v}</span>;
    },
  },
];

// ─── Component ────────────────────────────────────────────────────────────────

export function MacroDataPanel() {
  const { macroReport, macroLoadState, macroError, setMacroReport, setMacroLoadState, setMacroError } =
    useAuditStore();

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

  if (macroLoadState === "loading") {
    return (
      <div className="card" style={{ color: "var(--text-muted)", fontSize: "var(--text-sm)", textAlign: "center", padding: 40 }}>
        Loading macro data…
      </div>
    );
  }

  if (macroLoadState === "error" || !macroReport) {
    return (
      <div className="card" style={{ color: "var(--severity-high)", fontSize: "var(--text-sm)", textAlign: "center", padding: 40 }}>
        {macroError ?? "Macro data unavailable"}
      </div>
    );
  }

  // Build freshness monitor rows from policy_rates (representative check)
  const freshnessRows = [
    { source: "Policy Rates", records: macroReport.policy_rates },
    { source: "CPI YoY", records: macroReport.cpi_yoy },
  ].flatMap(({ source, records }) =>
    records.map((r) => ({
      source,
      currency: r.currency,
      lastRecord: r.last_update,
      age: r.freshness_days,
      status: freshnessLabel(r.freshness_days),
    }))
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Header */}
      <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
        Fetched: <strong style={{ color: "var(--text-secondary)" }}>{macroReport.fetchDate}</strong>
        &nbsp;·&nbsp;VIX: <strong style={{ color: macroReport.vix.value >= 25 ? "var(--severity-high)" : "var(--text-secondary)" }}>
          {macroReport.vix.value.toFixed(1)} ({macroReport.vix.regime})
        </strong>
      </p>

      {/* VIX Gauge */}
      <div className="card" style={{ padding: 20, maxWidth: 400 }}>
        <h3 style={{ margin: "0 0 16px", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          VIX — Volatility Regime
        </h3>
        <VixGauge value={macroReport.vix.value} regime={macroReport.vix.regime} delta1w={macroReport.vix.delta_1w} />
      </div>

      {/* Policy Rates */}
      <div>
        <h3 style={{ margin: "0 0 10px", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Policy Rates
        </h3>
        <DataTable data={macroReport.policy_rates} columns={RATE_COLS} />
      </div>

      {/* CPI YoY */}
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
          <h3 style={{ margin: 0, fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            CPI YoY
          </h3>
          <span style={{
            background: "var(--severity-medium)22",
            border: "1px solid var(--severity-medium)",
            borderRadius: "var(--card-radius-sm)",
            color: "var(--severity-medium)",
            fontSize: "var(--text-xs)",
            fontWeight: 600,
            padding: "2px 8px",
          }}>
            ⚠ Lag: T-2 months
          </span>
        </div>
        <DataTable data={macroReport.cpi_yoy} columns={CPI_COLS} />
      </div>

      {/* 10Y Yields */}
      <div>
        <h3 style={{ margin: "0 0 10px", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          10-Year Yields
        </h3>
        <DataTable data={macroReport.yields_10y} columns={YIELD_COLS} />
      </div>

      {/* Data Freshness Monitor */}
      <div>
        <h3 style={{ margin: "0 0 10px", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Data Freshness Monitor
        </h3>
        <div style={{ overflowX: "auto", borderRadius: "var(--card-radius-sm)", border: "1px solid var(--border)" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "var(--bg-card)" }}>
                {["Source", "Currency", "Last Record", "Age", "Status"].map((h) => (
                  <th key={h} style={{
                    padding: "10px 12px",
                    textAlign: "left",
                    fontSize: "var(--text-xs)",
                    fontWeight: 600,
                    letterSpacing: "0.05em",
                    textTransform: "uppercase",
                    color: "var(--text-muted)",
                    borderBottom: "1px solid var(--border)",
                  }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {freshnessRows.map((row, i) => (
                <tr key={i} style={{ background: "var(--bg-card)" }}>
                  <td style={{ padding: "10px 12px", fontSize: "var(--text-sm)", color: "var(--text-muted)", borderBottom: "1px solid var(--border-muted)" }}>{row.source}</td>
                  <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: "var(--text-sm)", color: "var(--text-primary)", borderBottom: "1px solid var(--border-muted)" }}>{row.currency}</td>
                  <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", color: "var(--text-muted)", borderBottom: "1px solid var(--border-muted)" }}>{row.lastRecord}</td>
                  <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", color: freshnessColor(row.age), borderBottom: "1px solid var(--border-muted)" }}>{row.age}d</td>
                  <td style={{ padding: "10px 12px", borderBottom: "1px solid var(--border-muted)" }}>
                    <Badge
                      variant={row.status === "Fresh" ? "bull" : row.status === "Aging" ? "medium" : "high"}
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
