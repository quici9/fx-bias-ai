"use client";

import { Keyboard, X } from "lucide-react";
import { useUiStore } from "@/lib/store/uiStore";

// ─── Shortcut entry data ──────────────────────────────────────────────────────

const SHORTCUTS: Array<{ key: string; description: string }> = [
  { key: "1", description: "Go to Dashboard" },
  { key: "2", description: "Go to Data Audit" },
  { key: "←  →", description: "Navigate weeks (previous / next)" },
  { key: "Esc", description: "Close panel / overlay" },
  { key: "?", description: "Toggle this help overlay" },
];

// ─── Component ────────────────────────────────────────────────────────────────

/**
 * F1-05f / F4-03h: Keyboard shortcut help overlay.
 * Toggled by pressing `?` or clicking the keyboard icon in the sidebar.
 */
export function ShortcutOverlay() {
  const open = useUiStore((s) => s.shortcutOverlayOpen);
  const toggle = useUiStore((s) => s.toggleShortcutOverlay);

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        role="presentation"
        onClick={toggle}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0, 0, 0, 0.6)",
          zIndex: 200,
          backdropFilter: "blur(2px)",
        }}
      />

      {/* Panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcut-overlay-title"
        style={{
          position: "fixed",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          zIndex: 201,
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          borderRadius: "var(--card-radius)",
          padding: 24,
          width: 400,
          maxWidth: "calc(100vw - 32px)",
          boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
          animation: "fadeInScale 150ms ease",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 20,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Keyboard size={16} aria-hidden="true" style={{ color: "var(--brand)" }} />
            <h2
              id="shortcut-overlay-title"
              style={{
                margin: 0,
                fontSize: "var(--text-base)",
                fontWeight: 600,
                color: "var(--text-primary)",
              }}
            >
              Keyboard Shortcuts
            </h2>
          </div>

          <button
            onClick={toggle}
            aria-label="Close keyboard shortcuts overlay"
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              color: "var(--text-muted)",
              display: "flex",
              alignItems: "center",
              padding: 4,
              borderRadius: 4,
            }}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        {/* Shortcut list */}
        <ul
          role="list"
          style={{
            margin: 0,
            padding: 0,
            listStyle: "none",
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}
        >
          {SHORTCUTS.map(({ key, description }) => (
            <li
              key={key}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
              }}
            >
              <span
                style={{
                  fontSize: "var(--text-sm)",
                  color: "var(--text-secondary)",
                }}
              >
                {description}
              </span>

              <kbd
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  padding: "3px 8px",
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border)",
                  borderRadius: 5,
                  fontSize: "var(--text-xs)",
                  fontFamily: "var(--font-mono)",
                  color: "var(--text-primary)",
                  whiteSpace: "nowrap",
                }}
              >
                {key}
              </kbd>
            </li>
          ))}
        </ul>

        <p
          style={{
            marginTop: 20,
            marginBottom: 0,
            fontSize: "var(--text-xs)",
            color: "var(--text-muted)",
            textAlign: "center",
          }}
        >
          Shortcuts are disabled when an input field is focused.
        </p>
      </div>
    </>
  );
}
