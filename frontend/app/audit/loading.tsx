// ─── App Router Loading Skeleton (F5-05c) ─────────────────────────────────────
// Shown by Next.js automatically while the /audit route segment loads

export default function AuditLoading() {
  return (
    <div
      role="status"
      aria-label="Loading data audit page"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 20,
        animation: "fadeInUp 300ms ease both",
      }}
    >
      {/* Page title skeleton */}
      <div
        style={{
          height: 32,
          width: 240,
          background: "var(--bg-card)",
          borderRadius: 6,
          opacity: 0.7,
        }}
      />

      {/* Tab bar skeleton */}
      <div style={{ display: "flex", gap: 8 }}>
        {[120, 100, 130, 140, 160].map((w, i) => (
          <div
            key={i}
            style={{
              height: 36,
              width: w,
              background: "var(--bg-card)",
              borderRadius: 6,
              opacity: 0.6,
            }}
          />
        ))}
      </div>

      {/* Table skeleton */}
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          borderRadius: "var(--card-radius)",
          overflow: "hidden",
        }}
      >
        {[1, 2, 3, 4, 5, 6, 7, 8].map((row) => (
          <div
            key={row}
            style={{
              padding: "12px 20px",
              borderBottom: "1px solid var(--border-muted)",
              display: "flex",
              gap: 16,
              opacity: Math.max(0.2, 1 - row * 0.1),
            }}
          >
            {[60, 120, 80, 80, 80].map((w, i) => (
              <div
                key={i}
                style={{
                  height: 14,
                  width: w,
                  background: "var(--bg-secondary)",
                  borderRadius: 4,
                }}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
