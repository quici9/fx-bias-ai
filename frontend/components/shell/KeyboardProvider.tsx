"use client";

import { useKeyboardShortcuts } from "@/lib/hooks/useKeyboardShortcuts";
import { ShortcutOverlay } from "@/components/shared/ShortcutOverlay";

/**
 * Client component that:
 * 1. Activates global keyboard shortcuts via the hook
 * 2. Renders the ShortcutOverlay (portal-like, fixed position)
 *
 * Mount once in root layout.tsx.
 */
export function KeyboardProvider({ children }: { children: React.ReactNode }) {
  useKeyboardShortcuts();

  return (
    <>
      {children}
      <ShortcutOverlay />
    </>
  );
}
