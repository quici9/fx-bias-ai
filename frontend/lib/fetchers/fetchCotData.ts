import type { CotReport } from "@/lib/types";

const CACHE_TTL_MS = 60 * 60 * 1000;
const BASE_URL = process.env.NEXT_PUBLIC_DATA_BASE_URL ?? "";

const cache = new Map<string, { data: CotReport; fetchedAt: number }>();

function isCotReport(value: unknown): value is CotReport {
  if (!value || typeof value !== "object") return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.reportDate === "string" &&
    Array.isArray(obj.legacy) &&
    Array.isArray(obj.tff)
  );
}

export async function fetchCotData(force = false): Promise<CotReport> {
  const cacheKey = "cot-latest";
  if (!force) {
    const entry = cache.get(cacheKey);
    if (entry && Date.now() - entry.fetchedAt < CACHE_TTL_MS) {
      return entry.data;
    }
  }

  const response = await fetch(`${BASE_URL}/data/cot-latest.json`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch COT data: ${response.status}`);
  }

  const raw: unknown = await response.json();
  if (!isCotReport(raw)) {
    throw new Error("Invalid CotReport schema");
  }

  cache.set(cacheKey, { data: raw, fetchedAt: Date.now() });
  return raw;
}
