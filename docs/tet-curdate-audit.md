# Khảo sát `CURDATE()` trong 4 Query Report Tết (SPEC 3b — bước 1)

> Commit TRƯỚC khi viết SQL Tết mới. SQL mới (`bc/api/tet.py`) **không** chứa
> `CURDATE()`, `NOW()`, `YEAR(CURDATE())` hay ngày Tết literal — mọi mốc là tham số
> do `tet_season(today)` (`bc/api/_common.py`) tính và truyền vào `frappe.db.sql`.

## ⚠️ Trạng thái

Phiên build **không truy cập được site** `a.rongvanghoanggia.com` (proxy chặn) nên
chưa đọc được `tabReport.query`. Bảng "Biểu thức gốc" dưới đây phải được điền từ
output của:

```bash
bench --site a.rongvanghoanggia.com execute bc.scripts.dump_report_sql.run
```

(script in sẵn bảng markdown `| report | dòng | biểu thức | ngữ cảnh |` cho mọi
`CURDATE()`, `NOW()`, ngày literal và `Hàng TTết`). Sau khi điền: đối chiếu cột
"Tham số thay thế" với SQL trong `bc/api/tet.py`, rồi chạy
`bc.scripts.compare_tet_reports.run` — diff phải rỗng (bước 3) trước khi bật
`tet_compare_mode = tet_aligned` (bước 4).

## Tham số do `tet_season(today)` cung cấp

| Tham số | Giá trị | Ghi chú |
|---|---|---|
| `tet_year` | năm của Tết sắp tới/vừa qua | ứng viên = tet_date gần nhất ≥ today − 60; nếu today < đầu mùa của ứng viên (giữa 2 mùa) → Tết vừa qua, `between_seasons = True` |
| `tet_date` | mùng 1 Tết `tet_year` (BC Settings) | thiếu → throw "Chưa khai báo ngày Tết {year} trong BC Settings" |
| `season_start` | 01/`tet_season_start_month`/(tet_year − 1) | mặc định 01/11 năm trước |
| `season_end` | `tet_date` | mùa kết thúc đúng mùng 1 |
| `asof` | min(today, season_end) | edge (c): xem sau Tết → số khoá |
| `ly_tet_date` / `ly_season_end` | mùng 1 Tết năm tet_year − 1 | thiếu → throw |
| `ly_season_start` | 01/`tet_season_start_month`/(tet_year − 2) | |
| `ly_asof_calendar` | asof − 1 năm | **mặc định** (`calendar`) — hành vi kiểu CURDATE cũ |
| `ly_asof_aligned` | ly_tet_date − (tet_date − asof) | dùng khi `tet_compare_mode = tet_aligned` |
| `ly_asof` | 1 trong 2 dòng trên theo Settings | cột "năm trước"/"NT Đi" |

## Ánh xạ mẫu thường gặp (SPEC 3b bước 2)

| Mẫu trong SQL gốc | Thay bằng |
|---|---|
| `YEAR(CURDATE())`, `YEAR(NOW())` | `%(tet_year)s` |
| `YEAR(CURDATE())-1` | `%(tet_year)s - 1` |
| `CONCAT(YEAR(CURDATE())-1,'-11-01')` | `%(season_start)s` |
| `CONCAT(YEAR(CURDATE())-2,'-11-01')` | `%(ly_season_start)s` |
| `posting_date <= CURDATE()` | `posting_date <= %(asof)s` |
| `DATE_SUB(CURDATE(), INTERVAL 1 YEAR)` | `%(ly_asof)s` (= `ly_asof_calendar` ở chế độ mặc định) |
| ngày Tết literal / `CASE YEAR(CURDATE()) WHEN …` | `%(season_end)s` / `%(ly_season_end)s` — ngày đã chép vào BC Settings.tet_dates (seed 2023–2030) |
| `<` hay `<=` với ngày Tết | giữ nguyên toán tử SQL gốc — SQL mới hiện dùng `<=` (mùng 1 tính vào mùa) **[VERIFY]** |
| `MONTH(CURDATE()) >= 11` | bỏ — Python đã chọn `tet_year` |
| `'Hàng TTết'` | `%(tet_group)s` = BC Settings.tet_item_group |

## Biểu thức gốc theo report (điền từ dump_report_sql)

| Report | Biểu thức gốc | Ý nghĩa nghiệp vụ suy ra | Tham số thay thế trong SQL mới |
|---|---|---|---|
| Tet NPP Tang Truong | _(chưa đọc được)_ | năm nay: đầu mùa → hôm nay; năm trước: đầu mùa trước → cùng kỳ | `season_start..asof`, `ly_season_start..ly_asof` |
| Tet NPP Hang Tet | _(chưa đọc được)_ | NT = cả mùa trước; NT Đi = mùa trước đến cùng kỳ; năm nay đến hôm nay; Tổng nhập/Tổng về | `ly_season_start..ly_season_end`, `ly_season_start..ly_asof`, `season_start..asof` |
| Tet Sieu thi MT | _(chưa đọc được)_ | như trên, kênh MT | như trên |
| Tet Ma Hang | _(chưa đọc được)_ | xuất/về theo mã hàng trong mùa, tách MT/GT, % kế hoạch | `season_start..asof` |

Biểu thức nào không khớp bảng ánh xạ → ghi thêm dòng ở đây, giữ nguyên ngữ nghĩa bằng
tham số mới, KHÔNG đoán đổi nghiệp vụ.
