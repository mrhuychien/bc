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

## Chia sẻ cho lãnh đạo (link / QR tự đăng nhập)

Quản trị (System Manager) vào `/bc` → **Quản trị › Chia sẻ lãnh đạo**:

1. **Tạo tài khoản lãnh đạo** (họ tên, SĐT tuỳ chọn) → tài khoản Website User + role
   BC Viewer: chỉ xem `/bc`, không vào được ERPNext. Hoặc cấp quyền xem cho user có sẵn.
2. Hệ thống hiện **QR + link** `https://<site>/bc?k=<token>` (chỉ hiện 1 lần — DB lưu
   hash). Gửi Zalo / cho quét QR.
3. Lãnh đạo quét/bấm → đăng nhập ngay, thiết bị được **nhớ 400 ngày** (cookie httponly
   `bc_key`): phiên Frappe hết hạn thì mở `/bc` sẽ tự đăng nhập lại.
4. **Thu hồi** từng link (mất máy) hoặc **Khoá** tài khoản. Nút "Đăng xuất" trong app
   xoá luôn cookie nhớ đăng nhập trên thiết bị đó.

An toàn: không bao giờ cấp/tự đăng nhập link cho tài khoản System Manager; login bằng
link giới hạn 30 lần/phút/IP; bảng link ở permlevel 1 (BC Viewer không đọc được).
Lưu ý iPhone: mở link bằng Safari (khung xem trong Zalo có kho cookie riêng).

## Ẩn sản phẩm khỏi báo cáo (chỉ quản trị)

System Manager: bấm biểu tượng 👁‍🗨 cạnh tên sản phẩm (thẻ SX Hàng Tết, Sản phẩm bán chạy,
bảng Mã hàng Tết) hoặc vào **Quản trị › Ẩn sản phẩm** (tìm mã để ẩn, danh sách đang ẩn,
"Hiện lại"). Mã ẩn không hiện ở các danh sách THEO MÃ; tổng doanh số / kênh / tỉnh /
lịch ngày / lịch SX không đổi. Lưu ở BC Settings.hidden_items (permlevel 1); server chặn
mọi thao tác ẩn của user không phải System Manager.

## Báo cáo thời gian thực + sơ đồ xưởng 3D (`#/thoi-gian-thuc`)

Tab đầu tiên của menu (nhóm **Điều hành**). Đồng hồ + chấm LIVE, tự làm mới 60 giây
(dừng khi tab ẩn); 6 KPI hôm nay có hiệu ứng đếm số; **sơ đồ xưởng 3D** (mã nguồn
RVHG-Xuong-3D, three.js 0.180 MIT, tại `bc/public/bc/xuong3d/`) với bảng số liệu nổi +
vòng sáng trên từng khu; dòng sự kiện trong ngày; biểu đồ theo giờ; top mã SX hôm nay.

- API `bc.api.live.get_snapshot` (cache 30 giây, dùng chung): bán hôm nay so cùng giờ hôm
  qua, luỹ kế tháng so cùng kỳ, SX hôm nay (Material Receipt vào kho thành phẩm như SX
  Hàng Tết), tồn kho thành phẩm, Sales Order chờ giao, Purchase Receipt hôm nay, sự kiện.
- 3D chạy trong iframe `/bc_xuong` (www page riêng, cùng quyền BC Viewer/System Manager);
  SPA gửi số liệu bằng postMessage cùng origin → `xuong3d/bridge.js` dùng `window.__RVHG`
  của mô hình để gắn nhãn; KHÔNG sửa lõi 3D (`app.js`, `view-ui.js` giữ nguyên bản gốc).
- Sơ đồ thoáng: KHÔNG vẽ khung số liệu đè lên mô hình, chỉ chấm sáng (cỡ cố định ~26px, đủ
  cho ngón tay) + vòng sáng ở khu đang hoạt động. **Bấm vào khu bất kỳ (sàn, máy hoặc chấm
  sáng) → card của khu đó hiện khối "Số liệu trực tiếp"**. Nút ▦ "Số liệu" trên thanh điều
  khiển bật lại khung số nổi khi cần nhìn tổng thể. Nhúng không còn "khung trong khung":
  bỏ thanh tiêu đề riêng của mô hình (nút tạm dừng thành nút nổi), bỏ thẻ bọc; điện thoại
  tràn sát mép.
- Số liệu theo khu: các phòng sản xuất (SX hôm nay toàn xưởng, top mã), Phòng đóng gói
  chính (SX hôm nay), Kho thành phẩm (tồn thùng/hộp/giá trị, mã tồn nhiều), các kho nguyên
  liệu/vật tư — tự khớp tên khu với kho ERPNext ("Kho đường" ↔ "Kho đường - HGC": giá trị
  tồn, mã giá trị lớn), Kho vật tư (+ nhập NVL hôm nay), Phòng kinh doanh (DS, theo kênh,
  top khách), Kế toán (hoá đơn bán/trả), Giám đốc (luỹ kế tháng), Chủ tịch (luỹ kế năm TC),
  Phòng họp (toàn cảnh), Bảo vệ (hàng ra/vào theo chứng từ), Nhà xe (đơn chờ giao, quá hạn).
  Khu không có số liệu phù hợp (WC, thay đồ, trạm biến áp…) chỉ hiện mô tả của mô hình.
  Chuyển động máy/người trong mô hình vẫn là minh hoạ, không phải dữ liệu vận hành.

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
