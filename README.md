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
giai đoạn P0 + P1 (chưa có OpenAI phản biện, bộ dò chứng từ, bản tin tuần / tháng, hỏi đáp).

**Luồng một lượt chạy** (`bc.ai.pipeline.run_daily`, cron `30 5 * * *` giờ của site → hàng đợi `long`, chống chạy
trùng):

1. `collect` gọi lại 23 method `bc.api.*` dưới Administrator (`refresh=1`, làm ấm luôn cache buổi sáng) → gói số
   `pack[mảng][tên]`. Không đọc thẳng chứng từ nào: muốn Trợ lý thấy thêm số gì thì thêm vào màn báo cáo trước.
2. 8 bộ dò hệ thống (`bc/ai/detectors/he_thong.py`, chỉ `SELECT`): Error Log tăng vọt, tác vụ định kỳ lỗi, email
   lỗi, hàng đợi ứ, sao lưu cũ, đĩa đầy, đăng nhập sai nhiều lần, Trợ lý lỗi 3 lượt liền.
3. 42 quy tắc (`bc/ai/rules/*.py`, hàm thuần trên gói số, không SQL): kinh doanh 5, kho & sản xuất 11, công nợ 7,
   vận chuyển 6, nhân sự 3, ATTP 2, hệ thống 8. Từng quy tắc đọc số nào, so ngưỡng ra sao:
   `docs/ai-rules-audit.md`.
4. Lưu vào `BC AI Insight` theo khoá tín hiệu: mới → mở; còn → cộng ngày kéo dài; hết → tự đóng; nguồn số lỗi →
   **giữ nguyên**, không đóng nhầm; đã đóng mà xuất hiện lại → mở lại.
5. Nếu bật AI, có khoá và chưa chạm trần chi: mỗi nhóm một lượt gọi Claude — viết lại lời, xếp ưu tiên, thêm khuyến
   nghị theo **bộ phận**, và được nêu thêm tối đa 3 nhận định ngoài quy tắc.
6. Máy chủ thay số vào lời rồi kiểm; lời không qua kiểm thì bỏ, tín hiệu giữ lời theo quy tắc.
7. Ghi `BC AI Run`: một dòng tổng + một dòng mỗi lượt gọi (token, chi phí, trạng thái) và ảnh chụp 70 chỉ số đầu màn.

Bước 5–6 hỏng kiểu gì (tắt AI, hết credit, API lỗi, quá giờ) cũng chỉ thành một trạng thái trong `BC AI Run`; màn
vẫn hiện đủ tín hiệu với nhãn "Quy tắc".

**Luật số.** Mô hình **không được viết con số**. Mọi số trong lời là chỗ giữ `{{path|kiểu}}` trỏ vào gói số
(`{{cong-no.receivables.kpis.overdue_pct|pct}}`), kiểu `tien | so | pct | ngay | chu`; máy chủ chèn số thật theo
đúng cách viết của màn báo cáo ("1,6 tỷ", "251 triệu", "35,0%", "5/11/2026"). Sau khi chèn, phần lời do mô hình viết
được soát lại: còn số viết tay ("1.250.000", "35%", "2 tỷ", "gấp đôi", "hai tỷ"), path không có thật, sai kiểu, hoặc
path của nhóm khác → bỏ cả nhận định (đếm ở cột "Bị loại" của lượt chạy, quản trị xem ở `#/ai`). Chỉ số ngắn chỉ thời
hạn ("trong 7 ngày") được viết thường. Lời theo quy tắc cũng dựng bằng chỗ giữ nên luôn khớp màn gốc tại lúc chạy.

**Luật riêng tư.**

- Khoá API chỉ nằm trong `site_config.json` (`bc_ai_anthropic_key`); không ở DocType, không trả ra API, không vào
  Error Log (thông báo lỗi được xoá mọi chuỗi trùng khoá trước khi lưu). Chỉ `bc/ai/llm/` được gọi mạng và đọc khoá.
- Gửi đi chỉ có payload của bc (đã qua luật riêng tư của từng màn: không tên nhân viên, lương gộp nhóm, số tài
  khoản đã che). Tên khách và nhà cung cấp được thay bằng mã `KH#0001`, `NCC#0001` trước khi gửi và đổi lại khi lưu
  (`ai_mask_parties`, mặc định bật); ghi chú của quản trị trên thẻ cũng được che tên nằm giữa câu — che hết sức: tên
  gọi tắt hoặc viết khác hồ sơ thì không nhận ra, nên đừng ghi tên riêng vào ghi chú và vào ô "Bối cảnh công ty".
- Đề bài và gói số không được lưu, không được ghi log. Lời chỉ được lưu sau khi đã thay số và kiểm.
- Người xem chỉ thấy nhận định dành cho lãnh đạo, đang mở, và **mọi** mảng mà nhận định dùng số đều đang hiện với
  họ (ẩn mảng Công nợ → nhận định công nợ biến mất; ẩn mảng Trợ lý AI → mất menu, API trả 403). Chứng từ liên quan,
  ghi chú quản trị, nhóm Hệ thống chỉ System Manager thấy.
- bc vẫn chỉ đọc: phần này chỉ ghi `BC AI Insight`, `BC AI Run` và mục "Trợ lý AI" của BC Settings.

**Cấu hình** (`/bc#/ai`, hoặc mục "Trợ lý AI" trong `/app/bc-settings` — mọi field permlevel 1):

| Field | Ý nghĩa | Mặc định |
|---|---|---|
| `ai_enabled` | Cho Claude viết lời. Tắt thì vẫn chạy quy tắc mỗi sáng | tắt |
| `ai_claude_model` | Model viết lời hằng ngày | `claude-sonnet-5-5` |
| `ai_mask_parties` | Thay tên khách / NCC bằng mã trước khi gửi | bật |
| `ai_max_signals` | Số tín hiệu tối đa gửi mỗi nhóm (đỏ trước, mới trước) | 40 |
| `ai_cap_claude_usd`, `ai_cycle_day_claude` | Trần chi mỗi kỳ và ngày bắt đầu kỳ; đã chi tới trần thì thôi gọi (đặt 0 = chặn hết) | 90 USD, ngày 1 |
| `ai_prices` | Giá mỗi model (USD / 1 triệu token vào, ra). Model chưa khai giá: vẫn chạy, chi phí ghi "chưa khai giá" và không tính vào trần | Sonnet 5.5: 2 / 10, Opus 5.5: 4 / 20 |
| `ai_context` | Bối cảnh công ty gửi kèm mọi lượt (mùa vụ, ưu tiên của năm) | trống |
| `ai_rules` | Ghi đè từng quy tắc: tắt, ngưỡng vàng, ngưỡng đỏ (trống hoặc 0 = dùng mặc định) | trống |

Ngoài trần mềm trên còn chặn cứng 30 lượt gọi mỗi ngày. Trần thật nằm ở Console của Anthropic: không gắn thẻ, không
bật tự nạp — hết credit thì API tự từ chối, lượt chạy ghi `het-credit` và dừng gọi tiếp. Các field `ai_openai_*`,
`ai_claude_model_deep` đã có sẵn cho giai đoạn sau, hiện chưa dùng.

Trên màn `#/tro-ly`, quản trị đánh dấu từng việc "Đang xử lý", "Bỏ qua" 7 ngày / 30 ngày / hẳn, ghi chú (lượt sau mô
hình đọc ghi chú này để nói tiến triển thay vì báo như việc mới). Màn `#/ai`: trạng thái khoá, "Thử kết nối", chi
phí kỳ này, "Chạy ngay", bảng quy tắc (bật / tắt, ngưỡng), các lượt chạy gần nhất, lời AI bị loại.

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

Khác đặc tả (đã cân nhắc, ghi ở đầu các module): ép đầu ra bằng structured outputs thay cho tool bắt buộc (các
model Claude 5.5 từ chối `tool_choice` ép buộc); `max_tokens` 16.000 vì model luôn suy nghĩ trước khi trả lời; có thêm
trạng thái lỗi "bị từ chối"; giá hai model được điền sẵn khi migrate; nhận định tự do của AI tự đóng khi lượt sau
không nêu lại. **Chưa kiểm trên site thật**: chưa có lượt gọi Claude thật nào (bộ thử dùng mô hình giả, không ra
mạng) và chưa chạy trên bench thật.

## Kiểm thử

Bộ thử chạy SQL thật trên MariaDB với schema sinh từ DocType JSON của ERPNext v16 + các app (không cần
bench): sản xuất 54 (gồm kiểm kê đưa về 0 rồi nhập lại), kênh 9, công nợ 30 (code ketoan thật cho MT), ATTP 15 (so vi sai với `tong_quan`
/ `so_lieu` của sx thật), ngày Tết 6 + 5, vận chuyển 65 (lịch xe gọi code vanchuyen thật), nhân sự 58
(so vi sai với cảnh báo của ns thật), ẩn / hiện mảng 39 + 30 giao diện (vai quản trị + người xem), **Kho**: tồn kho
120, hạn dùng 88, kiểm kê 73, nhập TP 99, nền dùng chung 39 + giao diện 4 màn trên sổ kho gộp 113 / 70 (+ 72 / 66 / 52
lượt cache, chỉ còn lô thu hồi, sổ rỗng) / 126 / 107 và Thời gian thực trên sổ kho 14; giao diện Playwright chung 138
(desktop + điện thoại), tab mở trước deploy 6. Mỗi bản sửa đều đã thử phá (đưa code về bản lỗi → test phải đỏ). Chạy:
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
               common.py, kd.py, tet.py, sx.py, live.py, cn.py (công nợ), attp.py, vc.py (vận chuyển),
               ns.py (nhân sự), kho.py (nền nhóm Kho) + kho_ton.py, kho_han.py, kho_kk.py, kho_nhap.py,
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
