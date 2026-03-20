import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/shell/Sidebar";
import { Header } from "@/components/shell/Header";
import { KeyboardProvider } from "@/components/shell/KeyboardProvider";

// ─── Metadata ─────────────────────────────────────────────────────────────────

export const metadata: Metadata = {
  title: "FX Bias AI — Prediction Dashboard",
  description:
    "Weekly FX directional bias powered by COT, macro, and cross-asset signals. Transparent, model-driven trading intelligence.",
  keywords: ["forex", "bias", "cot", "macro", "prediction", "trading"],
};

// ─── Root Layout ──────────────────────────────────────────────────────────────

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" data-theme="dark">
      <body>
        <KeyboardProvider>
          <div
            id="app-shell"
            style={{
              display: "flex",
              minHeight: "100dvh",
              background: "var(--bg-primary)",
            }}
          >
            {/* Fixed sidebar — width is controlled by the Sidebar component */}
            <Sidebar />

            {/* Main content area */}
            <div
              id="main-wrapper"
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                marginLeft: "var(--sidebar-width)",
                minWidth: 0,
                transition: "margin-left var(--transition-base)",
              }}
            >
              <Header />

              <main
                id="page-content"
                style={{
                  flex: 1,
                  padding: "var(--content-padding)",
                  overflowY: "auto",
                }}
              >
                {children}
              </main>
            </div>
          </div>
        </KeyboardProvider>
      </body>
    </html>
  );
}
