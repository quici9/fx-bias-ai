"use client";

import { useEffect, useState } from "react";
import { type ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/shared/DataTable";
import { Badge } from "@/components/shared/Badge";
import { Sparkline } from "@/components/shared/Sparkline";
import { useAuditStore } from "@/lib/store/auditStore";
import { fetchCotData } from "@/lib/fetchers/fetchCotData";
import type { CotLegacyRecord, CotTffRecord } from "@/lib/types";

// ─── Currency filter ──────────────────────────────────────────────────────────

const ALL_CURRENCIES = ["ALL", "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"] as const;

// ─── Legacy table columns ─────────────────────────────────────────────────────

const LEGACY_COLS: ColumnDef<CotLegacyRecord>[] = [
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
    accessorKey: "noncomm_long",
    header: "Net Long",
    cell: ({ getValue }) => (
      <span style={{ color: "var(--accent-bull)", fontFamily: "var(--font-mono)" }}>
        {getValue<number>().toLocaleString()}
      </span>
    ),
  },
  {
    accessorKey: "noncomm_short",
    header: "Net Short",
    cell: ({ getValue }) => (
      <span style={{ color: "var(--accent-bear)", fontFamily: "var(--font-mono)" }}>
        {getValue<number>().toLocaleString()}
      </span>
    ),
  },
  {
    accessorKey: "open_interest",
    header: "Open Interest",
    cell: ({ getValue }) => (
      <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>
        {getValue<number>().toLocaleString()}
      </span>
    ),
  },
  {
    accessorKey: "net",
    header: "Net",
    cell: ({ getValue }) => {
      const v = getValue<number>();
      return (
        <span style={{
          fontFamily: "var(--font-mono)",
          fontWeight: 600,
          color: v > 0 ? "var(--accent-bull)" : v < 0 ? "var(--accent-bear)" : "var(--text-secondary)",
        }}>
          {v > 0 ? "+" : ""}{v.toLocaleString()}
        </span>
      );
    },
  },
  {
    accessorKey: "net_delta_1w",
    header: "Δ1w",
    cell: ({ getValue }) => {
      const v = getValue<number>();
      return (
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-xs)",
          color: v > 0 ? "var(--accent-bull)" : v < 0 ? "var(--accent-bear)" : "var(--text-muted)",
        }}>
          {v > 0 ? "+" : ""}{v.toLocaleString()}
        </span>
      );
    },
  },
  {
    accessorKey: "cot_index_52w",
    header: "COT Index",
    cell: ({ getValue }) => {
      const v = getValue<number>();
      return (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{
            width: 64,
            height: 6,
            background: "var(--bg-card-hover)",
            borderRadius: 3,
            overflow: "hidden",
          }}>
            <div style={{
              height: "100%",
              width: `${v}%`,
              background: v > 75 ? "var(--accent-bull)" : v < 25 ? "var(--accent-bear)" : "var(--brand)",
              borderRadius: 3,
              transition: "width var(--transition-slow)",
            }} />
          </div>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>
            {v}
          </span>
        </div>
      );
    },
  },
  {
    accessorKey: "extreme_flag",
    header: "Flags",
    cell: ({ row }) => (
      <div style={{ display: "flex", gap: 4 }}>
        {row.original.extreme_flag && (
          <Badge variant="high" size="sm">EXTREME</Badge>
        )}
        {row.original.flip_flag && (
          <Badge variant="medium" size="sm">FLIP</Badge>
        )}
      </div>
    ),
  },
];

// ─── TFF table columns ────────────────────────────────────────────────────────

const TFF_COLS: ColumnDef<CotTffRecord>[] = [
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
    accessorKey: "lev_funds_net",
    header: "Lev Funds",
    cell: ({ getValue }) => {
      const v = getValue<number>();
      return (
        <span style={{
          fontFamily: "var(--font-mono)",
          color: v > 0 ? "var(--accent-bull)" : v < 0 ? "var(--accent-bear)" : "var(--text-secondary)",
        }}>
          {v > 0 ? "+" : ""}{v.toLocaleString()}
        </span>
      );
    },
  },
  {
    accessorKey: "asset_mgr_net",
    header: "Asset Mgr",
    cell: ({ getValue }) => {
      const v = getValue<number>();
      return (
        <span style={{
          fontFamily: "var(--font-mono)",
          color: v > 0 ? "var(--accent-bull)" : v < 0 ? "var(--accent-bear)" : "var(--text-secondary)",
        }}>
          {v > 0 ? "+" : ""}{v.toLocaleString()}
        </span>
      );
    },
  },
  {
    accessorKey: "dealer_net",
    header: "Dealer",
    cell: ({ getValue }) => {
      const v = getValue<number>();
      return (
        <span style={{
          fontFamily: "var(--font-mono)",
          color: v > 0 ? "var(--accent-bull)" : v < 0 ? "var(--accent-bear)" : "var(--text-secondary)",
        }}>
          {v > 0 ? "+" : ""}{v.toLocaleString()}
        </span>
      );
    },
  },
  {
    accessorKey: "lev_vs_assetmgr_divergence",
    header: "Divergence",
    cell: ({ getValue }) => {
      const v = getValue<number>();
      const isHigh = Math.abs(v) > 50000;
      return (
        <span style={{
          fontFamily: "var(--font-mono)",
          fontWeight: isHigh ? 700 : 400,
          color: isHigh ? "var(--severity-medium)" : "var(--text-secondary)",
        }}>
          {Math.abs(v).toLocaleString()}
        </span>
      );
    },
  },
];

// ─── Component ────────────────────────────────────────────────────────────────

export function CotDataPanel() {
  const { cotReport, cotLoadState, cotError, setCotReport, setCotLoadState, setCotError } = useAuditStore();
  const [selectedCurrency, setSelectedCurrency] = useState<string>("ALL");

  useEffect(() => {
    if (cotLoadState === "idle") {
      setCotLoadState("loading");
      fetchCotData()
        .then(setCotReport)
        .catch((err: unknown) => {
          setCotError(err instanceof Error ? err.message : "Failed to load COT data");
        });
    }
  }, [cotLoadState, setCotReport, setCotLoadState, setCotError]);

  if (cotLoadState === "loading") {
    return (
      <div className="card" style={{ color: "var(--text-muted)", fontSize: "var(--text-sm)", textAlign: "center", padding: 40 }}>
        Loading COT data…
      </div>
    );
  }

  if (cotLoadState === "error" || !cotReport) {
    return (
      <div className="card" style={{ color: "var(--severity-high)", fontSize: "var(--text-sm)", textAlign: "center", padding: 40 }}>
        {cotError ?? "COT data unavailable"}
      </div>
    );
  }

  const filteredLegacy = selectedCurrency === "ALL"
    ? cotReport.legacy
    : cotReport.legacy.filter((r) => r.currency === selectedCurrency);

  const filteredTff = selectedCurrency === "ALL"
    ? cotReport.tff
    : cotReport.tff.filter((r) => r.currency === selectedCurrency);

  // ─── Render ──────────────────────────────────────────────────────────────────

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <p style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
            Report Date: <strong style={{ color: "var(--text-secondary)" }}>{cotReport.reportDate}</strong>
            &nbsp;·&nbsp;Published: <strong style={{ color: "var(--text-secondary)" }}>{cotReport.publishDate}</strong>
            &nbsp;·&nbsp;Source: <strong style={{ color: "var(--text-secondary)" }}>CFTC Legacy + TFF</strong>
          </p>
        </div>

        {/* Currency filter */}
        <select
          id="cot-currency-select"
          value={selectedCurrency}
          onChange={(e) => setSelectedCurrency(e.target.value)}
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: "var(--card-radius-sm)",
            color: "var(--text-primary)",
            fontSize: "var(--text-sm)",
            padding: "6px 10px",
            cursor: "pointer",
          }}
        >
          {ALL_CURRENCIES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      {/* Legacy Report Table */}
      <div>
        <h3 style={{ margin: "0 0 10px", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Legacy Report — Non-Commercial Positioning
        </h3>
        <DataTable data={filteredLegacy} columns={LEGACY_COLS} emptyText="No data for selected currency" />
      </div>

      {/* TFF Report Table */}
      <div>
        <h3 style={{ margin: "0 0 10px", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          TFF Report — Disaggregated Positioning
        </h3>
        <DataTable data={filteredTff} columns={TFF_COLS} emptyText="No data for selected currency" />
      </div>

      {/* COT Index Sparklines */}
      <div>
        <h3 style={{ margin: "0 0 12px", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          COT Index — 12-Week Trend
        </h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
          {Object.entries(cotReport.cot_indices)
            .filter(([ccy]) => selectedCurrency === "ALL" || ccy === selectedCurrency)
            .map(([ccy, data]) => {
              const isExtreme = data.index > 80 || data.index < 20;
              return (
                <div
                  key={ccy}
                  className="card"
                  style={{
                    padding: "12px 16px",
                    borderLeft: `3px solid ${data.index > 60 ? "var(--accent-bull)" : data.index < 40 ? "var(--accent-bear)" : "var(--border)"}`,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                    <span style={{ fontWeight: 700, fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)" }}>{ccy}</span>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "var(--text-base)",
                        fontWeight: 700,
                        color: data.index > 60 ? "var(--accent-bull)" : data.index < 40 ? "var(--accent-bear)" : "var(--text-secondary)",
                      }}>
                        {data.index}
                      </span>
                      {isExtreme && <Badge variant="high" size="sm">EXTREME</Badge>}
                    </div>
                  </div>
                  <Sparkline data={data.trend_12w} height={32} />
                </div>
              );
            })}
        </div>
      </div>
    </div>
  );
}
