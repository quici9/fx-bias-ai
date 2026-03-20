"use client";

import { LineChart, Line, ResponsiveContainer, Tooltip } from "recharts";

// ─── Types ────────────────────────────────────────────────────────────────────

interface SparklineProps {
  data: number[];
  color?: string;
  height?: number;
  width?: number;
  showTooltip?: boolean;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function Sparkline({
  data,
  color = "var(--brand)",
  height = 32,
  width,
  showTooltip = false,
}: SparklineProps) {
  const chartData = data.map((value, index) => ({ index, value }));

  return (
    <ResponsiveContainer width={width ?? "100%"} height={height}>
      <LineChart data={chartData} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
        <Line
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
        {showTooltip && (
          <Tooltip
            contentStyle={{
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              fontSize: "var(--text-xs)",
              color: "var(--text-primary)",
              padding: "4px 8px",
            }}
            formatter={(value: unknown) => [
              typeof value === "number" ? value.toFixed(1) : String(value),
              "",
            ]}
            labelFormatter={() => ""}
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}
