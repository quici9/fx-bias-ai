/**
 * Tests for biasStore — F1-03d
 * Coverage: setReport, setHistoricalReport, setSelectedWeek, highAlerts derivation,
 * selectActiveReport selector (latest vs historical), selectIsStale.
 */

import { useBiasStore, selectActiveReport, selectIsStale } from "@/lib/store/biasStore";
import type { BiasReport, Currency } from "@/lib/types";

// ─── Fixtures ─────────────────────────────────────────────────────────────────

function makePrediction(currency: Currency, rank: number) {
  return {
    currency,
    bias: "BULL" as const,
    probability: { bull: 0.7, neutral: 0.2, bear: 0.1 },
    confidence: "HIGH" as const,
    rank,
    key_drivers: ["COT Index extreme"],
    alerts: [],
  };
}

function makeReport(weekLabel: string, hasHighAlert = false): BiasReport {
  return {
    meta: {
      weekLabel,
      generatedAt: "2026-03-21T00:00:00Z",
      modelVersion: "1.0.0",
      featureVersion: "1.0",
      overallConfidence: "HIGH",
      dataSourceStatus: { cot: "OK", macro: "OK", cross_asset: "OK", calendar: "OK" },
      pipelineRuntime: 42,
    },
    predictions: [
      makePrediction("USD" as Currency, 1),
      makePrediction("EUR" as Currency, 2),
      makePrediction("GBP" as Currency, 3),
      makePrediction("JPY" as Currency, 4),
    ],
    pair_recommendations: {
      strong_long: [{ pair: "USD/JPY", spread: 1.8, base_currency: "USD", quote_currency: "JPY", confidence: "HIGH" }],
      strong_short: [],
      avoid: [],
    },
    weekly_alerts: hasHighAlert
      ? [{ type: "EXTREME_POSITIONING", currency: "USD", message: "USD net long near 52w max", severity: "HIGH" }]
      : [{ type: "MOMENTUM_DECEL", currency: "EUR", message: "EUR momentum slowing", severity: "MEDIUM" }],
  };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function resetStore() {
  useBiasStore.getState().reset();
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("biasStore — load & state transitions", () => {
  beforeEach(resetStore);

  it("should start in idle state with no data", () => {
    const state = useBiasStore.getState();
    expect(state.loadState).toBe("idle");
    expect(state.currentReport).toBeNull();
    expect(state.highAlerts).toHaveLength(0);
    expect(state.sortedPredictions).toHaveLength(0);
    expect(state.selectedWeek).toBe("latest");
  });

  it("should set report and transition to success state", () => {
    const report = makeReport("2026-W12");
    useBiasStore.getState().setReport(report);
    const state = useBiasStore.getState();
    expect(state.loadState).toBe("success");
    expect(state.currentReport).toBe(report);
    expect(state.error).toBeNull();
    expect(state.lastFetchedAt).not.toBeNull();
  });

  it("should set error state correctly", () => {
    useBiasStore.getState().setError("Network timeout");
    const state = useBiasStore.getState();
    expect(state.loadState).toBe("error");
    expect(state.error).toBe("Network timeout");
  });

  it("should clear error when setReport is called after an error", () => {
    useBiasStore.getState().setError("fail");
    useBiasStore.getState().setReport(makeReport("2026-W12"));
    expect(useBiasStore.getState().error).toBeNull();
    expect(useBiasStore.getState().loadState).toBe("success");
  });

  it("should reset to initial state", () => {
    useBiasStore.getState().setReport(makeReport("2026-W12"));
    useBiasStore.getState().reset();
    const state = useBiasStore.getState();
    expect(state.currentReport).toBeNull();
    expect(state.loadState).toBe("idle");
    expect(state.highAlerts).toHaveLength(0);
  });
});

describe("biasStore — highAlerts derivation", () => {
  beforeEach(resetStore);

  it("should derive highAlerts when report has HIGH severity alert", () => {
    useBiasStore.getState().setReport(makeReport("2026-W12", true));
    const { highAlerts } = useBiasStore.getState();
    expect(highAlerts).toHaveLength(1);
    expect(highAlerts[0].severity).toBe("HIGH");
    expect(highAlerts[0].currency).toBe("USD");
  });

  it("should return empty highAlerts when no HIGH severity alerts", () => {
    useBiasStore.getState().setReport(makeReport("2026-W12", false));
    expect(useBiasStore.getState().highAlerts).toHaveLength(0);
  });
});

describe("biasStore — sortedPredictions", () => {
  beforeEach(resetStore);

  it("should sort predictions by rank ascending", () => {
    const report = makeReport("2026-W12");
    // Shuffle predictions to validate sorting
    report.predictions = [
      makePrediction("JPY" as Currency, 4),
      makePrediction("USD" as Currency, 1),
      makePrediction("GBP" as Currency, 3),
      makePrediction("EUR" as Currency, 2),
    ];
    useBiasStore.getState().setReport(report);
    const { sortedPredictions } = useBiasStore.getState();
    expect(sortedPredictions.map((p) => p.rank)).toEqual([1, 2, 3, 4]);
    expect(sortedPredictions[0].currency).toBe("USD");
  });
});

describe("biasStore — week navigation", () => {
  beforeEach(resetStore);

  it("should default to 'latest' week", () => {
    expect(useBiasStore.getState().selectedWeek).toBe("latest");
  });

  it("should update selectedWeek", () => {
    useBiasStore.getState().setSelectedWeek("2026-W11");
    expect(useBiasStore.getState().selectedWeek).toBe("2026-W11");
  });

  it("should store historical reports by week key", () => {
    const report = makeReport("2026-W11");
    useBiasStore.getState().setHistoricalReport("2026-W11", report);
    const { historicalReports } = useBiasStore.getState();
    expect(historicalReports["2026-W11"]).toBe(report);
  });

  it("should accumulate multiple historical reports", () => {
    useBiasStore.getState().setHistoricalReport("2026-W11", makeReport("2026-W11"));
    useBiasStore.getState().setHistoricalReport("2026-W10", makeReport("2026-W10"));
    const { historicalReports } = useBiasStore.getState();
    expect(Object.keys(historicalReports)).toHaveLength(2);
  });
});

describe("selectActiveReport", () => {
  beforeEach(resetStore);

  it("should return currentReport when selectedWeek is 'latest'", () => {
    const report = makeReport("2026-W12");
    useBiasStore.getState().setReport(report);
    const state = useBiasStore.getState();
    // Use toEqual (not toBe) — Zustand may update reference via spread
    expect(selectActiveReport(state)).toEqual(report);
  });

  it("should return historical report when a past week is selected", () => {
    const current = makeReport("2026-W12");
    const historical = makeReport("2026-W11");
    useBiasStore.getState().setReport(current);
    useBiasStore.getState().setHistoricalReport("2026-W11", historical);
    useBiasStore.getState().setSelectedWeek("2026-W11");
    const state = useBiasStore.getState();
    expect(selectActiveReport(state)).toBe(historical);
  });

  it("should fall back to currentReport if selected historical week not loaded", () => {
    const current = makeReport("2026-W12");
    useBiasStore.getState().setReport(current);
    useBiasStore.getState().setSelectedWeek("2026-W10"); // not loaded
    const state = useBiasStore.getState();
    // Falls back to currentReport (which has weekLabel "2026-W12")
    expect(selectActiveReport(state)).toEqual(current);
  });

  it("should return null if no report loaded and latest is selected", () => {
    const state = useBiasStore.getState();
    expect(selectActiveReport(state)).toBeNull();
  });
});

describe("selectIsStale", () => {
  beforeEach(resetStore);

  it("should return false when never fetched", () => {
    const state = useBiasStore.getState();
    expect(selectIsStale(state)).toBe(false);
  });

  it("should return false when freshly fetched", () => {
    useBiasStore.getState().setReport(makeReport("2026-W12"));
    const state = useBiasStore.getState();
    expect(selectIsStale(state)).toBe(false);
  });

  it("should return true when lastFetchedAt is over 1 hour ago", () => {
    useBiasStore.getState().setReport(makeReport("2026-W12"));
    // Manually set lastFetchedAt to >1 hour ago via Zustand's setState API
    const TWO_HOURS_AGO = Date.now() - 2 * 60 * 60 * 1000;
    useBiasStore.setState({ lastFetchedAt: TWO_HOURS_AGO });
    const state = useBiasStore.getState();
    expect(selectIsStale(state)).toBe(true);
  });
});
