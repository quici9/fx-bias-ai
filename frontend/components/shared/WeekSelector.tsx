"use client";

import { useEffect, useRef, useState } from "react";
import { getAvailableWeeks } from "@/lib/fetchers/fetchHistorical";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Props {
  currentWeek: string;        // "latest" | "2026-W11" etc.
  onWeekChange: (week: string) => void;
  isLoading?: boolean;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatWeekLabel(week: string): string {
  if (week === "latest") return "Current Week";
  // "2026-W12" → "W12 · 2026"
  const [year, w] = week.split("-");
  return `${w} · ${year}`;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function WeekSelector({ currentWeek, onWeekChange, isLoading }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Dynamic week list fetched from history/bias/index.json
  const [historicalWeeks, setHistoricalWeeks] = useState<string[]>([]);
  useEffect(() => {
    getAvailableWeeks().then(setHistoricalWeeks).catch(() => {});
  }, []);

  const weeks = ["latest", ...historicalWeeks];
  const selectedLabel = formatWeekLabel(currentWeek);

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Close on Escape
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, []);

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      {/* Trigger button */}
      <button
        id="week-selector-btn"
        onClick={() => setOpen((v) => !v)}
        disabled={isLoading}
        aria-haspopup="listbox"
        aria-expanded={open}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          padding: "4px 10px",
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          color: "var(--text-primary)",
          fontSize: "var(--text-sm)",
          fontFamily: "var(--font-mono)",
          cursor: isLoading ? "not-allowed" : "pointer",
          opacity: isLoading ? 0.6 : 1,
          transition: "border-color 0.15s, background 0.15s",
        }}
      >
        {/* Calendar icon */}
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
          <rect x="1" y="3" width="14" height="12" rx="2"/>
          <path d="M1 7h14"/>
          <path d="M5 1v4M11 1v4"/>
        </svg>
        {selectedLabel}
        {/* Chevron */}
        <svg
          width="10"
          height="10"
          viewBox="0 0 10 10"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          style={{
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.15s",
            marginLeft: 2,
            color: "var(--text-muted)",
          }}
        >
          <path d="M2 3.5l3 3 3-3"/>
        </svg>
      </button>

      {/* Dropdown */}
      {open && (
        <ul
          role="listbox"
          aria-label="Select week"
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: 0,
            minWidth: 160,
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "4px 0",
            listStyle: "none",
            margin: 0,
            zIndex: 50,
            boxShadow: "0 8px 24px rgba(0,0,0,0.3)",
          }}
        >
          {weeks.map((week) => {
            const isSelected = week === currentWeek;
            return (
              <li
                key={week}
                role="option"
                aria-selected={isSelected}
                onClick={() => {
                  onWeekChange(week);
                  setOpen(false);
                }}
                style={{
                  padding: "7px 14px",
                  cursor: "pointer",
                  fontSize: "var(--text-sm)",
                  fontFamily: "var(--font-mono)",
                  color: isSelected ? "var(--accent-bull)" : "var(--text-primary)",
                  background: isSelected ? "rgba(var(--accent-bull-rgb, 52,211,153), 0.08)" : "transparent",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 8,
                  transition: "background 0.1s",
                }}
                onMouseEnter={(e) => {
                  if (!isSelected) {
                    (e.currentTarget as HTMLElement).style.background = "var(--surface-3, var(--surface-1))";
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isSelected) {
                    (e.currentTarget as HTMLElement).style.background = "transparent";
                  }
                }}
              >
                <span>{formatWeekLabel(week)}</span>
                {isSelected && (
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M2 6l3 3 5-5"/>
                  </svg>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
