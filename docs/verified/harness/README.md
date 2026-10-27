# Bộ kiểm thử bc không cần bench (MariaDB thật + DocType JSON v16 thật)

Chạy `bc.api.*` THẬT trên một `frappe` giả mỏng (`frappe/`): `frappe.db.sql` đi thẳng xuống MariaDB, bảng
sinh từ DocType JSON của ERPNext/Frappe v16 + mọi app cạnh repo (`schema.py`) cộng Custom Field trong
fixtures và trong `install.py` (`extract_cf.py`). Cột không có trên site thật thì SQL nổ y như production
(đã bắt được giả định sai `is_scrap_item` — v16 dùng `secondary_item_type`).

Helper của app khác được gọi thật: `ketoan.api.mt_debt` (công nợ MT), `sx.api.qc_attp` / `sx.qc.*` (ATTP),
`pkd.api.utils` (ngày Tết), `vanchuyen…nhat_ky_xe` (lịch xe), `ns.api.canh_bao` (việc tồn nhân sự). Các app
phải nằm cạnh repo bc (`APPS_ROOT` để đổi). Bảng / field chỉ có trên site (tạo tay trên Desk, không nằm
trong repo nào) khai ở `site_doctypes.json` (SalaryDay) và `site_custom_fields.json` (field vận chuyển trên
Sales Invoice, field lương / CCCD trên Employee), mỗi mục ghi nguồn suy ra kiểu.

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
| `test_vc.py` | Vận chuyển: giao theo hình thức, chờ giao quá hạn, xếp chuyến theo dòng chuyến (chuyến nháp), giao lần đầu, tải có trọng số, cước chỉ chuyến đã duyệt + chia doanh thu theo kiện, sự cố, thu hồi (phiếu kiểm ketoan), lịch xe (code vanchuyen thật); riêng tư; từng phần thiếu |
| `test_ns.py` | Nhân sự: quân số, vào / nghỉ, BHXH, quỹ lương một phiếu / người / tháng, tạm tính vs đã chốt, ẩn nhóm < 5 người, giấy tờ (ATTP option sai chữ), việc tồn — so vi sai với `ns.api.canh_bao` THẬT; riêng tư; từng phần thiếu |
| `test_tet_source.py`, `lunar_check.mjs` | Ngày Tết một nguồn BC Settings (pkd đọc mềm, lịch frontend) |
| `old_tab_check.mjs` | Tab mở TRƯỚC deploy (lib/ cũ trong module map, view mới): view vẫn vẽ được — `BC_OLD_PUBLIC=<public/bc bản cũ> ./run_all.sh` |
| `ui_check.mjs` | Playwright: trang dựng từ chính `www/bc.html` (import map thật), API Python thật; desktop + 390px; lỗi JS/HTTP, cuộn ngang |

Thử phá: `BC_APP_ROOT=<bản bc đã sửa hỏng> python3 test_xxx.py` phải đỏ.
