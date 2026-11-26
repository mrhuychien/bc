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
  **Bỏ phiếu NHẬP LẠI sau kiểm kê** (`sx.nhap_lai_sau_kiem_ke`): lần kiểm kê sx đã chốt ở Kho TP đưa một mã KHÔNG
  ĐẾM về 0 (không dòng đếm nào — bấm "Không còn" là hàng hết thật; biên bản: số trước > 0, số sau = 0, bỏ lô đang thu
  hồi; sổ kho xác nhận phiếu của lần kiểm kê xuất đúng số đó, không tính phiếu bù D216) rồi hàng được nhập lại vào lô
  theo hạn dùng đúng bằng số đó → nhóm phiếu kho của MỘT phiếu Nhập TP (sx ghi mỗi lô một phiếu kho) hoặc một phiếu kho
  nhập trên Desk, TẠO sau giờ chốt (không theo giờ ghi sổ — phiếu sx ghi ngày lập phiếu), trong 60 ngày, có số của mã
  đúng bằng số bị đưa về 0, nhóm tạo sớm nhất, là nhập lại, không phải sản xuất (10/2026, KK-2026-002: ĐTL, HDT, BCT,
  CVTT, CĐTT, CLV, SR900 — không bỏ thì cùng số hàng tính hai lần). Áp cho SX Hàng Tết (theo mã, theo ngày, chi tiết
  ngày) và Thời gian thực; thẻ sản phẩm ghi rõ phần không tính. Kho › Nhập TP (đối chiếu sổ kho ↔ phiếu nhập) vẫn
  theo sổ.
  Màn **Báo cáo sản xuất** (`#/san-xuat`) KHÔNG theo định nghĩa này: ở đó là số hộp QC ghi đóng xong ở phần Ghi hộp
  của app sx, trước khi vào kho (mục riêng dưới).

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
  hoá đơn đầu kỳ, đúng nhóm khách `Showroom` như vanchuyen), giá trị trước VAT. **Giao được ngay lần
  đầu** = dòng chuyến kết thúc đầu tiên của mỗi đơn là "Đã giao".
- **Ảnh chụp hôm nay** (không đổi theo tháng chọn, như pool điều phối của vanchuyen; bỏ đơn cũ hơn 180
  ngày): đơn **chờ giao quá 3 ngày** và đơn xe nhà **chưa xếp chuyến** — tính theo dòng chuyến (chuyến
  nháp vẫn tính; cột trạng thái xếp trên hoá đơn chỉ cập nhật khi duyệt chuyến).
- **Chuyến**: tải trung bình có trọng số theo m³ (% thể tích), bỏ chuyến mà xe chưa khai sức chứa.
- **Cước**: chỉ chuyến đã duyệt. % cước / doanh thu đã giao tính CẢ HAI vế trên chuyến đã hoàn thành
  (đơn tách nhiều chuyến chia theo số kiện). Cảnh báo: chuyến đánh dấu đã trả mà bút toán chi chưa duyệt /
  đã huỷ; chuyến đã huỷ mà bút toán trả cước còn hiệu lực; cước sửa tay. **Tháng dưới 5 lái xe chạy: không
  hiện tiền cước** (cước là thu nhập lái xe — cùng ngưỡng với lương).
- **Sự cố** ("hàng chưa về" chỉ tính sự cố có hàng quay về — trường này mặc định "Chưa về" trên mọi sự
  cố), **thu hồi hàng** (chặng theo phiếu kiểm của Kế toán khi đã có), **đội xe** (lịch đăng kiểm / thay
  dầu / bảo dưỡng gọi hàm thuần của vanchuyen, chi phí xe năm nay).

Mỗi khối chạy riêng: site chạy bản vanchuyen cũ (thiếu cột hàng-về / trả cước) chỉ mất đúng chỉ số đó; lỗi
bất kỳ trong một khối chỉ tắt khối đó (ghi Error Log). Không trả tên / SĐT lái xe, tên khách, người liên hệ,
ghi chú tự do; biển số xe được hiện.

## Nhân sự (`#/nhan-su`)

`bc.api.ns` — chỉ số tổng hợp, không tên / mã nhân viên:

- **Quân số** theo trạng thái × bộ phận (khoán = bộ phận "Công khoán - HGC" như app ns); **vào / nghỉ
  12 tháng** theo ngày vào làm / ngày nghỉ trên hồ sơ (không dùng ngày sửa hồ sơ).
- **BHXH**: tỷ lệ đóng trong số đang làm, số người quá 30 ngày chưa đóng mà chưa ghi lý do (= cảnh báo
  của ns). Lý do không đóng chỉ hiện gộp, nhóm < 5 người bị gộp.
- **Quỹ lương THỰC NHẬN** 12 tháng theo loại: công nhật (SalaryDay) và khoán (phiếu lương khoán của
  sx); mỗi người mỗi tháng một phiếu như màn Lương của ns. Tháng trước + tháng này là tạm tính (gồm
  nháp); tháng cũ hơn chỉ phiếu đã duyệt. Trước tháng có phiếu đầu tiên hiện "chưa có dữ liệu" (không
  phải 0); tổng tháng ghi "chưa gồm khoán" khi một loại chưa có phiếu. **Không gồm lương Ban lãnh đạo.**
  Theo bộ phận chỉ cho **tháng đã chốt gần nhất, phiếu đã duyệt** (tháng tạm tính đổi theo từng phiếu HR
  nhập — so hai lần xem sẽ ra lương một người). Ngưỡng **5 người có tiền trên phiếu** (phiếu 0 đ không
  tính): nhóm nhỏ hơn gộp vào nhóm khác, không hiện tiền; tiền làm tròn 100.000 đ; người xem không bỏ qua
  cache được (chỉ quản trị bấm Làm mới mới tính lại ngay). Cảnh báo khi site chưa bật tính lại phiếu công
  nhật (`ns_tinh_lai_salaryday`).
- **Giấy tờ** hết hạn / sắp hết (HĐ, khám SK, ATTP — ATTP khớp cả option lưu sai chữ trên site) và
  **việc tồn** của Phòng nhân sự (gọi hàm thuần `canh_bao.tinh` của ns, đếm theo người).

## Báo cáo sản xuất (`#/san-xuat`)

`bc.api.sx_hop` — số hộp sản xuất **QC ghi theo ngày ở phần Ghi hộp của app sx**, một tháng chọn được (mặc định tháng
này, cắt ở hôm nay; tháng sai dạng / tương lai → tháng này — như mọi màn theo tháng; Hỏi đáp thì từ chối tháng tương
lai, xem dưới). Nhóm menu **Sản xuất**, đứng trước SX Hàng Tết.

- **Nguồn** (chỉ đọc): ngày sản xuất `SX Ngay San Xuat` chưa huỷ → bảng vào hộp `SX Bang Vao Hop` chưa huỷ của ngày đó →
  dòng `SX Bang Vao Hop Item` (mã, số hộp, cờ công nhật / khoán chung). Ngày huỷ, bảng huỷ không tính.
- **Đếm gì**: mọi dòng đều là hộp đã làm — dòng khoán của từng người, dòng **công khoán chung** (cả hai là "khoán") và
  dòng **công nhật** (dòng vừa công nhật vừa khoán chung tính là công nhật, như sx). Tổng từng ngày = đúng con số ô ngày
  trên lịch tháng của tab Ghi hộp mà quản lý thấy (bộ thử so vi sai với `sx.api.lich` thật). Dòng chưa chọn mã vẫn vào
  tổng ngày (nhóm "Khác") nhưng không có dòng theo mã.
- **Đã chốt** = viền xanh của lịch Ghi hộp: ngày có bảng còn hiệu lực mà phần vào hộp đã đồng bộ lương xong (không chờ,
  không lỗi) — từ D123 sx bỏ nút chốt nên cờ `chot_vaohop` không còn ai đặt; sx cũ chưa có hai cột đồng bộ thì dùng cờ
  đó. KPI cảnh báo "n ngày chưa chốt" (số còn có thể đổi).
- **Màn**: Tổng hộp tháng (so cùng kỳ tháng trước — ngày 1 tới cùng ngày trong tháng, kẹp cuối tháng — và cả tháng
  trước), quy thùng, TB hộp / ngày có ghi, ngày ghi gần nhất, công nhật (hộp + tỷ lệ), số mã; biểu đồ từng ngày (khoán /
  công nhật chồng nhau, Chủ nhật tô đỏ, đường TB / ngày của tháng trước); bảng **Theo ngày** (ngày không ghi hiện "—",
  bấm một ngày mở chi tiết theo mã của ngày đó — `get_day`, có tách phần khoán chung); nhóm Tết / truyền thống / khác;
  bảng **Theo mã** (10 dòng / trang); 12 tháng. Điện thoại: bảng theo ngày thành thẻ. `days` của API xếp **mới nhất
  trước** (như bảng; biểu đồ tự đảo lại).
- **Chi tiết ngày không cũ hơn dòng ngày**: màn gửi `since` = `meta.generated_at` của bảng tháng đang hiện; bản cache
  của `get_day` tính không sau mốc đó thì máy chủ tính lại (sau ↻ hay Làm mới chung, hôm nay QC còn ghi tiếp, chi tiết
  vẫn khớp dòng ngày); bản cache mới hơn vẫn dùng.
- **Lỗi ≠ chưa cài**: chỉ `meta.sx = false` mới hiện "app sx chưa cài"; máy chủ tính hỏng (`error: true`, đã ghi Error
  Log) → "Không tải được số ghi hộp — quản trị xem Error Log"; chi tiết ngày hỏng → "Không tải được chi tiết ngày".
- Thùng = hộp / quy cách "Thùng" của mã (như SX Hàng Tết): mã chưa khai quy cách không góp thùng, số hộp vẫn đủ. Làm
  tròn 2 số lẻ một lần: thùng một ngày (= total của chi tiết ngày) từ tổng chưa làm tròn của các mã; KPI thùng = cộng cột
  thùng các ngày, nên dòng "Cả tháng" đúng bằng cộng cột (cộng thùng theo mã có thể lệch vài phần trăm thùng). Mã ẩn
  (Quản trị › Ẩn sản phẩm) chỉ mất khỏi danh sách theo mã; mọi tổng giữ nguyên.
- **Khác SX Hàng Tết và Nhập TP**: SX Hàng Tết đếm hàng **đã nhập kho thành phẩm** theo phiếu kho (Manufacture /
  Material Receipt…); Kho › Nhập TP đếm **phiếu nhập thủ kho đã duyệt** và giá trị theo sổ. Màn này là số **đã ghi là
  đóng xong** trong ngày, trước khi vào kho — nên lệch ngày / lệch số với hai màn kia là bình thường (hàng ghi hôm nay có
  thể mai mới nhập kho, hộp chưa nhập vẫn nằm ở "đã vào hộp chưa nhập kho" của Nhập TP).
- **Riêng tư**: chỉ số hộp theo ngày × mã × loại dòng. Không đọc người làm, người ghi, đơn giá, thành tiền, bảng ăn ca,
  người chốt (bộ thử tĩnh chặn trên SQL của module).
- **Ghi hộp so với nhập kho** (khối giữa "Theo ngày" và "Theo mã", `get_compare`, cùng tháng chọn; tải song song, hỏng
  riêng — khối này lỗi không xoá phần trên và ngược lại):
  - **Ghi hộp** = đúng số hộp ở trên, theo **ngày sản xuất**. **Nhập kho** = phiếu nhập thành phẩm **thủ kho đã duyệt**
    (`SX Phieu Nhap TP` docstatus 1) theo **ngày nhận**, số = Σ số đếm của dòng — tổng tháng và từng ngày bằng đúng màn
    Kho › Nhập TP (bộ thử so vi sai). Phiếu nháp (kể cả phiếu nháp Tết đang giữ hàng) và phiếu huỷ chưa phải nhập kho.
  - **Chênh lệch = nhập kho − ghi hộp**, cùng dấu với bảng đối chiếu kho của Quản lý trên app sx
    (`sx.api.portal._vao_hop_vs_nhap_kho`, bộ thử so vi sai từng mã). Âm = đã ghi hộp mà chưa nhập kho (bình thường khi
    hàng còn ở xưởng); dương = kho nhận nhiều hơn số ghi (thường là ghi sót). Màn luôn ghi dấu + chữ ("−120 hộp · chưa
    nhập kho", "+30 hộp · nhập vượt số ghi", "0 · khớp"), không chỉ tô màu. sx cắt số đếm lẻ thành số nguyên; bc giữ 2
    số lẻ — số nguyên thì hai bên trùng.
  - **Từng ngày lệch là thường**: hàng ghi hôm nay mai mới nhập, hàng ghi cuối tháng trước nhập đầu tháng này — xem cột
    **Luỹ kế** (cộng dồn chênh lệch từ ngày 1). Bảng theo ngày chỉ hiện ngày có dòng **so được** (hộp hoặc phiếu của mã
    đơn vị Hộp, hộp chưa chọn mã) — ngày chỉ có mã khác đơn vị / dòng phiếu không mã không thành dòng "0 · 0 · 0".
    Ngay trên ba thẻ ghi tháng của khối ("Tháng MM/YYYY · từ … đến …"); trang tổng lỗi thì ô chọn tháng vẫn giữ tháng vừa
    chọn — ô chọn, khối và nút làm mới luôn cùng một tháng.
  - **Đơn vị**: ghi hộp đếm hộp, phiếu nhập đếm theo đơn vị kho của mã. Mã có đơn vị kho khác "Hộp" (hoặc không còn
    trong danh mục) vẫn liệt kê với nhãn **ĐVT khác** (cột chênh lệch "—"; API trả `lech: null` để Trợ lý AI không trích
    "Kg trừ hộp" như lệch hộp) nhưng ra khỏi cả hai vế của mọi tổng và mọi dòng ngày. Hộp **chưa chọn mã** vẫn vào ghi hộp, không phiếu nào khớp được nên nằm trong phần "chưa nhập kho"; dòng
    phiếu không mã không cộng. Ghi chú dưới bảng nói số hộp / số mã bị loại khi có.
  - Thẻ **Chưa nhập kho** / **Nhập vượt số ghi** = cộng phần âm / phần dương theo từng mã, mọi mã đơn vị Hộp kể cả mã
    "khớp" (nên lệch tổng = nhập vượt − chưa nhập, đúng cả sau làm tròn: ba mã +0,004 → "nhập vượt 0,01 hộp (0 mã)"), kèm số mã; chip lọc bảng theo mã theo hai nhóm đó. Mã xếp nhóm theo lệch **đã làm tròn 2 số lẻ** — đúng số
    trên bảng: lệch 0,004 là "0 · khớp" ở thẻ, bảng lẫn chip (số mã ở thẻ = số đếm ở chip); mã không có hộp mà nhập làm
    tròn 0 không thành dòng. Mọi số lượng làm tròn 2 số lẻ một lần từ số gốc (cả hai số "hiện tại" lấy từ Nhập TP: Nhập TP
    hiện 3 số lẻ, ở đây 2 số lẻ từ cùng số gốc — 0,3749 là 0,37, không 0,38).
  - Trên điện thoại bảng ngày đối chiếu là thẻ 2 cột (số 6 chữ số có phần lẻ không đè nhau), bảng theo mã cũng thành thẻ
    (tên ở hàng đầu, Ghi hộp · Nhập kho · Chênh lệch có nhãn — cột chênh lệch không bị đẩy khuất).
  - Dải **Hiện tại** (tới hôm nay, KHÔNG theo tháng chọn), mỗi số tính riêng (một số hỏng thì hiện "—"): **Đã ghi hộp,
    chưa nhập kho** = khối "đã vào hộp chưa nhập kho" của Nhập TP (`kho_nhap._vao_hop`, port `sx.api.khotp.tran_con_lai`
    / `cho_nhan`: 30 ngày gần nhất, trừ phần phiếu nháp Tết), **Phiếu nhập chờ thủ kho duyệt** = khối phiếu chờ duyệt của
    Nhập TP (`kho_nhap._cho_duyet`), **Kho nhận vượt số ghi hộp** = sổ nợ vào hộp sx tự ghi khi phiếu nhận vượt số chấm
    (`SX No Vao Hop` đang "Chờ chấm", như `khotp.so_no_vao_hop`; thiếu bảng → "—"). Số nợ theo đơn vị kho của từng mã
    (sx ghi nợ cả mã Kg / Gói) nên ô này chỉ cộng mã đơn vị **Hộp** (số, số mã, lâu nhất) và nói thêm "n mã đơn vị khác
    không cộng" — như sx `so_no_vao_hop` không bao giờ cộng lẫn mã. Phiếu chờ duyệt lẫn đơn vị → "nhiều đơn vị kho, không
    cộng" thay vì một số hộp. Hai số đầu bấm sang Nhập TP. Phần tháng hỏng (`error: true`) thì vẫn hiện dải này.
  - Site không cài sx → khối ẩn (phần trên đã báo); có sx mà thiếu bảng phiếu nhập → "Chưa đối chiếu được"; tháng không
    có cả hai → "Tháng này chưa có số ghi hộp lẫn nhập kho". Không đọc người lập / duyệt, ghi chú, lý do, tên phiếu.
- Site không cài sx / thiếu bảng → "Chưa có số liệu ghi hộp" (không lỗi, không Error Log); tháng không có số → "Chưa có
  số ghi hộp trong tháng này". Ẩn / hiện được như mọi mảng (`_guard("san-xuat")`). Trợ lý AI đọc hai khối tháng này
  (`san-xuat.overview` và `san-xuat.compare`, nhóm "Kho & SX"; hỏi đáp nhận `thang` ở cả hai), chưa có quy tắc riêng. Gói số cắt danh sách còn 30
  phần tử đầu — vì `days` mới nhất trước, tháng 31 ngày chỉ mất ngày 1, không mất hôm nay. Hỏi đáp từ chối `thang` sau
  tháng này (mọi khối theo tháng: Báo cáo sản xuất, Kiểm kê, Nhập TP, Vận chuyển, ATTP báo cáo) — các khối đó lặng lẽ trả
  tháng này nên mô hình sẽ đọc nhầm số tháng này thành số tháng hỏi.

## Kho (`#/ton-kho`, `#/han-dung`, `#/kiem-ke`, `#/nhap-tp`)

Bốn màn, mỗi màn một mảng ẩn / hiện được. Chung cho cả nhóm (`bc.api.kho`):

- **Số "bây giờ" = Bin** (như ERPNext / sổ cái, gồm cả phiếu ghi ngày sau hôm nay); giá trị tại một ngày và mọi dòng
  chảy (nhập, xuất bán, kiểm kê, điều chỉnh) = Σ chênh lệch giá trị trên sổ kho (dòng chưa huỷ). Giá trị theo **giá vốn,
  chưa VAT**. Không bao giờ cộng số lượng sổ kho làm số tồn (phiếu kiểm kê không lô ghi số lượng 0).
- Công ty = công ty mặc định của Kế toán (như Công nợ); kho thuộc công ty theo danh mục kho. **Vai trò kho**: kho thành
  phẩm (BC Settings / SX Settings), cửa hàng (kho của POS Profile đang dùng), hàng đi đường (loại Transit), xưởng / bán
  thành phẩm / nguyên vật liệu (SX Settings), **kho trả về & cách ly** (SX Settings hoặc cờ kho hàng lỗi) — kho nhóm cấu
  hình được bung ra các kho con; kho ngừng dùng còn hàng vẫn tính.
- **Thành phẩm** = danh sách thành phẩm của app sx (gồm mã ngừng dùng); site không có sx → mọi mã trong cây nhóm Tết và
  truyền thống. Nhóm hàng theo **cây** (nhóm con của "Hàng Tết" vẫn là Tết — các màn Kinh doanh so đúng tên nhóm, chỉ lệch
  khi nhóm có nhóm con; dải sức khoẻ báo).
- Số lượng theo đơn vị kho; **không cộng Hộp với Kg**; thùng theo quy cách "Thùng" của mã, mọi tổng thùng kèm phần hộp
  chưa khai quy cách. **Giá vốn dự phòng** (tồn âm, mã chưa có giá): giá kho đó → giá kho khác cùng công ty → lần ghi sổ
  gần nhất → giá vốn trên mã → "chưa có giá vốn"; không dùng giá mua.
- Đọc mềm app sx; không gọi method whitelisted nào của app khác, không dùng hàm có ghi dữ liệu của sx (bộ thử chặn
  import). BC Settings mục **Kho**: số ngày tính số ngày tồn (90), chậm luân chuyển (90), tồn chết (180), cận date (60).

**Tồn kho** — giá trị tồn hiện tại theo khu vực kho và nhóm hàng (thành phẩm hộp / thùng ngoài kho trả về & cách ly; dòng
"Kho thành phẩm" cùng số với màn Thời gian thực), xu hướng 12 tháng + **nhập–xuất–tồn theo tháng** (tồn đầu + nhập mua,
xuất bán (giá vốn hàng xuất, gần như gộp — hàng trả MT/NPP không qua kho), kiểm kê sản xuất, phiếu kiểm kho cửa hàng &
kho khác, dọn tồn, nhập tạm, bù nợ BOM, nhập / xuất khác, nội bộ = tồn cuối — khớp từng đồng), **số ngày tồn kho**
(truyền thống luôn; Tết chỉ trong mùa bán), **hàng chậm luân chuyển / tồn chết** (theo ngày xuất bán hoặc dùng sản xuất
cuối, gồm xuất bù nợ BOM; Tết tách riêng theo giai đoạn mùa), **sức khoẻ số liệu** (định giá lại đang chạy / lỗi, phiếu
ghi ngày tương lai, sổ lệch Bin, cho phép âm, hoá đơn POS chưa gộp, hoá đơn chưa trừ kho, …). Phần quét cả sổ cache theo
ngày (Làm mới tính lại).

**Hạn dùng & tồn âm** — thành phẩm theo hạn dùng: hết hạn (lô hết hạn hôm nay vẫn còn hạn), cận date ≤ N ngày, chưa rõ
hạn (lô không ghi HSD, lô tồn cũ, phần chưa gắn lô, mã chưa quản lý lô), phần âm — các phần cộng lại **đúng bằng** tồn
thành phẩm theo sổ; giá trị theo lô là ước tính (số lượng × giá vốn bình quân kho). **Tồn không bán được** = kho trả về &
cách ly + lô đang thu hồi còn ngoài kho đó + hàng hết hạn. **Tồn âm** theo mã (giá trị theo giá vốn dự phòng) và theo lô.
Số theo lô chụp cùng lúc với Bin, giữ ≤ 1 giờ (ghi giờ chụp).

**Kiểm kê & điều chỉnh** (chọn tháng) — lần kiểm kê gần nhất từng kho (phiếu kiểm kê sx; cửa hàng / kho khác theo phiếu
kiểm kho ERPNext; kho sx lấy lần mới hơn của hai nguồn), phiếu đang đếm, phiếu huỷ chốt, độ chính xác tồn của lần kiểm
gần nhất; chênh lệch trong tháng: kiểm kê sản xuất (theo ngày hiệu lực của lần kiểm, gồm phiếu bù ghi lùi và phần ghi ở
**kho khác** khi bật quản lý lô — sx nhập bù tồn âm về 0 là điều chỉnh thật), phiếu kiểm kho cửa hàng & kho khác (thừa /
thiếu / đổi giá), dọn tồn của sx, **xuất huỷ / xuất mẫu / xuất khác** (không gồm xuất bù nợ BOM). Kiểm kê sản xuất ở đây
khớp dòng tương ứng của nhập–xuất–tồn trừ phần ghi lùi ngày.

**Nhập TP & giá vốn** (chọn tháng) — thành phẩm nhập kho theo phiếu nhập đã duyệt (từng ngày, 12 tháng, hộp + thùng +
giá trị theo sổ), đối chiếu phiếu ↔ phiếu kho, hàng nhập Kho TP ngoài phiếu sx; **tình hình hôm nay**: phiếu chờ duyệt
(phần sẽ thành nợ BOM), đã vào hộp chưa nhập kho, **nợ BOM đang mở** (giá tạm lúc nhập, tuổi, mã đã có BOM xử lý được
ngay), nguyên liệu còn treo trên sổ (ước tính), thành phẩm đang tồn giá vốn 0.

## Trợ lý AI (`#/tro-ly`, quản trị: `#/ai`)

Mỗi sáng 5:30 máy chủ đọc lại **đúng các con số của các màn báo cáo**, dùng quy tắc có ngưỡng để tìm việc đáng chú
ý toàn công ty, rồi (nếu bật) nhờ Claude viết lại lời cho dễ đọc. Lãnh đạo mở `/bc#/tro-ly` thấy danh sách việc
cần chú ý: cái gì, bao nhiêu, nên làm gì, bấm sang màn gốc để xem số. Đặc tả: `docs/SPEC_bc_ai.md`; bản này làm
giai đoạn P0 + P1 + P2 (P2: OpenAI phản biện lời AI, nhóm Kiểm soát chứng từ / giá / chỉ số lệch chuẩn, bản tin tuần /
tháng) + P3 (hỏi đáp bằng lời ở `#/hoi-dap`, đặc tả riêng `docs/SPEC_bc_ai_p3.md`, **mặc định tắt**) — mục "Hỏi đáp
(P3)" cuối phần này.

**Luồng một lượt chạy** (`bc.ai.pipeline.run_daily`, cron `30 5 * * *` giờ của site → hàng đợi `long`, chống chạy
trùng):

1. `collect` gọi lại 25 lượt method `bc.api.*` dưới Administrator (`refresh=1`, làm ấm luôn cache buổi sáng) → gói
   số `pack[mảng][tên]`: 24 mục đúng như các màn đang hiện (gồm Báo cáo sản xuất tháng này, nhóm "Kho & SX"), cộng số vận chuyển của tháng trước (chỉ để quy tắc đọc,
   không gửi mô hình). Không đọc thẳng chứng từ nào: muốn Trợ lý thấy thêm số gì thì thêm vào màn báo cáo trước.
2. 8 bộ dò hệ thống (`bc/ai/detectors/he_thong.py`, chỉ `SELECT`): Error Log tăng vọt, tác vụ định kỳ lỗi, email
   lỗi, hàng đợi ứ, sao lưu cũ, đĩa đầy, đăng nhập sai nhiều lần, Trợ lý lỗi 3 lượt liền. Error Log chỉ được đếm
   theo tên lớp lỗi / tên method của app đã cài; tiêu đề lỗi nguyên văn (có thể chứa email, tên khách) không vào
   gói số. Rồi 3 bộ dò kiểm soát (P2, mảng `tro-ly`, đọc được gói vừa dựng): chứng từ (`chung_tu.py`), giá
   (`gia.py`), lịch sử chỉ số (`kpi.py`) — mục "Nhóm Kiểm soát" dưới.
3. 49 quy tắc (`bc/ai/rules/*.py`, hàm thuần trên gói số, không SQL): kinh doanh 5, kho & sản xuất 11, công nợ 7,
   vận chuyển 6, nhân sự 3, ATTP 2, hệ thống 8, kiểm soát 7. Từng quy tắc đọc số nào, so ngưỡng ra sao:
   `docs/ai-rules-audit.md`.
4. Lưu vào `BC AI Insight` theo khoá tín hiệu: mới → mở; còn → cộng ngày kéo dài; hết → tự đóng; nguồn số lỗi →
   **giữ nguyên**, không đóng nhầm; đã đóng mà xuất hiện lại → mở lại.
5. Nếu bật AI, có khoá và chưa chạm trần chi: mỗi nhóm một lượt gọi Claude — viết lại lời, xếp ưu tiên, thêm khuyến
   nghị theo **bộ phận**, và được nêu thêm tối đa 3 nhận định ngoài quy tắc.
6. Máy chủ thay số vào lời rồi kiểm; lời không qua kiểm thì bỏ, tín hiệu giữ lời theo quy tắc.
7. (P2, khi đặt `ai_openai_model`) Ngay sau mỗi nhóm viết xong: OpenAI phản biện các lời AI vừa lưu của nhóm đó —
   mục "Phản biện" dưới.
8. Ghi `BC AI Run`: một dòng tổng + một dòng mỗi lượt gọi (token, chi phí, trạng thái) và ảnh chụp 70 chỉ số đầu màn.

Bước 5–7 hỏng kiểu gì (tắt AI, hết credit, API lỗi, quá giờ) cũng chỉ thành một trạng thái trong `BC AI Run`; màn
vẫn hiện đủ tín hiệu với nhãn "Quy tắc". Phản biện chạy sau khi lời của nhóm đã được lưu chắc: phản biện hỏng không
xoá được lời đã viết.

**Luật số.** Mô hình **không được viết con số**. Mọi số trong lời là chỗ giữ `{{path|kiểu}}` trỏ vào gói số
(`{{cong-no.receivables.kpis.overdue_pct|pct}}`), kiểu `tien | so | pct | ngay | chu`; máy chủ chèn số thật theo
đúng cách viết của màn báo cáo ("1,6 tỷ", "251 triệu", "35,0%", "5/11/2026"). Sau khi chèn, phần lời do mô hình viết
được soát lại; phạm một luật dưới đây, hoặc path không có thật, sai kiểu, path của nhóm khác → bỏ cả nhận định (đếm ở
cột "Bị loại" của lượt chạy, quản trị xem ở `#/ai`), thẻ giữ lời của quy tắc. Lời theo quy tắc cũng dựng bằng chỗ
giữ nên luôn khớp màn gốc tại lúc chạy.

Bộ soát là **danh sách cho phép** — cái gì không nằm trong danh sách thì bị loại:

- **Chữ số viết tay** chỉ được ở bốn dạng: (1) năm `20xx` hoặc cặp năm "2026/27"; (2) ngày **đủ năm** ("5/11/2026",
  "05.11.2026", "2026-11-05"), tháng/năm "10/2026", riêng "24/7" — "5/11" thiếu năm bị loại; (3) mã chứng từ / mã
  hàng viết hoa **chép nguyên văn từ dữ liệu đã gửi cho mô hình** (mã bịa, mã của dòng bị cắt khỏi đề bài, kiểu
  "SL-350 khách" bị loại), số hiệu sau ISO / HACCP / TCVN / QCVN / TK / QĐ / NĐ / TT, và cách viết tắt "T10",
  "Q3/2026"; (4) thời hạn / thứ tự tối đa hai chữ số đứng sát từ chỉ thời gian ("trong 7 ngày", "quý 4", "tuần 2").
  Cả bốn dạng vẫn bị loại khi có đơn vị đi sau ("5/11/2026 tỷ", "Tết 26 tỏi", "tháng 10 lần").
- **Số viết bằng chữ** bị loại khi đứng trước đơn vị, dù viết hoa, không dấu, viết tắt, tiếng lóng hay tiếng Anh
  ("HAI TỶ", "ba tram trieu", "hai mươi k", "năm xị", "five million"); cũng bị loại phân số bằng chữ ("ba phần
  năm"), bội số ("nhân đôi", "gấp ba", "tăng ba lần"). Số La Mã I / V / X chỉ được đứng sau từ chỉ thứ tự ("quý IV").
- **Chỉ chữ La-tinh**: chữ của bảng chữ khác (Nga, Hy Lạp…) bị loại; chữ trông như chữ số ("I2O", "lOO triệu") được
  tính là số.
- **Quanh mỗi chỗ giữ** (mọi kiểu): ngay trước chỉ được là đầu câu, một từ thường, hoặc `( , : ;` rồi dấu cách;
  ngay sau chỉ được là hết câu, một từ thường, hoặc dấu đóng / ngắt rồi dấu cách. Không được là chữ số, dấu cộng
  trừ, đơn vị, tên tiền tệ, "đồng" (trừ "đồng hồ", "đồng thời", "đồng nghiệp"…), "lần", "năm", từ chỉ số, từ phép
  tính ("trừ", "cộng", "trên", "gấp", "âm"…), "điểm" sau tỷ lệ. Giữa hai chỗ giữ luôn phải có một từ thường.
- Tiêu đề và mỗi khuyến nghị được soát như một dòng; trong thân, xuống dòng sau chỗ giữ không tính là hết câu.
- **Kiểu phải đúng với con số** — số đếm không được viết thành %, tiền không được viết thành số đếm (đối chiếu với
  70 chỉ số đã khai kiểu, với lời quy tắc của lượt đó, còn lại xét theo tên khoá).

Lời nhắc gửi mô hình nêu đủ các luật trên kèm ví dụ đúng / sai (test kiểm từng ví dụ đúng như lời nhắc nói). Soát
nhầm thì thẻ chỉ quay về lời quy tắc; soát sót mới là lỗi, nên bộ soát nghiêng về phía loại. **Giới hạn đã biết**
(máy không phân biệt được thật / giả): dạng chữ số được phép nhưng dùng sai nghĩa ("DSO 62 ngày"); số bằng chữ không
kèm đơn vị và không sát chỗ giữ ("hai khách lớn nhất"); số La Mã có L, C, D, M không kèm đơn vị.

Thẻ của quy tắc **không chạy được** ở lượt gần nhất (nguồn số lỗi) vẫn hiện nhưng mang nhãn "Số ngày … — chưa cập
nhật được", để số cũ không bị đọc như số sáng nay.

**Luật riêng tư.**

- Khoá API chỉ nằm trong `site_config.json` (`bc_ai_anthropic_key`, `bc_ai_openai_key`); không ở DocType, không trả ra API, không vào
  Error Log (thông báo lỗi được xoá mọi chuỗi trùng khoá trước khi lưu; Error Log của phần này chỉ ghi tên loại lỗi
  và dòng code). Chỉ `bc/ai/llm/` được gọi mạng và đọc khoá. Khoá dán lỗi (có dấu cách, xuống dòng) được coi như
  chưa có khoá — lượt chạy ghi `khong-khoa`.
- Gửi đi chỉ có payload của bc (đã qua luật riêng tư của từng màn: không tên nhân viên, lương gộp nhóm, số tài
  khoản đã che). Tên khách và nhà cung cấp được thay bằng mã `KH#0001`, `NCC#0001` trước khi gửi và đổi lại khi lưu
  (`ai_mask_parties`, mặc định bật):
  - tên trên hồ sơ, mã hồ sơ, và cả tên cũ còn nằm trên hoá đơn đã duyệt (khách đổi tên) về cùng một mã;
  - tên nằm giữa một câu (vd "Nguồn: <tên NCC>" trong số ATTP) cũng được thay, khi đứng riêng thành từ và đủ dài
    (từ 2 từ hoặc 6 ký tự);
  - ô nào mang tên khách / NCC / chuỗi siêu thị mà không khớp hồ sơ nào thì vẫn được cấp mã mới — không để lọt;
  - khi lưu, chỉ mã **đã thật sự gửi trong lượt gọi đó** mới được đổi lại thành tên; mã mô hình tự bịa bị loại.
  Ghi chú của quản trị trên thẻ và ô "Bối cảnh công ty" là chữ tự do: ghi chú được che như trên, còn tên gọi tắt
  hoặc viết khác hồ sơ thì máy không nhận ra — đừng ghi tên riêng vào hai chỗ này.
- Đề bài và gói số không được lưu, không được ghi log. Lời chỉ được lưu sau khi đã thay số và kiểm.
- Người xem chỉ thấy nhận định dành cho lãnh đạo, đang mở, và **mọi** mảng mà nhận định dùng số đều đang hiện với
  họ (ẩn mảng Công nợ → nhận định công nợ biến mất; ẩn mảng Trợ lý AI → mất menu, API trả 403). Chứng từ liên quan,
  ghi chú quản trị, nhóm Hệ thống chỉ System Manager thấy.
- Mảng đang ẩn không được gửi cho mô hình. Lời AI được tính là "dùng số" của mọi mảng mô hình đã thấy trong lượt
  gọi đó, nên **vừa ẩn thêm một mảng thì các thẻ lời AI cùng nhóm tạm biến mất với người xem cho tới lượt chạy sau**
  — ẩn xong hãy bấm "Chạy ngay" ở `#/ai` để lời được viết lại không có số của mảng đó.
- Việc quản trị đã "Bỏ qua" không quay lại dưới dạng nhận định tự do của AI.
- Lời mô hình chỉ được trích số có trong **chính đề bài nó nhận**: số nằm trong khối không gửi (lịch sử chỉ số của mọi
  mảng, số vận chuyển tháng trước) hay phần danh sách bị cắt khỏi đề bài thì máy chủ vẫn điền được, nhưng lời đó bị loại
  như path sai (để một nhận định không mang số của mảng đang ẩn vào nhóm khác).
- bc vẫn chỉ đọc: phần này chỉ ghi `BC AI Insight`, `BC AI Run`, `BC AI Brief` và mục "Trợ lý AI" của BC Settings.

**Cấu hình** (`/bc#/ai`, hoặc mục "Trợ lý AI" trong `/app/bc-settings` — mọi field permlevel 1):

| Field | Ý nghĩa | Mặc định |
|---|---|---|
| `ai_enabled` | Cho Claude viết lời (lượt ngày + bản tin). Tắt thì vẫn chạy quy tắc mỗi sáng và bản tin theo quy tắc | tắt |
| `ai_claude_model` | Model viết lời hằng ngày | `claude-sonnet-5-5` |
| `ai_claude_model_deep` | Model viết bản tin tuần / tháng (trống = dùng model ngày) | `claude-opus-5-5` |
| `ai_openai_model` | Model OpenAI phản biện. **Trống = phản biện tắt** | trống |
| `ai_cap_openai_usd`, `ai_cycle_day_openai` | Trần chi / kỳ và ngày bắt đầu kỳ của OpenAI (như Claude) | 90 USD, ngày 1 |
| `ai_mask_parties` | Thay tên khách / NCC bằng mã trước khi gửi | bật |
| `ai_max_signals` | Số tín hiệu tối đa gửi mỗi nhóm (đỏ trước, mới trước) | 40 |
| `ai_cap_claude_usd`, `ai_cycle_day_claude` | Trần chi mỗi kỳ và ngày bắt đầu kỳ; đã chi tới trần thì thôi gọi (đặt 0 = chặn hết) | 90 USD, ngày 1 |
| `ai_prices` | Giá mỗi model (USD / 1 triệu token vào, ra). Model chưa khai giá: vẫn chạy, chi phí ghi "chưa khai giá" và không tính vào trần | Sonnet 5.5: 2 / 10, Opus 5.5: 4 / 20 |
| `ai_context` | Bối cảnh công ty gửi kèm mọi lượt (mùa vụ, ưu tiên của năm) | trống |
| `ai_rules` | Ghi đè từng quy tắc: tắt, ngưỡng vàng, ngưỡng đỏ (trống hoặc 0 = dùng mặc định) | trống |

Ngoài trần mềm trên còn chặn cứng 30 lượt gọi mỗi ngày **mỗi nhà cung cấp** (bản tin tính chung với lượt ngày của
Claude; nút "Thử kết nối" cũng tính). Trần thật nằm ở Console của Anthropic / OpenAI: không gắn thẻ, không bật tự nạp —
hết credit thì API tự từ chối, lượt chạy ghi `het-credit` và dừng gọi tiếp nhà cung cấp đó. Giá ghi `ai_prices` theo
tên model đã đặt; model trả lời bằng tên bản chụp có hậu tố ngày (OpenAI hay làm vậy) mà chưa khai giá → tính theo giá
model đã đặt.

Trên màn `#/tro-ly`, quản trị đánh dấu từng việc "Đang xử lý", "Bỏ qua" 7 ngày / 30 ngày / hẳn, ghi chú (lượt sau mô
hình đọc ghi chú này để nói tiến triển thay vì báo như việc mới). Màn `#/ai`: trạng thái khoá Claude / OpenAI, "Thử kết
nối" từng bên, chi phí kỳ này / trần từng bên, "Chạy ngay", "Tạo bản tin tuần" / "Tạo bản tin tháng" + bảng 6 bản tin
gần nhất, bảng quy tắc (bật / tắt, ngưỡng), các lượt chạy gần nhất (cột bước đọc được: "Phản biện · <nhóm>", "Bản tin
tuần / tháng"), lời AI bị loại.

**Phản biện (P2, OpenAI).** Chỉ chạy khi `ai_openai_model` khác trống. Sau mỗi nhóm Claude viết xong, một lượt gọi
OpenAI (Responses API, ép đầu ra theo JSON schema, `store: false` — OpenAI không giữ lại câu trả lời) nhận **đúng gói số
người viết đã nhận** (đã che tên, đã bỏ mảng ẩn) cùng các lời AI vừa lưu (đã thay số, còn mã giả) và chấm từng lời:
`dong-y` hoặc `nghi-ngo` (khẳng định không có số đỡ, nguyên nhân không bằng chứng, dùng số sai nghĩa, mức đỏ / vàng
không tương xứng) kèm ghi chú ≤ 30 từ. Ghi chú qua đúng bộ soát số như lời người viết, thêm luật không thời hạn viết
tay ("45 ngày", "chín mươi ngày" — phản biện không có số ngày để đối chiếu) (sai → bỏ ghi chú, giữ verdict).
`nghi-ngo` → thẻ có badge "Cần kiểm chứng" (mọi người); ghi chú chỉ quản trị thấy. Phản biện không đổi lời, mức, trạng
thái, không ẩn gì; lời AI mới hôm sau xoá verdict cũ. Không model → không dòng Run nào; có model mà thiếu khoá / vượt
trần / hết credit → MỘT dòng `review:<nhóm>` của trạng thái đó rồi thôi phản biện cho cả lượt. Lời có số ngoài đề bài
người viết không được gửi phản biện.

**Nhóm Kiểm soát (P2).** Ba bộ dò mới chỉ đọc chứng từ (SQL chỉ `SELECT`, mốc ngày truyền tham số, bỏ chứng từ đầu kỳ;
"7 ngày" = hôm nay và 6 ngày trước). Tín hiệu nằm ở mảng `tro-ly`, nhóm lọc "Kiểm soát", dành cho lãnh đạo, không có nút
sang màn gốc; danh sách chứng từ làm bằng chứng (≤ 20) chỉ quản trị thấy. Mức vàng mặc định, đỏ chỉ khi quản trị đặt
ngưỡng đỏ ở `#/ai`.

| Quy tắc | Báo khi (ngưỡng vàng mặc định) |
|---|---|
| `ct.huy_nhieu` | Số chứng từ bị huỷ trong 7 ngày (hoá đơn bán / mua, phiếu thu chi, bút toán nhập tay, phiếu kho) ≥ 5 **và** > 2 × trung bình mỗi tuần của 8 tuần trước |
| `ct.ghi_lui` | Chứng từ tạo trong 7 ngày (đã duyệt; xét theo ngày TẠO bản nháp — v16 không có cột thời điểm duyệt có chỉ mục), có ngày hạch toán lùi quá 10 ngày so với ngày tạo |
| `ct.but_toan_tay_lon` | Bút toán nhập tay (không phải bút toán do chứng từ / tác vụ khác sinh) đã duyệt trong 7 ngày, tổng nợ ≥ 100 triệu |
| `gia.ban_lech` | Dòng hoá đơn bán 7 ngày có đơn giá (theo đơn vị kho, **tiền công ty** — hoá đơn ngoại tệ đã quy đổi) thấp hơn trung vị 90 ngày trước của cùng mã × kênh quá 15% (cần ≥ 5 dòng nền; bỏ giá 0, trả hàng) |
| `gia.chiet_khau_cao` | Dòng hoá đơn bán 7 ngày có chiết khấu dòng > 15% (giá trị các dòng tính bằng tiền công ty) |
| `gia.mua_tang` | Giá mua bình quân 30 ngày của một mã tăng > 10% so 90 ngày trước đó (chỉ mã mua ≥ 20 triệu trong 30 ngày) |
| `kpi.lech_chuan` | Một trong 70 chỉ số đầu màn lệch khỏi trung vị 28 ngày quá 3 lần độ lệch trung vị (MAD), đủ lớn để không phải nhiễu; cần ≥ 14 ngày ảnh chụp (lời nêu số ngày có số thật sự làm nền). Một tín hiệu / chỉ số, nằm ở **mảng của chỉ số đó** (ẩn theo mảng đó). Bỏ chỉ số cộng dồn trong kỳ và tỷ lệ tính trên kỳ tới hôm nay (đổi kỳ là đổi nền). Ngày màn nguồn của chỉ số lỗi (hoặc lịch sử tụt dưới 14 ngày) → tín hiệu đang mở **giữ nguyên**, không đóng rồi mở lại |

Nhóm Kiểm soát chỉ gọi mô hình khi có tín hiệu và không nhận nhận định tự do (như nhóm Hệ thống). Lịch sử chỉ số
không bao giờ gửi mô hình (có số của mọi mảng). Gói số chỉ có số đếm, số tiền, ngày, mã chứng từ, mã + tên hàng, tên
khách / NCC (che bằng mã giả); không người lập / người sửa, không diễn giải bút toán. Phân loại 70 chỉ số (cộng dồn /
tỷ lệ theo kỳ / ảnh chụp) và điều kiện SQL từng khối: `docs/ai-rules-audit.md` mục "Kiểm soát (P2)".

**Bản tin tuần / tháng (P2).** Thứ Hai 06:00 (cron `0 6 * * 1`, `bc.ai.jobs.weekly`) viết bản tin của tuần trọn trước
(thứ Hai → Chủ nhật); ngày 2 lúc 07:00 (`0 7 2 * *`, `bc.ai.jobs.monthly`) bản tin của tháng trước; quản trị bấm được ở
`#/ai`. Hàng đợi `long`, khoá riêng từng loại (bản tin không chặn lượt ngày và ngược lại; bản tin tuần còn chạy lúc 07:00
ngày 2 không chặn bản tin tháng); chạy lại trong cùng tuần / tháng thì ghi đè cùng bản tin. Đầu vào do Python tính sẵn từ ảnh chụp chỉ số hằng ngày: giá trị cuối kỳ, so kỳ trước, so 4 tuần / 3
tháng trước, cùng kỳ năm trước (tháng), thấp nhất / cao nhất 8 tuần / 12 tháng; chỉ số cộng dồn trong kỳ chỉ có giá trị
(không phép so). Kèm tiêu đề các việc của kỳ (mới mở, đã đóng, còn tồn ≥ 7 / 30 ngày; che tên NGẶT — cả tên khách / NCC
một từ ngắn như "Hùng", vì tiêu đề đã lưu mang tên thật) và số ngày đã kéo dài của từng việc ở dạng trích được — không
gửi thân lời, ghi chú, chứng từ. Thời hạn trong bản tin chỉ qua chỗ giữ số ngày đó; "45 ngày", "chín mươi ngày", "trong
7 ngày" viết tay làm hỏng mục. Claude (model deep) viết ba phần "Điều đáng chú ý", "Việc tồn chưa xử lý", "Ưu tiên tuần / tháng tới" (≤ 5
mục mỗi phần), số chỉ qua chỗ giữ và qua đúng bộ soát của lượt ngày; mục hỏng bị bỏ. AI tắt / hỏng / mọi mục bị loại →
**bản tin theo quy tắc**: tối đa 5 chỉ số đổi nhiều nhất (≥ 10%; chỉ số là tỷ lệ thì ≥ 2 điểm phần trăm — 1,0% → 1,1%
không phải "+10%"), 5 việc tồn lâu nhất, 3 việc đỏ đang mở. Bản tin hiện
dưới bản tin ngày ở `#/tro-ly` (tuần ≤ 14 ngày, tháng ≤ 45 ngày), badge "AI" / "Quy tắc". Mục AI mang mọi mảng mô hình
đã thấy: người xem bị ẩn một trong các mảng đó thì không thấy mục đó (bản tin hết mục thì vắng; tiêu đề AI đổi thành
tiêu đề trung tính); mục theo quy tắc chỉ mang mảng của chính nó.

**Thêm một quy tắc.** Viết một hàm trong `bc/ai/rules/<nhóm>.py`; không cần khai báo ở đâu khác (màn `#/ai` tự có
dòng mới; file quy tắc mới thì thêm tên module vào `_MODULES` của `bc/ai/registry.py`). Số phải có sẵn trong payload của một màn; đọc code method đó để lấy đúng tên khoá và đơn vị, rồi ghi vào
`docs/ai-rules-audit.md`.

```python
from bc.ai.registry import ph, resolve, rule

SRC = "cong-no.receivables"

@rule("cn.qua_han_ty_le", section="cong-no", sources=[SRC], vang=20, do=35, unit="%", label="Tỷ lệ nợ quá hạn")
def qua_han_ty_le(pack, cfg):
	p = f"{SRC}.kpis.overdue_pct"
	muc = cfg.muc(resolve(pack, p))          # None | "vang" | "do" theo ngưỡng (đã tính ghi đè của quản trị)
	if not muc:
		return []
	return [cfg.signal(muc, f"Nợ quá hạn chiếm {ph(p, 'pct')} phải thu", paths=[p])]
```

Khối nguồn trong `sources` bị lỗi hoặc `available: False` → quy tắc được ghi là "không chạy được" và tín hiệu cũ giữ
nguyên. Số quy tắc tự tính (không có sẵn trên payload) đưa qua `tinh={"ten": giá_trị}` và viết `{{@ten|kiểu}}` trong
lời — không gõ số vào chuỗi. Mỗi quy tắc cần ca dương, ca âm, ca đúng ngưỡng trong `test_ai_rules_*.py`.

**Deploy lần đầu.**

```bash
cd ~/frappe-bench
 bench --site a.rongvanghoanggia.com set-config bc_ai_anthropic_key 'KHOÁ'   # dấu cách đầu dòng: không vào history
cd apps/bc && git pull && cd ../..
bench --site a.rongvanghoanggia.com migrate && bench build --app bc && bench restart
bench --site a.rongvanghoanggia.com execute bc.ai.pipeline.run_daily          # chạy thử ngay, chưa gọi Claude
```

Thứ tự nên làm: (1) deploy, để AI **tắt**, xem 3 sáng liên tiếp — tín hiệu phải khớp số trên màn gốc, chỉnh ngưỡng
ở `#/ai`; (2) tạo API key ở Console (không gắn thẻ, không tự nạp), `set-config`, vào `#/ai` bấm "Thử kết nối", kiểm
lại bảng giá `ai_prices` theo bảng giá hiện hành; (3) bật `ai_enabled`. Sau một tuần xem cột "Bị loại" ở `#/ai`: mục
tiêu dưới 10% lời AI bị loại.

**Deploy P2.** `migrate` tạo DocType `BC AI Brief`, thêm lựa chọn `thang` cho `BC AI Run.run_type` và hai cron bản tin;
không đổi gì trên site cho tới khi quản trị bật (phản biện tắt vì `ai_openai_model` trống; nhóm Kiểm soát và bản tin
theo quy tắc chạy ngay không cần khoá). `kpi.lech_chuan` cần 14 sáng có ảnh chụp mới bắt đầu so; bản tin tháng cần vài
tháng ảnh chụp mới có đủ phép so (thiếu thì phép so vắng mặt, không thành 0). Bật phản biện:

```bash
 bench --site a.rongvanghoanggia.com set-config bc_ai_openai_key 'KHOÁ'      # dấu cách đầu dòng: không vào history
bench --site a.rongvanghoanggia.com migrate && bench build --app bc && bench restart
```

rồi tạo key ở platform.openai.com (project riêng, không gắn thẻ, không auto recharge, đặt giới hạn chi của project),
khai giá model vào `ai_prices`, đặt `ai_openai_model` ở `/app/bc-settings`, vào `#/ai` bấm "Thử kết nối" OpenAI. Tên
model OpenAI không điền sẵn: chọn model hiện hành trên trang models của OpenAI lúc bật.

Khác đặc tả (đã cân nhắc, ghi ở đầu các module): ép đầu ra bằng structured outputs thay cho tool bắt buộc (các
model Claude 5.5 từ chối `tool_choice` ép buộc); `max_tokens` 16.000 vì model luôn suy nghĩ trước khi trả lời; có thêm
trạng thái lỗi "bị từ chối"; giá hai model được điền sẵn khi migrate; nhận định tự do của AI tự đóng khi lượt sau
không nêu lại; che tên cả khi nằm giữa câu (đặc tả chỉ thay chuỗi bằng đúng một tên); cảnh báo trả cước xe nhà tính
cả tháng trước để không tự đóng vào ngày 1 (chỉ theo dõi tháng này và tháng trước — chuyến cũ hơn thì thẻ tự đóng,
phải xem màn Vận chuyển theo tháng); đề bài kèm bảng kiểu của các con số. Kiểm nhanh sau deploy:
`grep -rn "sk-" apps/bc/bc` phải rỗng. **Chưa kiểm trên site thật**: chưa có lượt gọi Claude thật nào (bộ thử dùng mô hình giả, không ra
mạng) và chưa chạy trên bench thật.

Khác đặc tả ở P2 (đã cân nhắc, ghi ở đầu các module): phản biện chạy ngay sau từng nhóm (không phải một bước cuối) và
chấm mọi lời AI vừa lưu của nhóm (cả nhận định tự do), một lượt gọi / nhóm; lời có số ngoài đề bài người viết không gửi
phản biện, và (đặt ở bước 6 của lượt ngày) bị loại luôn; nhóm Kiểm soát không nhận nhận định tự do; `kpi.lech_chuan`
bỏ cả tỷ lệ tính trên kỳ tới hôm nay (không chỉ số cộng dồn); bộ lọc "bút toán nhập tay" áp cho bút toán ở cả ba khối
chứng từ (huỷ chứng từ gốc kéo theo huỷ bút toán hệ thống không bị đếm hai lần); giá bán so theo đơn vị kho, giá mua
theo tiền công ty; Retry-After của OpenAI từ 60 giây trở lên → chờ mặc định 5 / 20 giây; bản tin có bản theo quy tắc
khi AI tắt; khoá bản tin là "loại:ngày sau kỳ" (một bản / tuần / tháng); người xem bị ẩn mảng thấy tiêu đề bản tin
trung tính. **Giới hạn đã biết của P2**: một số chi tiết API OpenAI chưa đối chiếu được trên tài liệu (mẫu đầy đủ của
thân lỗi, `usage` khi lượt hỏng, thử lại 502 / 504, header `retry-after-ms`) — làm theo dạng thường gặp, ghi ở đầu
`bc/ai/llm/openai.py`; `ct.huy_nhieu` lọc theo `modified` không có chỉ mục trên v16 → mỗi bảng quét một lượt lúc 5:30;
nút bản tin ở `#/ai` không tự làm mới (tải lại trang để thấy bản mới); chưa có lượt gọi OpenAI thật nào.

### Hỏi đáp (P3, `#/hoi-dap`)

Người vào được mảng Trợ lý AI gõ câu hỏi bằng lời ("Phải thu quá hạn tháng này bao nhiêu, khách nào nợ nhiều nhất?");
máy chủ cho Claude tra **đúng các khối số của màn báo cáo**, Claude viết câu trả lời có số, máy chủ đối chiếu từng con
số với kết quả vừa tra rồi trả về màn hình. Vào từ nút "Hỏi trợ lý" trên `#/tro-ly` (chỉ hiện khi hỏi đáp đang bật và
có khoá Claude); không có mục menu. Ẩn mảng Trợ lý AI với ai thì người đó mất luôn hỏi đáp (API 403, route chuyển về
như màn ẩn).

**Luồng.** `bc.api.ai.ask(question, history)` (POST, `_guard("tro-ly")`) kiểm bật / khoá / giới hạn / trần chi, tạo
một dòng `BC AI Run` loại `hoi-dap` (đếm lượt ngay), xếp job `bc.ai.qa.run` (hàng `default`, timeout 300) và trả
`{id, status: "cho"}`. Khoá "đang hỏi" của người hỏi lấy **nguyên tử** (Redis `SET NX EX`) trước khi đếm; đếm giới hạn
+ ghi dòng Run nằm trong khoá MariaDB `GET_LOCK` theo CSDL của site — yêu cầu song song (nhiều tab, nhiều worker) không
lọt qua giới hạn. Tham số job chỉ có `qid` + `user`; câu hỏi + lịch sử nằm trong cache (hạn 330 giây), job đọc xong xoá
ngay. Job chạy **dưới chính người hỏi**: dựng đề bài (vai trò, luật trả lời, bối cảnh công ty đã
che tên, ngày hôm nay, năm tài chính — không số liệu kinh doanh), rồi vòng tool use ≤ 7 lượt gọi Claude, ≤ 6 bước tra;
hết lượt tra thì lượt cuối buộc trả lời bằng số đã có (`tool_choice: none`). Hạn 150 giây tính **từ lúc hỏi** (gồm
thời gian chờ trong hàng đợi). Lượt gọi của hỏi đáp **không thử lại** (429 / 5xx / quá giờ → báo bận ngay để người hỏi
hỏi lại): nhờ vậy mỗi lượt được chờ đọc tới 60 giây, và chỉ bắt đầu khi (10 giây nối + chờ đọc) vẫn xong trước hạn;
công cụ xin sau hạn không chạy. Màn hình hỏi `get_answer(id)` mỗi 2
giây, tối đa 180 giây (hạn máy chủ + 30 giây, để luôn lấy được kết quả cuối). Câu trả lời nằm trong cache 30 phút dưới khoá gắn với người hỏi — người khác (kể cả quản trị) không
lấy được.

**Hai tầng công cụ.**

- `xem_mang(mang, ten, tham_so)` — mọi người: 25 khối của `bc.ai.collect.CALLS` (bỏ khối vận chuyển tháng trước) trên
  17 mảng; tham số theo bảng cố định (`limit` 1–20, `year` / `month`, `group` = `all` | `tet` | `traditional`,
  `from_date` + `to_date` đi cùng nhau ≤ 731 ngày, `thang`) — lạ, sai kiểu, ngoài khoảng → lỗi cho mô hình, không gọi;
  method vẫn từ chối tham số (`frappe.throw`) → lỗi "tham số không hợp lệ" cho mô hình, không Error Log; **không bao giờ** `refresh` (đọc cache như màn). Gọi thẳng
  method `bc.api.*` dưới phiên người hỏi: mảng đang ẩn với họ bị chặn hai lớp (trước khi gọi và `_guard` của method),
  và không có trong mô tả công cụ gửi mô hình. Kết quả: danh sách cắt 30 phần tử (khoá `_cat` ghi số bị cắt),
  ≤ 40.000 ký tự JSON, che tên khách / NCC, rồi mới gửi.
- `get_schema(doctype)` + `run_select(sql)` — chỉ System Manager, và chỉ khi `site_config.json` có tài khoản MariaDB
  chỉ đọc **và** tài khoản đó thật sự chỉ đọc (máy chủ nối thử, chạy `SHOW GRANTS`: chỉ `USAGE` / `SELECT` / `SHOW VIEW`
  trên đúng CSDL của site; thấy quyền khác, `*.*`, CSDL khác, `WITH GRANT OPTION`, vai trò → không dùng). Ba lớp chặn:
  tài khoản chỉ đọc; phiên `SET SESSION TRANSACTION READ ONLY` + `max_statement_time` 10 giây; bộ soát
  `bc/ai/sqlguard.py` (hàm thuần): một câu `SELECT` / `WITH` ≤ 4.000 ký tự, không chú thích, không biến, không từ khoá
  ghi / khoá / hàm ngủ, ngoặc phải cân, không CSDL hệ thống, không bảng nhạy cảm (phiên, khoá, OAuth, Error Log, Singles,
  bảng lương, bảng con của Employee…) và **không bảng chép lại dữ liệu của bảng khác** (`tabVersion`, `tabDeleted
  Document`, Comment / Communication, các log, Prepared Report, Submission Queue, Data Import, Webhook*, Bank Account),
  `tabEmployee` / `tabUser` chỉ cột được phép và không `*` (từ đứng ngay sau hai bảng đó luôn coi là bí danh, kể cả
  `END` / `FULL`… — CTE cùng tên không mở được cột cấm). Trên danh sách tên còn một **lớp theo cấu trúc**: mọi bảng
  `tab…` trong câu phải là bảng của một DocType có trên site, và DocType đó không thuộc phân hệ hệ thống / thư / tích
  hợp / địa chỉ liên hệ / nhân sự (Core, Desk, Email, Integrations, Website, Automation, Custom, Printing, Social,
  Workflow, Portal, Telephony, Contacts, HR, Payroll, app `ns`, MISA Integration) — bảng mới của các phân hệ đó bị
  chặn mà không cần kể tên; `get_schema` theo cùng luật. Câu bị chặn → lý do ngắn cho mô
  hình, mô hình viết lại câu khác. Chạy dạng `SET STATEMENT max_statement_time=10 FOR SELECT * FROM (<câu>) AS _t LIMIT
  …`: ≤ 200 dòng, ≤ 40.000 ký tự. Ô chuỗi được che tên khách / NCC và tên người (không phân biệt hoa thường — `UPPER(tên)`
  cũng che) **rồi mới** cắt 200 ký tự (cắt trước thì tên nằm ở chỗ cắt lọt một nửa); cột người
  (`owner`, `modified_by`, tên cột có `user`, `employee_name`, `full_name`) thành `NV#01…`, đổi lại khi hiển thị.

**Đối chiếu số.** Sau khi có câu trả lời (còn mã giả), máy chủ tách mọi con số kèm đơn vị (tỷ, triệu, nghìn, %, đ, và
dạng viết tắt / dính liền "47tr", "999k", "2tỷ5" = 2,5 tỷ; khoảng "1–30 triệu", "từ 9 đến 30 triệu" — đầu dưới dùng chung
đơn vị đầu trên),
đổi mỗi số thành khoảng theo độ chính xác nó được viết ("1,6 tỷ" → [1,55; 1,65) tỷ, "35,2%" → [35,15; 35,25) và dạng tỷ
số 0,3515–0,3525, "1.250.000 đ" → đúng 1.250.000) và tìm trong **mọi kết quả tra cứu của chính lượt hỏi đó** (bản mô
hình đã thấy) một giá trị rơi vào khoảng. Số "%" chỉ so với lá tỷ lệ (khoá có `pct` / `ty_le` / `rate` / `growth`…,
hoặc dòng có `don_vi` = "%") và thang tỷ số 0–1 — không với số đếm / số ngày. Ngày ("5/11", "5/11/2026") so với ngày có
trong kết quả (chuỗi ISO) và ngày của đề bài hệ thống (hôm nay, năm tài chính). Không tìm thấy → "chưa kiểm": màn gạch
chấm dưới số đó và ghi một dòng nhắc kiểm ở màn gốc. Không tính: năm `20xx`, tháng / năm, giờ, mã (`KH#0007`, mã chứng
từ), số thứ tự đầu dòng; số dính chữ không đọc được ("10A1") luôn "chưa kiểm". Bước
này không sửa, không xoá chữ nào của mô hình. **Giới hạn**: số viết bằng chữ ("hai tỷ") không được tách; so theo trị
tuyệt đối ("giảm 12,3%" khớp số −12,34); một số tự tính tình cờ rơi vào khoảng của một giá trị bất kỳ trong kết quả
(nhất là số nhỏ, tỷ số nhỏ) vẫn được tính là đã kiểm — "đã kiểm" nghĩa là "có số như vậy trong dữ liệu đã tra", không
phải "đúng nghĩa".

**Riêng tư.** Gửi Claude chỉ có: đề bài hệ thống, câu hỏi + tối đa 3 lượt hỏi đáp trước (trình duyệt giữ, ≤ 4.000 ký
tự, máy chủ không lưu), kết quả công cụ đã cắt, đã che. Câu hỏi, lịch sử, bối cảnh công ty, ô chuỗi của kết quả SQL
được che **ngặt**: mọi tên khách / NCC đã biết (kể cả tên một từ ngắn; chữ đưa về NFC, không phân biệt hoa thường với
tên ≥ 2 từ / ≥ 6 ký tự, tên một từ ngắn thêm dạng VIẾT HOA, tên ≥ 2 từ cả khi gõ không dấu) và tên người đã biết (tài
khoản, nhân viên); chỉ
mã đã thật sự gửi trong câu hỏi đó được đổi lại thành tên. Không lưu câu hỏi, câu trả lời, đề bài, kết quả tra cứu vào
CSDL: `BC AI Run` chỉ ghi model, token, chi phí, số bước tra, số con số đã kiểm / chưa kiểm, số lượt gọi, trạng thái
và một lời báo ngắn cố định. Error Log của phần này chỉ có tên loại lỗi + dòng code. Khoá Claude chỉ `bc/ai/llm/` đọc;
mật khẩu tài khoản chỉ đọc chỉ `bc/ai/sqlro.py` đọc (luật tĩnh kiểm cả cây `bc/`). Công cụ chỉ đọc, không công cụ nào
gửi dữ liệu ra ngoài. **Lưu ý cho quản trị**: `run_select` gửi kết quả truy vấn cho Claude — tên khách / NCC / người
đã che, còn nội dung khác của ô (địa chỉ, ghi chú, diễn giải) thì không; không muốn gửi thì đừng khai tài khoản chỉ đọc.

**Giới hạn và chi phí.** `ai_qa_per_day` câu / người / ngày (mặc định 20; đếm dòng `BC AI Run` `hoi-dap` của người đó
trong ngày, cả câu lỗi; câu bị từ chối lúc hỏi không tính); 200 câu / ngày toàn site; mỗi người một câu tại một thời
điểm; câu hỏi ≤ 500 ký tự; ≤ 6 bước tra, ≤ 7 lượt gọi, `max_tokens` 6.000 mỗi lượt (gồm phần suy nghĩ), cả câu ≤ 150 giây (thời gian chờ
tính từ lúc hỏi; chờ đọc mỗi lượt gọi tối đa 60 giây, thu theo thời gian còn lại; không thử lại). Chi phí tính vào **cùng trần chi theo kỳ của Claude** (`ai_cap_claude_usd`;
chạm trần → từ chối), ghi theo token thực tế sau mỗi lượt gọi (đọc cache × 0,1, ghi cache × 1,25 giá token vào —
`cache_control` cấp trên cho phần lặp lại giữa các lượt của một câu). Lượt gọi hỏi đáp **không** tính vào 30 lượt / ngày
của lượt sáng; có giới hạn riêng 300 lượt gọi / ngày (câu đang chạy giữ chỗ 7 lượt). Mọi lỗi (tắt, thiếu khoá, hết
credit, vượt trần, quá giờ, mô hình từ chối, trả lời bị cắt) thành một trạng thái có lời báo ngắn cho người hỏi và một
dòng `BC AI Run`; không lỗi nào đụng tới lượt chạy sáng.

**Cấu hình** (BC Settings, mục "Trợ lý AI — hỏi đáp", permlevel 1):

| Field | Ý nghĩa | Mặc định |
|---|---|---|
| `ai_qa_enabled` | Bật hỏi đáp (cần khoá Claude) | tắt |
| `ai_qa_per_day` | Số câu / người / ngày (trống, 0 → 20) | 20 |
| `ai_qa_model` | Model Claude cho hỏi đáp; trống = `ai_claude_model` | trống |

Tài khoản chỉ đọc (chỉ khi muốn quản trị hỏi được bằng SQL) — tạo trên MariaDB của site, host phải khớp cách Frappe nối
(`localhost` khi nối qua socket; nối qua `db_host` khác thì dùng đúng host / IP đó), quyền **chỉ** `SELECT` trên đúng CSDL
của site (tên CSDL = `db_name` trong `site_config.json`):

```sql
CREATE USER 'bc_ai_ro'@'localhost' IDENTIFIED BY '<mật khẩu dài, ngẫu nhiên>';
GRANT SELECT ON `<db_name của site>`.* TO 'bc_ai_ro'@'localhost';
SHOW GRANTS FOR 'bc_ai_ro'@'localhost';   -- chỉ được thấy USAGE + SELECT ON `<db_name>`.*
```

```bash
 bench --site a.rongvanghoanggia.com set-config bc_ai_ro_user bc_ai_ro            # dấu cách đầu dòng: không vào history
 bench --site a.rongvanghoanggia.com set-config bc_ai_ro_password '<mật khẩu>'
```

Kiểm: `bench --site a.rongvanghoanggia.com execute bc.ai.qa.status` (chạy dưới Administrator) phải trả `"sql": true`;
`false` nghĩa là tài khoản chưa dùng được (chưa khai, nối không được, hoặc có quyền ngoài `SELECT`) — khi đó quản trị
vẫn hỏi được bằng `xem_mang`, chỉ không có SQL.

**Deploy P3.** `migrate` thêm ba field trên (điền `ai_qa_per_day` = 20, `ai_qa_enabled` để tắt) — không đổi gì trên site
cho tới khi quản trị bật; `bench build --app bc && bench restart` (dấu build lúc giao P3 là `bc-p9-r1`; bản hiện tại
`bc-p10-r2` — gõ `BC.build` trong Console phải ra đúng chuỗi của bản đang chạy). Bật: đặt `ai_qa_model` nếu muốn model khác lượt ngày, khai giá model đó ở `ai_prices`, tick
`ai_qa_enabled`; người xem thấy nút "Hỏi trợ lý" ở `#/tro-ly`. Worker hàng `default` phải đang chạy (`bench doctor`).

**Khác `docs/SPEC_bc_ai_p3.md`** (đã cân nhắc): `get_qa.enabled` chỉ đúng khi bật **và** có khoá Claude dùng được;
`get_qa.sql` nối thử và kiểm `SHOW GRANTS` thật (không chỉ xem đã khai); bộ soát SQL chặt hơn đặc tả (thêm mọi bảng `__…`,
bảng chép lại dữ liệu (Version, Deleted Document, Comment, Communication, log, Webhook, Bank Account…), số dính chữ
"1e0union",
mọi bảng `tabEmployee …`, bảng email / webhook / tích hợp / thưởng / thuế lương, từ khoá `TABLE` `SHOW` `PROCEDURE`
`OUTFILE` …; quyền đọc chỉ được trên CSDL của site); câu có `ORDER BY` mà không `LIMIT` được thêm `LIMIT` bên trong
(MariaDB bỏ `ORDER BY` của bảng dẫn xuất không `LIMIT`); "bước tra" đếm theo từng khối `tool_use` (một lượt xin 4 khối
là 4 bước; khối vượt trần nhận lỗi "đã hết lượt tra"); che cả tên người trong câu hỏi / lịch sử / bối cảnh / ô SQL (đặc
tả chỉ nói cột người); `steps` mang cờ `ok`, bước bị chặn trước khi chạy (tham số sai, mảng ẩn, DocType cấm) không liệt
kê, câu SQL bị soát chặn vẫn liệt kê cho quản trị; câu chờ quá 330 giây báo lỗi; quá đông yêu cầu cùng lúc (khoá đếm
không lấy được trong 5 giây) → "đang nhận nhiều câu hỏi cùng lúc"; job đã xếp mà quản trị tắt hỏi đáp trước
khi chạy → không gọi mô hình (Run `tat`); trả lời bị cắt vì `max_tokens` → báo lỗi, không trả nửa câu; lỗi lạ của lượt
gọi mô hình chỉ ghi tên loại + dòng code (không lời của lỗi — có thể chép câu hỏi).

**Giới hạn đã biết của P3.** Model Claude 5.5 luôn suy nghĩ trước khi trả lời và phần suy nghĩ tính vào `max_tokens`
(6.000 mỗi lượt) — câu hỏi rất rộng vẫn có thể bị cắt ("Câu trả lời bị cắt giữa chừng — thử hỏi hẹp hơn"); nếu gặp
thường xuyên thì nâng `MAX_TOKENS` trong `bc/ai/qa.py`. Giá đọc cache tính 0,1× (Sonnet / Opus 5.5 thật là 0,05×) — chi phí ghi
hơi cao hơn thực, an toàn cho trần. Vì tên khách đã thành mã, SQL của quản trị không lọc được theo tên / mã khách cụ thể
(hỏi theo nhóm, kênh, tỉnh thì được). Chữ tự do trong payload màn báo cáo (ghi chú, diễn giải) chỉ che tên khách / NCC
từ 2 từ hoặc 6 ký tự (như lượt ngày) — tên một từ ngắn nằm giữa câu trong ô đó có thể lọt. Tên gọi tắt ("Tân Phát"),
tên một từ ngắn gõ chữ thường, tên dính liền chữ khác (`CONCAT(x, tên)` không dấu cách) không nhận ra được. Câu hỏi +
lịch sử nằm tạm trong cache Redis (không trong tham số job) từ lúc hỏi tới lúc job bắt đầu, tối đa 330 giây. Khối "Thời gian thực" chưa tra được. **Chưa kiểm trên site
thật**: chưa có lượt gọi Claude thật nào với công cụ (bộ thử dựng request thật nhưng mô hình giả), chưa chạy tài khoản
chỉ đọc trên MariaDB của bench thật.

## Kiểm thử

Bộ thử chạy SQL thật trên MariaDB với schema sinh từ DocType JSON của ERPNext v16 + các app (không cần
bench): sản xuất 54 (gồm kiểm kê đưa về 0 rồi nhập lại), kênh 9, công nợ 30 (code ketoan thật cho MT), ATTP 15 (so vi sai với `tong_quan`
/ `so_lieu` của sx thật), ngày Tết 6 + 5, vận chuyển 65 (lịch xe gọi code vanchuyen thật), nhân sự 58
(so vi sai với cảnh báo của ns thật), ẩn / hiện mảng 40 + 30 giao diện (vai quản trị + người xem), **Kho**: tồn kho
120, hạn dùng 88, kiểm kê 73, nhập TP 99, nền dùng chung 39 + giao diện 4 màn trên sổ kho gộp 113 / 70 (+ 72 / 66 / 52
lượt cache, chỉ còn lô thu hồi, sổ rỗng) / 126 / 107 và Thời gian thực trên sổ kho 14; **Báo cáo sản xuất** 148
(so vi sai với lịch Ghi hộp và bảng đối chiếu kho của sx thật, với màn Nhập TP) + giao diện 576 (+ 12 lượt site không cài sx); giao diện Playwright chung 144
(desktop + điện thoại), tab mở trước deploy 6. **Trợ lý AI** (mô hình giả, không bộ nào ra mạng): dựng lời + soát số
926, mã giả khách / NCC 58, cửa gọi Claude + trần chi + đề bài 346, lưu trữ + thu số 175, quy tắc 675 (kinh doanh 189,
kho 182, công nợ 126, vận chuyển 116, nhân sự + ATTP 62), bộ dò hệ thống 75, API 174, một lượt chạy trọn vẹn 274, luật
tĩnh 65, giao diện hai màn 268 + 183 (lượt "đã cũ"); P2: nền dùng chung 123, cửa gọi OpenAI 140, phản biện 84, nhóm
Kiểm soát 98, chỉ số lệch chuẩn 69, bản tin tuần / tháng 157, đầu-cuối P2 (Claude + OpenAI giả, ẩn mảng, AI tắt) 58; P3 hỏi đáp: `llm.chat` 120, bộ soát SQL + kết nối chỉ đọc trên MariaDB thật 141, máy hỏi đáp 183, đầu-cuối P3 (request thật, cửa HTTP giả, tài khoản chỉ đọc thật, ẩn mảng, lỗi, giới hạn, tắt) 105, giao diện `#/hoi-dap` 65. Mỗi bản sửa đều đã thử phá (đưa code về bản lỗi → test phải đỏ). Chạy:
`docs/verified/harness/run_all.sh` (xem README trong thư mục đó).

## Cài đặt / deploy

```bash
cd ~/frappe-bench
bench get-app bc https://github.com/mrhuychien/bc
bench --site a.rongvanghoanggia.com install-app bc
# mỗi lần cập nhật:
bench --site a.rongvanghoanggia.com migrate && bench build --app bc && bench restart
```

Dấu build hiện tại **`bc-p10-r2`** (Báo cáo sản xuất thêm khối Ghi hộp so với nhập kho): sau `bench build` + `restart`, gõ `BC.build` trong
Console của `/bc` phải ra đúng chuỗi này (khác là trình duyệt / CDN còn shell cũ). Màn mới không cần `migrate` (chỉ đọc
bảng sx có sẵn); site chưa cài sx thì màn báo "chưa có số liệu".

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

## Ẩn / hiện mảng báo cáo (chỉ quản trị)

System Manager vào `/bc` → **Quản trị › Ẩn / hiện mảng**: mỗi màn báo cáo (Thời gian thực, Tổng quan, …,
Nhân sự & lương, An toàn thực phẩm) có một công tắc, nhóm nhiều màn có nút "Ẩn / Hiện cả nhóm", và nút
"Hiện tất cả". Áp dụng cho mọi người xem (BC Viewer):

- mảng bị ẩn không còn trong menu (nhóm ẩn hết thì mất cả nhóm); mở đường dẫn cũ sẽ về trang đầu (Tổng quan,
  hoặc màn còn mở đầu tiên); ẩn hết thì người xem thấy "chưa có mảng báo cáo nào được mở";
- **máy chủ chặn thật**: mọi method báo cáo gọi `_guard("<mảng>")` ở dòng đầu, trước cache — gọi thẳng API
  của mảng đang ẩn trả 403 "Mảng báo cáo này đang được quản trị ẩn";
- quản trị vẫn mở được mọi mảng (menu có dấu 👁‍🗨 "đang ẩn") để kiểm tra trước khi mở lại;
- người xem đang mở trang thấy thay đổi khi tải lại trang hoặc bấm Làm mới.

Ẩn theo màn, không theo nguồn số liệu: số dùng chung vẫn có thể hiện ở màn khác (vd doanh số hôm nay ở Thời
gian thực). Lưu ở `BC Settings.hidden_sections` (permlevel 1, mỗi dòng một mã màn — sửa được cả trên Desk,
mã sai bị từ chối); mỗi lần đổi ghi vào lịch sử (Version) của BC Settings — biết ai ẩn / mở mảng nào, lúc nào.
**Phải `bench migrate` trước** khi ẩn (chưa migrate thì màn quản trị báo lỗi, người xem vẫn thấy đủ).

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
               common.py, kd.py, tet.py, sx.py, sx_hop.py (Báo cáo sản xuất — Ghi hộp), live.py, cn.py (công nợ),
               attp.py, vc.py (vận chuyển), ns.py (nhân sự), kho.py (nền nhóm Kho) + kho_ton.py, kho_han.py, kho_kk.py, kho_nhap.py,
               sections.py (ẩn / hiện mảng), hidden.py, share.py, _provinces.py,
               ai.py (API màn Trợ lý AI + Cấu hình AI)
bc/ai/         Trợ lý AI: registry.py (Signal, @rule, @detector, KPIS), collect.py, rules/, detectors/,
               store.py, render.py, redact.py, budget.py, prompt.py, llm/ (nơi duy nhất gọi mạng + đọc khoá),
               pipeline.py, jobs.py
bc/www/        bc.py (guard + BC_CONTEXT), bc.html (import map + shell)
bc/public/bc/  shell.js, shell.css, lib/, components/, views/
bc/scripts/    dump_report_sql.py, compare_tet_reports.py
docs/          tet-curdate-audit.md, report-sql/, SPEC_bc_ai.md, ai-rules-audit.md
```
