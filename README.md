# bc — Báo cáo điều hành cho Ban lãnh đạo RVHG

Custom app Frappe/ERPNext v16, **chỉ đọc**: Ban lãnh đạo xem báo cáo toàn công ty
trên điện thoại + desktop. Thay 2 dashboard HTML cũ (Báo cáo KD tổng quát v29,
Báo cáo SX Tết v6) bằng SPA tại **`/bc`**; số liệu do whitelisted method
`bc.api.*` tính (port từ 15 Query Report), frontend không còn chạy Query Report
qua desk API.

- www route `/bc` · CSS prefix `bc-` · context `window.BC_CONTEXT`
- Quyền: role **BC Viewer** (fixture) hoặc System Manager — kiểm ở www page và ở
  dòng đầu mọi API (`_guard()` → `PermissionError`).
- Cấu hình: **BC Settings** (Single) — tháng bắt đầu năm TC, nhóm Hàng Tết / Hàng
  truyền thống, % mục tiêu Tết, bảng ngày mùng 1 Tết, khoảng SX mặc định, TTL cache,
  cách tính cùng kỳ Tết. Không còn hardcode năm/ngày/tên nhóm trong JS.

## Cài đặt / deploy

```bash
cd ~/frappe-bench
bench get-app bc https://github.com/mrhuychien/bc
bench --site a.rongvanghoanggia.com install-app bc
# mỗi lần cập nhật:
bench --site a.rongvanghoanggia.com migrate && bench build --app bc && bench restart
```

Sau khi cài: mở `/app/bc-settings`, kiểm tra nhóm hàng + bảng ngày Tết (đã seed
2023–2030), gán role **BC Viewer** cho người xem.

## Đối chiếu với Query Report cũ (bắt buộc trước nghiệm thu)

Phiên build không truy cập được site nên SQL trong `bc/api/*.py` được dựng theo
mô tả cột (SPEC bảng 3) và đánh dấu `[VERIFY]`. Trên bench:

```bash
# 1) Lưu SQL gốc của 15 report vào docs/report-sql/ (để port 1:1 và review)
bench --site a.rongvanghoanggia.com execute bc.scripts.dump_report_sql.run
# 2) So 4 report Tết cũ ↔ 4 method mới (diff phải rỗng, sai số ≤ 1)
bench --site a.rongvanghoanggia.com execute bc.scripts.compare_tet_reports.run
# 3) So các report KD (tổng quan, kênh, ngày, tỉnh, ngành hàng, top KH)
bench --site a.rongvanghoanggia.com execute bc.scripts.compare_tet_reports.run_kd
```

Chỗ chỉnh tập trung khi diff lệch: `SI_AMOUNT`/`SII_AMOUNT` (net_total vs
grand_total), `_KEYWORDS` (map kênh), `PLAN_COLUMNS` (cột kế hoạch trên Item) —
đều trong `bc/api/_common.py`.

## Cấu trúc

```
bc/api/        _common.py (guard, settings, fy_range, tet_season, cache, kênh),
               common.py, kd.py, tet.py, sx.py, _provinces.py
bc/www/        bc.py (guard + BC_CONTEXT), bc.html (import map + shell)
bc/public/bc/  shell.js, shell.css, lib/, components/, views/
bc/scripts/    dump_report_sql.py, compare_tet_reports.py
docs/          tet-curdate-audit.md, report-sql/
```
