import { clsx } from "clsx";
import type { Bias, Confidence, Severity } from "@/lib/types";

// ─── Types ────────────────────────────────────────────────────────────────────

type BadgeVariant = "bias" | "confidence" | "severity" | "neutral"
  | "bull" | "bear" | "high" | "medium" | "low";

interface BadgeProps {
  variant: BadgeVariant;
  value?: Bias | Confidence | Severity | string;
  children?: React.ReactNode;
  size?: "sm" | "md";
  className?: string;
}

// ─── Color Maps ───────────────────────────────────────────────────────────────

const BIAS_STYLES: Record<string, { color: string; bg: string; border: string }> = {
  BULL: {
    color: "var(--accent-bull)",
    bg: "var(--accent-bull-glow)",
    border: "rgba(16, 185, 129, 0.3)",
  },
  BEAR: {
    color: "var(--accent-bear)",
    bg: "var(--accent-bear-glow)",
    border: "rgba(239, 68, 68, 0.3)",
  },
  NEUTRAL: {
    color: "var(--accent-neutral)",
    bg: "var(--accent-neutral-muted)",
    border: "rgba(107, 114, 128, 0.3)",
  },
};

const CONFIDENCE_STYLES: Record<string, { color: string; bg: string; border: string }> = {
  HIGH: {
    color: "var(--confidence-high)",
    bg: "rgba(16, 185, 129, 0.08)",
    border: "rgba(16, 185, 129, 0.25)",
  },
  MEDIUM: {
    color: "var(--confidence-medium)",
    bg: "rgba(245, 158, 11, 0.08)",
    border: "rgba(245, 158, 11, 0.25)",
  },
  LOW: {
    color: "var(--confidence-low)",
    bg: "rgba(107, 114, 128, 0.08)",
    border: "rgba(107, 114, 128, 0.25)",
  },
};

const SEVERITY_STYLES: Record<string, { color: string; bg: string; border: string }> = {
  HIGH: {
    color: "var(--severity-high)",
    bg: "var(--severity-high-bg)",
    border: "rgba(239, 68, 68, 0.3)",
  },
  MEDIUM: {
    color: "var(--severity-medium)",
    bg: "var(--severity-medium-bg)",
    border: "rgba(245, 158, 11, 0.3)",
  },
  LOW: {
    color: "var(--severity-low)",
    bg: "var(--severity-low-bg)",
    border: "rgba(107, 114, 128, 0.3)",
  },
};

// Map shorthand aliases to canonical style objects
const ALIAS_STYLES: Record<string, { color: string; bg: string; border: string }> = {
  bull:   BIAS_STYLES.BULL,
  bear:   BIAS_STYLES.BEAR,
  neutral: BIAS_STYLES.NEUTRAL,
  high:   SEVERITY_STYLES.HIGH,
  medium: SEVERITY_STYLES.MEDIUM,
  low:    SEVERITY_STYLES.LOW,
};

// ─── Component ────────────────────────────────────────────────────────────────

export function Badge({ variant, value, children, size = "md", className }: BadgeProps) {
  const label = children ?? value ?? "";

  const styles =
    variant === "bias"
      ? BIAS_STYLES[value as string] ?? BIAS_STYLES.NEUTRAL
      : variant === "confidence"
        ? CONFIDENCE_STYLES[value as string] ?? CONFIDENCE_STYLES.LOW
        : variant === "severity"
          ? SEVERITY_STYLES[value as string] ?? SEVERITY_STYLES.LOW
          : variant === "neutral"
            ? { color: "var(--text-secondary)", bg: "var(--bg-card-hover)", border: "var(--border)" }
            : ALIAS_STYLES[variant] ?? { color: "var(--text-secondary)", bg: "var(--bg-card-hover)", border: "var(--border)" };

  const paddingY = size === "sm" ? "2px" : "4px";
  const paddingX = size === "sm" ? "6px" : "8px";
  const fontSize = size === "sm" ? "var(--text-xs)" : "var(--text-xs)";

  if (!styles) return null;

  return (
    <span
      className={clsx(className)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: `${paddingY} ${paddingX}`,
        borderRadius: 4,
        fontSize,
        fontWeight: 600,
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        color: styles.color,
        background: styles.bg,
        border: `1px solid ${styles.border}`,
        lineHeight: 1.2,
      }}
    >
      {label}
    </span>
  );
}
