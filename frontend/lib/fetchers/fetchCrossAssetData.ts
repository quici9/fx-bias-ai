import type { CrossAssetReport } from "@/lib/types";
import { DATA_BASE_URL } from "./base-url";

const CACHE_TTL_MS = 60 * 60 * 1000;

const cache = new Map<string, { data: CrossAssetReport; fetchedAt: number }>();

function isCrossAssetReport(value: unknown): value is CrossAssetReport {
  if (!value || typeof value !== "object") return false;
  const obj = value as Record<string, unknown>;
  return typeof obj.fetchDate === "string" && typeof obj.commodities === "object";
}

export async function fetchCrossAssetData(force = false): Promise<CrossAssetReport> {
  const cacheKey = "cross-asset-latest";
  if (!force) {
    const entry = cache.get(cacheKey);
    if (entry && Date.now() - entry.fetchedAt < CACHE_TTL_MS) {
      return entry.data;
    }
  }

  const response = await fetch(`${DATA_BASE_URL}/data/cross-asset-latest.json`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch cross-asset data: ${response.status}`);
  }

  const raw: unknown = await response.json();
  if (!isCrossAssetReport(raw)) {
    throw new Error("Invalid CrossAssetReport schema");
  }

  cache.set(cacheKey, { data: raw, fetchedAt: Date.now() });
  return raw;
}
