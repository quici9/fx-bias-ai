"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useUiStore } from "@/lib/store/uiStore";

// ─── Types ────────────────────────────────────────────────────────────────────

type RouteKey = "1" | "2";

const ROUTE_MAP: Record<RouteKey, string> = {
  "1": "/",
  "2": "/audit",
};

// ─── Hook ─────────────────────────────────────────────────────────────────────

/**
 * F4-03h / F1-05f: Global keyboard shortcuts
 *
 * `1`     → Dashboard
 * `2`     → Data Audit
 * `←`     → Previous week
 * `→`     → Next week
 * `Esc`   → Close current slide panel / overlay
 * `?`     → Toggle shortcut overlay
 */
export function useKeyboardShortcuts() {
  const router = useRouter();

  const selectedWeek = useUiStore((s) => s.selectedWeek);
  const availableWeeks = useUiStore((s) => s.availableWeeks);
  const setSelectedWeek = useUiStore((s) => s.setSelectedWeek);
  const closeSlidePanel = useUiStore((s) => s.closeSlidePanel);
  const slidePanelOpen = useUiStore((s) => s.slidePanelOpen);
  const toggleShortcutOverlay = useUiStore((s) => s.toggleShortcutOverlay);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore shortcuts when focus is inside an input/textarea/select
      const target = e.target as HTMLElement;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        target.isContentEditable
      ) {
        return;
      }

      // Ignore modifier key combos
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      const allOptions = ["latest", ...availableWeeks];
      const currentIndex = allOptions.indexOf(selectedWeek);

      switch (e.key) {
        case "1":
        case "2":
          router.push(ROUTE_MAP[e.key as RouteKey]);
          break;

        case "ArrowLeft": {
          const prevIndex = currentIndex - 1;
          if (prevIndex >= 0) {
            const prev = allOptions[prevIndex];
            if (prev) setSelectedWeek(prev);
          }
          break;
        }

        case "ArrowRight": {
          const nextIndex = currentIndex + 1;
          if (nextIndex < allOptions.length) {
            const next = allOptions[nextIndex];
            if (next) setSelectedWeek(next);
          }
          break;
        }

        case "Escape":
          if (slidePanelOpen) {
            closeSlidePanel();
          }
          break;

        case "?":
          toggleShortcutOverlay();
          break;

        default:
          break;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    router,
    selectedWeek,
    availableWeeks,
    setSelectedWeek,
    closeSlidePanel,
    slidePanelOpen,
    toggleShortcutOverlay,
  ]);
}
