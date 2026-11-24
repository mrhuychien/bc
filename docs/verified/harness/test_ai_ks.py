"""Trợ lý AI P2 — detector kiểm soát (bc.ai.detectors.chung_tu / gia) + quy tắc ct.* / gia.* (bc.ai.rules.ks; đặc tả §4.3,
hợp đồng P2 §3.1).

A–B: detector SQL trên MariaDB thật (bảng Sales / Purchase Invoice (+ Item), Payment Entry, Journal Entry, Stock Entry
sinh từ DocType JSON v16): seed tay, mốc cửa sổ [today − 6, today] với ca đúng biên, loại đầu kỳ / trả hàng / giá 0 /
bút toán hệ thống sinh, nền 8 tuần / 90 ngày, đơn giá theo đơn vị kho, ngưỡng ghi đè đi tới detector. C: quy tắc trên gói
số dựng tay (dương / âm / đúng ngưỡng, đỏ chỉ khi đặt, nguồn lỗi → không chạy được, ngưỡng gói ≠ ngưỡng áp). D: riêng
tư (không owner / tên người, tên khách / NCC dưới khoá che được), E5 (lời quy tắc chép làm lời mô hình qua render_insight
với kinds + nguon), AST (chỉ SELECT, không NOW(), quy tắc không SQL). E: run_daily thật (mô hình giả): tín hiệu ở nhóm
kiem-soat cho quản trị và người xem, documents chỉ quản trị, đề bài không tên khách / NCC / người, E5 qua lượt chạy.
Số kỳ vọng TÍNH TAY (ghi ở comment).

Chạy: BC_TEST_DB=bc_test_ai_p2b_ks python3 -B test_ai_ks.py
"""
import ast
import copy
import datetime
import json
import os
import re
import socket

from seed import Check, bc_settings, child, insert, reset, single
from paths import BC_ROOT

import ai_testlib  # noqa: E402

registry = ai_testlib.chi_module("bc.ai.rules.ks", "bc.ai.detectors.chung_tu", "bc.ai.detectors.gia",
	"bc.ai.detectors.kpi")

import frappe  # noqa: E402
import frappe.utils  # noqa: E402
from bc.ai import render  # noqa: E402
from bc.ai.detectors import chung_tu as CT, gia as GIA  # noqa: E402

c = Check()
T = "tro-ly"
NOW = frappe.utils.now_datetime()          # 27/10/2026 10:30
TODAY = NOW.date()
CTX = {"now": NOW, "today": TODAY, "pack": {}}
RULES = ("ct.huy_nhieu", "ct.ghi_lui", "ct.but_toan_tay_lon", "gia.ban_lech", "gia.chiet_khau_cao", "gia.mua_tang")
MOI = []
KH, KH2, NCC, NCC2 = "Đại lý Minh Phát", "Siêu thị Bí Mật Xanh", "Công ty Đường Biên Hoà", "Nông sản Bí Mật Hai"
NGUOI = "ke.toan.bimat@hgc.vn"                # owner / modified_by của mọi chứng từ — không được vào gói số
KEY = "sk-ant-api03-KHOAGIA-p2b-ks-77Qx"


def eq(label, got, want):
	c(label, got == want, f"\n      được: {got!r}\n      cần : {want!r}")


def d(s):
	return datetime.date.fromisoformat(s)


def dt(s):
	return datetime.datetime.fromisoformat(s)


def chay(pack, only=RULES, ov=None):
	run = registry.run_rules(pack, overrides=ov, only=only)
	MOI.extend((s, pack) for s in run.signals)
	return run


def muc_all(pack, key, ov=None):
	pack = copy.deepcopy(pack)
	run = chay(pack, only=(key,), ov={key: ov} if ov else None)
	if key not in run.ran:
		return "KHONG-CHAY"
	return {s.key: s.severity for s in run.signals}


def mot(pack, key, ov=None):
	pack = copy.deepcopy(pack)
	run = chay(pack, only=(key,), ov={key: ov} if ov else None)
	return run, {s.key: s for s in run.signals}, pack


def loi(s, pack):
	return render.fill(s.title + " | " + s.detail, pack).text


# Chặn mạng (MariaDB qua unix socket vẫn chạy).
class MangBiChan(RuntimeError):
	pass


def _chan(fn):
	def g(self, addr, *a, **k):
		if self.family in (socket.AF_INET, socket.AF_INET6):
			raise MangBiChan(f"bộ thử chặn mạng: {addr}")
		return fn(self, addr, *a, **k)
	return g


socket.socket.connect, socket.socket.connect_ex = _chan(socket.socket.connect), _chan(socket.socket.connect_ex)

BANG = {"Sales Invoice", "Sales Invoice Item", "Purchase Invoice", "Purchase Invoice Item", "Payment Entry",
	"Journal Entry", "Stock Entry", "Customer", "Customer Group", "Supplier", "User", "BC AI Run", "BC AI Insight",
	"BC AI Brief", "BC AI Rule", "BC AI Model Price", "BC Tet Date", "BC Hidden Item", "BC Share Link"}
reset(only=BANG)
bc_settings()
insert("User", name=NGUOI, enabled=1, first_name="Kế Toán Bí Mật")
for g, cha, l, r in (("All Customer Groups", "", 1, 8), ("Nhà phân phối", "All Customer Groups", 2, 3),
		("Siêu thị", "All Customer Groups", 4, 5), ("Khách lẻ", "All Customer Groups", 6, 7)):
	insert("Customer Group", name=g, customer_group_name=g, parent_customer_group=cha, lft=l, rgt=r, is_group=0)
for ten, g in ((KH, "Nhà phân phối"), (KH2, "Siêu thị")):
	insert("Customer", name=ten, customer_name=ten, customer_group=g)
for ten in (NCC, NCC2):
	insert("Supplier", name=ten, supplier_name=ten)
NGUOI_COT = {"owner": NGUOI, "modified_by": NGUOI}


def doc(doctype, name, *, docstatus=1, creation=None, modified=None, **f):
	creation = creation or dt(f"{f.get('posting_date', '2026-10-27')} 09:00:00")
	return insert(doctype, name=name, docstatus=docstatus, creation=creation, modified=modified or creation,
		**NGUOI_COT, **f)


# ═══ A. Detector chung_tu ════════════════════════════════════════════════════
print("A. Detector chung_tu — hôm nay 27/10/2026, cửa sổ [21/10, 27/10], nền huỷ [26/8, 20/10]")
eq("cửa sổ 7 ngày", CT.cua_so(CTX), (d("2026-10-21"), d("2026-10-27")))

# A1. Huỷ. Trong cửa sổ (đếm): SI ×3 (một lúc 21/10 00:00:00 — đầu biên, một lúc 27/10 23:59:59 — cuối biên), PI ×1,
# PE ×1 (đối tượng là nhân viên → không nêu), JE nhập tay ×1 = 6. Không đếm: JE hệ thống sinh, SE đầu kỳ, SI huỷ lúc
# 28/10 00:00 (sau cửa sổ), SI đã duyệt sửa trong cửa sổ, JE khấu hao huỷ.
doc("Sales Invoice", "SI-H1", docstatus=2, posting_date=d("2026-10-20"), modified=dt("2026-10-21 00:00:00"),
	customer=KH, base_grand_total=11_000_000, is_opening="No")
doc("Sales Invoice", "SI-H2", docstatus=2, posting_date=d("2026-10-26"), modified=dt("2026-10-27 23:59:59"),
	customer=KH2, base_grand_total=22_000_000, is_opening="No")
doc("Sales Invoice", "SI-H3", docstatus=2, posting_date=d("2026-10-25"), modified=dt("2026-10-26 08:00:00"),
	customer=KH, base_grand_total=5_000_000)
doc("Purchase Invoice", "PI-H1", docstatus=2, posting_date=d("2026-10-22"), modified=dt("2026-10-23 10:00:00"),
	supplier=NCC, base_grand_total=40_000_000, is_opening="No")
doc("Payment Entry", "PE-H1", docstatus=2, posting_date=d("2026-10-22"), modified=dt("2026-10-24 10:00:00"),
	party_type="Employee", party="NV-BI-MAT", party_name="Nguyễn Văn Bí Mật", base_paid_amount=3_000_000,
	is_opening="No")
doc("Journal Entry", "JE-H1", docstatus=2, posting_date=d("2026-10-22"), modified=dt("2026-10-25 10:00:00"),
	voucher_type="Journal Entry", total_debit=7_000_000, is_opening="No", is_system_generated=0)
doc("Journal Entry", "JE-H-SYS", docstatus=2, posting_date=d("2026-10-22"), modified=dt("2026-10-25 10:00:00"),
	voucher_type="Exchange Gain Or Loss", total_debit=1_000, is_opening="No", is_system_generated=1)
doc("Journal Entry", "JE-H-KH", docstatus=2, posting_date=d("2026-10-22"), modified=dt("2026-10-25 11:00:00"),
	voucher_type="Depreciation Entry", total_debit=2_000, is_opening="No", is_system_generated=0)
doc("Stock Entry", "SE-H-DK", docstatus=2, posting_date=d("2026-10-22"), modified=dt("2026-10-25 10:00:00"),
	is_opening="Yes", total_outgoing_value=9)
doc("Sales Invoice", "SI-H-SAU", docstatus=2, posting_date=d("2026-10-27"), modified=dt("2026-10-28 00:00:00"),
	customer=KH, base_grand_total=1)
doc("Sales Invoice", "SI-DUYET", docstatus=1, posting_date=d("2026-10-27"), modified=dt("2026-10-27 09:00:00"),
	customer=KH, base_grand_total=1)
# Nền 8 tuần: 23 chứng từ huỷ trong [26/8 00:00, 20/10 23:59:59] — một đúng 26/8 00:00 (đầu biên), một 20/10 23:59:59;
# 25/8 23:59:59 (ngoài) không tính. Stock Entry để is_opening trống (mặc định của phiếu kho) vẫn tính.
NEN = [dt("2026-08-26 00:00:00"), dt("2026-10-20 23:59:59")] + [dt("2026-09-01 08:00:00") + datetime.timedelta(days=2 * i)
	for i in range(21)]
for i, m in enumerate(NEN):
	doc("Stock Entry", f"SE-N{i:02d}", docstatus=2, posting_date=m.date(), modified=m, total_incoming_value=1000)
doc("Stock Entry", "SE-N-NGOAI", docstatus=2, posting_date=d("2026-08-25"), modified=dt("2026-08-25 23:59:59"))

h = CT._huy(CTX)
eq("huy: 6 trong cửa sổ, nền 23, 8 tuần, trung bình 2,9", (h["so"], h["so_nen"], h["so_tuan_nen"], h["so_tb_tuan"]),
	(6, 23, 8, 2.9))
eq("huy: theo loại (giảm dần)", h["theo_loai"], [{"doctype": "Sales Invoice", "loai": "hoá đơn bán", "so": 3},
	{"doctype": "Journal Entry", "loai": "bút toán", "so": 1}, {"doctype": "Payment Entry", "loai": "phiếu thu chi",
	"so": 1}, {"doctype": "Purchase Invoice", "loai": "hoá đơn mua", "so": 1}])
eq("huy: dòng mới huỷ trước, đối tác dưới customer / supplier, nhân viên không nêu", [(r["name"], r["cancel_date"],
	r.get("customer"), r.get("supplier"), r["gia_tri"]) for r in h["rows"]], [
	("SI-H2", "2026-10-27", KH2, None, 22_000_000), ("SI-H3", "2026-10-26", KH, None, 5_000_000),
	("JE-H1", "2026-10-25", None, None, 7_000_000), ("PE-H1", "2026-10-24", None, None, 3_000_000),
	("PI-H1", "2026-10-23", None, NCC, 40_000_000), ("SI-H1", "2026-10-21", KH, None, 11_000_000)])

# A2. Ghi lùi: chứng từ đã duyệt TẠO trong cửa sổ, posting_date sớm hơn ngày tạo.
doc("Sales Invoice", "SI-L15", posting_date=d("2026-10-10"), creation=dt("2026-10-25 09:00:00"), customer=KH,
	base_grand_total=15_000_000, is_opening="No", amended_from="SI-L15-CU")         # lùi 15
doc("Purchase Invoice", "PI-L10", posting_date=d("2026-10-11"), creation=dt("2026-10-21 00:00:00"), supplier=NCC2,
	base_grand_total=10_000_000, is_opening="No")                                       # lùi 10 (đầu biên cửa sổ)
doc("Journal Entry", "JE-L26", posting_date=d("2026-10-01"), creation=dt("2026-10-27 08:00:00"), total_debit=26_000,
	voucher_type="Journal Entry", is_opening="No", is_system_generated=0)              # lùi 26
doc("Journal Entry", "JE-L-SYS", posting_date=d("2026-09-01"), creation=dt("2026-10-26 08:00:00"), total_debit=1,
	voucher_type="Exchange Gain Or Loss", is_opening="No", is_system_generated=1)      # hệ thống sinh → bỏ
doc("Stock Entry", "SE-L11", posting_date=d("2026-10-11"), creation=dt("2026-10-22 15:00:00"),
	total_outgoing_value=11_000_000)                                                    # lùi 11 (is_opening trống)
doc("Payment Entry", "PE-L1", posting_date=d("2026-10-25"), creation=dt("2026-10-26 10:00:00"), party_type="Customer",
	party=KH, base_paid_amount=1_000_000, is_opening="No")                             # lùi 1
doc("Payment Entry", "PE-L0", posting_date=d("2026-10-23"), creation=dt("2026-10-23 10:00:00"), party_type="Customer",
	party=KH, base_paid_amount=1, is_opening="No")                                     # không lùi
doc("Sales Invoice", "SI-L-DK", posting_date=d("2026-09-01"), creation=dt("2026-10-24 09:00:00"), customer=KH,
	base_grand_total=1, is_opening="Yes")                                               # đầu kỳ → bỏ
doc("Sales Invoice", "SI-L-TRUOC", posting_date=d("2026-09-01"), creation=dt("2026-10-20 23:59:59"), customer=KH,
	base_grand_total=1, is_opening="No")                                                # tạo trước cửa sổ → bỏ
doc("Sales Invoice", "SI-L-HUY", docstatus=2, posting_date=d("2026-09-01"), creation=dt("2026-10-24 09:00:00"),
	modified=dt("2026-08-01 09:00:00"), customer=KH, base_grand_total=1, is_opening="No")  # đã huỷ → bỏ
gl = CT._ghi_lui(CTX)
eq("ghi_lui: phân bố số ngày lùi (giảm dần) + tổng 5", (gl["so"], gl["phan_bo"]), (5, [{"so_ngay_lui": 26, "so": 1},
	{"so_ngay_lui": 15, "so": 1}, {"so_ngay_lui": 11, "so": 1}, {"so_ngay_lui": 10, "so": 1}, {"so_ngay_lui": 1, "so": 1}]))
eq("ghi_lui: dòng lùi xa trước, có ngày tạo / ngày hạch toán / sửa lại", [(r["name"], r["so_ngay_lui"], r["posting_date"],
	r["creation_date"], r["sua_lai"]) for r in gl["rows"]], [("JE-L26", 26, "2026-10-01", "2026-10-27", False),
	("SI-L15", 15, "2026-10-10", "2026-10-25", True), ("SE-L11", 11, "2026-10-11", "2026-10-22", False),
	("PI-L10", 10, "2026-10-11", "2026-10-21", False), ("PE-L1", 1, "2026-10-25", "2026-10-26", False)])
eq("ghi_lui: PE khách → customer", [r.get("customer") for r in gl["rows"] if r["name"] == "PE-L1"], [KH])

# A3. Bút toán nhập tay lớn (≥ 100 triệu, hạch toán trong cửa sổ).
for n, v, kw in [("JE-T100", 100_000_000, {"posting_date": d("2026-10-21")}),          # đúng ngưỡng → tính
		("JE-T250", 250_000_000, {"posting_date": d("2026-10-27")}),
		("JE-T-DUOI", 99_999_999, {"posting_date": d("2026-10-24")}),
		("JE-T-SYS", 300_000_000, {"posting_date": d("2026-10-24"), "is_system_generated": 1}),
		("JE-T-KH", 400_000_000, {"posting_date": d("2026-10-24"), "voucher_type": "Depreciation Entry"}),
		("JE-T-DK", 500_000_000, {"posting_date": d("2026-10-24"), "is_opening": "Yes"}),
		("JE-T-TRUOC", 150_000_000, {"posting_date": d("2026-10-20")}),
		("JE-T-NHAP", 120_000_000, {"posting_date": d("2026-10-24"), "docstatus": 0}),
		("JE-T-PB", 130_000_000, {"posting_date": d("2026-10-24"), "process_deferred_accounting": "PDA-0001"})]:
	f = {"voucher_type": "Journal Entry", "is_opening": "No", "is_system_generated": 0, **kw}
	doc("Journal Entry", n, total_debit=v, user_remark=f"Chi cho {NGUOI} Nguyễn Văn Bí Mật", title="Bí Mật", **f)
bt = CT._but_toan(CTX)
eq("but_toan: ngưỡng 100 triệu (mặc định), 2 bút toán, tổng 350 triệu, lớn trước", (bt["nguong"], bt["so"],
	bt["gia_tri_tong"], [(r["name"], r["gia_tri"], r["voucher_type"]) for r in bt["rows"]]),
	(100_000_000, 2, 350_000_000, [("JE-T250", 250_000_000, "Journal Entry"), ("JE-T100", 100_000_000, "Journal Entry")]))
child("BC Settings", "BC Settings", "BC AI Rule", "ai_rules", [{"rule_key": "ct.but_toan_tay_lon",
	"threshold": 200_000_000}])
frappe.cache().store.clear()
bt2 = CT._but_toan(CTX)
eq("but_toan: ngưỡng ghi đè 200 triệu đi tới detector → 1 bút toán", (bt2["nguong"], bt2["so"], bt2["gia_tri_tong"]),
	(200_000_000, 1, 250_000_000))
frappe.db.sql("DELETE FROM `tabBC AI Rule`")
frappe.cache().store.clear()

# ═══ B. Detector gia ═════════════════════════════════════════════════════════
print("\nB. Detector gia — dòng bán [21/10, 27/10], nền [23/7, 20/10]; mua [28/9, 27/10], nền [30/6, 27/9]")
_si = iter(range(1, 1000))


def ban(ngay, dong, *, kh=KH, nhom="Nhà phân phối", is_return=0, is_opening="No", docstatus=1, name=None, ty_gia=1):
	"""Hoá đơn bán; giá trong `dong` là giá TIỀN CÔNG TY (đồng). ty_gia ≠ 1: hoá đơn ngoại tệ — net_rate / net_amount
	(tiền hoá đơn) = giá đồng / ty_gia, base_* = giá đồng."""
	n = name or f"SI-B{next(_si):03d}"
	doc("Sales Invoice", n, docstatus=docstatus, posting_date=d(ngay), customer=kh, customer_group=nhom,
		is_return=is_return, is_opening=is_opening, base_grand_total=0, conversion_rate=ty_gia,
		modified=dt("2026-07-01 09:00:00") if docstatus == 2 else None)      # huỷ lâu rồi: ngoài nền ct.huy_nhieu
	for i, x in enumerate(dong, 1):
		ma, rate, cf = x[0], x[1], x[2] if len(x) > 2 else 1
		ck = x[3] if len(x) > 3 else 0
		qty = x[4] if len(x) > 4 else 1
		insert("Sales Invoice Item", parent=n, parenttype="Sales Invoice", parentfield="items", idx=i, item_code=ma,
			item_name={"BDX": "Bánh đậu xanh hộp", "KEO": "Kẹo dừa"}.get(ma, ma), net_rate=rate / ty_gia,
			base_net_rate=rate, conversion_factor=cf, discount_percentage=ck, qty=qty, net_amount=rate * qty / ty_gia,
			base_net_amount=rate * qty, **NGUOI_COT)
	return n


# Nền NPP × BDX (đơn vị kho = hộp): 100.000 (hộp), 2.000.000 / thùng 20 = 100.000, 100.000, 102.000, 90.000 → trung vị
# 100.000 (trung bình 98.400 — khác trung vị), đủ 5 dòng (dòng 23/7 = đầu biên nền). Không vào nền: 22/7 (ngoài), trả hàng, đầu kỳ, đã huỷ, giá 0.
ban("2026-07-23", [("BDX", 100_000)])
ban("2026-08-10", [("BDX", 2_000_000, 20)])
ban("2026-09-10", [("BDX", 100_000)])
ban("2026-10-01", [("BDX", 102_000)])
ban("2026-10-20", [("BDX", 90_000)])
ban("2026-07-22", [("BDX", 50_000)])
ban("2026-09-11", [("BDX", 10)], is_return=1)
ban("2026-09-12", [("BDX", 10)], is_opening="Yes")
ban("2026-09-13", [("BDX", 10)], docstatus=2)
ban("2026-09-14", [("BDX", 0)])
# Nền MT × BDX: chỉ 4 dòng → không đủ, dòng MT trong cửa sổ không được xét.
for ngay in ("2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"):
	ban(ngay, [("BDX", 100_000)], kh=KH2, nhom="Siêu thị")
# Cửa sổ (NPP × BDX): 85.000 → lệch 15,0% (đúng ngưỡng, không báo); 1.690.000 / 20 = 84.500 → 15,5%; 70.000 → 30,0%;
# 90.000 chiết khấu 20% → lệch 10,0%; 100.000 chiết khấu 15% (đúng ngưỡng) → 0%. Không xét: giá 0, trả hàng, MT
# (thiếu nền), KEO (không nền). KEO chiết khấu 15,5%.
SI_L1 = ban("2026-10-21", [("BDX", 85_000)])
SI_L2 = ban("2026-10-27", [("BDX", 1_690_000, 20)])
SI_L3 = ban("2026-10-25", [("BDX", 70_000), ("BDX", 0, 1, 100)])
SI_L7 = ban("2026-10-24", [("BDX", 90_000, 1, 20, 10), ("BDX", 100_000, 1, 15)])
ban("2026-10-24", [("BDX", 50_000)], is_return=1)
SI_MT = ban("2026-10-23", [("BDX", 50_000)], kh=KH2, nhom="Siêu thị")
SI_KEO = ban("2026-10-22", [("KEO", 31_000, 1, 15.5, 5)], kh=KH2, nhom="Siêu thị")
ban("2026-10-20", [("KEO", 1, 1, 90)])                        # trước cửa sổ: chiết khấu cao không tính

dong = GIA._dong_ban(CTX)
eq("dòng bán trong cửa sổ: 7 dòng (bỏ giá 0, trả hàng, ngoài cửa sổ)", len(dong), 7)
bl = GIA._ban_lech(CTX, dong)
eq("ban_lech: ngưỡng 15, xét 5 dòng NPP × BDX, 2 dòng lệch ở 2 hoá đơn", (bl["nguong"], bl["so_ngay_nen"],
	bl["so_dong_xet"], bl["so_dong"], bl["so_hd"]), (15, 90, 5, 2, 2))
eq("ban_lech: dòng lệch nhiều trước (đơn giá theo đơn vị kho, trung vị, 5 dòng nền)", [(r["name"], r["rate"],
	r["trung_vi"], r["lech_pct"], r["so_dong_nen"], r["kenh"], r["customer"], r["item_name"]) for r in bl["rows"]],
	[(SI_L3, 70_000, 100_000, 30.0, 5, "NPP", KH, "Bánh đậu xanh hộp"),
	(SI_L2, 84_500, 100_000, 15.5, 5, "NPP", KH, "Bánh đậu xanh hộp")])
# Tên hiển thị: hoá đơn chụp customer_name khác mã hồ sơ → dòng mang TÊN (như các màn khác của bc), trống thì mã
frappe.db.sql("UPDATE `tabSales Invoice` SET customer_name = %s WHERE name = %s", ("Đại lý Tên Hiển Thị", SI_L3))
eq("ban_lech: khách hiện theo tên chụp trên hoá đơn (customer_name), hoá đơn không có tên thì hiện mã",
	[r["customer"] for r in GIA._ban_lech(CTX, GIA._dong_ban(CTX))["rows"]], ["Đại lý Tên Hiển Thị", KH])
frappe.db.sql("UPDATE `tabSales Invoice` SET customer_name = NULL WHERE name = %s", (SI_L3,))
ck = GIA._chiet_khau(CTX, dong)
eq("chiet_khau: > 15% (ngặt): 2 dòng, 2 hoá đơn, Σ thành tiền 900.000 + 155.000", (ck["nguong"], ck["so_dong"],
	ck["so_hd"], ck["gia_tri"], [(r["name"], r["ck_pct"], r["gia_tri"], r["kenh"]) for r in ck["rows"]]),
	(15, 2, 2, 1_055_000, [(SI_L7, 20, 900_000, "NPP"), (SI_KEO, 15.5, 155_000, "MT")]))
child("BC Settings", "BC Settings", "BC AI Rule", "ai_rules", [{"rule_key": "gia.ban_lech", "threshold": 20},
	{"rule_key": "gia.chiet_khau_cao", "threshold": 16}])
frappe.cache().store.clear()
eq("ngưỡng ghi đè đi tới detector: lệch > 20 → 1 dòng; chiết khấu > 16 → 1 dòng",
	[(x["nguong"], x["so_dong"]) for x in (GIA._ban_lech(CTX, dong), GIA._chiet_khau(CTX, dong))], [(20, 1), (16, 1)])
frappe.db.sql("DELETE FROM `tabBC AI Rule`")
frappe.cache().store.clear()
# Hoá đơn ngoại tệ (USD, tỷ giá 25.000) đúng giá nền: net_rate = 4 (USD) nhưng base_net_rate = 100.000 đ → không lệch;
# dòng chiết khấu 20% tính giá trị bằng TIỀN CÔNG TY (100.000 đ, không phải 4).
SI_USD = ban("2026-10-26", [("BDX", 100_000), ("BDX", 100_000, 1, 20)], ty_gia=25_000)
dong_usd = GIA._dong_ban(CTX)
bl_usd, ck_usd = GIA._ban_lech(CTX, dong_usd), GIA._chiet_khau(CTX, dong_usd)
eq("ngoại tệ: dòng USD đúng giá được xét nhưng không lệch (đơn giá tiền công ty); chiết khấu cộng tiền công ty",
	(bl_usd["so_dong_xet"], bl_usd["so_dong"], [r["name"] for r in bl_usd["rows"]], ck_usd["so_dong"], ck_usd["gia_tri"],
	[r["gia_tri"] for r in ck_usd["rows"] if r["name"] == SI_USD]),
	(7, 2, [SI_L3, SI_L2], 3, 1_155_000, [100_000]))
frappe.db.sql("DELETE FROM `tabSales Invoice Item` WHERE parent = %s", SI_USD)
frappe.db.sql("DELETE FROM `tabSales Invoice` WHERE name = %s", SI_USD)

_pi = iter(range(1, 1000))


def mua(ngay, ma, sl, tien, *, ncc=NCC, is_return=0, is_opening="No", docstatus=1, cf=1):
	n = f"PI-M{next(_pi):03d}"
	doc("Purchase Invoice", n, docstatus=docstatus, posting_date=d(ngay), supplier=ncc, is_return=is_return,
		is_opening=is_opening, base_grand_total=tien, creation=dt(f"{ngay} 09:00:00"),
		modified=dt("2026-07-01 09:00:00") if docstatus == 2 else None)
	insert("Purchase Invoice Item", parent=n, parenttype="Purchase Invoice", parentfield="items", idx=1, item_code=ma,
		item_name={"DUONG": "Đường kính trắng"}.get(ma, ma), stock_qty=sl, qty=sl / cf, conversion_factor=cf,
		base_net_amount=tien, **NGUOI_COT)
	return n


# DUONG: kỳ mới (28/9 đầu biên … 27/10) 22 tr / 1.000 (NCC) + 11,5 tr / 500 (NCC2, 27/10) = 33,5 tr / 1.500 = 22.333,33;
# nền (30/6 đầu biên … 27/9 cuối biên) 20 tr / 1.000 + 20 tr / 1.000 = 20.000 → tăng 11,666… → 11,7% > 10.
# TRUNG: 22 tr / 1.000 = 22.000 vs 20.000 → đúng 10,0% (không báo). BOT: kỳ mới 19.999.999 < 20 tr → bỏ dù tăng gấp
# đôi. MOI: không mua trong nền → bỏ. SUA: nền chỉ có 29/6 (ngoài nền), trả hàng, đầu kỳ, đã huỷ → bỏ.
mua("2026-09-28", "DUONG", 1000, 22_000_000)
PI_DUONG_MOI = mua("2026-10-27", "DUONG", 500, 11_500_000, ncc=NCC2)
mua("2026-09-27", "DUONG", 1000, 20_000_000)
mua("2026-06-30", "DUONG", 1000, 20_000_000)
mua("2026-06-29", "DUONG", 1000, 1_000)                       # ngoài nền
mua("2026-10-10", "TRUNG", 1000, 22_000_000)
mua("2026-08-10", "TRUNG", 1000, 20_000_000)
mua("2026-10-10", "BOT", 1000, 19_999_999)
mua("2026-08-10", "BOT", 1000, 5_000_000)
mua("2026-10-10", "MOI", 1000, 30_000_000)
mua("2026-10-10", "SUA", 1000, 25_000_000)
mua("2026-06-29", "SUA", 1000, 1_000)
mua("2026-08-10", "SUA", 1000, 1_000, is_return=1)
mua("2026-08-11", "SUA", 1000, 1_000, is_opening="Yes")
mua("2026-08-12", "SUA", 1000, 1_000, docstatus=2)
mt = GIA._mua_tang(CTX)
eq("mua_tang: xét 2 mã (DUONG, TRUNG), 1 mã tăng quá 10%", (mt["nguong"], mt["so_ngay"], mt["so_ngay_nen"],
	mt["gia_tri_san"], mt["so_ma_xet"], mt["so_ma"]), (10, 30, 90, 20_000_000, 2, 1))
eq("mua_tang: DUONG 20.000 → 22.333,33 (+11,7%), NCC chính = NCC (22 tr), hoá đơn mới nhất", mt["rows"],
	[{"item_code": "DUONG", "item_name": "Đường kính trắng", "gia_moi": 22_333.33, "gia_cu": 20_000.0, "tang_pct": 11.7,
	"gia_tri_mua": 33_500_000, "so_hd": 2, "supplier": NCC, "doctype": "Purchase Invoice", "name": PI_DUONG_MOI}])

# Detector đầy đủ + khối lỗi.
G0 = GIA.d_gia(CTX)
C0 = CT.d_chung_tu(CTX)
eq("detector gia / chung_tu: đủ khối, không lỗi", (sorted(G0), sorted(C0)), (["ban_lech", "chiet_khau", "den", "mua_tang",
	"so_ngay", "tu"], ["but_toan", "den", "ghi_lui", "huy", "so_ngay", "tu"]))
eq("tu / den / so_ngay", (G0["tu"], G0["den"], G0["so_ngay"], C0["tu"], C0["den"]),
	("2026-10-21", "2026-10-27", 7, "2026-10-21", "2026-10-27"))
_goc = GIA._dong_ban
GIA._dong_ban = lambda ctx: 1 / 0
try:
	g1 = GIA.d_gia(CTX)
finally:
	GIA._dong_ban = _goc
eq("dòng bán lỗi → ban_lech, chiet_khau {_error}; mua_tang vẫn có", (g1["ban_lech"], g1["chiet_khau"],
	g1["mua_tang"]["so_ma"]), ({"_error": True}, {"_error": True}, 1))
_goc = CT._huy
CT._huy = lambda ctx: 1 / 0
try:
	c1 = CT.d_chung_tu(CTX)
finally:
	CT._huy = _goc
eq("khối huy lỗi → {_error}; ghi_lui / but_toan vẫn có", (c1["huy"], c1["ghi_lui"]["so"], c1["but_toan"]["so"]),
	({"_error": True}, 5, 2))

# ═══ C. Quy tắc trên gói thật + gói dựng tay ════════════════════════════════
print("\nC. Quy tắc trên gói thật (seed) và gói dựng tay")
PACK = {T: registry.run_detectors(NOW, T, {})}
eq("run_detectors(tro-ly): chung_tu, gia, kpi (kpi: chưa có lịch sử)", sorted(PACK[T]), ["chung_tu", "gia", "kpi"])
p1 = copy.deepcopy(PACK)
r = chay(p1)
sig = {s.key: s for s in r.signals}
eq("chạy đủ 6 quy tắc, không quy tắc nào lỗi", (sorted(k for k in r.ran if k in RULES), r.not_run), (sorted(RULES), {}))
eq("tín hiệu + mức (ngưỡng mặc định)", {k: s.severity for k, s in sig.items()}, {k: "vang" for k in RULES})
eq("mọi tín hiệu: mảng tro-ly, lanh-dao, route rỗng, khoá = quy tắc", {(s.section, s.audience, s.route, s.key == s.rule)
	for s in sig.values()}, {(T, "lanh-dao", "", True)})
eq("lời đã thay số (seed)", {k: loi(s, p1) for k, s in sig.items()}, {
	"ct.huy_nhieu": "6 chứng từ bị huỷ trong 7 ngày qua | Trung bình 8 tuần trước là 2,9 chứng từ mỗi tuần, nhiều nhất "
		"là hoá đơn bán với 3 chứng từ; kế toán trưởng cần rà soát lý do huỷ.",
	"ct.ghi_lui": "3 chứng từ mới tạo bị ghi lùi ngày quá 10 ngày | Lùi xa nhất 26 ngày ở bút toán số JE-L26, kế toán "
		"cần kiểm tra lý do ghi sổ muộn.",
	"ct.but_toan_tay_lon": "2 bút toán nhập tay từ 100 triệu trở lên trong tuần qua | Tổng 350 triệu, lớn nhất 250 "
		"triệu ở bút toán JE-T250; kế toán trưởng cần đối chiếu chứng từ gốc.",
	"gia.ban_lech": f"2 dòng hàng bán thấp hơn giá trung vị quá 15,0% | Lệch nhiều nhất là Bánh đậu xanh hộp bán cho {KH} "
		"với đơn giá 70.000 đ, trung vị 90 ngày trước đó là 100.000 đ; phòng kinh doanh cần kiểm tra giá đã duyệt.",
	"gia.chiet_khau_cao": f"2 dòng hàng bán có chiết khấu quá 15,0% | Cao nhất 20,0% ở Bánh đậu xanh hộp bán cho {KH}, tổng "
		"giá trị các dòng này 1,1 triệu; phòng kinh doanh cần đối chiếu chính sách chiết khấu.",
	"gia.mua_tang": f"1 mã hàng mua vào tăng giá quá 10,0% | Tăng nhiều nhất là Đường kính trắng với 11,7%, giá bình quân "
		f"từ 20.000 đ lên 22.333 đ mỗi đơn vị kho, nhà cung cấp chính {NCC}; phòng mua hàng cần đối chiếu báo giá."})
eq("documents (chỉ quản trị thấy): bằng chứng của từng tín hiệu", {k: [x["name"] for x in s.documents]
	for k, s in sig.items()}, {
	"ct.huy_nhieu": ["SI-H2", "SI-H3", "JE-H1", "PE-H1", "PI-H1", "SI-H1"],
	"ct.ghi_lui": ["JE-L26", "SI-L15", "SE-L11"],                    # chỉ chứng từ lùi QUÁ 10 ngày
	"ct.but_toan_tay_lon": ["JE-T250", "JE-T100"],
	"gia.ban_lech": [SI_L3, SI_L2], "gia.chiet_khau_cao": [SI_L7, SI_KEO], "gia.mua_tang": [PI_DUONG_MOI]})
eq("documents đúng doctype", {(k, x["doctype"]) for k, s in sig.items() for x in s.documents}, {
	("ct.huy_nhieu", "Sales Invoice"), ("ct.huy_nhieu", "Journal Entry"), ("ct.huy_nhieu", "Payment Entry"),
	("ct.huy_nhieu", "Purchase Invoice"), ("ct.ghi_lui", "Journal Entry"), ("ct.ghi_lui", "Sales Invoice"),
	("ct.ghi_lui", "Stock Entry"), ("ct.but_toan_tay_lon", "Journal Entry"), ("gia.ban_lech", "Sales Invoice"),
	("gia.chiet_khau_cao", "Sales Invoice"), ("gia.mua_tang", "Purchase Invoice")})
eq("mọi lời dựng được", {k: ai_testlib.kiem_loi(s, p1) for k, s in sig.items() if ai_testlib.kiem_loi(s, p1)}, {})
# Đúng ngưỡng trên bảng thật: thêm 1 phiếu huỷ vào nền → 6 vs 24 = đúng 2× trung bình → không báo; bỏ đi → lại báo.
doc("Stock Entry", "SE-N-THEM", docstatus=2, posting_date=d("2026-10-01"), modified=dt("2026-10-01 08:00:00"))
p2 = {T: registry.run_detectors(NOW, T, {})}
eq("huy trên bảng thật: nền 24 (đúng 2×) → chạy, không tín hiệu", (p2[T]["chung_tu"]["huy"]["so_nen"],
	muc_all(p2, "ct.huy_nhieu")), (24, {}))
frappe.db.sql("DELETE FROM `tabStock Entry` WHERE name = 'SE-N-THEM'")

# Nguồn lỗi / thiếu → không chạy được (không phải "chạy, không tín hiệu").
NGUON = {"ct.huy_nhieu": ("chung_tu", "huy"), "ct.ghi_lui": ("chung_tu", "ghi_lui"),
	"ct.but_toan_tay_lon": ("chung_tu", "but_toan"), "gia.ban_lech": ("gia", "ban_lech"),
	"gia.chiet_khau_cao": ("gia", "chiet_khau"), "gia.mua_tang": ("gia", "mua_tang")}


def bo_khoi(pack, det, blk, v):
	p = copy.deepcopy(pack)
	if v is None:
		p[T][det].pop(blk)
	else:
		p[T][det][blk] = v
	return p


eq("khối nguồn _error / available False / thiếu → không chạy được", {k: [muc_all(bo_khoi(PACK, *NGUON[k], v), k)
	for v in ({"_error": True}, {"available": False}, None)] for k in RULES}, {k: ["KHONG-CHAY"] * 3 for k in RULES})
eq("detector cả khối lỗi (pack[tro-ly][chung_tu] = _error) → ct.* không chạy được", sorted(k for k in RULES
	if muc_all({T: {"chung_tu": {"_error": True}, "gia": PACK[T]["gia"]}}, k) == "KHONG-CHAY"),
	["ct.but_toan_tay_lon", "ct.ghi_lui", "ct.huy_nhieu"])

# ct.huy_nhieu — biên: so × 8 > 2 × nền (ngặt) và so ≥ 5.
K = "ct.huy_nhieu"


def HU(so, nen, loai=True):
	return {T: {"chung_tu": {"so_ngay": 7, "huy": {"so": so, "so_nen": nen, "so_tuan_nen": 8,
		"so_tb_tuan": round(nen / 8, 1), "theo_loai": [{"doctype": "Sales Invoice", "loai": "hoá đơn bán", "so": so}]
		if loai else [], "rows": []}}}}


eq("huy: 6 vs nền 24 (đúng 2×) → không; nền 23 → vàng; 7 vs 24 → vàng",
	[muc_all(HU(6, 24), K), muc_all(HU(6, 23), K), muc_all(HU(7, 24), K)], [{}, {K: "vang"}, {K: "vang"}])
eq("huy: nền 0 → 4 không (< 5), 5 vàng", [muc_all(HU(4, 0), K), muc_all(HU(5, 0), K)], [{}, {K: "vang"}])
eq("huy: ghi đè vàng 3 đỏ 5: 10 vs nền 16 (2/tuần) → vàng (10 > 6, ≤ 10); 11 → đỏ; 6 → không",
	[muc_all(HU(v, 16), K, {"vang": 3, "do": 5}) for v in (10, 11, 6)], [{K: "vang"}, {K: "do"}, {}])
eq("huy: không đặt đỏ → không bao giờ đỏ (100 vs nền 0)", muc_all(HU(100, 0), K), {K: "vang"})
_, sg, pk = mot(HU(9, 0, loai=False), K)
eq("huy: không theo_loai → lời không nêu loại", loi(sg[K], pk), "9 chứng từ bị huỷ trong 7 ngày qua | Trung bình 8 tuần "
	"trước là 0 chứng từ mỗi tuần; kế toán trưởng cần rà soát lý do huỷ.")
eq("huy: None / chuỗi / bool / tắt → không", [muc_all(HU(None, 1), K), muc_all(HU("9", 1), K), muc_all(HU(True, 0), K),
	muc_all(HU(9, 0), K, {"disabled": True})], [{}, {}, {}, {}])

# ct.ghi_lui — biên: lùi > 10 (ngặt).
K = "ct.ghi_lui"


def GL(pb, rows=None):
	return {T: {"chung_tu": {"so_ngay": 7, "ghi_lui": {"so": sum(n for _d, n in pb), "phan_bo": [{"so_ngay_lui": x,
		"so": n} for x, n in pb], "rows": rows if rows is not None else [{"doctype": "Journal Entry", "loai": "bút toán",
		"name": "JE-X", "so_ngay_lui": pb[0][0] if pb else 0}]}}}}


eq("ghi_lui: lùi 10 → không; 11 → vàng; [10 ×9] → không", [muc_all(GL([(10, 1)]), K), muc_all(GL([(11, 1)]), K),
	muc_all(GL([(10, 9)]), K)], [{}, {K: "vang"}, {}])
eq("ghi_lui: ghi đè vàng 15 đỏ 25: 20 → vàng, 26 → đỏ, 15 → không",
	[muc_all(GL([(v, 1)]), K, {"vang": 15, "do": 25}) for v in (20, 26, 15)], [{K: "vang"}, {K: "do"}, {}])
_, sg, pk = mot(GL([(30, 2), (12, 3), (10, 4), (2, 5)]), K)
eq("ghi_lui: đếm chỉ phần lùi > ngưỡng (2 + 3 = 5)", (sg[K].tinh, loi(sg[K], pk).split(" | ")[0]),
	({"so": 5, "nguong": 10}, "5 chứng từ mới tạo bị ghi lùi ngày quá 10 ngày"))
_, sg, pk = mot(GL([(30, 1)], rows=[]), K)
eq("ghi_lui: không dòng → lời chung, không documents", (sg[K].detail, sg[K].documents),
	("Kế toán cần kiểm tra lý do ghi sổ muộn và khoá sổ các kỳ đã chốt.", []))
eq("ghi_lui: phan_bo rác → không", [muc_all({T: {"chung_tu": {"ghi_lui": {"phan_bo": x}}}}, K) for x in (None, "x",
	[{"so_ngay_lui": "30", "so": 1}, {"so_ngay_lui": 30, "so": True}])], [{}, {}, {}])

# ct.but_toan_tay_lon — ngưỡng có dấu bằng; gói mang ngưỡng.
K = "ct.but_toan_tay_lon"


def BT(so, top, nguong=100_000_000):
	return {T: {"chung_tu": {"so_ngay": 7, "but_toan": {"nguong": nguong, "so": so, "gia_tri_tong": top * so,
		"rows": [{"doctype": "Journal Entry", "name": "JE-1", "gia_tri": top}] if so else []}}}}


eq("but_toan: 0 → không; 1 (100 triệu) → vàng", [muc_all(BT(0, 0), K), muc_all(BT(1, 100_000_000), K)], [{}, {K: "vang"}])
eq("but_toan: đỏ chỉ khi đặt (ngưỡng đỏ 250 tr có dấu bằng): 250 tr → đỏ, 249.999.999 → vàng; không đặt → vàng",
	[muc_all(BT(1, 250_000_000), K, {"do": 250_000_000}), muc_all(BT(1, 249_999_999), K, {"do": 250_000_000}),
	muc_all(BT(1, 9e12), K)], [{K: "do"}, {K: "vang"}, {K: "vang"}])
eq("but_toan: gói dựng theo ngưỡng khác ngưỡng đang áp → không chạy được (tín hiệu cũ giữ nguyên)",
	[muc_all(BT(1, 300_000_000, nguong=50_000_000), K), muc_all(BT(1, 300_000_000), K, {"vang": 200_000_000}),
	muc_all(BT(1, 300_000_000, nguong=200_000_000), K, {"vang": 200_000_000}), muc_all(BT(1, 1, nguong=None), K)],
	["KHONG-CHAY", "KHONG-CHAY", {K: "vang"}, "KHONG-CHAY"])
_, sg, pk = mot(BT(3, 120_000_000), K)
eq("but_toan: lời", loi(sg[K], pk), "3 bút toán nhập tay từ 100 triệu trở lên trong tuần qua | Tổng 360 triệu, lớn nhất "
	"120 triệu ở bút toán JE-1; kế toán trưởng cần đối chiếu chứng từ gốc.")

# gia.* — gói mang ngưỡng; mức theo dòng đầu.
for K, blk, f, top_k in (("gia.ban_lech", "ban_lech", "so_dong", "lech_pct"), ("gia.chiet_khau_cao", "chiet_khau",
		"so_dong", "ck_pct"), ("gia.mua_tang", "mua_tang", "so_ma", "tang_pct")):
	nguong = registry.RULES[K].vang

	def GP(so, top, ng=nguong, blk=blk, f=f, top_k=top_k):
		return {T: {"gia": {"so_ngay": 7, blk: {"nguong": ng, f: so, "so_ngay_nen": 90, "gia_tri": 1_000_000,
			"rows": [{"doctype": "Sales Invoice", "name": "SI-1", "item_name": "Bánh", "customer": KH, "rate": 1.0,
			"trung_vi": 2.0, "gia_cu": 1.0, "gia_moi": 2.0, top_k: top}] if so else []}}}}
	eq(f"{K}: 0 dòng → không; có dòng → vàng; đỏ chỉ khi đặt (> đỏ, ngặt)", [muc_all(GP(0, 0), K),
		muc_all(GP(1, nguong + 0.1), K), muc_all(GP(1, 99.0), K), muc_all(GP(1, 30.0), K, {"do": 30}),
		muc_all(GP(1, 30.1), K, {"do": 30})], [{}, {K: "vang"}, {K: "vang"}, {K: "vang"}, {K: "do"}])
	eq(f"{K}: ngưỡng gói ≠ ngưỡng áp → không chạy được", (muc_all(GP(1, 50, ng=nguong + 1), K),
		muc_all(GP(1, 50, ng=nguong + 1), K, {"vang": nguong + 1})), ("KHONG-CHAY", {K: "vang"}))
_, sg, pk = mot({T: {"gia": {"ban_lech": {"nguong": 15, "so_dong": 1, "rows": [{"doctype": "Sales Invoice",
	"name": "SI-1", "item_name": "Bánh", "lech_pct": 20.0}]}}}}, "gia.ban_lech")
eq("ban_lech: thiếu đơn giá / trung vị / khách → lời chung", loi(sg["gia.ban_lech"], pk),
	"1 dòng hàng bán thấp hơn giá trung vị quá 15,0% | Phòng kinh doanh cần kiểm tra giá đã duyệt cho các dòng này.")
_, sg, pk = mot({T: {"gia": {"mua_tang": {"nguong": 10, "so_ma": 1, "rows": [{"item_code": "X", "item_name": "Bột",
	"tang_pct": 12.0, "gia_cu": 1000.0, "gia_moi": 1120.0}]}}}}, "gia.mua_tang")
eq("mua_tang: không NCC → không nêu NCC, không documents", (loi(sg["gia.mua_tang"], pk), sg["gia.mua_tang"].documents),
	("1 mã hàng mua vào tăng giá quá 10,0% | Tăng nhiều nhất là Bột với 12,0%, giá bình quân từ 1.000 đ lên 1.120 đ mỗi "
	"đơn vị kho; phòng mua hàng cần đối chiếu báo giá.", []))

# ═══ D. Riêng tư, E5, AST ════════════════════════════════════════════════════
print("\nD. Riêng tư, lời (E5), AST")
dump = json.dumps(PACK, ensure_ascii=False, default=str)
eq("gói số: không owner / modified_by / tên người / diễn giải / tên nhân viên", [x for x in (NGUOI, "bimat",
	"Kế Toán Bí Mật", "Nguyễn Văn Bí Mật", "NV-BI-MAT", "Chi cho", "owner", "modified_by") if x in dump], [])
TEN_DT = {KH, KH2, NCC, NCC2}


def khoa_cua(obj, path=""):
	"""[(khoá, giá trị)] của mọi chuỗi trong obj."""
	if isinstance(obj, dict):
		return [x for k, v in obj.items() for x in (khoa_cua(v, k) if isinstance(v, (dict, list)) else [(k, v)])]
	if isinstance(obj, list):
		return [x for v in obj for x in khoa_cua(v, path)]
	return []


from bc.ai import redact  # noqa: E402

eq("tên khách / NCC chỉ nằm dưới khoá che được (PARTY_KEYS / SUPPLIER_KEYS)", sorted({k for k, v in khoa_cua(PACK)
	if v in TEN_DT and k not in redact.PARTY_KEYS | redact.SUPPLIER_KEYS}), [])
c("gói có tên khách và NCC (để phần che có việc)", {v for _k, v in khoa_cua(PACK)} >= TEN_DT,
	sorted(TEN_DT - {v for _k, v in khoa_cua(PACK)}))
MK = redact.build(True)
MK.begin()
che = json.dumps(MK.mask(PACK), ensure_ascii=False, default=str)
eq("sau mask: không còn tên khách / NCC nào", [x for x in TEN_DT if x in che], [])

c("có đủ ca để soát chung", len(MOI) > 30 and {s.rule for s, _ in MOI} == set(RULES),
	(len(MOI), sorted({s.rule for s, _ in MOI})))
bo_ph = lambda s: registry.PLACEHOLDER.sub(" ", (s.title or "") + " \n " + (s.detail or ""))  # noqa: E731
eq("lời (đã bỏ placeholder) không có chữ số", sorted({bo_ph(s) for s, _ in MOI if re.search(r"\d", bo_ph(s))}), [])
eq("lời / tinh không tên người, email, tên khách gõ tay", sorted({bo_ph(s) for s, _ in MOI if re.search(
	r"bimat|@|Bí Mật|Minh Phát", bo_ph(s))}), [])
eq("mọi lời dựng được trên gói của nó", sorted({f"{s.key}: {ai_testlib.kiem_loi(s, p)}" for s, p in MOI
	if ai_testlib.kiem_loi(s, p)}), [])


def e5(s, p):
	"""Lời quy tắc chép nguyên làm lời mô hình (kinds của chính tín hiệu, nguon = đề bài có gói đã che + lời quy tắc)."""
	m = MK
	m.begin()
	nguon = json.dumps({"pack": m.mask(p), "loi": s.title + " — " + s.detail}, ensure_ascii=False, default=str)
	m.restrict(nguon)
	out = render.render_insight({"title": s.title, "body": s.detail or s.title, "advice": []}, p, {s.section}, m,
		kinds=registry.kind_map([s]), nguon=nguon)
	render.forget_source()
	return out


eq("E5: mọi lời quy tắc (mọi ca của bộ thử) qua render_insight với kinds + nguon", sorted({f"{s.key}: {e5(s, p)['errors']}"
	for s, p in MOI if not e5(s, p)["ok"]}), [])
tu = lambda x: len(registry.PLACEHOLDER.sub("X", x).split())  # noqa: E731
eq("tiêu đề ≤ 12 từ, thân MỘT câu", sorted({s.title for s, _ in MOI if tu(s.title) > 12} | {s.detail for s, _ in MOI
	if not s.detail.endswith(".") or ". " in s.detail}), [])
eq("khai báo quy tắc", {k: (r.section, r.sources, r.vang, r.do, r.audience, r.route) for k, r in registry.RULES.items()
	if k in RULES}, {
	"ct.huy_nhieu": (T, (f"{T}.chung_tu.huy",), 2, None, "lanh-dao", ""),
	"ct.ghi_lui": (T, (f"{T}.chung_tu.ghi_lui",), 10, None, "lanh-dao", ""),
	"ct.but_toan_tay_lon": (T, (f"{T}.chung_tu.but_toan",), 100_000_000, None, "lanh-dao", ""),
	"gia.ban_lech": (T, (f"{T}.gia.ban_lech",), 15, None, "lanh-dao", ""),
	"gia.chiet_khau_cao": (T, (f"{T}.gia.chiet_khau",), 15, None, "lanh-dao", ""),
	"gia.mua_tang": (T, (f"{T}.gia.mua_tang",), 10, None, "lanh-dao", "")})
eq("detector đăng ký ở mảng tro-ly", {n: x.section for n, x in registry.DETECTORS.items()},
	{"chung_tu": T, "gia": T, "kpi": T})

CAM = re.compile(r"\b(INSERT|UPDATE|DELETE|ALTER|DROP|REPLACE|TRUNCATE|CREATE|GRANT)\b", re.I)
for f in ("chung_tu.py", "gia.py", "kpi.py"):
	src = open(os.path.join(BC_ROOT, "bc", "ai", "detectors", f), encoding="utf-8").read()
	tree = ast.parse(src)
	doc_ids = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef)) and n.body
		and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
	sql = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
		and id(n) not in doc_ids and re.search(r"\bSELECT\b|\bWHERE\b|\bFROM\b", n.value)]
	sql += [ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)
		and re.search(r"SELECT|WHERE", ast.unparse(n))]
	c(f"{f}: có chuỗi SQL để soát", len(sql) >= {"kpi.py": 1}.get(f, 4), len(sql))
	eq(f"{f}: chuỗi SQL chỉ SELECT", [s[:60] for s in sql if CAM.search(s)], [])
	eq(f"{f}: không NOW() / CURDATE() / SYSDATE / CURRENT_", [s[:60] for s in sql
		if re.search(r"NOW\(|CURDATE|SYSDATE|CURRENT_", s, re.I)], [])
	# tên hiển thị của khách / NCC (customer_name, supplier_name, party_name) ĐƯỢC đọc: nằm dưới khoá customer /
	# supplier nên được che như mọi màn; cấm là người tạo / sửa, tên người, chữ tự do
	eq(f"{f}: không đọc owner / modified_by / tên người / diễn giải", [s[:60] for s in sql if re.search(
		r"\b(owner|modified_by|user_remark|remarks|title|full_name|employee_name)\b", s)], [])
	eq(f"{f}: không gọi ghi DB", sorted({n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
		and n.attr in ("set_value", "delete", "insert", "commit", "save", "get_doc", "db_set", "set_single_value")}), [])
src = open(os.path.join(BC_ROOT, "bc", "ai", "rules", "ks.py"), encoding="utf-8").read()
tree = ast.parse(src)
eq("rules/ks.py thuần: không frappe / SQL / os", sorted({x.id for x in ast.walk(tree) if isinstance(x, ast.Name)
	and x.id in ("frappe", "os", "shutil")} | {x.attr for x in ast.walk(tree) if isinstance(x, ast.Attribute)
	and x.attr in ("sql", "db", "get_all", "get_value")} | {m for n in ast.walk(tree) if isinstance(n, (ast.Import,
	ast.ImportFrom)) for m in ([n.module or ""] if isinstance(n, ast.ImportFrom) else [a.name for a in n.names])
	if m.split(".")[0] in ("frappe", "os", "shutil", "requests")}), [])

# ═══ E. run_daily thật (mô hình giả) ═════════════════════════════════════════
print("\nE. run_daily thật: nhóm kiem-soat, quản trị / người xem, đề bài, E5 qua lượt chạy")
from bc.ai import collect, llm, pipeline, review  # noqa: E402
from bc.api import ai as api  # noqa: E402

bc_settings(ai_enabled=1, ai_mask_parties=1, ai_cap_claude_usd=90, ai_openai_model="", hidden_sections="")
child("BC Settings", "BC Settings", "BC AI Model Price", "ai_prices",
	[{"model": "claude-sonnet-5-5", "price_in": 3, "price_out": 15}])
frappe.conf["bc_ai_anthropic_key"] = KEY
frappe.cache().store.clear()
collect.build = lambda today: {}
GOI = []


def echo(provider, model, system, user, schema_name, schema, max_tokens=16000, timeout=300):
	obj = json.loads(user)
	GOI.append({"nhom": obj["nhom"], "user": user, "system": system, "obj": obj})
	out = []
	for t in obj["tin_hieu"]:
		tt, _, bd = t["loi_quy_tac"].partition(" — ")
		out.append({"signal": t["id"], "severity": t["muc"], "priority": 3, "title": tt, "body": bd or tt, "advice": []})
	return {"data": {"insights": out}, "tokens_in": 1000, "tokens_out": 100, "model": model}


llm.call = echo
review.run_group = lambda **kw: None
frappe.session.user = "viewer@example.com"
out = pipeline.run_daily()
eq("lượt chạy ok, 6 tín hiệu, mô hình nhận cả 6 lời quy tắc chép lại, loại 0 (E5)", (out.get("status"), out.get("signals"),
	out.get("accepted"), out.get("rejected")), ("ok", 6, 6, 0))
eq("chỉ nhóm kiem-soat được gọi", [g["nhom"] for g in GOI], ["kiem-soat"])
gks = GOI[0] if GOI else {"user": "", "system": "", "obj": {"pack": {}, "tin_hieu": []}}
eq("đề bài kiem-soat: đủ 6 tín hiệu", sorted(t["rule"] for t in gks["obj"]["tin_hieu"]), sorted(RULES))
c("đề bài kiem-soat: có khối chung_tu, gia (+ số tự tính _ai); KHÔNG khối kpi (NO_SEND)",
	sorted(k for k in gks["obj"]["pack"].get(T, {}) if k != "_ai") == ["chung_tu", "gia"], sorted(gks["obj"]["pack"].get(T, {})))
toan = gks["user"] + gks["system"]
eq("đề bài: không tên khách / NCC, không email / tên người / tên nhân viên, không khoá", [x for x in (*TEN_DT, NGUOI,
	"bimat", "Bí Mật", "NV-BI-MAT", KEY) if x in toan], [])
c("đề bài: tên đối tác đã thành mã giả KH# / NCC#", "KH#" in gks["user"] and "NCC#" in gks["user"])
ROW = {r.rule: r for r in frappe.db.sql("SELECT * FROM `tabBC AI Insight` WHERE rule IN %(r)s", {"r": RULES},
	as_dict=True)}
eq("Insight: mảng tro-ly, nhóm-lọc tro-ly, route rỗng, nguồn AI (lời chép lại hợp lệ)", {(r.section, r.sections_used,
	r.route, r.source, r.audience) for r in ROW.values()}, {(T, T, "", "ai", "lanh-dao")})
c("Insight lưu tên thật (đã hoàn nguyên mã giả)", KH in (ROW.get("gia.ban_lech") or {}).get("body", "")
	and NCC in (ROW.get("gia.mua_tang") or {}).get("body", ""), [(r.rule, r.body) for r in ROW.values()])

frappe.session.user = "Administrator"
fa = {x["signal_key"]: x for x in api.get_feed()["insights"]}
eq("get_feed quản trị: 6 tín hiệu nhóm kiem-soat (Kiểm soát), documents có chứng từ", {k: (x["group"], x["group_label"],
	bool(x["documents"])) for k, x in fa.items() if k in RULES}, {k: ("kiem-soat", "Kiểm soát", True) for k in RULES})
eq("documents của ct.but_toan_tay_lon (quản trị)", fa.get("ct.but_toan_tay_lon", {}).get("documents"),
	[{"doctype": "Journal Entry", "name": "JE-T250"}, {"doctype": "Journal Entry", "name": "JE-T100"}])
frappe.session.user = "viewer@example.com"
fv = {x["id"]: x for x in api.get_feed()["insights"]}
eq("get_feed người xem: thấy đủ 6 ở nhóm kiem-soat, KHÔNG documents / trường quản trị",
	sorted((x["group"], "documents" in x, "signal_key" in x, "review_note" in x) for x in fv.values()),
	[("kiem-soat", False, False, False)] * 6)
c("người xem thấy đúng các Insight đó", set(fv) == {r.name for r in ROW.values()})
single("BC Settings", hidden_sections="tro-ly")
try:
	api.get_feed()
	chan = False
except frappe.PermissionError:
	chan = True
c("ẩn mảng tro-ly: người xem bị chặn khỏi get_feed", chan)
frappe.session.user = "Administrator"
eq("ẩn mảng tro-ly: quản trị vẫn thấy đủ", len([x for x in api.get_feed()["insights"] if x["rule"] in RULES]), 6)
single("BC Settings", hidden_sections="")

c.done()
