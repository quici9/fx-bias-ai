# Architectural Decisions Log — FX Bias AI

**Project:** FX Bias AI Prediction System
**Created:** 2026-03-19

---

## ADR-001: Hosting — GitHub Pages

**Date:** 2026-03-19
**Status:** Accepted
**Context:** Need static hosting for Next.js exported frontend. Options: GitHub Pages vs Vercel.
**Decision:** GitHub Pages
**Rationale:**
- Same repo for code + data + hosting — simplest possible setup
- Zero external dependency — no Vercel account needed
- Free tier sufficient for single-user dashboard
- Custom domain support available if needed later
- Data JSON files served from same origin = no CORS issues

---

## ADR-002: Chart Library — Recharts

**Date:** 2026-03-19
**Status:** Accepted
**Context:** Need charts for sparklines, accuracy trends, feature importance bars. Options: `recharts` vs `lightweight-charts`.
**Decision:** `recharts`
**Rationale:**
- Consistent API across all chart types (bar, line, sparkline)
- React-native integration — composable with JSX
- Sufficient performance for 8-currency dataset (~100 data points max)
- `lightweight-charts` optimized for financial time-series at scale — overkill for this use case
- Smaller learning curve, better documentation

---

## ADR-003: Model Storage — Direct Commit (revisit after Phase B3)

**Date:** 2026-03-19
**Status:** Accepted (provisional)
**Context:** `model.pkl` needs to be stored in repo. Options: direct commit vs Git LFS.
**Decision:** Direct commit if model < 5MB. Revisit after Phase B3 when actual model size is known.
**Rationale:**
- RandomForest with 200 trees, max_depth=8, 28 features → expected ~2-3MB
- Direct commit avoids Git LFS setup complexity
- If model > 5MB after training → migrate to Git LFS

---

## ADR-004: Historical Retention Policy

**Date:** 2026-03-19
**Status:** Accepted
**Context:** How long to keep bias history and model metrics.
**Decision:**
- `data/history/bias/`: 2 years (104 weeks)
- `data/history/model-metrics/`: 12 entries (rolling)
**Rationale:**
- 2 years bias history = sufficient for seasonal pattern analysis
- 12 model-metrics entries covers quarterly review cycle
- Older files archived or deleted annually in January

---

## ADR-005: Notification Channel — Telegram

**Date:** 2026-03-19
**Status:** Accepted
**Context:** Need push notification for weekly predictions and critical alerts.
**Decision:** Telegram Bot
**Rationale:**
- Free, no rate limits for single-user usage
- Mobile push notification — instant delivery
- Markdown support for formatted messages
- ~20 lines Python implementation
- Rollback alerts sent immediately (not batched weekly)

---

## ADR-006: Frontend Render Mode — Static Export

**Date:** 2026-03-19
**Status:** Accepted
**Context:** Next.js supports SSR, SSG, ISR, and static export. Which mode?
**Decision:** Static export (`next export` / `output: 'export'`)
**Rationale:**
- No server needed — GitHub Pages serves static files
- All data comes from JSON files in repo — no server-side API calls needed
- FCP < 1.5s achievable with SSG
- Zero runtime cost
- Frontend is read-only — no write operations from browser

---

*Add new decisions below. Include context, decision, and rationale for each.*
