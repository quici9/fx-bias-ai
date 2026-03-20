"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface AccuracyDataPoint {
  week: string;
  accuracy: number;
}

interface AccuracyLineChartProps {
  data: AccuracyDataPoint[];
  targetAccuracy?: number; // green target line (default 0.70)
  minAccuracy?: number;   // red minimum line (default 0.65)
  height?: number;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function AccuracyLineChart({
  data,
  targetAccuracy = 0.7,
  minAccuracy = 0.65,
  height = 200,
}: AccuracyLineChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart
        data={data}
        margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
      >
        <XAxis
          dataKey="week"
          tick={{ fill: "var(--text-muted)", fontSize: 10 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          domain={[0.4, 1.0]}
          tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
          tick={{ fill: "var(--text-muted)", fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          width={36}
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
            "Accuracy",
          ]}
        />

        {/* Target line */}
        <ReferenceLine
          y={targetAccuracy}
          stroke="var(--accent-neutral)"
          strokeDasharray="4 4"
          label={{
            value: `Target ${(targetAccuracy * 100).toFixed(0)}%`,
            fill: "var(--accent-neutral)",
            fontSize: 10,
            position: "insideTopRight",
          }}
        />

        {/* Minimum threshold line */}
        <ReferenceLine
          y={minAccuracy}
          stroke="var(--severity-high)"
          strokeDasharray="4 4"
          label={{
            value: `Min ${(minAccuracy * 100).toFixed(0)}%`,
            fill: "var(--severity-high)",
            fontSize: 10,
            position: "insideBottomRight",
          }}
        />

        <Line
          type="monotone"
          dataKey="accuracy"
          stroke="var(--brand)"
          strokeWidth={2}
          dot={{ fill: "var(--brand)", r: 3, strokeWidth: 0 }}
          activeDot={{ r: 5, fill: "var(--brand)" }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
