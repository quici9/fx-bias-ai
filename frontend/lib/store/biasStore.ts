import { create } from "zustand";
import type { BiasReport, CurrencyPrediction, Alert } from "@/lib/types";

// ─── Types ────────────────────────────────────────────────────────────────────

type LoadState = "idle" | "loading" | "success" | "error" | "stale";

interface BiasState {
  // Data
  currentReport: BiasReport | null;
  historicalReports: Record<string, BiasReport>; // key: weekLabel
  selectedWeek: string; // "2026-W12" | "latest"

  // Loading state
  loadState: LoadState;
  error: string | null;
  lastFetchedAt: number | null;

  // Derived — computed on set
  highAlerts: Alert[];
  sortedPredictions: CurrencyPrediction[]; // sorted by rank

  // Actions
  setReport: (report: BiasReport) => void;
  setHistoricalReport: (week: string, report: BiasReport) => void;
  setSelectedWeek: (week: string) => void;
  setLoadState: (state: LoadState) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function deriveHighAlerts(report: BiasReport | null): Alert[] {
  if (!report) return [];
  return report.weekly_alerts.filter((a) => a.severity === "HIGH");
}

function deriveSortedPredictions(report: BiasReport | null): CurrencyPrediction[] {
  if (!report) return [];
  return [...report.predictions].sort((a, b) => a.rank - b.rank);
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useBiasStore = create<BiasState>((set) => ({
  currentReport: null,
  historicalReports: {},
  selectedWeek: "latest",
  loadState: "idle",
  error: null,
  lastFetchedAt: null,
  highAlerts: [],
  sortedPredictions: [],

  setReport: (report) =>
    set({
      currentReport: report,
      highAlerts: deriveHighAlerts(report),
      sortedPredictions: deriveSortedPredictions(report),
      loadState: "success",
      lastFetchedAt: Date.now(),
      error: null,
    }),

  setHistoricalReport: (week, report) =>
    set((state) => ({
      historicalReports: { ...state.historicalReports, [week]: report },
    })),

  setSelectedWeek: (week) => set({ selectedWeek: week }),

  setLoadState: (loadState) => set({ loadState }),

  setError: (error) => set({ error, loadState: "error" }),

  reset: () =>
    set({
      currentReport: null,
      loadState: "idle",
      error: null,
      lastFetchedAt: null,
      highAlerts: [],
      sortedPredictions: [],
    }),
}));

// ─── Selectors ────────────────────────────────────────────────────────────────

/** Returns the active report — either historical (if week selected) or current */
export function selectActiveReport(state: BiasState): BiasReport | null {
  if (state.selectedWeek === "latest") return state.currentReport;
  return state.historicalReports[state.selectedWeek] ?? state.currentReport;
}

export function selectIsStale(state: BiasState): boolean {
  if (!state.lastFetchedAt) return false;
  const ONE_HOUR = 60 * 60 * 1000;
  return Date.now() - state.lastFetchedAt > ONE_HOUR;
}
