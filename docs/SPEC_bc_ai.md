# SPEC_bc_ai — Trợ lý AI trong app `bc`

Bản 1 · 23/11/2026 · viết theo code `mrhuychien/bc` nhánh `main` (commit `ac4de5f`, shell `bc-p6-r1`).
Người thực thi: Claude Code. Đọc trước khi code: `README.md`, `bc/api/_common.py`, `bc/api/sections.py`,
`docs/verified/harness/README.md`, `docs/verified/harness/test_sections.py`.

---

## 0. Quyết định đã chốt

| Chủ đề | Quyết định |
|---|---|
| Vị trí | Trong app `bc`: package lõi `bc/ai/` + whitelisted `bc/api/ai.py`. Không app mới, không phụ thuộc `tc` / AKASHIC. |
| Nguồn số | Một nguồn: **payload của chính các method `bc.api.*`** (AI thấy đúng cái lãnh đạo thấy trên màn hình, đã qua luật riêng tư của bc) + detector SQL mới cho hệ thống / chứng từ / giá. AI không tự truy vấn DB (trừ P3, chỉ quản trị). |
| Tín hiệu | **Python sinh tín hiệu** (quy tắc có ngưỡng). LLM chỉ xếp hạng, giải thích, khuyến nghị, và được nêu thêm tối đa 3 nhận định tự do mỗi nhóm. |
| Con số | LLM **không được viết số liệu**. Mọi số trong lời là placeholder trỏ vào gói số; máy chủ thay bằng số thật rồi mới lưu. Lời còn số trần → không hiện cho người xem. |
| Không LLM vẫn chạy | Tắt AI / hết credit / API lỗi → màn vẫn hiện tín hiệu với lời theo quy tắc (nhãn "Quy tắc"). |
| Provider | Claude viết chính. OpenAI phản biện (P2, để trống model = tắt). Gọi HTTP bằng `requests` có sẵn của Frappe — **không thêm dependency** vào `pyproject.toml`. |
| Khoá API | `site_config.json`: `bc_ai_anthropic_key`, `bc_ai_openai_key`. Không nằm trong DocType, không trả ra API, không ghi log / Error Log. |
| Trần chi | Trần mềm theo provider / kỳ trong BC Settings (mặc định 90 USD). Trần cứng: Console không gắn thẻ, không auto-reload → hết credit thì API tự từ chối. |
| Quyền | Mảng mới `tro-ly` (ẩn / hiện như mọi mảng). Nhận định dùng số của mảng nào thì mảng đó đang ẩn → người xem không thấy. Tín hiệu `audience = quan-tri` chỉ System Manager thấy. |
| Riêng tư khi gửi đi | Chỉ gửi payload bc (không tên nhân viên, lương đã gộp nhóm < 5, số TK đã che) + thay tên khách / NCC bằng mã giả, hoàn nguyên khi lưu (bật mặc định). |
| "bc chỉ đọc" | Giữ nguyên: không ghi chứng từ nghiệp vụ. Chỉ ghi DocType của chính bc (`BC AI *`, `BC Settings`). |

## 1. Build brief

- **Domain**: mỗi sáng lãnh đạo mở `/bc#/tro-ly` thấy 5–15 việc đáng chú ý nhất toàn công ty (kèm vì sao, nên làm gì,
  bấm sang màn gốc). Quản trị thấy thêm nhóm Hệ thống. Chỉ đọc.
- **DocType mới**: `BC AI Insight`, `BC AI Run`, `BC AI Brief` (P2) + 2 child của BC Settings (`BC AI Rule`, `BC AI Model Price`).
- **Vai trò**: `BC Viewer` đọc qua API đã lọc (không DocPerm trên DocType mới); `System Manager` toàn quyền + màn cấu hình.
- **Giao diện**: 2 view SPA no-build — `views/tro-ly.js` (mọi người), `views/ai-quan-tri.js` (quản trị). CSS prefix `bc-ai-`.
- **Ràng buộc**: theo đúng nếp hiện có của repo — guard dòng đầu, `safe_block`, mốc thời gian từ Python, fieldname ASCII,
  `__init__.py` mọi package, `py_compile` + `node --check` + `run_all.sh` xanh, commit-per-feature (P0…P3), thử phá.
- **Khi nghi ngờ hành vi Frappe v16 / định dạng API của Anthropic, OpenAI: đọc source / tài liệu thật, không code theo trí nhớ.**

## 2. Luồng chạy

```
cron 05:30 → bc.ai.jobs.daily → enqueue(queue="long") → bc.ai.pipeline.run_daily()
 1 collect   gọi bc.api.* (user Administrator, refresh=1)            → pack[mảng][tên] = payload
 2 detect    detector SQL mới                                        → pack["he-thong"][...], pack["tro-ly"][...]
 3 signals   quy tắc đọc pack                                        → [Signal]
 4 upsert    BC AI Insight theo signal_key: mới / còn / hết → đóng
 5 write     (ai_enabled, có khoá, chưa chạm trần) Claude, 1 lượt gọi / nhóm → lời + khuyến nghị + ≤ 3 nhận định tự do
 6 render    placeholder → số thật; lint số trần; sai → needs_check, quay về lời quy tắc
 7 review    (P2, có ai_openai_model) OpenAI phản biện nhận định đỏ / vàng
 8 log       BC AI Run: token, chi phí, trạng thái, ảnh chụp KPI
```

Bước 5–7 lỗi bất kỳ → ghi `BC AI Run.status`, **không** làm hỏng bước 1–4, 8. Đầu lượt chạy:
`frappe.set_user("Administrator")` (job do quản trị bấm "Chạy ngay" cũng phải qua `_guard` của mảng đang ẩn).
Bản tin ngày không phải một bước: ghép lúc đọc (mục 6.3).

```
bc/ai/__init__.py
bc/ai/registry.py     Signal, @rule, @detector, KPIS
bc/ai/collect.py      dựng pack từ bc.api.*            (chỉ import bc.api.* và frappe)
bc/ai/rules/          kd.py, kho.py, cn.py, vc.py, ns.py, attp.py        (hàm thuần trên pack, KHÔNG SQL)
bc/ai/detectors/      he_thong.py (P0), chung_tu.py, gia.py (P2)         (SQL chỉ SELECT)
bc/ai/store.py        upsert / đóng / tắt tín hiệu, dọn dữ liệu cũ
bc/ai/redact.py       mã giả khách + NCC
bc/ai/render.py       placeholder, định dạng số, lint
bc/ai/budget.py       chi phí, trần
bc/ai/prompt.py       system prompt + JSON schema
bc/ai/llm/            __init__.py (call), anthropic.py, openai.py        (CHỈ nơi này import requests + đọc khoá)
bc/ai/pipeline.py     run_daily, run_weekly
bc/ai/jobs.py         điểm vào scheduler (enqueue)
bc/api/ai.py          whitelisted
```

## 3. Gói số (pack)

`collect.build(today)` gọi thẳng hàm Python (không qua HTTP), mỗi lời gọi bọc try/except; lỗi →
`{"_error": true}` + `frappe.clear_last_message()`. Danh sách cố định:

| Mảng | `pack[mảng][tên]` ← method (tham số) |
|---|---|
| `tong-quan` | `summary` ← `kd.get_summary` · `channels` ← `kd.get_channels` · `item_groups` ← `kd.get_item_groups` · `top_customers` ← `kd.get_top_customers` |
| `ngay` | `daily` ← `kd.get_daily(năm, tháng hiện tại)` |
| `thang` | `monthly` ← `kd.get_monthly` |
| `tet` | `npp_growth` ← `tet.get_npp_growth` · `items` ← `tet.get_items` |
| `tinh-thanh` | `provinces` ← `kd.get_provinces` |
| `san-pham` | `top_products` ← `kd.get_top_products("all")` |
| `san-xuat` | `overview` ← `sx_hop.get_overview()` (tháng này — số hộp ghi ở phần Ghi hộp của sx) |
| `sx-tet` | `items` ← `sx.get_items()` · `daily` ← `sx.get_daily_summary(năm, tháng)` |
| `ton-kho` | `overview` ← `kho_ton.get_overview` · `trend` ← `kho_ton.get_trend` |
| `han-dung` | `overview` ← `kho_han.get_overview` |
| `kiem-ke` | `overview` ← `kho_kk.get_overview()` |
| `nhap-tp` | `overview` ← `kho_nhap.get_overview()` |
| `van-chuyen` | `overview` ← `vc.get_overview()` |
| `cong-no` | `receivables` ← `cn.get_receivables` |
| `phai-tra` | `payables` ← `cn.get_payables` |
| `nhan-su` | `overview` ← `ns.get_overview` |
| `attp` | `overview` ← `attp.get_overview` · `report` ← `attp.get_report()` |

- Không lấy `thoi-gian-thuc` (5:30 sáng chưa có số trong ngày).
- Mọi lời gọi `refresh=1` (tính lại + làm ấm cache cho buổi sáng). Chạy dưới Administrator nên qua `_guard` kể cả mảng đang ẩn.
- Quy tắc và việc phân giải path luôn chạy trên **pack đầy đủ**. Riêng bản sao gửi LLM: danh sách > 30 phần tử giữ 30
  đầu, thêm `"_cat": <số bị cắt>` ở dict cha; JSON một nhóm > 120.000 ký tự → cắt tiếp danh sách dài nhất, ghi vào Run.
- **`collect.py` không đọc DocType nghiệp vụ nào trực tiếp** (bộ thử AST chặn). Muốn AI thấy thêm số gì → thêm vào
  màn bc trước.

**Đường dẫn (path)** vào pack: `cong-no.receivables.kpis.overdue_pct`, `cong-no.receivables.top_overdue[0].overdue`.
Đây là địa chỉ duy nhất của mọi con số trong hệ thống AI.

**Nhóm gọi LLM** (mỗi nhóm một lượt):

| Nhóm | Mảng | audience |
|---|---|---|
| `kinh-doanh` | tong-quan, ngay, thang, tet, tinh-thanh, san-pham | lanh-dao |
| `kho-sx` | san-xuat, sx-tet, ton-kho, han-dung, kiem-ke, nhap-tp | lanh-dao |
| `van-chuyen` | van-chuyen | lanh-dao |
| `tai-chinh` | cong-no, phai-tra | lanh-dao |
| `nhan-su` | nhan-su | lanh-dao |
| `attp` | attp | lanh-dao |
| `kiem-soat` (P2) | tro-ly (detector chứng từ, giá) | lanh-dao |
| `he-thong` | he-thong (detector) | quan-tri |

## 4. Tín hiệu

```python
@dataclass
class Signal:
    key: str          # ổn định: "<rule>" hoặc "<rule>:<đối tượng>"  vd "cn.qua_han_ty_le", "kd.kenh_sut:npp"
    rule: str
    section: str      # mảng chính (một mã trong SECTIONS, hoặc "he-thong")
    audience: str     # "lanh-dao" | "quan-tri"
    severity: str     # "do" | "vang"
    title: str        # lời quy tắc, có placeholder: "Nợ quá hạn chiếm {{cong-no.receivables.kpis.overdue_pct|pct}} phải thu"
    detail: str       # (tuỳ chọn) một câu nói rõ thêm, cùng cú pháp placeholder — thân thẻ khi không có lời AI
    paths: list[str]  # mọi path quy tắc đã dùng
    documents: list   # [{"doctype","name"}] ≤ 20 — chỉ trả cho quản trị
    route: str        # "#/cong-no"

@rule("cn.qua_han_ty_le", section="cong-no", vang=20, do=35, unit="%", label="Tỷ lệ nợ quá hạn")
def qua_han_ty_le(pack, cfg) -> list[Signal]: ...
```

- Quy tắc = hàm thuần trên pack (không SQL, không frappe.db). Khối nguồn `_error` / `available: False` → quy tắc
  **"không chạy được"** (khác với "chạy, không có tín hiệu").
- Ngưỡng: mặc định trong decorator; `BC Settings.ai_rules` ghi đè (`disabled`, `threshold`, `threshold_red`).
- Vòng đời theo `signal_key` (`store.py`):
  - mới → tạo Insight `status = mo`, `first_seen = now`;
  - còn → cập nhật `last_seen`, `severity`, `paths`, lời; `seen_count + 1` (tối đa 1 / ngày);
  - quy tắc chạy được mà không còn tín hiệu → `status = dong`, `closed_on`;
  - quy tắc không chạy được → **giữ nguyên**, không đóng;
  - `dong` rồi xuất hiện lại → mở lại (`mo`, `first_seen = now`);
  - `bo-qua` + `mute_until`: không hiện cho người xem, không gửi LLM; hết hạn mà còn tín hiệu → `mo`. `mute_until`
    trống = bỏ qua hẳn.
- Dọn hằng ngày: Insight `dong` > 180 ngày, Run > 180 ngày, Brief > 400 ngày.

### 4.1 Danh mục quy tắc trên payload sẵn có

Cột "Nguồn" là khối đã xác nhận có trong code. **Khoá con phải đọc code từng method để lấy đúng tên; khối / khoá
không có → KHÔNG đoán, bỏ quy tắc và ghi vào `docs/ai-rules-audit.md`** (bảng: quy tắc · path đã dùng · ghi chú).
Commit file audit trước khi viết quy tắc. Ngưỡng là giá trị khởi điểm, chỉnh sau 3 ngày chạy thật.

| Rule | Mảng | Nguồn (trong pack) | Điều kiện (vàng / đỏ) | P |
|---|---|---|---|---|
| `cn.qua_han_ty_le` | cong-no | `receivables.kpis.overdue_pct` | > 20% / > 35% | 0 |
| `cn.qua_han_lon` | cong-no | `receivables.top_overdue[]` (`max_days`, `overdue`) | có khách quá hạn > 90 ngày và ≥ 50 tr → gộp 1 tín hiệu, tối đa 5 khách | 0 |
| `cn.vuot_han_muc` | cong-no | `receivables.kpis.over_limit` | > 0 | 1 |
| `cn.dso_cao` | cong-no | `receivables.kpis.dso` | > 45 ngày / > 60 | 1 |
| `cn.chua_phan_bo` | cong-no | `receivables.kpis.unallocated` | ≥ 100 tr | 1 |
| `cn.phai_tra_qua_han` | phai-tra | `payables.ap.due.overdue_total`, `overdue_count` | > 0 / ≥ 200 tr | 1 |
| `cn.thieu_tien_14_ngay` | phai-tra | `payables.ap.due.{overdue_total,upcoming_total}` so `payables.cash.total` | phải trả 14 ngày > 80% quỹ / > 100% | 1 |
| `kho.ton_am` | han-dung | `overview.am` | có mã âm / giá trị âm ≥ 20 tr | 0 |
| `kho.het_han` | han-dung | `overview.han` (phần hết hạn) | — / giá trị > 0 | 0 |
| `kho.can_date` | han-dung | `overview.han` (cận date ≤ N ngày) | > 10% tồn thành phẩm / > 20% | 1 |
| `kho.khong_ban_duoc` | han-dung | `overview.khong_ban` | ≥ 50 tr / ≥ 200 tr | 1 |
| `kho.ton_chet` | ton-kho | `overview.slow` | tồn chết > 5% / > 10% hàng bán được | 1 |
| `kho.doi_cao` | ton-kho | `overview.doi` (truyền thống) | > 45 ngày / > 75 | 1 |
| `kho.suc_khoe` | ton-kho (quan-tri) | `overview.health`, `trend.trend` | định giá lại lỗi → đỏ; hoá đơn chưa trừ kho, POS chưa gộp, sổ lệch Bin, phiếu ngày tương lai → vàng. Mỗi mục 1 key `kho.suc_khoe:<mục>` | 1 |
| `kho.kk_lech` | kiem-ke | `overview.ira`, `meta.nguong` | dưới ngưỡng `canh_bao` / `nguy` có sẵn | 1 |
| `kho.xuat_khac_cao` | kiem-ke | `overview.xuat_khac` | ≥ 30 tr / tháng | 1 |
| `kho.no_bom` | nhap-tp | `overview.no_bom` | có nợ BOM > 7 ngày / > 30 ngày | 1 |
| `kho.gia_von_0` | nhap-tp | `overview.gia_von_0` | có mã / — | 1 |
| `vc.cho_qua_han` | van-chuyen | `overview.giao.cho_qua_han.qua_n` | > 0 / > 10 | 0 |
| `vc.chua_xep_chuyen` | van-chuyen | `overview.giao.xep` | > 0 / > 10 | 1 |
| `vc.giao_lan_dau` | van-chuyen | `overview.giao.lan_dau` | < 90% / < 80% | 1 |
| `vc.su_co_mo` | van-chuyen | `overview.su_co` | có sự cố mở > 7 ngày | 1 |
| `vc.cuoc_canh_bao` | van-chuyen | `overview.cuoc` (các cảnh báo trả cước) | > 0 | 1 |
| `vc.xe_qua_han` | van-chuyen | `overview.xe.can_xu_ly` | sắp đến / quá hạn | 1 |
| `ns.bhxh_rui_ro` | nhan-su | `overview.bhxh` | > 0 người | 1 |
| `ns.giay_to` | nhan-su | `overview.giay_to` | sắp hết / đã hết hạn | 1 |
| `ns.viec_ton` | nhan-su | `overview.canh_bao.rows[]` (`muc`, `so_nguoi`) | 1 key / mã cảnh báo mức đỏ | 1 |
| `attp.den_do` | attp | `overview.linh_vuc[]` (`den`, `ma`, `ten`, `nhac`) | 1 key `attp.den_do:<ma>` / lĩnh vực đỏ | 0 |
| `attp.chi_tieu` | attp | `report.chi_tieu[]` | chỉ tiêu luỹ kế chưa đạt | 1 |
| `kd.tang_truong_am` | tong-quan | `summary.meta.growth.net` | < −10% / < −20% | 1 |
| `kd.tra_hang_cao` | tong-quan | `summary.rows[]` (`return_rate`) | > 3% và cao hơn cùng kỳ ≥ 1 điểm / > 5% | 1 |
| `kd.kenh_sut` | tong-quan | `channels.rows[]` | kênh ≥ 10% doanh số giảm > 15% so cùng kỳ; key `kd.kenh_sut:<channel_key>` | 1 |
| `tet.npp_tut` | tet | `npp_growth.rows[]`; chỉ khi `npp_growth.meta.between_seasons` sai | ≥ 3 NPP (năm trước ≥ 100 tr) giảm > 20% → gộp | 1 |
| `tet.cham_muc_tieu` | tet | `npp_growth.rows[]` + `npp_growth.meta.target_pct`; chỉ trong mùa | tăng trưởng cùng kỳ thấp hơn mục tiêu ≥ 10 điểm / ≥ 20 | 1 |

### 4.2 Detector hệ thống (SQL / hệ điều hành — `audience = quan-tri`, mảng `he-thong`)

Kết quả đổ vào `pack["he-thong"][<tên>]`, quy tắc tương ứng đọc từ đó. Tên bảng / cột kiểm trên schema v16 của bộ thử.

| Rule | Nguồn | Điều kiện | P |
|---|---|---|---|
| `ht.error_log` | `tabError Log` 24 giờ, nhóm theo `method` | tổng > 2× trung bình 7 ngày và ≥ 10; kèm 5 nhóm nhiều nhất (chỉ tên `method` + số lần, **không gửi traceback**) | 0 |
| `ht.job_that_bai` | `tabScheduled Job Log` status Failed, 24 giờ | > 0 theo `scheduled_job_type` | 0 |
| `ht.email_loi` | `tabEmail Queue` status Error, 24 giờ | > 0 | 1 |
| `ht.hang_doi` | số job chờ của RQ (`frappe.utils.background_jobs`) | > 50 / > 200 | 1 |
| `ht.backup_cu` | file mới nhất trong thư mục backup của site | > 26 giờ → đỏ | 1 |
| `ht.dia_day` | `shutil.disk_usage` thư mục site | > 85% / > 93% | 1 |
| `ht.dang_nhap_sai` | `tabActivity Log` đăng nhập thất bại 24 giờ | 1 tài khoản > 10 lần | 1 |
| `ht.ai_loi` | `BC AI Run` 3 lượt gần nhất | cả 3 lỗi / hết credit | 1 |

"Bộ lập lịch chết" không tự phát hiện được bằng job. Xử lý ở lúc đọc: `get_feed` trả `meta.stale = true` khi lượt
chạy thành công gần nhất > 26 giờ → view hiện dải đỏ.

### 4.3 Detector kiểm soát (P2 — mảng `tro-ly`, `audience = lanh-dao`, danh sách chứng từ chỉ quản trị thấy)

| Rule | Ý | Mặc định |
|---|---|---|
| `ct.huy_nhieu` | Số chứng từ bị huỷ 7 ngày (Sales Invoice, Purchase Invoice, Payment Entry, Journal Entry, Stock Entry) so trung bình 8 tuần | > 2× và ≥ 5 |
| `ct.ghi_lui` | Chứng từ tạo trong 7 ngày (đã duyệt) có `posting_date` lùi so ngày tạo | lùi > 10 ngày |
| `ct.but_toan_tay_lon` | Journal Entry nhập tay đã duyệt 7 ngày | `total_debit` ≥ 100 tr |
| `gia.ban_lech` | Dòng Sales Invoice 7 ngày có `net_rate` thấp hơn trung vị 90 ngày của cùng mã × kênh (bỏ dòng giá 0) | thấp hơn > 15% |
| `gia.chiet_khau_cao` | Dòng Sales Invoice 7 ngày có `discount_percentage` cao | > 15% |
| `gia.mua_tang` | Giá mua 30 ngày của một mã so trung bình 90 ngày trước đó, giá trị mua ≥ 20 tr | tăng > 10% |
| `kpi.lech_chuan` | KPI trong `KPIS` lệch > 3 MAD so trung vị 28 ngày (từ `BC AI Run.kpis`, cần ≥ 14 ngày lịch sử) | 1 key / KPI |

Luật SQL: chỉ SELECT; `docstatus`, loại `is_opening` như `_common`; mốc ngày truyền tham số (không `CURDATE()`);
trung vị tính ở Python. Không trả tên người tạo / người sửa cho `lanh-dao`.

## 5. Hợp đồng LLM

### 5.1 Adapter (`bc/ai/llm/`)

```python
def call(provider, model, system, user, schema_name, schema, max_tokens=4000, timeout=120) -> dict
# → {"data": dict theo schema, "tokens_in": int, "tokens_out": int, "model": str}
# lỗi → raise LLMError(kind): "no_key" | "credit" | "rate" | "http" | "timeout" | "schema"
```

- Anthropic: Messages API, ép đầu ra bằng tool + `tool_choice` chỉ định tool. OpenAI: Responses API, structured output
  theo JSON schema. **Lấy đúng URL, header, tên trường `usage` từ tài liệu hiện hành** (docs.claude.com,
  platform.openai.com) lúc code.
- Retry tối đa 2 lần, backoff 5 s / 20 s, chỉ cho 429 giới hạn tốc độ, 5xx, timeout. Lỗi hết credit (OpenAI trả 429
  mã `credit_balance_exhausted`; Anthropic: đọc mã lỗi billing trong tài liệu) → `kind = "credit"`, **không retry**.
- Khoá đọc bằng `frappe.conf.get(...)` ngay trong hàm gọi; không gán vào biến module, không đưa vào message lỗi.
  Message lỗi lưu vào Run cắt 300 ký tự và đã xoá mọi chuỗi trùng khoá.
- Bộ thử thay `bc.ai.llm.call` bằng bản giả; **không test nào được ra mạng**.

### 5.2 Đầu vào mỗi nhóm

`system` = vai trò + luật (dưới) + `BC Settings.ai_context` + ngày, năm tài chính, mùa Tết (`tet_season`).
`user` = JSON: `{"nhom", "pack": <payload các mảng của nhóm, đã mã giả>, "tin_hieu": [{"id": "S1", "rule", "muc",
"loi_quy_tac", "paths", "so_ngay", "trang_thai", "ghi_chu_quan_tri"}]}`. Tối đa `ai_max_signals` tín hiệu / nhóm
(ưu tiên đỏ, rồi mới nhất). Tín hiệu `bo-qua` không gửi.

Luật viết trong system prompt (tiếng Việt):

1. Với mỗi tín hiệu đáng nói: tiêu đề ≤ 12 từ; nội dung ≤ 60 từ: cái gì, bao nhiêu, vì sao đáng quan tâm.
2. 1–3 khuyến nghị cụ thể, giao theo **bộ phận** (không tên người).
3. Mọi số liệu viết bằng placeholder `{{path|kiểu}}`, kiểu ∈ `tien | so | pct | ngay | chu`. Cấm tự viết, tự tính, tự
   làm tròn số liệu. Số chỉ thời hạn trong khuyến nghị ("trong 7 ngày") được viết thường.
4. Nguyên nhân không có trong số liệu → viết "cần kiểm tra: …", không khẳng định.
5. Tín hiệu `dang-xu-ly` hoặc kéo dài nhiều ngày → nói tiến triển (tốt lên / xấu đi), không báo như việc mới.
6. Được nêu thêm tối đa 3 nhận định ngoài danh sách tín hiệu nếu số trong pack cho thấy điều đáng chú ý mà quy tắc chưa
   bắt. Không có thì để trống. Không viết cho đủ số lượng.
7. Giọng: ngắn, thẳng, không thuật ngữ kế toán khó, không cảm thán.

### 5.3 Đầu ra (schema `ghi_nhan_dinh`)

```json
{"insights": [{
   "signal": "S3 | null",
   "severity": "do | vang",
   "priority": 1,
   "title": "…", "body": "…", "advice": ["…"]
}]}
```

Máy chủ xử lý từng insight (`render.py`):

1. Tách mọi `{{path|kiểu}}` trong title / body / advice. Path phải tồn tại trong pack **của nhóm đó**; kiểu khớp giá trị
   (`tien | so | pct` → số; `ngay` → ngày ISO; `chu` → chuỗi ≤ 120 ký tự). Sai → `needs_check`.
2. Định dạng: `tien` như `fmtMoney` của `lib/format.js` nhưng viết đủ ("1,6 tỷ", "33 triệu", "450.000 đ");
   `so` nhóm nghìn kiểu VN; `pct` 1 chữ số thập phân + `%`; `ngay` `d/m/yyyy`; `chu` hoàn nguyên mã giả.
3. Lint phần lời **đã bỏ placeholder**: còn dãy ≥ 3 chữ số không dính liền chữ cái, hoặc số đứng trước `%`, `đ`, `₫`,
   `k`, `tr`, `triệu`, `tỷ`, `nghìn` → `needs_check`. Ngoại lệ được giữ: năm `20xx`, ngày dạng `d/m` hoặc `d/m/yyyy`,
   mã có chữ đứng trước (vd `SR900`).
4. `needs_check` → không dùng lời AI: tín hiệu giữ lời quy tắc (`source = quy-tac`); nhận định tự do bị bỏ. Đếm vào Run.
5. `signal = S…`: lời gắn vào Insight của tín hiệu đó. `severity = max(quy tắc, LLM)` — LLM không hạ được mức đỏ. Mỗi S
   tối đa 1 insight (trùng → lấy cái đầu).
6. `signal = null`: `signal_key = "ai:" + <path đầu tiên trong body, bỏ chỉ số mảng>`, `rule = "ai"`,
   `source = "ai"`, `section` = mảng của path đó. Tối đa 3 / nhóm. Lượt sau LLM không nêu lại → đóng.
7. `sections_used` = tập mảng (khoá cấp 1) của mọi path trong insight. Lưu lời **đã thay số** + `paths` + thời điểm.
8. Thứ tự toàn cục (`rank`): đỏ trước, `priority` cao trước, `first_seen` cũ trước.

### 5.4 Mã giả (`redact.py`)

Bật bởi `ai_mask_parties`. Bảng ánh xạ dựng mỗi lượt từ `tabCustomer` (`name`, `customer_name`) và `tabSupplier`
(`name`, `supplier_name`) → `KH#0001…`, `NCC#0001…`. Duyệt bản sao pack: **chuỗi nào bằng đúng** một tên → thay (không
thay chuỗi con). Sau khi nhận lời: thay mã giả trong lời về tên thật. Path luôn phân giải trên pack gốc. Bảng ánh xạ
không lưu, không gửi.

### 5.5 Chi phí và trần (`budget.py`)

- Chi phí = `tokens_in × price_in + tokens_out × price_out` (USD / 1 triệu token, từ `ai_prices` theo đúng model).
  Model chưa khai giá → `cost_usd` trống, màn quản trị báo "chưa khai giá".
- Kỳ = từ ngày `ai_cycle_day_<provider>` gần nhất (mặc định 1) đến nay. Đã chi ≥ trần → bỏ lượt gọi, Run
  `status = vuot-tran`.
- Chặn cứng thêm: ≤ 30 lượt gọi LLM / ngày / provider (hằng số), kể cả khi chưa khai giá.

## 6. Dữ liệu

### 6.1 `BC AI Insight` (autoname `hash`; DocPerm: chỉ System Manager)

| fieldname | type | ghi chú |
|---|---|---|
| `signal_key` | Data, unique, reqd | |
| `rule` · `section` · `route` | Data | |
| `sections_used` | Small Text | mỗi dòng một mã mảng |
| `audience` | Select `lanh-dao` / `quan-tri` | |
| `severity` | Select `do` / `vang` | |
| `status` | Select `mo` / `dang-xu-ly` / `bo-qua` / `dong` | mặc định `mo` |
| `source` | Select `quy-tac` / `ai` | lời đang hiển thị do ai viết |
| `title` · `rule_title` | Data (200) | `rule_title` luôn là lời quy tắc đã thay số |
| `body` · `advice` | Small Text | `advice`: mỗi dòng một khuyến nghị |
| `paths` · `documents` | JSON | |
| `priority` · `rank` · `seen_count` | Int | |
| `first_seen` · `last_seen` · `closed_on` · `text_at` | Datetime | `text_at`: lúc sinh lời |
| `mute_until` | Date | |
| `admin_note` | Small Text | đưa vào prompt lượt sau |
| `review_verdict` | Select (trống) / `dong-y` / `nghi-ngo` | P2 |
| `review_note` | Small Text | P2 |
| `needs_check` | Check | lượt gần nhất lời AI bị loại |

### 6.2 `BC AI Run` (autoname `hash`; chỉ System Manager)

`run_type` (Select `ngay` / `tuan` / `tay` / `hoi-dap`) · `step` (Data: nhóm hoặc `review`) · `provider` · `model` ·
`started` · `finished` · `status` (Select `ok` / `loi` / `het-credit` / `vuot-tran` / `tat` / `khong-khoa`) ·
`tokens_in` · `tokens_out` · `cost_usd` (Float) · `signals` · `insights_ai` · `rejected` (Int) · `error` (Small Text) ·
`kpis` (JSON, chỉ ở dòng tổng của lượt chạy ngày).

Một lượt chạy ngày = 1 dòng tổng (`step = "tong"`) + 1 dòng / lượt gọi LLM. **Không lưu prompt, không lưu pack.**

`KPIS` (registry trong `registry.py`): ~40 path chọn tay kèm kiểu + nhãn (phải thu, quá hạn, DSO, phải trả, quỹ, tồn
kho, tồn chết, hết hạn, tồn âm, doanh số luỹ kế, tỷ lệ trả hàng, đơn chờ giao, tỷ lệ giao, quân số, số đèn đỏ ATTP…).
`kpis` = `{path: giá trị}` của ngày đó.

### 6.3 `BC AI Brief` (autoname `hash`; chỉ System Manager)

`brief_type` (Select `ngay` / `tuan` / `thang`) · `brief_date` (Date) · `title` · `body` (Text) · `sections_used`
(Small Text) · `source` · `model` · duy nhất theo (`brief_type`, `brief_date`).

Bản tin ngày (P1, không LLM): tiêu đề "Sáng {ngày}: {n} việc cần chú ý", thân = tiêu đề của 5 nhận định `lanh-dao`
xếp đầu. Vì người xem có thể bị ẩn một số mảng, **bản tin ngày ghép lúc đọc** từ danh sách đã lọc (không cần lưu);
`BC AI Brief` dùng từ P2 cho bản tin tuần / tháng.

### 6.4 BC Settings — mục mới "Trợ lý AI" (Section Break + mọi field **permlevel 1**)

| fieldname | type | mặc định | dùng cho |
|---|---|---|---|
| `ai_enabled` | Check | 0 | bật LLM viết lời (tắt = chỉ quy tắc) |
| `ai_claude_model` | Data | `claude-sonnet-5-5` | lượt ngày |
| `ai_claude_model_deep` | Data | `claude-opus-5-5` | bản tin tuần / tháng (P2); trống = dùng model ngày |
| `ai_openai_model` | Data | (trống) | phản biện (P2); trống = tắt |
| `ai_cap_claude_usd` · `ai_cap_openai_usd` | Float | 90 | trần mềm / kỳ |
| `ai_cycle_day_claude` · `ai_cycle_day_openai` | Int | 1 | ngày bắt đầu kỳ credit |
| `ai_prices` | Table `BC AI Model Price` | | `model` Data · `price_in` Float · `price_out` Float |
| `ai_mask_parties` | Check | 1 | mã giả khách / NCC |
| `ai_max_signals` | Int | 40 | tín hiệu tối đa / nhóm / lượt |
| `ai_context` | Small Text | | bối cảnh công ty cho AI (quản trị tự viết) |
| `ai_rules` | Table `BC AI Rule` | | `rule_key` Data · `disabled` Check · `threshold` Float · `threshold_red` Float · `note` Data |

`install.seed_settings()` điền mặc định cho ô trống (không ghi đè). Tên model mặc định: kiểm lại trên trang models của
Anthropic lúc code; sai tên thì để trống và báo trong README.

## 7. API `bc/api/ai.py`

Mọi method: docstring + guard ở **dòng đầu**. Thêm `"tro-ly"` vào `_common.SECTIONS` (ngay sau `"thoi-gian-thuc"`).

| Method | Guard | Trả |
|---|---|---|
| `get_feed(refresh=0)` | `_guard("tro-ly")` | `{meta, brief, counts, insights[]}` |
| `get_badge(refresh=0)` | `_guard("tro-ly")` | `{do, vang}` sau lọc — cho chấm đỏ trên menu (`test_sections.py` gọi mọi method báo cáo với `refresh=1` nên phải nhận tham số này) |
| `get_admin()` | `_admin_guard()` | trạng thái khoá (chỉ có / không), model, chi phí kỳ này so trần, 20 Run gần nhất, danh mục quy tắc (mặc định + ghi đè + số tín hiệu đang mở), Insight `needs_check`, Insight đang `bo-qua` |
| `run_now()` POST | `_admin_guard()` | enqueue `run_daily` (`run_type = tay`) → `{queued: true}`; đang chạy → từ chối |
| `set_status(insight, status, mute_days=None, note=None)` POST | `_admin_guard()` | Insight sau cập nhật |
| `set_rule(rule_key, disabled=None, threshold=None, threshold_red=None)` POST | `_admin_guard()` | quy tắc sau cập nhật; `rule_key` lạ → lỗi |
| `test_connection(provider)` POST | `_admin_guard()` | `{ok, model, error}` — gọi thử 1 lượt tối thiểu, ghi Run |

`_admin_guard()` như `sections.py`. `get_feed` lọc theo người gọi:

- Người xem: `audience = lanh-dao`; `status ∈ (mo, dang-xu-ly)`; **mọi** mảng trong `sections_used` không nằm trong
  `hidden_sections()`; bỏ `documents`, `admin_note`, `review_note`, `needs_check`. Không trả số lượng bị lọc.
- Quản trị: tất cả `audience`, mọi trạng thái trừ `dong` (tham số `closed=1` để xem 30 ngày đã đóng), đủ trường.
- `meta`: `last_run`, `last_ok`, `stale` (lượt ok gần nhất > 26 giờ), `ai_on` (ai_enabled và có khoá),
  `as_of`.
- **Không dùng `run_cached` dùng chung** (kết quả phụ thuộc vai và mảng ẩn). Truy vấn nhẹ, đọc thẳng.
- Mỗi insight: `id, section, section_label, group, severity, title, body, advice[], route, source, status, days`
  (số ngày từ `first_seen`), `first_seen, last_seen, review_verdict`.

`hooks.py`:

```python
scheduler_events = {"cron": {
	"30 5 * * *": ["bc.ai.jobs.daily"],
	# P2: "0 6 * * 1": ["bc.ai.jobs.weekly"],
}}
```

`jobs.daily` chỉ enqueue (`queue="long"`, `timeout=1800`, chống chạy trùng bằng `job_id` + khoá cache
`bc:ai:lock` 30 phút). Kiểm trong source v16: tham số chống trùng của `frappe.enqueue`, và múi giờ mà cron của
scheduler dùng (mục tiêu 05:30 giờ Việt Nam).

## 8. Giao diện

- `lib/nav.js` nhóm "Điều hành", sau Thời gian thực: `{ route: '/tro-ly', label: 'Trợ lý AI', icon: 'fa-wand-magic-sparkles' }`.
  `nav.js` chỉ chứa route của mảng và phải **đúng thứ tự `SECTIONS`** (bộ thử so từng phần tử) — route quản trị không
  đặt ở đây.
- `shell.js`: thêm `'/tro-ly'` vào `ALL_VIEWS` (đúng mẫu dòng hiện có — bộ thử đọc bằng regex); quản trị:
  `VIEW_MODULES['/ai']` → `views/ai-quan-tri.js`, mục menu Quản trị `{ route: '/ai', label: 'Cấu hình AI', icon: 'fa-robot' }`.
  Chấm đỏ cạnh mục Trợ lý AI khi `get_badge().do > 0` (gọi 1 lần sau `buildNav`, lỗi thì bỏ qua).
- `lib/api.js`: `export const ai = { feed, badge, admin, runNow, setStatus, setRule, test }`.
- Đổi `BUILD` (`shell.js`) và `SHELL_BUILD` (`www/bc.py`) thành `bc-p7-r1`. File mới trong `lib/` hoặc `components/`
  (nếu có) → thêm dòng import map trong `www/bc.html`.

**`#/tro-ly`**

1. Banner: tiêu đề, "Cập nhật {last_ok}", badge "AI" hoặc "Quy tắc" theo `meta.ai_on`.
2. `meta.stale` → `bc-alert` đỏ: "Trợ lý chưa chạy từ {last_ok} — số dưới đây có thể đã cũ."
3. Bản tin ngày: thẻ đầu trang, 5 dòng tiêu đề (bấm cuộn tới thẻ tương ứng).
4. Thanh lọc nhóm: Tất cả · Kinh doanh · Kho & SX · Vận chuyển · Công nợ · Nhân sự · ATTP · (quản trị) Hệ thống. Chỉ
   hiện nhóm có nhận định.
5. Thẻ nhận định (`bc-ai-card`, viền trái đỏ / vàng): tiêu đề · nội dung · khuyến nghị (danh sách) · dòng phụ
   "{n} ngày · {nhãn mảng} · AI | Quy tắc" · nút "Xem ở màn {nhãn}" (`href = route`). `dang-xu-ly` → badge "Đang xử lý".
   `review_verdict = nghi-ngo` → badge "Cần kiểm chứng".
6. Quản trị, trên mỗi thẻ: Đang xử lý · Bỏ qua 7 ngày / 30 ngày / hẳn · Mở lại · ô ghi chú · danh sách chứng từ
   (link `/app/<doctype>/<name>`, tab mới) · `review_note`.
7. Trống: `emptyState` "Không có việc cần chú ý".
8. Chân trang `bc-note`: "ⓘ Tín hiệu do quy tắc tính trên cùng số liệu với các màn báo cáo. Phần lời có nhãn AI do mô
   hình ngôn ngữ viết; mọi con số trong lời do máy chủ chèn từ số liệu gốc. Cập nhật 5:30 mỗi sáng."

**`#/ai`** (quản trị): khối trạng thái (khoá Claude / OpenAI: có / chưa; model; nút "Thử kết nối"; `ai_enabled`) · chi
phí kỳ này / trần mỗi provider (thanh tiến độ) · nút "Chạy ngay" · bảng quy tắc (bật / tắt, ngưỡng vàng / đỏ, số tín
hiệu đang mở) · bảng Run gần nhất · danh sách lời AI bị loại · link `/app/bc-settings`.

Không tràn ngang ở 390px; mọi chuỗi từ server qua `escapeHtml`; lời AI hiển thị dạng **văn bản thuần** (không
`innerHTML` nội dung chưa escape, không render markdown).

## 9. Kiểm thử (bộ `docs/verified/harness`)

Mở rộng `frappe/` giả: `enqueue` (chạy thẳng), `conf`, những hàm `frappe.utils` mới dùng. Thêm vào `run_all.sh`.

**`test_ai.py`** (MariaDB + LLM giả, không ra mạng):

1. Quy tắc: mỗi rule có ca dương + ca âm trên pack dựng tay; ngưỡng ghi đè từ `ai_rules`; rule `disabled` không sinh.
2. Vòng đời: mới → còn (`seen_count` tăng 1 / ngày) → hết thì `dong` → xuất hiện lại thì `mo`; khối nguồn `_error` →
   **không** đóng; `bo-qua` còn hạn không gửi LLM, hết hạn mở lại.
3. Render: path đúng → số định dạng đúng (tỷ / triệu / % / ngày); path sai, sai kiểu, path ngoài nhóm → `needs_check` +
   quay về lời quy tắc; lời AI có "1.250.000", "35%", "2 tỷ" viết trần → bị loại; "trong 7 ngày" được giữ.
4. LLM hạ mức đỏ xuống vàng → vẫn đỏ. Hai insight cùng một S → lấy cái đầu. > 3 nhận định tự do → cắt còn 3.
5. Mã giả: tên khách / NCC không xuất hiện trong `user` gửi LLM giả; lời lưu có tên thật; chuỗi chỉ chứa tên như chuỗi
   con không bị thay.
6. Lọc: người xem không thấy `quan-tri`, `bo-qua`, `needs_check`, `documents`, `admin_note`; ẩn mảng `cong-no` →
   nhận định có `sections_used` chứa `cong-no` biến mất với người xem, quản trị vẫn thấy; ẩn `tro-ly` → `get_feed`
   của người xem 403.
7. Trần: đã chi ≥ trần → không gọi LLM, Run `vuot-tran`, tín hiệu vẫn cập nhật. `LLMError("credit")` → Run
   `het-credit`, không retry. Không có khoá → `khong-khoa`. `ai_enabled = 0` → `tat`. Mọi trường hợp bước 1–4 vẫn chạy.
8. Lộ khoá: đặt khoá giả đặc biệt trong `frappe.conf`; chuỗi đó không có trong kết quả mọi method `bc.api.ai.*`, trong
   `BC AI Run.error`, trong tham số `log_error` (kể cả khi adapter ném lỗi chứa khoá).
9. `get_admin` / `run_now` / `set_status` / `set_rule` / `test_connection`: người xem → PermissionError.

**AST (thêm vào `test_ai.py` hoặc `test_kho_nen.py`)**: `bc/ai/collect.py` chỉ import `frappe`, `bc.api.*`, thư viện
chuẩn; chỉ `bc/ai/llm/*` import `requests` và đọc `bc_ai_*_key`; `bc/ai/rules/*` không gọi `frappe.db`;
`bc/ai/detectors/*` không có `INSERT | UPDATE | DELETE | ALTER | DROP` trong chuỗi SQL.

**`test_sections.py`**: `EXPECTED` thêm `"ai.get_feed": "tro-ly"`, `"ai.get_badge": "tro-ly"`; `KHONG_MANG` thêm 5 method
quản trị; menu `nav.js` ↔ `SECTIONS` ↔ `ALL_VIEWS` khớp.

**Giao diện**: `ui_check.mjs` thêm `#/tro-ly` (người xem + quản trị) và `#/ai` (quản trị): không lỗi JS / HTTP, 390px
không cuộn ngang, số thẻ = số insight API trả, người xem không có nút quản trị.

Mỗi nhóm kiểm đều thử phá (`BC_APP_ROOT=<bản sửa hỏng>` phải đỏ) như nếp hiện có.

## 10. Giai đoạn

| P | Nội dung | Nghiệm thu trước khi sang P kế |
|---|---|---|
| **P0 — Nền, chưa gọi LLM** | `BC AI Insight`, `BC AI Run`, 2 child + field Settings + mảng `tro-ly`; `registry`, `collect`, `store`, `render` (phần lời quy tắc), `jobs`, `pipeline` bước 1–4, 8; rule cột P = 0 (8 cái); API `get_feed`, `get_badge`, `get_admin`, `run_now`, `set_status`, `set_rule`; 2 view; `docs/ai-rules-audit.md` | Deploy, chạy 3 sáng liên tiếp. Tín hiệu khớp số trên màn gốc. Chỉnh ngưỡng. |
| **P1 — AI viết** | `llm/anthropic.py`, `prompt`, `render` đầy đủ + lint, `redact`, `budget`, `test_connection`, bước 5–6; đủ rule cột P = 1 và detector hệ thống | Một tuần chạy: tỷ lệ lời AI bị loại < 10%; không số nào trong lời lệch màn gốc; chi phí / ngày ghi nhận trong Run. |
| **P2 — Phản biện, kiểm soát, bản tin** | `llm/openai.py` + bước 7; detector 4.3; `kpi.lech_chuan`; `run_weekly` (model deep) → `BC AI Brief` tuần / tháng | Xem mục 11. |
| **P3 — Hỏi đáp** | Xem mục 12. **Cần spec riêng được duyệt trước khi code.** | |

Mỗi P: `bench --site site1.local migrate && bench build --app bc && bench restart`, thử trên điện thoại thật.

## 11. P2 — phác thảo

- **Phản biện**: với mỗi nhận định đỏ / vàng `source = ai` của lượt ngày, gửi OpenAI: lời đã thay số + pack của nhóm (đã
  mã giả). Schema: `{"verdict": "dong-y | nghi-ngo", "note": "≤ 30 từ"}`. `note` qua cùng lint số. `nghi-ngo` → badge
  "Cần kiểm chứng" (mọi người), `review_note` (chỉ quản trị). Không tự ẩn nhận định.
- **Bản tin tuần** (thứ Hai 06:00, model deep): đầu vào = `kpis` 8 tuần (mỗi KPI: giá trị, Δ tuần, Δ 4 tuần, min / max
  — **Python tính sẵn**, đưa vào pack tuần dưới `tuan.<kpi>.<chỉ_số>`), nhận định mở / đóng / kéo dài ≥ 7 ngày trong
  tuần, `ai_context`. Đầu ra 3 phần: "Điều đáng chú ý", "Việc tồn chưa xử lý", "Ưu tiên tuần tới". Cùng luật
  placeholder + lint. `sections_used` suy từ path; người xem chỉ thấy bản tin khi không mảng nào trong đó bị ẩn.
- **Bản tin tháng**: như tuần, kỳ 12 tháng, ngày 2 hằng tháng.

## 12. P3 — hỏi đáp (phác thảo, chưa làm)

- **Người xem**: tool duy nhất `xem_mang(mảng, tên, tham_số)` gọi đúng các method trong bảng mục 3 **dưới phiên của
  chính người hỏi** (`_guard` tự chặn mảng ẩn) → không mở thêm bề mặt lộ dữ liệu nào so với màn hình.
- **Quản trị**: thêm `get_schema(doctype)`, `run_select(sql)`. `run_select` chỉ tồn tại khi `site_config` có
  `bc_ai_ro_user` / `bc_ai_ro_password` (tài khoản MariaDB **chỉ GRANT SELECT**); một câu lệnh, bắt đầu bằng
  `SELECT` / `WITH`; bọc `LIMIT 200` + `max_statement_time`; từ chối khi đụng `__Auth`, `tabSessions`, `tabOAuth%`,
  `tabBC Share Link`, bảng lương, cột nhạy cảm của `tabEmployee`; cấm `INTO OUTFILE`, `LOAD_FILE`, `SLEEP`, `BENCHMARK`.
- Số trong câu trả lời: đối chiếu với kết quả tool của chính phiên đó; số không đối chiếu được → đánh dấu "chưa kiểm".
- Giới hạn: câu / ngày / người, ≤ 6 bước tool / câu, mọi lượt ghi `BC AI Run` (`hoi-dap`).

## 13. Deploy

Trước khi deploy P1 (làm một lần, ngoài server):

1. Claude: claude.ai → Settings › Billing › mục API credits › Link organization (gói Max phải đủ 7 ngày). OpenAI
   (P2): ChatGPT → Settings › Billing › API credits, nối với API organization cùng email.
2. Tạo API key ở Console mỗi bên. **Không gắn thẻ, không bật auto-reload / auto recharge** — hết credit là dừng.
3. Khai giá model vào `BC Settings › ai_prices` theo bảng giá hiện hành.

```bash
cd /home/frappe/frappe-bench
 bench --site site1.local set-config bc_ai_anthropic_key 'KHOÁ'      # dấu cách đầu dòng: không lưu vào history
 bench --site site1.local set-config bc_ai_openai_key 'KHOÁ'         # P2
cd apps/bc && git pull && cd ../..
bench --site site1.local migrate && bench build --app bc && bench restart
bench --site site1.local execute bc.ai.pipeline.run_daily             # chạy thử ngay
```

## 14. Checklist nghiệm thu (P0 + P1)

- [ ] `/bc#/tro-ly` với user chỉ có BC Viewer: thấy nhận định `lanh-dao`, không nút quản trị, không nhóm Hệ thống.
- [ ] Ẩn mảng Công nợ ở `#/an-mang` → nhận định công nợ biến mất với người xem; ẩn Trợ lý AI → mất menu + API 403.
- [ ] Mỗi con số trong 10 thẻ bất kỳ khớp màn gốc cùng thời điểm (bấm "Xem ở màn…").
- [ ] Tắt `ai_enabled` → chạy lại → mọi thẻ nhãn "Quy tắc", không lỗi.
- [ ] Đặt trần 0 → Run `vuot-tran`, không phát sinh lượt gọi.
- [ ] Rút khoá khỏi `site_config` → Run `khong-khoa`, màn quản trị báo "chưa có khoá".
- [ ] `grep -r "sk-" apps/bc` rỗng; Error Log không chứa khoá sau khi cố tình cấu hình khoá sai.
- [ ] Không còn `requests` ngoài `bc/ai/llm/`; `pyproject.toml` `dependencies = []` như cũ.
- [ ] Dừng scheduler 27 giờ (hoặc sửa `last_ok` trong test) → dải đỏ "chưa chạy".
- [ ] `py_compile` + `node --check` + `run_all.sh` xanh; mọi package có `__init__.py`; `BUILD` = `SHELL_BUILD` = `bc-p7-r1`.
- [ ] README thêm mục "Trợ lý AI" (luồng, luật số, luật riêng tư, cấu hình, cách thêm một quy tắc).
