import { create } from "zustand";
import type { CotReport, MacroReport, CrossAssetReport, ModelMetrics } from "@/lib/types";

// ─── Types ────────────────────────────────────────────────────────────────────

type LoadState = "idle" | "loading" | "success" | "error" | "stale";

interface AuditState {
  // Data slices
  cotReport: CotReport | null;
  macroReport: MacroReport | null;
  crossAssetReport: CrossAssetReport | null;
  modelMetrics: ModelMetrics | null;
  modelMetricsHistory: ModelMetrics[]; // last 12 weeks

  // Load states per slice
  cotLoadState: LoadState;
  macroLoadState: LoadState;
  crossAssetLoadState: LoadState;
  modelMetricsLoadState: LoadState;

  // Errors per slice
  cotError: string | null;
  macroError: string | null;
  crossAssetError: string | null;
  modelMetricsError: string | null;

  // Actions — COT
  setCotReport: (report: CotReport) => void;
  setCotLoadState: (state: LoadState) => void;
  setCotError: (error: string | null) => void;

  // Actions — Macro
  setMacroReport: (report: MacroReport) => void;
  setMacroLoadState: (state: LoadState) => void;
  setMacroError: (error: string | null) => void;

  // Actions — Cross-Asset
  setCrossAssetReport: (report: CrossAssetReport) => void;
  setCrossAssetLoadState: (state: LoadState) => void;
  setCrossAssetError: (error: string | null) => void;

  // Actions — Model Metrics
  setModelMetrics: (metrics: ModelMetrics) => void;
  addModelMetricsToHistory: (metrics: ModelMetrics) => void;
  setModelMetricsLoadState: (state: LoadState) => void;
  setModelMetricsError: (error: string | null) => void;
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useAuditStore = create<AuditState>((set) => ({
  cotReport: null,
  macroReport: null,
  crossAssetReport: null,
  modelMetrics: null,
  modelMetricsHistory: [],

  cotLoadState: "idle",
  macroLoadState: "idle",
  crossAssetLoadState: "idle",
  modelMetricsLoadState: "idle",

  cotError: null,
  macroError: null,
  crossAssetError: null,
  modelMetricsError: null,

  setCotReport: (report) =>
    set({ cotReport: report, cotLoadState: "success", cotError: null }),

  setCotLoadState: (state) => set({ cotLoadState: state }),

  setCotError: (error) => set({ cotError: error, cotLoadState: "error" }),

  setMacroReport: (report) =>
    set({ macroReport: report, macroLoadState: "success", macroError: null }),

  setMacroLoadState: (state) => set({ macroLoadState: state }),

  setMacroError: (error) => set({ macroError: error, macroLoadState: "error" }),

  setCrossAssetReport: (report) =>
    set({
      crossAssetReport: report,
      crossAssetLoadState: "success",
      crossAssetError: null,
    }),

  setCrossAssetLoadState: (state) => set({ crossAssetLoadState: state }),

  setCrossAssetError: (error) =>
    set({ crossAssetError: error, crossAssetLoadState: "error" }),

  setModelMetrics: (metrics) =>
    set({
      modelMetrics: metrics,
      modelMetricsLoadState: "success",
      modelMetricsError: null,
    }),

  addModelMetricsToHistory: (metrics) =>
    set((state) => {
      const MAX_HISTORY = 12;
      const exists = state.modelMetricsHistory.some((m) => m.week === metrics.week);
      if (exists) return {};
      const next = [metrics, ...state.modelMetricsHistory].slice(0, MAX_HISTORY);
      return { modelMetricsHistory: next };
    }),

  setModelMetricsLoadState: (state) => set({ modelMetricsLoadState: state }),

  setModelMetricsError: (error) =>
    set({ modelMetricsError: error, modelMetricsLoadState: "error" }),
}));

// ─── Selectors ────────────────────────────────────────────────────────────────

/** True when at least one data source is in error or stale state */
export function selectHasAuditIssues(state: AuditState): boolean {
  return (
    state.cotLoadState === "error" ||
    state.macroLoadState === "error" ||
    state.crossAssetLoadState === "error" ||
    state.cotLoadState === "stale" ||
    state.macroLoadState === "stale" ||
    state.crossAssetLoadState === "stale"
  );
}
