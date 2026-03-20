"use client";

import { useEffect, useState } from "react";
import { useBiasStore } from "@/lib/store/biasStore";
import { useAuditStore } from "@/lib/store/auditStore";
import { fetchBiasData } from "@/lib/fetchers/fetchBiasData";
import { fetchCotData } from "@/lib/fetchers/fetchCotData";
import { Badge } from "@/components/shared/Badge";
import { VersionMismatchBanner } from "@/components/shared/VersionMismatchBanner";

// Dashboard-specific components
import { AlertBanner } from "@/components/dashboard/AlertBanner";
import { PairRecommendationGrid } from "@/components/dashboard/PairRecommendationGrid";
import { CurrencyStrengthChart } from "@/components/dashboard/CurrencyStrengthChart";
import { AlertDetailSection } from "@/components/dashboard/AlertDetailSection";
import { CurrencyDetailPanel } from "@/components/dashboard/CurrencyDetailPanel";

import type { CurrencyPrediction, PairRecommendation } from "@/lib/types";

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const setReport = useBiasStore((s) => s.setReport);
  const setLoadState = useBiasStore((s) => s.setLoadState);
  const setError = useBiasStore((s) => s.setError);
  const currentReport = useBiasStore((s) => s.currentReport);
  const highAlerts = useBiasStore((s) => s.highAlerts);
  const sortedPredictions = useBiasStore((s) => s.sortedPredictions);
  const loadState = useBiasStore((s) => s.loadState);

  const setCotReport = useAuditStore((s) => s.setCotReport);
  const cotReport = useAuditStore((s) => s.cotReport);

  // Currency detail panel state
  const [selectedPrediction, setSelectedPrediction] = useState<CurrencyPrediction | null>(null);

  // Pair slide panel (not yet implemented in detail — placeholder)
  const [_selectedPair, setSelectedPair] = useState<PairRecommendation | null>(null);
  void _selectedPair; // suppress unused warning

  useEffect(() => {
    if (currentReport) return; // already loaded
    setLoadState("loading");
    fetchBiasData({ week: "latest" })
      .then(setReport)
      .catch((err: Error) => setError(err.message));
  }, [currentReport, setReport, setLoadState, setError]);

  // Pre-fetch COT data for the detail panel sparklines
  useEffect(() => {
    if (cotReport) return;
    fetchCotData()
      .then(setCotReport)
      .catch(() => { /* non-critical */ });
  }, [cotReport, setCotReport]);

  if (loadState === "loading" || loadState === "idle") {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "50vh",
          color: "var(--text-muted)",
          gap: 12,
        }}
      >
        <span
          style={{
            display: "inline-block",
            width: 16,
            height: 16,
            border: "2px solid var(--border)",
            borderTopColor: "var(--accent-bull)",
            borderRadius: "50%",
            animation: "spin 0.8s linear infinite",
          }}
        />
        Loading bias data…
      </div>
    );
  }

  if (loadState === "error" || !currentReport) {
    return (
      <div
        style={{
          padding: 24,
          color: "var(--severity-high)",
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        <strong>Failed to load bias data.</strong>
        <span style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>
          Check that <code>public/data/bias-latest.json</code> exists and is valid JSON.
        </span>
      </div>
    );
  }

  const report = currentReport;

  // Get COT trend for selected currency
  const selectedCotTrend = selectedPrediction && cotReport
    ? cotReport.cot_indices[selectedPrediction.currency]?.trend_12w
    : undefined;

  return (
    <div className="animate-stagger" style={{ display: "flex", flexDirection: "column", gap: 32 }}>
      {/* ── Page header ── */}
      <div>
        <h1
          style={{
            margin: 0,
            fontSize: "var(--text-2xl)",
            fontWeight: 700,
            color: "var(--text-primary)",
          }}
        >
          Weekly Bias Dashboard
        </h1>
        <div
          style={{
            marginTop: 6,
            display: "flex",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 10,
            fontSize: "var(--text-sm)",
            color: "var(--text-secondary)",
          }}
        >
          <span>{report.meta.weekLabel}</span>
          <span style={{ color: "var(--border-strong)" }}>·</span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)" }}>
            {report.meta.modelVersion}
          </span>
          <span style={{ color: "var(--border-strong)" }}>·</span>
          <Badge variant="confidence" value={report.meta.overallConfidence} size="sm" />
          <span style={{ color: "var(--border-strong)" }}>·</span>
          <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
            Generated {new Date(report.meta.generatedAt).toLocaleString()}
          </span>
        </div>
      </div>

      {/* ── F4-02a: Schema Version Mismatch Banner ── */}
      <VersionMismatchBanner />

      {/* ── F2-01: High Priority Alert Banner ── */}
      <AlertBanner alerts={highAlerts} />

      {/* ── F2-03: Currency Strength Chart ── */}
      <CurrencyStrengthChart
        predictions={sortedPredictions}
        onCurrencyClick={(pred) => setSelectedPrediction(pred)}
      />

      {/* ── F2-02: Pair Recommendation Grid ── */}
      <PairRecommendationGrid
        strongLong={report.pair_recommendations.strong_long}
        strongShort={report.pair_recommendations.strong_short}
        avoid={report.pair_recommendations.avoid}
        onPairSelect={(pair) => setSelectedPair(pair)}
      />

      {/* ── F2-04: Alert Detail Section (all alerts) ── */}
      <AlertDetailSection alerts={report.weekly_alerts} />

      {/* ── F2-05: Currency Detail Slide Panel ── */}
      <CurrencyDetailPanel
        prediction={selectedPrediction}
        allAlerts={report.weekly_alerts}
        cotTrend={selectedCotTrend}
        onClose={() => setSelectedPrediction(null)}
      />
    </div>
  );
}
