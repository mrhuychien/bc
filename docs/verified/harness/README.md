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
| `test_sx.py` | Số sản xuất: Manufacture dòng thành phẩm + Material Receipt trừ phiếu kiểm kê / dọn lô; bỏ phiếu nhập lại sau kiểm kê đưa về 0 (mã không đếm; nhóm theo phiếu Nhập TP hoặc phiếu kho, đúng số, tạo sớm nhất sau giờ chốt — kể cả ghi sổ lùi giờ, ≤ 60 ngày; bỏ phiếu bù D216 và lô thu hồi khi đối chiếu; không bỏ phiếu gốc trước giờ chốt, phiếu đúng số tạo giữa hai lần kiểm kê, mã bấm Không còn, kiểm kê còn số / đã huỷ / kho khác / biên bản lệch sổ, phiếu số khác) ở SX Tết + Thời gian thực, Kho › Nhập TP vẫn theo sổ; site không có sx; kho TP từ SX Settings |
| `test_channel.py` | Kênh Showroom từ PKD Settings; pkd chưa migrate `kenh_showroom` vẫn giữ 3 kênh |
| `test_cn.py` | Phải thu FIFO + tuổi nợ theo kênh, MT theo bảng kê (code ketoan thật), DSO, phải trả, quỹ, che số TK; các nhánh dự phòng |
| `test_attp.py` | So vi sai với `sx.api.qc_attp.tong_quan` / `qc_baocao.so_lieu` THẬT (bc dưới BC Viewer, sx dưới System Manager) |
| `test_vc.py` | Vận chuyển: giao theo hình thức, chờ giao quá hạn, xếp chuyến theo dòng chuyến (chuyến nháp), giao lần đầu, tải có trọng số, cước chỉ chuyến đã duyệt + chia doanh thu theo kiện, sự cố, thu hồi (phiếu kiểm ketoan), lịch xe (code vanchuyen thật); riêng tư; từng phần thiếu |
| `test_ns.py` | Nhân sự: quân số, vào / nghỉ, BHXH, quỹ lương một phiếu / người / tháng, tạm tính vs đã chốt, ẩn nhóm < 5 người, giấy tờ (ATTP option sai chữ), việc tồn — so vi sai với `ns.api.canh_bao` THẬT; riêng tư; từng phần thiếu |
| `test_kho_ton.py` | Tồn kho (K1–K5 + sức khoẻ, xu hướng + nhập–xuất–tồn): giá trị theo vai trò kho / nhóm cây (nhóm con Tết), kho TP = Thời gian thực, công ty khác / kho ngừng dùng / mã ngừng dùng, phiếu ngày tương lai, đẳng thức nhập–xuất–tồn từng tháng, phân loại dòng chảy (nhập tạm, bù nợ BOM, kiểm kê sx, dọn tồn, đầu kỳ), số ngày tồn (pha Tết), chậm / chết (xuất bù nợ BOM là dùng, trả hàng / chuyển kho / Repack kiểm kê không phải), thùng theo đơn vị, cài đặt kho_*, định giá lại lỗi; riêng tư |
| `test_kho_han.py` | Hạn dùng & tồn âm (K6–K8): các phần hạn dùng cộng đúng bằng Bin thành phẩm (lô bundle + batch_no cũ, phần chưa gắn lô ±, mã không lô, lô âm), lô hết hạn hôm nay chưa hết hạn, lô thu hồi sang tồn không bán được, kho trả về & cách ly + tuổi (kiểm kê có lô hai chân không làm mới tuổi), tồn âm theo giá vốn dự phòng trong công ty, đơn vị lẫn Hộp + Kg, ảnh chụp lô có cache; `seed-cache` / `seed-thu-hoi` / `seed-empty` cho lượt giao diện phụ |
| `test_kho_kk.py` | Kiểm kê & điều chỉnh (K9–K10): lần kiểm gần nhất từng kho (SX Kiem Ke + phiếu kiểm kho, bỏ đầu kỳ / điều chỉnh), phiếu đang đếm / huỷ chốt, độ chính xác tồn, chênh lệch kiểm kê sx theo ngày hiệu lực (phiếu ghi lùi D216, kho khác khi bật lô D191), phiếu kiểm kho thừa / thiếu / đổi giá, dọn tồn, xuất khác (loại kiểm kê / dọn tồn / bù nợ BOM), khớp nhập–xuất–tồn trừ phần ghi lùi; site không sx |
| `test_kho_nhap.py` | Nhập TP & giá vốn (K11–K12): nhập theo phiếu đã duyệt từng ngày / 12 tháng, giá trị theo sổ chỉ dòng thành phẩm (bỏ phế / phụ phẩm), phiếu huỷ / phiếu kho huỷ, đối chiếu phiếu ↔ sổ, nhập ngoài phiếu, chờ duyệt, đã vào hộp chưa nhập, nợ BOM (giá tạm, giá 0, tuổi, BOM mặc định), nguyên liệu treo, tồn giá vốn 0; đơn vị lẫn; site không sx; tháng cực đoan không lỗi |
| `test_kho_nen.py` | Nền nhóm Kho: chặn import AST trên `kho.py` + `kho_*.py` (danh sách cho phép, `sau_kiem_ke.xu_ly` chỉ `chay=0`), alias SQL trùng method dict trên mọi `bc/api` (Thời gian thực "số mã có tồn"), vai trò kho (kho nhóm bung con, quy tắc chồng nhau, POS tắt), nhóm con truyền thống, thùng ròng có dấu, ngưỡng Bin, giá vốn sổ kho mới nhất, kiểm kê có lô hai chân như ERPNext v16, kẹp tháng chọn |
| `ui_kho_*.mjs` | Playwright 4 màn Kho trên seed sổ kho gộp (`seed_ui_kho.py`, DB `bc_test_kho_ui`): mọi số trên màn = API, desktop + 390px, đổi tháng / tab, không lỗi JS/HTTP, không cuộn ngang; `ui_kho_han.mjs <url> cache\|thu-hoi\|empty` cần `test_kho_han.py seed-<lượt>` trước |
| `test_sections.py` | Ẩn / hiện mảng: AST — mọi method @whitelist gọi `_guard("<mảng>")` đúng mảng ở dòng đầu (method mới quên khai thì đỏ), menu `lib/nav.js` khớp `SECTIONS`; ẩn từng mảng → người xem bị chặn đúng 30 method, quản trị vẫn qua; cache không lách được; chỉ quản trị đổi được; dữ liệu lưu tay / Desk |
| `sections_check.mjs` | Playwright 2 server cùng DB: vai quản trị bật/tắt ở `#/an-mang` (công tắc, cả nhóm, phím cách, hiện tất cả) → vai người xem mất menu / route / 403, thanh dưới điện thoại bù màn, Làm mới tải lại theo danh sách mới, ẩn hết → trang trống có lời nhắn |
| `test_ai_render.py` | Trợ lý AI — dựng lời: định dạng số khớp từng ký tự với `lib/format.js` (chạy node đối chiếu), chỗ giữ sai path / sai kiểu / ngoài nhóm, soát số viết tay (số trần, đơn vị, số bằng chữ, phân số, số ghép quanh chỗ giữ; giữ năm, ngày, mã chứng từ, thời hạn ngắn), mã giả khách / NCC (chỉ thay chuỗi bằng đúng tên, hoàn nguyên, mã lạ bị bắt, ghi chú chữ tự do) |
| `test_ai_redact.py` | Mã giả khách / NCC: tên cũ trên hoá đơn về cùng mã với hồ sơ, tên nằm giữa câu (đứng riêng thành từ), ô mang tên đối tác không khớp hồ sơ vẫn được cấp mã, chỉ mã đã gửi trong lượt gọi mới đổi lại thành tên, 5.000 đối tác × gói 150 KB dưới 5 giây |
| `test_ai_llm.py` | Cửa gọi Claude trên `requests` giả (chặn mạng ở tầng socket): thân + header đúng tài liệu API, phân loại lỗi (hết credit không thử lại; 429 / 5xx / quá giờ thử lại 5 s, 20 s), khoá không lọt vào lỗi / traceback, trần chi theo kỳ + 30 lượt / ngày, giá model, đề bài không chứa số liệu, cắt danh sách dài |
| `test_ai_store.py` | Vòng đời tín hiệu trên bảng thật (mới → còn → đóng → mở lại, bỏ qua có hạn, nguồn lỗi không đóng), lời AI gắn vào tín hiệu (không hạ được mức đỏ), nhận định tự do, xếp hạng, nhật ký lượt chạy, dọn 180 ngày; `collect` gọi đủ 24 lượt (23 mục của các màn + vận chuyển tháng trước) trên DB có số thật, một method lỗi chỉ hỏng mục đó; việc đã bỏ qua không quay lại thành nhận định tự do |
| `test_ai_rules_{kd,kho,cn,vc,ns}.py`, `test_ai_he_thong.py` | 42 quy tắc + 8 bộ dò: mỗi quy tắc ca dương / âm / đúng ngưỡng trên gói số dựng tay VÀ trên payload thật của seed (số tính tay), ngưỡng ghi đè, nguồn lỗi → "không chạy được", lời không có chữ số gõ tay, không tên người; AST: quy tắc không SQL, bộ dò chỉ `SELECT`; gói số hệ thống không chứa traceback / tên tài khoản |
| `test_ai_api.py` | `bc.api.ai`: người xem chỉ nhận nhận định lãnh đạo đang mở và không dùng số của mảng đang ẩn, không có trường quản trị; chấm đỏ = số trên màn; quá 26 giờ chưa chạy → cũ; 5 method quản trị chặn người xem; khoá không có trong bất kỳ kết quả / nhật ký nào; đổi trạng thái, ngưỡng, thử kết nối |
| `test_ai_pipeline.py` | Một lượt chạy trọn vẹn với mô hình giả trên DB có số thật: tắt AI / thiếu khoá / chạm trần / hết credit vẫn có tín hiệu theo quy tắc; lời AI có số thật, lời sai bị loại; tên khách (kể cả tên cũ trên hoá đơn, tên giữa câu), tiêu đề Error Log, số của mảng đang ẩn không rời máy chủ; mã giả chưa gửi không thành tên; số đếm viết thành % bị loại; quy tắc lỗi không đóng nhầm tín hiệu; khoá và đề bài không được lưu; chống chạy trùng; luật tĩnh toàn `bc/ai` (chỉ `llm/` gọi mạng + đọc khoá) |
| `test_ai_tinh.py` | Luật tĩnh, không cần DB: mọi field `ai_*` của BC Settings permlevel 1, `BC AI Insight` / `BC AI Run` chỉ System Manager, mọi đường dẫn trong `hooks.py` trỏ tới hàm có thật, giá trị điền sẵn khi cài (che tên mặc định bật), cả `bc/` chỉ `bc/ai/llm/` import `requests` và đọc khoá, `collect.py` chỉ import frappe + `bc.api.*` + thư viện chuẩn |
| `ui_ai.mjs` | Playwright 2 server cùng DB (`seed_ui_ai.py`, DB `bc_test_ai_ui`): `#/tro-ly` vai người xem + quản trị, `#/ai` vai quản trị — số thẻ = API, người xem không có nút / nhóm quản trị, lời hiển thị dạng chữ thuần (chuỗi HTML không chạy), thao tác quản trị ghi thật, 390px không cuộn ngang |
| `test_tet_source.py`, `lunar_check.mjs` | Ngày Tết một nguồn BC Settings (pkd đọc mềm, lịch frontend) |
| `old_tab_check.mjs` | Tab mở TRƯỚC deploy (lib/ cũ trong module map, view mới): view vẫn vẽ được — `BC_OLD_PUBLIC=<public/bc bản cũ> ./run_all.sh` |
| `ui_check.mjs` | Playwright (vai người xem; `BC_UI_USER=Administrator python3 server.py <port>` = vai quản trị): trang dựng từ chính `www/bc.html` (import map thật), API Python thật; desktop + 390px; lỗi JS/HTTP, cuộn ngang; 4 màn Kho dựng được khi chưa có sổ kho; `/thoi-gian-thuc` trên seed Kho với `BC_UI_KHO=1` (danh sách kho rỗng thì trượt) |

Thử phá: `BC_APP_ROOT=<bản bc đã sửa hỏng> python3 test_xxx.py` phải đỏ.

Sổ kho trong bộ thử Kho chỉ ghi qua `seed_kho.K` (chứng từ + dòng sổ + bundle lô; kiểm kê có lô hai chân như ERPNext
v16) rồi `finalize()` tính lại Bin từ sổ theo đúng ngữ nghĩa ERPNext (thứ tự ghi sổ, dòng huỷ bỏ qua, kiểm kê không lô đặt
thẳng tồn sau). `seed_kho.base(k)` = cây kho + nhóm hàng + SX Settings + POS Profile chung; mỗi bộ thử thêm dữ liệu với
tiền tố riêng (TON-, HAN-, KKE-, NTP-, NEN-) để gộp được vào một DB cho kiểm giao diện.
