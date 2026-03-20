import type { BiasReport } from "@/lib/types";
import { fetchBiasData } from "./fetchBiasData";

// ─── Historical Weeks Index ───────────────────────────────────────────────────

// Hardcoded set of available historical weeks — backend should write a manifest
// file in the future so the frontend doesn't need to know this list.
const AVAILABLE_WEEKS = [
  "2026-W12",
  "2026-W11",
  "2026-W10",
  "2026-W09",
];

export function getAvailableWeeks(): string[] {
  return AVAILABLE_WEEKS;
}

// ─── Fetcher ─────────────────────────────────────────────────────────────────

/**
 * Fetches multiple historical bias reports in parallel.
 * Returns a map of weekLabel -> BiasReport.
 * Failures for individual weeks are silently dropped (logged to console).
 */
export async function fetchHistoricalBias(
  weeks: string[] = AVAILABLE_WEEKS
): Promise<Record<string, BiasReport>> {
  const results = await Promise.allSettled(
    weeks.map((week) => fetchBiasData({ week }))
  );

  const map: Record<string, BiasReport> = {};

  results.forEach((result, index) => {
    const week = weeks[index];
    if (!week) return;
    if (result.status === "fulfilled") {
      map[week] = result.value;
    } else {
      console.error(`[fetchHistoricalBias] Failed for ${week}:`, result.reason);
    }
  });

  return map;
}
