"""Trợ lý AI — bc.ai.redact sau vòng soát chéo (quyết định D2, D3, D4 của FIXES).

- D2: tên khách / NCC chép trên hoá đơn đã duyệt (khác hồ sơ hiện tại — đổi tên sau khi xuất hoá đơn) là bí danh của
  CÙNG mã; đối tác chỉ có trên hoá đơn vẫn có mã; chuỗi dưới khoá đối tác (customer, customer_name, customer_id,
  chain, supplier …) mà không phải tên đã biết → mã cùng dòng (customer_id) hoặc mã MỚI, hoàn nguyên ra đúng chuỗi.
- D3: tên nằm GIỮA câu trong gói số (attp "Nguồn: <NCC>") được thay khi đứng riêng thành từ; nhanh với 5.000 đối tác
  × gói 150 KB.
- D4: chỉ mã ĐÃ PHÁT RA (gửi) mới hoàn nguyên / bỏ; begin() xoá bản ghi.
render.py và phần redact cũ có bộ thử riêng (test_ai_render.py). Chỉ redact.build cần MariaDB.

Chạy: BC_TEST_DB=bc_test_ai_redact python3 -B test_ai_redact.py
"""
import copy
import json
import random
import time

from seed import Check, drop_column, drop_doctype, insert, reset

import frappe  # noqa: E402  (giả)

from bc.ai import redact, render  # noqa: E402

c = Check()
LAN_ANH, ABC, BAO_BI = "Tạp hoá 268 Lan Anh", "Công ty ABC", "NCC Bao Bì Số 1"


def eq(label, got, want):
	c(label, got == want, f"\n      được: {got!r}\n      cần : {want!r}")


def begin(m):
	"""Mask.begin() (bản trước sửa không có → bỏ qua)."""
	getattr(m, "begin", lambda: None)()


def base():
	return redact.Mask([
		("KH#0001", LAN_ANH, {"CUST-0001", LAN_ANH}),
		("KH#0002", ABC, {"CUST-0002", ABC}),
		("NCC#0001", BAO_BI, {"SUP-0001", BAO_BI}),
	])


# ══ D2: đóng chặt theo khoá ═══════════════════════════════════════════════════
print("\n— D2: chuỗi dưới khoá đối tác không có trong bảng vẫn ra mã —")
M = base()
goc = {
	"tong-quan": {"top_customers": {"rows": [
		{"customer": "Đại lý Phúc Lộc (tên cũ)", "customer_id": "CUST-0001", "amount": 450_000_000},
		{"customer": "Khách Vãng Lai Mới", "customer_id": "KHONG-CO-HO-SO", "amount": 1},
		{"customer": ABC, "customer_id": "CUST-0002", "amount": 2},
	]}},
	"cong-no": {"receivables": {"mt": {"chains": [{"chain": "Saigon Co.op", "amount": 40_000_000}]},
		"top_overdue": [{"customer": "Khách Lẻ Không Mã", "overdue": 5}]}},
	"phai-tra": {"payables": {"ap": {"due": {"rows": [{"supplier": "NCC Bao bì (tên cũ)", "amount": 15_000_000}]},
		"top": [{"supplier": "NCC Đường Lạ", "outstanding": 1}]}}},
	"san-pham": {"top_products": {"rows": [{"item_name": "Khách Vãng Lai Mới", "item_group": "Hàng Tết"}]}},
	"van-chuyen": {"overview": {"giao": {"by_type": [{"hinh_thuc": "Viettel Post", "n": 6}]},
		"xe": {"can_xu_ly": [{"xe": "29C-111.11", "loai": "Xe tải"}]}}},
	"tinh-thanh": {"provinces": {"rows": [{"province": "Hà Nội", "sales": 1}]}},
}
truoc = copy.deepcopy(goc)
che = M.mask(goc)
c("mask không đổi obj gốc", goc == truoc)
r0, r1, r2 = che["tong-quan"]["top_customers"]["rows"]
eq("tên cũ cạnh customer_id đã biết → mã CỦA khách đó (KH#0001)", (r0["customer"], r0["customer_id"]), ("KH#0001", "KH#0001"))
c("khách không có hồ sơ (cả tên lẫn mã) → mã MỚI, đánh số sau mã có sẵn", r1["customer"].startswith("KH#")
	and r1["customer_id"].startswith("KH#") and int(r1["customer"][3:]) >= 3 and int(r1["customer_id"][3:]) >= 3, str(r1))
eq("tên đã biết vẫn như cũ", (r2["customer"], r2["customer_id"]), ("KH#0002", "KH#0002"))
ch = che["cong-no"]["receivables"]["mt"]["chains"][0]["chain"]
c("nhãn chuỗi MT (khoá chain) → mã KH mới", ch.startswith("KH#") and ch not in ("KH#0001", "KH#0002"), ch)
c("khách lẻ không mã (khoá customer) → mã KH mới", che["cong-no"]["receivables"]["top_overdue"][0]["customer"].startswith("KH#"),
	str(che["cong-no"]["receivables"]["top_overdue"]))
s_due = che["phai-tra"]["payables"]["ap"]["due"]["rows"][0]["supplier"]
s_top = che["phai-tra"]["payables"]["ap"]["top"][0]["supplier"]
c("NCC tên cũ / NCC lạ (khoá supplier) → mã NCC mới, khác nhau", s_due.startswith("NCC#") and s_top.startswith("NCC#")
	and s_due != s_top and "NCC#0001" not in (s_due, s_top), f"{s_due} {s_top}")
eq("khoá KHÔNG phải đối tác (tên hàng, hãng xe, xe, tỉnh, nhóm hàng) giữ nguyên",
	(che["san-pham"]["top_products"]["rows"][0], che["van-chuyen"]["overview"]["giao"]["by_type"][0]["hinh_thuc"],
	che["van-chuyen"]["overview"]["xe"]["can_xu_ly"][0], che["tinh-thanh"]["provinces"]["rows"][0]["province"]),
	({"item_name": "KH#" + r1["customer"][3:], "item_group": "Hàng Tết"}, "Viettel Post",
	{"xe": "29C-111.11", "loai": "Xe tải"}, "Hà Nội"))
gui = json.dumps(che, ensure_ascii=False)
c("không tên khách / NCC nào (kể cả tên cũ, khách lạ, nhãn chuỗi) còn trong bản gửi", not any(x in gui for x in (
	"Phúc Lộc", "Khách Vãng Lai", "KHONG-CO-HO-SO", "Saigon Co.op", "Khách Lẻ", "Bao bì (tên cũ)", "NCC Đường Lạ",
	LAN_ANH, ABC, BAO_BI)), gui[:400])
eq("hoàn nguyên: mã mới ra đúng chuỗi đã che; mã dùng lại ra tên hồ sơ",
	(M.unmask(r1["customer"]), M.unmask(ch), M.unmask(s_due), M.unmask(s_top), M.unmask("KH#0001")),
	("Khách Vãng Lai Mới", "Saigon Co.op", "NCC Bao bì (tên cũ)", "NCC Đường Lạ", LAN_ANH))
che2 = M.mask(goc)
eq("che lần hai (nhóm khác) cho cùng mã", (che2["cong-no"]["receivables"]["mt"]["chains"][0]["chain"],
	che2["tong-quan"]["top_customers"]["rows"][1]["customer"]), (ch, r1["customer"]))
eq("tên cũ đã thành bí danh → giữa câu cũng ra cùng mã", M.mask_text("Gọi Đại lý Phúc Lộc (tên cũ) hôm nay"),
	"Gọi KH#0001 hôm nay")
eq("chuỗi rỗng / khoảng trắng / không phải chuỗi dưới khoá đối tác giữ nguyên",
	M.mask({"customer": "", "supplier": "  ", "customer_name": None, "chain": 5}),
	{"customer": "", "supplier": "  ", "customer_name": None, "chain": 5})
eq("Mask() rỗng (tắt che): khoá đối tác cũng không che", redact.Mask().mask({"customer": "Khách X", "chain": "Co.op"}),
	{"customer": "Khách X", "chain": "Co.op"})

# ══ D3: tên giữa câu ══════════════════════════════════════════════════════════
print("\n— D3: tên đã biết nằm giữa câu trong gói số được thay (đứng riêng thành từ) —")
M3 = redact.Mask([
	("NCC#0001", "Công ty Cát Vàng Sông Hồng", {"NCC-CAT-01", "Công ty Cát Vàng Sông Hồng"}),
	("KH#0001", "Hà An", {"C-HA", "Hà An"}),
	("KH#0002", "Hùng", {"C-HUNG", "Hùng"}),
	("KH#0003", "Phương", {"C-PHUONG", "Phương"}),
])
attp = {"attp": {"overview": {"linh_vuc": [{"ma": "cat", "dong": ["Nguồn: Công ty Cát Vàng Sông Hồng",
	"1 lần đổi nguồn chờ kết quả kim loại nặng"], "nhac": [{"chi_tiet": "Nguồn Công ty Cát Vàng Sông Hồng, nhập ngày "
	"20/10. Đổi nguồn cát phải kiểm kim loại nặng.", "tieu_de": "Cát từ Hà An chưa kiểm"}]}]}}}
che = M3.mask(attp)
lv = che["attp"]["overview"]["linh_vuc"][0]
eq("attp: 'Nguồn: <NCC>' trong dòng / lời nhắc → mã", (lv["dong"][0], lv["nhac"][0]["chi_tiet"][:16], lv["nhac"][0]["tieu_de"]),
	("Nguồn: NCC#0001", "Nguồn NCC#0001, ", "Cát từ KH#0001 chưa kiểm"))
c("attp: tên NCC không còn trong bản gửi", "Cát Vàng" not in json.dumps(che, ensure_ascii=False))
eq("path phân giải như cũ trên bản gốc (khoá không đổi)", list(lv), list(attp["attp"]["overview"]["linh_vuc"][0]))
eq("tên ≥ 2 từ thay dù ngắn; tên MỘT từ < 6 ký tự không thay; một từ ≥ 6 ký tự thì thay",
	M3.mask(["Gặp Hà An chiều nay", "Anh Hùng gọi", "Chị Phương gọi"]),
	["Gặp KH#0001 chiều nay", "Anh Hùng gọi", "Chị KH#0003 gọi"])
eq("'từ' = dãy chữ / số: mã ngắn có gạch ('NPP-B', 'C-HA') là 2 từ → thay giữa câu",
	redact.Mask([("KH#0009", "NPP-B", {"NPP-B"}), ("KH#0001", "Hà An", {"C-HA"})]).mask(["Đã gọi NPP-B và C-HA."]),
	["Đã gọi KH#0009 và KH#0001."])
eq("tên dính chữ / số hai bên không thay", M3.mask(["xHà An", "Hà An2", "Hà Anh", "Công ty Cát Vàng Sông Hồng9"]),
	["xHà An", "Hà An2", "Hà Anh", "Công ty Cát Vàng Sông Hồng9"])
eq("chuỗi bằng đúng tên một từ ngắn vẫn thay (khớp đúng, như cũ)", M3.mask("Hùng"), "KH#0002")
eq("unmask lời có mã đã gửi", M3.unmask("Kiểm cát của NCC#0001 và KH#0001."),
	"Kiểm cát của Công ty Cát Vàng Sông Hồng và Hà An.")

print("\n— D3: nhanh — 5.000 đối tác × gói số 150 KB —")
rnd = random.Random(7)
HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Vũ", "Đặng", "Bùi"]
parties = [(f"KH#{i:04d}", f"Đại lý {HO[i % 8]} Văn {i}", {f"CUST-{i:05d}", f"Đại lý {HO[i % 8]} Văn {i}"})
	for i in range(1, 4001)]
parties += [(f"NCC#{i:04d}", f"Công ty Cung Ứng {i}", {f"SUP-{i:05d}", f"Công ty Cung Ứng {i}"}) for i in range(1, 1001)]
MB = redact.Mask(parties)
rows = []
while len(json.dumps(rows, ensure_ascii=False)) < 150_000:
	i = rnd.randint(1, 4000)
	rows.append({"customer": f"CUST-{i:05d}", "customer_name": f"Đại lý {HO[i % 8]} Văn {i}", "amount": i * 1000,
		"ghi_chu": f"Giao cho Đại lý {HO[i % 8]} Văn {i} và Công ty Cung Ứng {rnd.randint(1, 1000)} ngày 5/11, "
		f"tổng {rnd.randint(1, 99)} hộp bánh đậu xanh",
		"item_name": "Bánh đậu xanh Tết hộp quà cao cấp loại một"})
pack = {"tong-quan": {"x": {"rows": rows}}}
kb = len(json.dumps(pack, ensure_ascii=False)) // 1000
t0 = time.monotonic()
che = MB.mask(pack)
dt = time.monotonic() - t0
gui = json.dumps(che, ensure_ascii=False)
c(f"5.000 đối tác × gói {kb} KB: mask < 5 s ({dt:.2f} s)", dt < 5, f"{dt:.2f} s")
c("… và không tên nào còn sót (kể cả giữa câu)", "Đại lý " not in gui and "Công ty Cung Ứng" not in gui
	and "CUST-" not in gui, gui[:300])
t0 = time.monotonic()
for _ in range(200):
	MB.mask_text("Gọi Đại lý Trần Văn 9 và Công ty Cung Ứng 77 trước 5/11; nhắc Đại lý Lê Văn 3999.")
dt = time.monotonic() - t0
c(f"mask_text 200 lời ngắn với bảng 5.000 đối tác < 2 s ({dt:.2f} s)", dt < 2, f"{dt:.2f} s")
eq("… kết quả đúng (tên dài thắng tên là tiền tố của nó: 'Văn 3999' không thành 'Văn 399' + '9'; 'Văn 3999x' dính chữ)",
	MB.mask_text("nhắc Đại lý Bùi Văn 3999 và Đại lý Phạm Văn 3, Đại lý Bùi Văn 399x."),
	"nhắc KH#3999 và KH#0003, Đại lý Bùi Văn 399x.")

# ══ D4: chỉ mã đã gửi ═════════════════════════════════════════════════════════
print("\n— D4: unmask / strip chỉ với mã ĐÃ GỬI; begin() xoá bản ghi —")
M4 = base()
begin(M4)
M4.mask({"rows": [{"customer": "CUST-0001"}]})
eq("mã đã gửi → tên; mã có trong bảng nhưng chưa gửi → giữ nguyên",
	M4.unmask("KH#0001 / KH#0002 / NCC#0001"), f"{LAN_ANH} / KH#0002 / NCC#0001")
eq("strip chỉ bỏ mã đã gửi (mã chưa gửi còn lại cho lint bắt)", M4.strip("KH#0001, KH#0002."), " , KH#0002.")
eq("lint bắt mã chưa gửi", render.lint(M4.strip("KH#0001 và KH#0002")), ["KH#0002"])
begin(M4)
eq("begin() → mã của đề bài trước không còn hoàn nguyên", M4.unmask("KH#0001"), "KH#0001")
M4.mask_text("gọi Công ty ABC")
eq("mã phát qua mask_text cũng là đã gửi", M4.unmask("KH#0002 / KH#0001"), f"{ABC} / KH#0001")
M5 = base()
eq("Mask mới (chưa begin, chưa phát mã) → không hoàn nguyên mã nào (ví dụ đề bài 'KH#0001' không thành tên)",
	(M5.unmask("KH#0001"), M5.strip("NCC#0001")), ("KH#0001", "NCC#0001"))

# ══ D2: redact.build đọc tên trên hoá đơn ═════════════════════════════════════
print("\n— D2: redact.build thêm tên chép trên hoá đơn đã duyệt (MariaDB) —")
reset(only={"Customer", "Supplier", "Sales Invoice", "Purchase Invoice"})
insert("Customer", name="NPP-A", customer_name="Công ty Hà Thành (tên mới)")
insert("Customer", name="NPP-B", customer_name="Đại lý Bình Minh")
insert("Supplier", name="SUP-BB", supplier_name="NCC Bao bì Mới")
insert("Sales Invoice", name="SI-1", customer="NPP-A", customer_name="Đại lý Phúc Lộc (tên cũ)", docstatus=1)
insert("Sales Invoice", name="SI-2", customer="NPP-A", customer_name="Công ty Hà Thành (tên mới)", docstatus=1)
insert("Sales Invoice", name="SI-3", customer="NPP-XOA", customer_name="Khách Đã Xoá Hồ Sơ", docstatus=1)
insert("Sales Invoice", name="SI-4", customer="NPP-B", customer_name="Tên Nháp Chưa Duyệt", docstatus=0)
insert("Sales Invoice", name="SI-5", customer="NPP-B", customer_name=None, docstatus=1)
insert("Purchase Invoice", name="PI-1", supplier="SUP-BB", supplier_name="NCC Bao bì (tên cũ)", docstatus=1)
insert("Purchase Invoice", name="PI-2", supplier="SUP-XOA", supplier_name="NCC Đã Xoá", docstatus=1)
B = redact.build()
begin(B)
eq("tên cũ trên hoá đơn → CÙNG mã với hồ sơ", B.mask(["NPP-A", "Công ty Hà Thành (tên mới)", "Đại lý Phúc Lộc (tên cũ)"]),
	["KH#0001", "KH#0001", "KH#0001"])
eq("khách chỉ còn trên hoá đơn → mã đánh tiếp sau hồ sơ (KH#0003), cả mã lẫn tên",
	B.mask(["NPP-XOA", "Khách Đã Xoá Hồ Sơ"]), ["KH#0003", "KH#0003"])
eq("NCC: tên cũ trên hoá đơn mua → cùng mã; NCC chỉ có trên hoá đơn → NCC#0002",
	B.mask(["SUP-BB", "NCC Bao bì (tên cũ)", "SUP-XOA", "NCC Đã Xoá"]), ["NCC#0001", "NCC#0001", "NCC#0002", "NCC#0002"])
eq("hoá đơn chưa duyệt (docstatus 0) không thêm tên", B.mask("Tên Nháp Chưa Duyệt"), "Tên Nháp Chưa Duyệt")
eq("hoàn nguyên: mã hồ sơ ra tên HIỆN TẠI; mã chỉ có trên hoá đơn ra tên trên hoá đơn",
	B.unmask("KH#0001 | KH#0003 | NCC#0002"), "Công ty Hà Thành (tên mới) | Khách Đã Xoá Hồ Sơ | NCC Đã Xoá")
dong = B.mask({"rows": [{"customer": "Đại lý Phúc Lộc (tên cũ)", "customer_id": "NPP-A", "amount": 450_000_000}]})
eq("payload kd.get_top_customers (tên chép trên hoá đơn + mã) → cùng một mã", dong["rows"][0],
	{"customer": "KH#0001", "customer_id": "KH#0001", "amount": 450_000_000})
eq("tên cũ giữa câu cũng che", B.mask_text("Đã gọi Đại lý Phúc Lộc (tên cũ) hôm qua"), "Đã gọi KH#0001 hôm qua")
frappe.db.queries.clear()
redact.build()
c("build chỉ SELECT", frappe.db.queries and all(q.lstrip().upper().startswith("SELECT") for q in frappe.db.queries),
	str(frappe.db.queries))
drop_column("Sales Invoice", "customer_name")
B = redact.build()
eq("thiếu cột tên trên hoá đơn → vẫn chạy, mã khách chỉ có trên hoá đơn vẫn có mã (tên cũ thì không đọc được)",
	B.mask(["NPP-A", "NPP-XOA", "Đại lý Phúc Lộc (tên cũ)"]), ["KH#0001", "KH#0003", "Đại lý Phúc Lộc (tên cũ)"])
drop_doctype("Purchase Invoice")
drop_doctype("Sales Invoice")
B = redact.build()
eq("thiếu bảng hoá đơn → như cũ (chỉ hồ sơ)", B.mask(["NPP-A", "SUP-BB", "Đại lý Phúc Lộc (tên cũ)"]),
	["KH#0001", "NCC#0001", "Đại lý Phúc Lộc (tên cũ)"])
eq("… nhưng chuỗi lạ dưới khoá đối tác vẫn ra mã (đóng chặt theo khoá)",
	B.mask({"customer": "Đại lý Phúc Lộc (tên cũ)", "customer_id": "NPP-A"})["customer"], "KH#0001")

c.done()
