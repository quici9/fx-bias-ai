"use client";

import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { useUiStore } from "@/lib/store/uiStore";
import { useBiasStore } from "@/lib/store/biasStore";
import { StatusDot } from "@/components/shared/StatusDot";

// ─── Week Picker ──────────────────────────────────────────────────────────────

function WeekPicker() {
  const selectedWeek = useUiStore((s) => s.selectedWeek);
  const availableWeeks = useUiStore((s) => s.availableWeeks);
  const setSelectedWeek = useUiStore((s) => s.setSelectedWeek);
  const biasSetSelectedWeek = useBiasStore((s) => s.setSelectedWeek);

  // Array order: newest first → ["latest", "2026-W12", "2026-W10", "2026-W09"]
  // index 0 = newest (latest), last index = oldest
  const allOptions = ["latest", ...availableWeeks];
  const currentIndex = allOptions.indexOf(selectedWeek);

  const canGoOlder = currentIndex < allOptions.length - 1; // more past weeks exist
  const canGoNewer = currentIndex > 0;                     // a newer week exists

  const navigate = (direction: "older" | "newer") => {
    const nextIndex = direction === "older" ? currentIndex + 1 : currentIndex - 1;
    if (nextIndex < 0 || nextIndex >= allOptions.length) return;
    const next = allOptions[nextIndex];
    if (!next) return;
    setSelectedWeek(next);
    biasSetSelectedWeek(next);
  };

  const displayLabel =
    selectedWeek === "latest"
      ? "Current Week"
      : selectedWeek;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
      {/* ← goes to older (past) weeks */}
      <button
        onClick={() => navigate("older")}
        disabled={!canGoOlder}
        aria-label="Previous week (older)"
        style={{
          width: 28,
          height: 28,
          background: "transparent",
          border: "1px solid var(--border)",
          borderRadius: 6,
          color: !canGoOlder ? "var(--text-muted)" : "var(--text-secondary)",
          cursor: !canGoOlder ? "not-allowed" : "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <ChevronLeft size={14} />
      </button>

      <div
        style={{
          padding: "4px 12px",
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          fontSize: "var(--text-sm)",
          color: "var(--text-primary)",
          fontWeight: 500,
          fontFamily: selectedWeek !== "latest" ? "var(--font-mono)" : undefined,
          minWidth: 120,
          textAlign: "center",
        }}
      >
        {displayLabel}
      </div>

      {/* → goes to newer (current) weeks */}
      <button
        onClick={() => navigate("newer")}
        disabled={!canGoNewer}
        aria-label="Next week (newer)"
        style={{
          width: 28,
          height: 28,
          background: "transparent",
          border: "1px solid var(--border)",
          borderRadius: 6,
          color: !canGoNewer ? "var(--text-muted)" : "var(--text-secondary)",
          cursor: !canGoNewer ? "not-allowed" : "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <ChevronRight size={14} />
      </button>
    </div>
  );
}


// ─── Header ───────────────────────────────────────────────────────────────────

export function Header() {
  const currentReport = useBiasStore((s) => s.currentReport);
  const loadState = useBiasStore((s) => s.loadState);

  const pipelineStatus = currentReport?.meta.dataSourceStatus;
  const allOk = pipelineStatus
    ? Object.values(pipelineStatus).every((s) => s === "OK")
    : null;

  const cotStatus = pipelineStatus?.cot ?? null;
  const macroStatus = pipelineStatus?.macro ?? null;

  return (
    <header
      style={{
        height: "var(--header-height)",
        background: "var(--bg-header)",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        alignItems: "center",
        padding: "0 var(--content-padding)",
        gap: 16,
        position: "sticky",
        top: 0,
        zIndex: 40,
      }}
    >
      {/* Week Picker */}
      <WeekPicker />

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Pipeline Status */}
      {loadState === "success" && (
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
            Data sources:
          </span>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <StatusDot
              status={cotStatus === "OK" ? "ok" : cotStatus === "STALE" ? "warn" : cotStatus ? "error" : "unknown"}
              label="COT"
            />
            <StatusDot
              status={macroStatus === "OK" ? "ok" : macroStatus === "STALE" ? "warn" : macroStatus ? "error" : "unknown"}
              label="Macro"
            />
            {allOk !== null && (
              <span
                style={{
                  fontSize: "var(--text-xs)",
                  color: allOk ? "var(--accent-bull)" : "var(--severity-medium)",
                  fontWeight: 500,
                }}
              >
                {allOk ? "All OK" : "Issues"}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Loading indicator */}
      {loadState === "loading" && (
        <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--text-muted)" }}>
          <RefreshCw size={14} style={{ animation: "spin 1s linear infinite" }} />
          <span style={{ fontSize: "var(--text-xs)" }}>Loading…</span>
        </div>
      )}

      {/* Generated at */}
      {currentReport && (
        <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
          {new Date(currentReport.meta.generatedAt).toUTCString().slice(0, 22)}
        </div>
      )}
    </header>
  );
}
