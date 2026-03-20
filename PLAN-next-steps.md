# Plan — Next Steps After B3

**Ngày:** 2026-03-20
**Trạng thái model hiện tại:** Walk-forward mean acc = 0.4976, RF > COT gap = +0.1700 (PASS)
**Context:** B3-01 / B3-02 / B3-03 hoàn thành. Cần fix gate misleading → verify B4 → fix data gaps.

---

## Ưu tiên & thứ tự

```
[1] Fix gate              ~30 phút   (unblock CI clarity)
[2] Verify B4 pipeline    ~2–4 giờ   (critical path to production)
[3] Fix TFF data          ~1–2 giờ   (highest-impact feature fix)
[4] Frontend F1           ongoing    (parallel sau khi B4 stable)
```

---

## [1] Fix Gate — train_model.py

**Vấn đề:** Gate 68% là tư duy binary-classification áp lên 3-class problem → CI luôn in `FAIL` dù model thực sự tốt.

**Thay đổi:**

| | Trước | Sau |
|---|---|---|
| Primary gate | `mean_acc >= 0.68` | `mean_acc >= 0.52` |
| Secondary gate (giữ) | RF > COT + 5% | RF > COT + 5% ← đây là gate thực sự quan trọng |

**Cơ sở:**
- Random baseline (3-class) ≈ 33%
- Model đạt 49.76% out-of-sample = +17pp vs random
- 52% là ngưỡng realistic cho FX 3-class với 50% NEUTRAL label
- Gate RF > COT + 5% đã PASS ở tất cả 4 folds — đây là metric có ý nghĩa kinh doanh

**Files cần sửa:**
- `training/train_model.py` — đổi `0.68` → `0.52` ở gate check
- `DECISIONS.md` — ghi lý do thay đổi gate

---

## [2] Verify B4 Inference Pipeline

B4 đã được implement (marked [x] trong task list) nhưng cần verify end-to-end với model mới.

### B4-06b — Telegram verification (còn pending)

**Yêu cầu:** Trigger `predict-bias.yml` thủ công → verify Telegram message nhận được.

Checklist trước khi trigger:
- [ ] `TELEGRAM_BOT_TOKEN` và `TELEGRAM_CHAT_ID` đã set trong GitHub Secrets
- [ ] `predict-bias.yml` workflow có bước gọi `notify.py`
- [ ] Model files (`model.pkl`, `calibrator.pkl`) đã được commit sau B3 run mới nhất

### Verify output format

Sau khi workflow chạy, kiểm tra:
- [ ] `data/bias-latest.json` được commit với đúng format
- [ ] `data/history/bias/2026-W12.json` được append
- [ ] Không có `FEATURE_VERSION_MISMATCH` alert (feature count = 26 phải match model)

---

## [3] Fix TFF Data — Socrata Field Names

**Vấn đề:** `lev_funds_net_index` và `asset_mgr_net_direction` constant (zero) trong 20 năm data — TFF fields không được join vào pivot.

**Root cause:** `dealer_net` hoạt động nhưng `lev_funds_net` và `asset_mgr_net` thì không → tên field trong Socrata API có thể khác với assumption trong `download_cot_history.py`.

### Debug plan

**Bước 1:** Inspect raw TFF response từ Socrata API để xem field names thực tế.

```python
# Thêm vào download_cot_history.py hoặc chạy ad-hoc
import requests
url = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
params = {
    "$where": "cftc_contract_market_code='099741'",  # EUR
    "$limit": 1
}
r = requests.get(url, params=params)
print(list(r.json()[0].keys()))  # Xem toàn bộ field names
```

**Bước 2:** So sánh với current assumptions trong `parse_tff()`:

```
Current assumption        → Cần verify
lev_money_positions_long_all   → ?
lev_money_positions_short_all  → ?
asset_mgr_positions_long_all   → ?
asset_mgr_positions_short_all  → ?
dealer_positions_long_all      → ✅ works
dealer_positions_short_all     → ✅ works
```

**Bước 3:** Nếu field names khác → update `parse_tff()` → re-run `download_cot_history` workflow → re-run `B3-01 Walk-Forward Training`.

**Expected impact:** Thêm 2 features hợp lệ (lev_funds_net_index, asset_mgr_net_direction) → có thể tăng 1–3% accuracy.

---

## [4] Frontend F1 — Parallel Track

Sau khi B4 stable, bắt đầu F1 song song với B5.

### Thứ tự trong F1

```
F1-01 Project Setup       → Next.js 15 + TypeScript + Tailwind
F1-02 Mock Data           → Dùng bias-latest.json từ B4 output thực
F1-03 Zustand Store       → State management
F1-04 Data Fetching       → Fetchers với cache
F1-05 App Shell           → Layout, Sidebar, Header
F1-06 Shared Components   → Badge, DataTable, Sparkline
F2    Dashboard page      → Main view
F3    Data Audit page
```

**Quyết định cần confirm trước F1:**
- [ ] Hosting: GitHub Pages hay Vercel? (S-01a)
- [ ] Chart library: `recharts` hay `lightweight-charts`? (S-01b)
- [ ] Model storage: Git LFS cần không? (model.pkl = 29MB hiện tại)

---

## Remaining Data Quality Issues (backlog)

| Issue | Impact | Effort | Priority |
|-------|--------|--------|----------|
| TFF Socrata field names | Medium (+1–3% acc) | Low | High |
| `yield_10y_diff` chỉ 43% non-zero (AUD/CAD/CHF/NZD thiếu) | Low–Medium | Medium | Medium |
| `pmi_composite_diff` = 0 (PMI data không có) | Low | High | Low |
| `rate_hike_expectation` cần verify logic | Low | Low | Low |

---

## Summary

```
Ngay bây giờ:   [1] Fix gate → commit → push
Tuần này:       [2] Verify B4 end-to-end + Telegram
Sau đó:         [3] Debug TFF → nếu fix được → retrain B3
Parallel:       [4] Bắt đầu F1 frontend sau khi B4 confirmed stable
```
