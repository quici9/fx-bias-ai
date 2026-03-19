# CLAUDE.md — FX Bias AI Project Notes

## API Keys & Secrets

Tất cả secrets (FRED_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, v.v.) **chỉ được lưu trên GitHub Secrets**, không có trong local `.env` hay bất kỳ file nào trong repo.

## Giới hạn IP — Không chạy data fetch locally

Một số API bị hạn chế theo IP địa phương (residential IP bị block hoặc rate-limit nặng). **Mọi script fetch dữ liệu phải chạy qua GitHub Actions**, không phải local:

- `backend/scripts/fetch_cot.py` → chạy qua `fetch-data.yml`
- `backend/scripts/fetch_macro.py` → chạy qua `fetch-data.yml`
- `backend/scripts/fetch_cross_asset.py` → chạy qua `fetch-data.yml`
- `training/build_labels.py` → chạy qua GitHub Actions workflow khi cần download

Khi viết hoặc test scripts fetch dữ liệu, **đừng cố chạy local** — sẽ fail do thiếu key hoặc bị block IP. Thay vào đó:
1. Viết code + unit tests với mock data
2. Push lên GitHub → trigger workflow thủ công (`workflow_dispatch`)
3. Kiểm tra kết quả từ Actions logs và artifacts

## Workflow cho Data Scripts

```
Local: viết code → unit test với mock → commit & push
GitHub Actions: fetch real data → commit output JSON/CSV → pull về local
```
