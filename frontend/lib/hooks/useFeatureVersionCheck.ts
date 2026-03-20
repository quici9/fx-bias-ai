"use client";

import { useEffect } from "react";
import { useBiasStore } from "@/lib/store/biasStore";

const SUPPORTED_FEATURE_VERSION = "v1.2";

/**
 * F4-02a: Checks the featureVersion in the loaded BiasReport against the
 * supported version. Exposes the mismatch via a Zustand-compatible
 * signal by writing to sessionStorage for the banner component to read.
 *
 * The banner itself lives in `VersionMismatchBanner`.
 */
export function useFeatureVersionCheck(): { mismatch: boolean; serverVersion: string | null } {
  const currentReport = useBiasStore((s) => s.currentReport);

  if (!currentReport) {
    return { mismatch: false, serverVersion: null };
  }

  const serverVersion = currentReport.meta.featureVersion;
  const mismatch = !serverVersion.startsWith(SUPPORTED_FEATURE_VERSION);

  return { mismatch, serverVersion };
}
