// ─── Types ────────────────────────────────────────────────────────────────────

type Status = "ok" | "warn" | "error" | "unknown";

interface StatusDotProps {
  status: Status;
  label?: string;
  pulse?: boolean;
}

// ─── Color Map ────────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<Status, string> = {
  ok: "var(--accent-bull)",
  warn: "var(--severity-medium)",
  error: "var(--severity-high)",
  unknown: "var(--text-muted)",
};

// ─── Component ────────────────────────────────────────────────────────────────

export function StatusDot({ status, label, pulse = false }: StatusDotProps) {
  const color = STATUS_COLOR[status];

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
      }}
      title={label ? `${label}: ${status}` : status}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: color,
          flexShrink: 0,
          display: "block",
          boxShadow: status === "error" ? `0 0 0 2px rgba(239, 68, 68, 0.2)` : undefined,
          animation: pulse && (status === "error" || status === "warn")
            ? "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite"
            : undefined,
        }}
      />
      {label && (
        <span
          style={{
            fontSize: "var(--text-xs)",
            color: color,
            fontWeight: 500,
          }}
        >
          {label}
        </span>
      )}
    </div>
  );
}
