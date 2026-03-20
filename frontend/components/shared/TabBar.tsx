"use client";

import { clsx } from "clsx";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface TabItem {
  id: string;
  label: string;
  badge?: string | number;
  disabled?: boolean;
}

interface TabBarProps {
  tabs: TabItem[];
  activeTab: string;
  onTabChange: (id: string) => void;
  className?: string;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function TabBar({ tabs, activeTab, onTabChange, className }: TabBarProps) {
  return (
    <div
      className={clsx(className)}
      role="tablist"
      style={{
        display: "flex",
        gap: 2,
        borderBottom: "1px solid var(--border)",
        overflowX: "auto",
        scrollbarWidth: "none",
      }}
    >
      {tabs.map((tab) => {
        const isActive = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={isActive}
            aria-controls={`panel-${tab.id}`}
            disabled={tab.disabled}
            onClick={() => !tab.disabled && onTabChange(tab.id)}
            style={{
              padding: "10px 16px",
              background: "transparent",
              border: "none",
              borderBottom: isActive ? "2px solid var(--brand)" : "2px solid transparent",
              color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
              fontWeight: isActive ? 500 : 400,
              fontSize: "var(--text-sm)",
              cursor: tab.disabled ? "not-allowed" : "pointer",
              opacity: tab.disabled ? 0.5 : 1,
              display: "flex",
              alignItems: "center",
              gap: 6,
              whiteSpace: "nowrap",
              transition: "color var(--transition-fast), border-color var(--transition-fast)",
              outline: "none",
              flexShrink: 0,
            }}
          >
            {tab.label}
            {tab.badge !== undefined && (
              <span
                style={{
                  padding: "1px 6px",
                  background: isActive ? "var(--brand-muted)" : "var(--bg-card-hover)",
                  borderRadius: 10,
                  fontSize: "var(--text-xs)",
                  color: isActive ? "var(--brand)" : "var(--text-muted)",
                  fontWeight: 600,
                }}
              >
                {tab.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
