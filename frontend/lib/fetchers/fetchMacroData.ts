import type { MacroReport } from "@/lib/types";
import { DATA_BASE_URL } from "./base-url";

const CACHE_TTL_MS = 60 * 60 * 1000;

const cache = new Map<string, { data: MacroReport; fetchedAt: number }>();

function isMacroReport(value: unknown): value is MacroReport {
  if (!value || typeof value !== "object") return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.fetchDate === "string" &&
    Array.isArray(obj.policy_rates) &&
    typeof obj.vix === "object"
  );
}

export async function fetchMacroData(force = false): Promise<MacroReport> {
  const cacheKey = "macro-latest";
  if (!force) {
    const entry = cache.get(cacheKey);
    if (entry && Date.now() - entry.fetchedAt < CACHE_TTL_MS) {
      return entry.data;
    }
  }

  const response = await fetch(`${DATA_BASE_URL}/data/macro-latest.json`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch macro data: ${response.status}`);
  }

  const raw: unknown = await response.json();
  if (!isMacroReport(raw)) {
    throw new Error("Invalid MacroReport schema");
  }

  cache.set(cacheKey, { data: raw, fetchedAt: Date.now() });
  return raw;
}
