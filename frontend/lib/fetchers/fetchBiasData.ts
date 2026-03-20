import type { BiasReport } from "@/lib/types";

// ─── Constants ───────────────────────────────────────────────────────────────

const CACHE_TTL_MS = 60 * 60 * 1000; // 1 hour
const SUPPORTED_FEATURE_VERSION = "v1.2";
const BASE_URL = process.env.NEXT_PUBLIC_DATA_BASE_URL ?? "";

// ─── Cache ────────────────────────────────────────────────────────────────────

interface CacheEntry {
  data: BiasReport;
  fetchedAt: number;
}

const cache = new Map<string, CacheEntry>();

function getCached(key: string): BiasReport | null {
  const entry = cache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.fetchedAt > CACHE_TTL_MS) {
    cache.delete(key);
    return null;
  }
  return entry.data;
}

function setCache(key: string, data: BiasReport): void {
  cache.set(key, { data, fetchedAt: Date.now() });
}

// ─── Type Guard ───────────────────────────────────────────────────────────────

export function isBiasReport(value: unknown): value is BiasReport {
  if (!value || typeof value !== "object") return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.meta === "object" &&
    Array.isArray((obj as { predictions?: unknown }).predictions) &&
    typeof obj.pair_recommendations === "object" &&
    Array.isArray((obj as { weekly_alerts?: unknown }).weekly_alerts)
  );
}

// ─── Schema Version Check ─────────────────────────────────────────────────────

function checkFeatureVersion(report: BiasReport): void {
  const version = report.meta.featureVersion;
  if (!version.startsWith(SUPPORTED_FEATURE_VERSION)) {
    console.warn(
      `[fetchBiasData] featureVersion mismatch: expected ${SUPPORTED_FEATURE_VERSION}.x, got ${version}`
    );
  }
}

// ─── Fetcher ───────────────────────────────────────────────────────────────────

export interface FetchBiasOptions {
  /** "latest" fetches bias-latest.json; a weekLabel fetches from history */
  week?: string;
  /** Force bypass cache */
  force?: boolean;
}

export async function fetchBiasData(
  options: FetchBiasOptions = {}
): Promise<BiasReport> {
  const { week = "latest", force = false } = options;

  const cacheKey = week;
  if (!force) {
    const cached = getCached(cacheKey);
    if (cached) return cached;
  }

  const url =
    week === "latest"
      ? `${BASE_URL}/data/bias-latest.json`
      : `${BASE_URL}/data/history/bias/${week}.json`;

  const response = await fetch(url, { cache: "no-store" });

  if (!response.ok) {
    throw new Error(
      `Failed to fetch bias data for ${week}: ${response.status} ${response.statusText}`
    );
  }

  const raw: unknown = await response.json();

  if (!isBiasReport(raw)) {
    throw new Error(`Invalid BiasReport schema for week: ${week}`);
  }

  checkFeatureVersion(raw);
  setCache(cacheKey, raw);

  return raw;
}
