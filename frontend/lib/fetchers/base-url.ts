/**
 * Resolves the base URL for fetching static JSON data files.
 *
 * Priority (highest → lowest):
 *  1. NEXT_PUBLIC_DATA_BASE_URL — explicit override (e.g. CDN, backend API)
 *  2. NEXT_PUBLIC_BASE_PATH     — derived from Next.js basePath (GitHub Pages sub-path)
 *  3. ""                        — local dev running at /
 *
 * Result is always a string with NO trailing slash so callers can do:
 *   `${DATA_BASE_URL}/data/bias-latest.json`
 */
export const DATA_BASE_URL: string = (() => {
  // Explicit override wins
  const explicit = process.env.NEXT_PUBLIC_DATA_BASE_URL;
  if (explicit) return explicit.replace(/\/$/, "");

  // Fall back to basePath (set when deploying to GitHub Pages)
  const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
  return basePath.replace(/\/$/, "");
})();
