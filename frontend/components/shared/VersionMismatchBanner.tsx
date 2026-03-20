"use client";

import { AlertTriangle, X } from "lucide-react";
import { useState } from "react";
import { useFeatureVersionCheck } from "@/lib/hooks/useFeatureVersionCheck";

// ─── Component ────────────────────────────────────────────────────────────────

/**
 * F4-02a: Amber banner shown when the loaded BiasReport's featureVersion
 * does not match the version the dashboard was built for.
 *
 * Renders nothing when versions match or no report is loaded.
 */
export function VersionMismatchBanner() {
  const { mismatch, serverVersion } = useFeatureVersionCheck();
  const [dismissed, setDismissed] = useState(false);

  if (!mismatch || dismissed) return null;

  return (
    <aside
      role="alert"
      aria-live="polite"
      aria-atomic="true"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "10px 16px",
        background: "rgba(245, 158, 11, 0.12)",
        border: "1px solid rgba(245, 158, 11, 0.3)",
        borderRadius: "var(--card-radius-sm)",
        marginBottom: 8,
      }}
    >
      <AlertTriangle
        size={15}
        aria-hidden="true"
        style={{ color: "var(--severity-medium)", flexShrink: 0 }}
      />

      <p
        style={{
          margin: 0,
          flex: 1,
          fontSize: "var(--text-sm)",
          color: "var(--text-primary)",
          lineHeight: 1.5,
        }}
      >
        <strong style={{ color: "var(--severity-medium)" }}>Schema mismatch: </strong>
        Dashboard was built for <code style={{ fontFamily: "var(--font-mono)" }}>v1.2.x</code> but
        the loaded data reports{" "}
        <code style={{ fontFamily: "var(--font-mono)" }}>{serverVersion ?? "unknown"}</code>.
        Some values may display incorrectly until the pipeline re-runs.
      </p>

      <button
        onClick={() => setDismissed(true)}
        aria-label="Dismiss schema mismatch warning"
        style={{
          background: "transparent",
          border: "none",
          cursor: "pointer",
          color: "var(--text-muted)",
          display: "flex",
          alignItems: "center",
          padding: 4,
          borderRadius: 4,
          flexShrink: 0,
        }}
      >
        <X size={14} aria-hidden="true" />
      </button>
    </aside>
  );
}
