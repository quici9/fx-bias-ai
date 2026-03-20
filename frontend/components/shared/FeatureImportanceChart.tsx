"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface FeatureImportanceEntry {
  name: string;
  importance: number; // 0–1
}

interface FeatureImportanceChartProps {
  data: FeatureImportanceEntry[];
  maxItems?: number;
  height?: number;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function FeatureImportanceChart({
  data,
  maxItems = 10,
  height = 320,
}: FeatureImportanceChartProps) {
  const sorted = [...data]
    .sort((a, b) => b.importance - a.importance)
    .slice(0, maxItems);

  const getColor = (value: number) => {
    if (value >= 0.4) return "var(--brand)";
    if (value >= 0.2) return "var(--accent-bull)";
    return "var(--text-muted)";
  };

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={sorted}
        layout="vertical"
        margin={{ top: 0, right: 16, bottom: 0, left: 120 }}
      >
        <XAxis
          type="number"
          domain={[0, 1]}
          tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
          tick={{ fill: "var(--text-muted)", fontSize: 11 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="name"
          width={115}
          tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          contentStyle={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            fontSize: "var(--text-xs)",
            color: "var(--text-primary)",
          }}
          formatter={(value: unknown) => [
            typeof value === "number" ? `${(value * 100).toFixed(1)}%` : String(value),
            "Importance",
          ]}
        />
        <Bar dataKey="importance" radius={[0, 4, 4, 0]}>
          {sorted.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={getColor(entry.importance)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
