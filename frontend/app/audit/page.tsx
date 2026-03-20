"use client";

import { useState, Suspense } from "react";
import { TabBar, type TabItem } from "@/components/shared/TabBar";
import { CotDataPanel } from "@/components/audit/CotDataPanel";
import { MacroDataPanel } from "@/components/audit/MacroDataPanel";
import { CrossAssetPanel } from "@/components/audit/CrossAssetPanel";
import { FeatureInspector } from "@/components/audit/FeatureInspector";
import { ModelDiagnostics } from "@/components/audit/ModelDiagnostics";
import type { ActiveTab } from "@/lib/store/uiStore";

// ─── Tab config ───────────────────────────────────────────────────────────────

const AUDIT_TABS: TabItem[] = [
  { id: "cot",         label: "COT Data" },
  { id: "macro",       label: "Macro Data" },
  { id: "cross-asset", label: "Cross-Asset" },
  { id: "features",    label: "Feature Inspector" },
  { id: "diagnostics", label: "Model Diagnostics" },
];

// ─── Loading fallback ────────────────────────────────────────────────────────

function TabLoader() {
  return (
    <div
      className="card"
      style={{
        color: "var(--text-muted)",
        fontSize: "var(--text-sm)",
        textAlign: "center",
        padding: 48,
      }}
    >
      Loading…
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function AuditPage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("cot");

  return (
    <div className="animate-stagger" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Page header */}
      <div>
        <h1
          style={{
            margin: 0,
            fontSize: "var(--text-2xl)",
            fontWeight: 700,
            color: "var(--text-primary)",
          }}
        >
          Data Audit
        </h1>
        <p
          style={{
            margin: "4px 0 0",
            fontSize: "var(--text-sm)",
            color: "var(--text-secondary)",
          }}
        >
          Inspect raw inputs, features, and model diagnostics for the selected week.
        </p>
      </div>

      {/* Tab navigation */}
      <TabBar
        tabs={AUDIT_TABS}
        activeTab={activeTab}
        onTabChange={(id) => setActiveTab(id as ActiveTab)}
      />

      {/* Tab panels */}
      <div
        role="tabpanel"
        id={`panel-${activeTab}`}
        aria-labelledby={`tab-${activeTab}`}
      >
        <Suspense fallback={<TabLoader />}>
          {activeTab === "cot"         && <CotDataPanel />}
          {activeTab === "macro"       && <MacroDataPanel />}
          {activeTab === "cross-asset" && <CrossAssetPanel />}
          {activeTab === "features"    && <FeatureInspector />}
          {activeTab === "diagnostics" && <ModelDiagnostics />}
        </Suspense>
      </div>
    </div>
  );
}
