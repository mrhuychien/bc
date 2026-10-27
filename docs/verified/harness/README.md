# Bộ kiểm thử bc không cần bench (MariaDB thật + DocType JSON v16 thật)

Chạy `bc.api.*` THẬT trên một `frappe` giả mỏng (`frappe/`): `frappe.db.sql` đi thẳng xuống MariaDB, bảng
sinh từ DocType JSON của ERPNext/Frappe v16 + mọi app cạnh repo (`schema.py`) cộng Custom Field trong
fixtures và trong `install.py` (`extract_cf.py`). Cột không có trên site thật thì SQL nổ y như production
(đã bắt được giả định sai `is_scrap_item` — v16 dùng `secondary_item_type`).

Helper của app khác được gọi thật: `ketoan.api.mt_debt` (công nợ MT), `sx.api.qc_attp` / `sx.qc.*` (ATTP),
`pkd.api.utils` (ngày Tết). Các app phải nằm cạnh repo bc (`APPS_ROOT` để đổi).

```bash
sudo apt-get install -y mariadb-server && sudo mysqld_safe --user=mysql &   # hoặc service mariadb start
pip install pymysql
./run_all.sh          # tự lấy schema v16 lần đầu (./fetch_schema.sh)
```

| File | Kiểm gì |
|---|---|
| `test_sx.py` | Số sản xuất: Manufacture dòng thành phẩm + Material Receipt trừ phiếu kiểm kê / dọn lô; site không có sx; kho TP từ SX Settings |
| `test_channel.py` | Kênh Showroom từ PKD Settings; pkd chưa migrate `kenh_showroom` vẫn giữ 3 kênh |
| `test_cn.py` | Phải thu FIFO + tuổi nợ theo kênh, MT theo bảng kê (code ketoan thật), DSO, phải trả, quỹ, che số TK; các nhánh dự phòng |
| `test_attp.py` | So vi sai với `sx.api.qc_attp.tong_quan` / `qc_baocao.so_lieu` THẬT (bc dưới BC Viewer, sx dưới System Manager) |
| `test_tet_source.py`, `lunar_check.mjs` | Ngày Tết một nguồn BC Settings (pkd đọc mềm, lịch frontend) |
| `old_tab_check.mjs` | Tab mở TRƯỚC deploy (lib/ cũ trong module map, view mới): view vẫn vẽ được — `BC_OLD_PUBLIC=<public/bc bản cũ> ./run_all.sh` |
| `ui_check.mjs` | Playwright: trang dựng từ chính `www/bc.html` (import map thật), API Python thật; desktop + 390px; lỗi JS/HTTP, cuộn ngang |

Thử phá: `BC_APP_ROOT=<bản bc đã sửa hỏng> python3 test_xxx.py` phải đỏ.
