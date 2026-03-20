import { create } from "zustand";

// ─── Types ────────────────────────────────────────────────────────────────────

export type ActiveTab =
  | "cot"
  | "macro"
  | "cross-asset"
  | "features"
  | "diagnostics";

interface UiState {
  // Sidebar
  sidebarCollapsed: boolean;

  // Slide panel
  slidePanelOpen: boolean;
  slidePanelCurrency: string | null;

  // Week navigation (shared across Dashboard + Audit)
  selectedWeek: string; // "latest" | "2026-W12"
  availableWeeks: string[];

  // Audit tab
  activeAuditTab: ActiveTab;

  // Theme
  theme: "dark"; // only dark for now — kept for future

  // Keyboard shortcut help overlay
  shortcutOverlayOpen: boolean;

  // Actions
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  openSlidePanel: (currency: string) => void;
  closeSlidePanel: () => void;
  setSelectedWeek: (week: string) => void;
  setAvailableWeeks: (weeks: string[]) => void;
  setActiveAuditTab: (tab: ActiveTab) => void;
  toggleShortcutOverlay: () => void;
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useUiStore = create<UiState>((set) => ({
  sidebarCollapsed: false,
  slidePanelOpen: false,
  slidePanelCurrency: null,
  selectedWeek: "latest",
  availableWeeks: [],
  activeAuditTab: "cot",
  theme: "dark",
  shortcutOverlayOpen: false,

  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),

  openSlidePanel: (currency) =>
    set({ slidePanelOpen: true, slidePanelCurrency: currency }),

  closeSlidePanel: () =>
    set({ slidePanelOpen: false, slidePanelCurrency: null }),

  setSelectedWeek: (week) => set({ selectedWeek: week }),

  setAvailableWeeks: (availableWeeks) => set({ availableWeeks }),

  setActiveAuditTab: (activeAuditTab) => set({ activeAuditTab }),

  toggleShortcutOverlay: () =>
    set((state) => ({ shortcutOverlayOpen: !state.shortcutOverlayOpen })),
}));
