import type { BiasReport } from "@/lib/types";
import { fetchBiasData } from "./fetchBiasData";
import { DATA_BASE_URL } from "./base-url";

// ─── Historical Weeks Discovery ───────────────────────────────────────────────

interface WeekIndex {
  available_weeks: string[];
}

/**
 * Fetches the list of available historical weeks from the auto-generated
 * index.json. The backend writes this file after each pipeline run.
 * Excludes currentWeekLabel (already served by bias-latest.json).
 */
export async function getAvailableWeeks(
  currentWeekLabel?: string
): Promise<string[]> {
  try {
    const url = `${DATA_BASE_URL}/data/history/bias/index.json`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const index: WeekIndex = await res.json();
    const weeks = index.available_weeks ?? [];
    // Exclude current week — it's already shown via bias-latest.json
    return currentWeekLabel
      ? weeks.filter((w) => w !== currentWeekLabel)
      : weeks;
  } catch (err) {
    console.error("[getAvailableWeeks] Failed to load index.json:", err);
    return [];
  }
}

// ─── Fetcher ─────────────────────────────────────────────────────────────────

/**
 * Fetches multiple historical bias reports in parallel.
 * Returns a map of weekLabel -> BiasReport.
 * Failures for individual weeks are silently dropped (logged to console).
 */
export async function fetchHistoricalBias(
  weeks: string[]
): Promise<Record<string, BiasReport>> {
  if (weeks.length === 0) return {};

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
