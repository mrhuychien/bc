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

## Định nghĩa số liệu dùng chung (đã chốt)

- **Doanh số** = `net_total` (tiền hàng trước VAT, loại hoá đơn số dư đầu kỳ). Mọi màn có doanh số ghi
  rõ dòng này ở cuối trang (`salesBasisNote()` trong `lib/format.js`). Portal NPP và Kế toán dùng
  `grand_total` (gồm VAT) nên số ở đó cao hơn.
- **Công nợ** tính như app **ketoan**: số dư sổ cái; riêng **MT theo bảng kê thanh toán của chuỗi**.
  Tiền ở nhóm Công nợ GỒM VAT.
- **Ngày Tết**: một nguồn duy nhất là **BC Settings › Ngày mùng 1 Tết**. Frontend nhận
  `BC_CONTEXT.tetDates` (lịch SX Tết tô mùng 1–3 theo bảng này, năm chưa khai mới dùng thuật toán âm
  lịch); app **pkd** đọc mềm bảng này (đè từng năm lên hằng số dự phòng của nó).
- **Kênh**: NPP / MT / Du lịch / **Showroom** / Khác — theo 4 nhóm gốc trong PKD Settings (`kenh_*`,
  đọc từng field: pkd chưa có `kenh_showroom` thì chỉ mất Showroom), không có PKD Settings thì dò từ
  khoá tên nhóm. Showroom chỉ hiện thẻ khi có số.
- **Sản xuất** = phiếu SẢN XUẤT nhập kho thành phẩm (`bc.api.sx.production_filter`): Manufacture (dòng
  thành phẩm — app sx ghi Work Order + Manufacture cho mã có BOM) + Material Receipt, TRỪ phiếu điều
  chỉnh của app sx (kiểm kê / bù sau kiểm kê có `custom_kiem_ke`; dọn lô / tồn âm theo `remarks`) + phiếu
  chuyển từ Kho Xưởng sản xuất (`SX Settings.kho_xuong`) vào Kho TP — trước D191 (12/10/2026) thành phẩm vào
  kho bằng phiếu chuyển này mà không ghi sản xuất vào Xưởng. Trước đây chỉ đếm Material Receipt → thiếu hàng
  có BOM và hàng chuyển từ Xưởng, thừa phiếu kiểm kê. Kho thành phẩm: BC Settings → `SX Settings.kho_tp` →
  "Thành phẩm - HGC".

## Công nợ (`#/cong-no`, `#/phai-tra`)

`bc.api.cn` — công ty do server chọn (Ketoan Portal Settings.default_company → Global Defaults), không
nhận từ client; cache dùng chung theo ngày.
- **Phải thu**: số dư GL từng khách trên TK phải thu (Ketoan Portal Settings.receivable_account, trống thì
  mọi TK loại Receivable). Quá hạn phân bổ FIFO như danh sách công nợ của Kế toán (số dư thuộc hoá đơn
  mới nhất; hạn = due_date, trống thì ngày HĐ + invoice_due_days); phần không gắn được hoá đơn → cột
  "Chưa rõ hạn". Tuổi nợ theo aging_bucket_1/2/3 (mặc định 30/60/90). DSO như `ketoan.get_dso` (nợ GL toàn
  công ty / doanh thu gồm VAT từ dso_window_days ngày trước, không cận trên — y như Kế toán).
- **MT**: gọi thẳng helper của ketoan (`mt_debt._fetch/_enrich/_rollup/_orphan_returns` — không guard,
  không phụ thuộc phiên); khách MT (nhóm = Ketoan Portal Settings.mt_customer_group) bị loại khỏi phần GL.
  Không có bảng kê / helper lỗi → MT tính theo GL, trang ghi rõ.
- **Phải trả & quỹ**: GL TK loại Payable (tuổi nợ theo hạn Purchase Invoice, lịch trả 14 ngày); số dư TK
  Cash/Bank (`cash_bank_account_filter`), số tài khoản ngân hàng trong tên TK được che (`•••1234`, kể cả số
  viết theo nhóm "1903 5678 9012").

## ATTP (`#/attp`)

`bc.api.attp` — cùng số với màn **Tổng quan ATTP** và **Báo cáo tháng** của Ban ISO (app sx): gọi helper
của sx (19 mảng, hộp nhắc, luật đèn), chỉ làm lại 2 chỗ phụ thuộc người xem: chỉ số Vòng kiểm (sx gọi
`dashboard` có guard) và mục biên bản (sx tính "chờ BẠN ký" theo người mở màn). Không trả route SPA của
sx, bỏ chi tiết dòng sổ. Site không cài sx → trang báo "chưa có số liệu".

## Vận chuyển (`#/van-chuyen`)

`bc.api.vc` đọc mềm app **vanchuyen** (+ phiếu kiểm thu hồi của **ketoan**), một tháng chọn được (mặc
định tháng này, cắt ở hôm nay):

- **Giao hàng**: hoá đơn bán đã duyệt trong tháng theo hình thức × trạng thái vận chuyển (bỏ hàng trả,
  hoá đơn đầu kỳ, đúng nhóm khách `Showroom` như vanchuyen), giá trị trước VAT. Đơn **chờ giao quá 3
  ngày** là ảnh chụp hôm nay (mọi tháng, bỏ đơn cũ hơn 180 ngày). Đơn xe nhà **chưa xếp chuyến** tính
  theo dòng chuyến (chuyến nháp vẫn tính — cột trạng thái xếp trên hoá đơn chỉ cập nhật khi duyệt
  chuyến). **Giao được ngay lần đầu** = dòng chuyến kết thúc đầu tiên của mỗi đơn là "Đã giao".
- **Chuyến**: tải trung bình có trọng số theo m³, bỏ xe chưa khai sức chứa.
- **Cước**: chỉ chuyến đã duyệt; % trên doanh thu ĐÃ GIAO (đơn tách nhiều chuyến chia theo số kiện);
  cảnh báo chuyến đánh dấu đã trả cước mà bút toán chi chưa duyệt / đã huỷ, và phần cước sửa tay.
- **Sự cố**, **thu hồi hàng** (chặng theo phiếu kiểm của Kế toán khi đã có), **đội xe** (lịch đăng
  kiểm / thay dầu / bảo dưỡng gọi hàm thuần của vanchuyen, chi phí xe năm nay).

Không trả tên / SĐT lái xe, tên khách, người liên hệ, ghi chú tự do; biển số xe được hiện.

## Nhân sự (`#/nhan-su`)

`bc.api.ns` — chỉ số tổng hợp, không tên / mã nhân viên:

- **Quân số** theo trạng thái × bộ phận (khoán = bộ phận "Công khoán - HGC" như app ns); **vào / nghỉ
  12 tháng** theo ngày vào làm / ngày nghỉ trên hồ sơ (không dùng ngày sửa hồ sơ).
- **BHXH**: tỷ lệ đóng trong số đang làm, số người quá 30 ngày chưa đóng mà chưa ghi lý do (= cảnh báo
  của ns). Lý do không đóng chỉ hiện gộp, nhóm < 5 người bị gộp.
- **Quỹ lương THỰC NHẬN** 12 tháng theo loại: công nhật (SalaryDay) và khoán (phiếu lương khoán của
  sx); mỗi người mỗi tháng một phiếu như màn Lương của ns. Tháng trước + tháng này là tạm tính (gồm
  nháp); tháng cũ hơn chỉ phiếu đã duyệt. Trước tháng có phiếu đầu tiên hiện "chưa có dữ liệu" (không
  phải 0). **Không gồm lương Ban lãnh đạo.** Theo bộ phận chỉ cho tháng trước; nhóm < 5 người không hiện
  tiền (gộp vào nhóm khác), tiền làm tròn 100.000 đ. Cảnh báo khi site chưa bật tính lại phiếu công nhật
  (`ns_tinh_lai_salaryday`).
- **Giấy tờ** hết hạn / sắp hết (HĐ, khám SK, ATTP — ATTP khớp cả option lưu sai chữ trên site) và
  **việc tồn** của Phòng nhân sự (gọi hàm thuần `canh_bao.tinh` của ns, đếm theo người).

## Kiểm thử

Bộ thử chạy SQL thật trên MariaDB với schema sinh từ DocType JSON của ERPNext v16 + các app (không cần
bench): sản xuất 41, kênh 9, công nợ 30 (code ketoan thật cho MT), ATTP 15 (so vi sai với `tong_quan`
/ `so_lieu` của sx thật), ngày Tết 6 + 5, vận chuyển 59 (lịch xe gọi code vanchuyen thật), nhân sự 52
(so vi sai với cảnh báo của ns thật), giao diện Playwright 104 (desktop + điện thoại), tab mở trước
deploy 6. Mỗi bản sửa đều đã thử phá (đưa code về bản lỗi → test phải đỏ). Chạy:
`docs/verified/harness/run_all.sh` (xem README trong thư mục đó).

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
  qua, luỹ kế tháng so cùng kỳ, SX hôm nay (phiếu sản xuất nhập kho thành phẩm như SX
  Hàng Tết — `production_filter`), tồn kho thành phẩm, Sales Order chờ giao, Purchase Receipt hôm nay, sự kiện.
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
               common.py, kd.py, tet.py, sx.py, live.py, cn.py (công nợ), attp.py, _provinces.py
bc/www/        bc.py (guard + BC_CONTEXT), bc.html (import map + shell)
bc/public/bc/  shell.js, shell.css, lib/, components/, views/
bc/scripts/    dump_report_sql.py, compare_tet_reports.py
docs/          tet-curdate-audit.md, report-sql/
```
