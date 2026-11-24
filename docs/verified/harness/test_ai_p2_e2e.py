"""Trợ lý AI P2 — ĐẦU-CUỐI trên một DB: lượt ngày (người viết Claude + phản biện OpenAI) → bản tin tuần / tháng →
bc.api.ai.get_feed (người xem / quản trị, có và không mảng ẩn); rồi AI tắt + không khoá.

Mọi module THẬT: collect (bc.api.* trên seed gộp seed_ui2), registry + mọi quy tắc / detector (hệ thống, kiểm soát
chung_tu / gia, kpi), store, render, redact, budget, prompt, review, brief, bc.api.ai. Chỉ thay CỬA MẠNG
bc.ai.llm.call (mô hình giả cho CẢ claude và openai; has_key / LLMError / clean vẫn thật). Socket ra ngoài bị chặn.

Seed thêm (hôm nay giả 27/10/2026, cửa sổ kiểm soát [21/10, 27/10]):
- 5 hoá đơn bán huỷ trong cửa sổ (nền 8 tuần 0) → ct.huy_nhieu; bút toán tay ghi lùi 26 ngày → ct.ghi_lui; bút toán tay
  250 triệu → ct.but_toan_tay_lon; dòng bán E2E-BDX 70.000 so trung vị nền 100.000 (lệch 30%) → gia.ban_lech; dòng
  chiết khấu 20% → gia.chiet_khau_cao; mua E2E-DUONG 23.000 / kg so 20.000 (tăng 15%, 23 triệu) → gia.mua_tang.
  Khách / NCC của các chứng từ này có tên riêng; người lập là một User có tên — không tên nào được rời máy chủ.
- 60 ngày ảnh chụp KPI (dòng tổng BC AI Run) = ảnh chụp hôm nay, trừ hai KPI: cong-no.receivables.kpis.receivable và
  nhan-su.overview.nhan_su.dang_lam — tháng 8 = 0,4 × hôm nay, 1/9 → 18/10 = 0,5 ×, 19/10 → 26/10 = 1 × (dang_lam:
  hôm nay − 20 / − 10 / hôm nay). Trung vị 28 ngày (29/9 → 26/10: 20 ngày 0,5 × + 8 ngày 1 ×) = 0,5 × → hôm nay lệch
  0,5 × > 3 × max(MAD 0, 1% trung vị) → kpi.lech_chuan cho cả hai, mỗi tín hiệu ở mảng của KPI.

Soát MỌI đề bài của MỌI nhà cung cấp (người viết, phản biện, bản tin): không tên khách / NCC / chuỗi MT, không tên
người / email, không khoá; lượt có mảng ẩn: không số của mảng đó; không gì của đề bài nằm trong bảng nào.

Chạy: BC_TEST_DB=bc_test_ai_p2e python3 -B test_ai_p2_e2e.py
"""
import datetime
import json
import re
import socket

from seed import Check, child, insert, single
from paths import DB

import frappe  # noqa: E402  (giả)

c = Check()
D, d = datetime.datetime, datetime.date
INSIGHT, RUN, BRIEF = "BC AI Insight", "BC AI Run", "BC AI Brief"
KEY = "sk-ant-api03-KHOAGIA-p2e2e-Zq81LmVw"
OKEY = "sk-proj-KHOAGIA-p2e2e-Openai_5c3d"
OPENAI_MODEL = "gpt-6.2-astra"
TODAY = d(2026, 10, 27)
KH_TEN, KH_ID = "Công ty Tân Phát Lộc", "KH-TAN-PHAT"
NCC_TEN, NCC_ID = "Nhà cung cấp Hoà Bình Xanh", "NCC-HOA-BINH"
NGUOI, NGUOI_TEN = "ke.toan.e2e@hgc.vn", "Trần Thị Kế Toán"
KPI_A, KPI_B = "cong-no.receivables.kpis.receivable", "nhan-su.overview.nhan_su.dang_lam"
AN = "cong-no"     # mảng ẩn ở lượt thứ hai


def eq(label, got, want):
	c(label, got == want, f"\n      được: {got!r}\n      cần : {want!r}")


# ═══════════════════════════════════════════════════════════════════════════
print("A. Dựng: seed gộp + chứng từ kiểm soát + lịch sử KPI; chặn mạng; mô hình giả hai nhà cung cấp")
import seed_ui2  # noqa: E402,F401  (reset + seed SX, công nợ, ATTP, vận chuyển, nhân sự, bán hàng)

frappe.db.sql("UPDATE `tabCustomer` SET customer_name = 'Đại lý Minh Phát' WHERE name = 'NPP-A'")
insert("Customer", name=KH_ID, customer_name=KH_TEN, customer_group="NPP")
insert("Supplier", name=NCC_ID, supplier_name=NCC_TEN)
insert("User", name=NGUOI, enabled=1, first_name="Trần Thị", last_name="Kế Toán", full_name=NGUOI_TEN)
AI = {"owner": NGUOI, "modified_by": NGUOI}


def doc(doctype, name, *, docstatus=1, creation=None, modified=None, **f):
	creation = creation or D.combine(f.get("posting_date", TODAY), datetime.time(9))
	return insert(doctype, name=name, docstatus=docstatus, creation=creation, modified=modified or creation, **AI, **f)


for i in range(5):    # huỷ trong cửa sổ — nền 8 tuần không có chứng từ huỷ nào → trung bình 0 → báo khi ≥ 5
	doc("Sales Invoice", f"E2E-HUY-{i}", docstatus=2, posting_date=d(2026, 10, 22), customer=KH_ID, customer_group="NPP",
		base_grand_total=3_100_000 + i, is_opening="No", modified=D(2026, 10, 23 + i % 4, 10))
doc("Journal Entry", "E2E-JE-LUI", posting_date=d(2026, 10, 1), creation=D(2026, 10, 27, 8), total_debit=7_000_000,
	voucher_type="Journal Entry", is_opening="No", is_system_generated=0, user_remark=f"Chi cho {NGUOI_TEN}")
doc("Journal Entry", "E2E-JE-LON", posting_date=d(2026, 10, 24), total_debit=250_000_000, voucher_type="Journal Entry",
	is_opening="No", is_system_generated=0, user_remark=f"Tạm ứng {NGUOI_TEN}", title=NGUOI_TEN)
_n = iter(range(1, 100))


def ban(ngay, rate, ck=0):
	n = f"E2E-SI-{next(_n):02d}"
	doc("Sales Invoice", n, posting_date=ngay, customer=KH_ID, customer_group="NPP", is_return=0, is_opening="No",
		base_grand_total=0)
	insert("Sales Invoice Item", parent=n, parenttype="Sales Invoice", parentfield="items", idx=1, item_code="E2E-BDX",
		item_name="Bánh đậu xanh E2E", net_rate=rate, base_net_rate=rate, conversion_factor=1, discount_percentage=ck,
		qty=1, net_amount=rate, base_net_amount=rate, **AI)
	return n


for ngay in (d(2026, 8, 1), d(2026, 8, 20), d(2026, 9, 5), d(2026, 9, 25), d(2026, 10, 10)):
	ban(ngay, 100_000)               # nền 90 ngày: 5 dòng, trung vị 100.000
SI_LECH = ban(d(2026, 10, 25), 70_000)          # lệch 30%
SI_CK = ban(d(2026, 10, 26), 100_000, ck=20)    # chiết khấu 20%


def mua(ngay, sl, tien):
	n = f"E2E-PI-{next(_n):02d}"
	doc("Purchase Invoice", n, posting_date=ngay, supplier=NCC_ID, is_return=0, is_opening="No", base_grand_total=tien)
	insert("Purchase Invoice Item", parent=n, parenttype="Purchase Invoice", parentfield="items", idx=1,
		item_code="E2E-DUONG", item_name="Đường E2E", stock_qty=sl, qty=sl, conversion_factor=1, base_net_amount=tien, **AI)


mua(d(2026, 10, 15), 1000, 23_000_000)          # 30 ngày gần nhất: 23.000 / kg, 23 triệu ≥ 20 triệu
mua(d(2026, 8, 15), 1000, 20_000_000)           # 90 ngày trước đó: 20.000 / kg → tăng 15% > 10

frappe.session.user = "viewer@example.com"

MANG = []


class MangBiChan(RuntimeError):
	pass


def _chan(fn):
	def g(self, addr, *a, **k):
		if self.family in (socket.AF_INET, socket.AF_INET6):
			MANG.append(addr)
			raise MangBiChan(f"bộ thử chặn mạng: {addr}")
		return fn(self, addr, *a, **k)
	return g


def _dns(*a, **k):
	MANG.append(a[:2])
	raise MangBiChan("bộ thử chặn DNS")


socket.socket.connect, socket.socket.connect_ex = _chan(socket.socket.connect), _chan(socket.socket.connect_ex)
socket.getaddrinfo = socket.create_connection = _dns

single("BC Settings", ai_enabled=1, ai_mask_parties=1, ai_cap_claude_usd=90, ai_cap_openai_usd=90,
	ai_openai_model=OPENAI_MODEL, ai_claude_model_deep="claude-opus-5-5", hidden_sections="")
child("BC Settings", "BC Settings", "BC AI Model Price", "ai_prices", [
	{"model": "claude-sonnet-5-5", "price_in": 3, "price_out": 15},
	{"model": "claude-opus-5-5", "price_in": 4, "price_out": 20},
	{"model": OPENAI_MODEL, "price_in": 1.25, "price_out": 10}])
# ht.dia_day đọc ổ đĩa THẬT của máy chạy thử → tắt cho kết quả ổn định
child("BC Settings", "BC Settings", "BC AI Rule", "ai_rules", [{"rule_key": "ht.dia_day", "disabled": 1}])
frappe.conf["bc_ai_anthropic_key"] = KEY
frappe.conf["bc_ai_openai_key"] = OKEY

from bc.ai import brief, collect, llm, pipeline, registry, store  # noqa: E402
from bc.api import ai as api  # noqa: E402

# Lịch sử KPI: ảnh chụp hôm nay (collect thật) cho 60 ngày trước, hai KPI theo bậc thang (docstring).
PACK_NAY = collect.build(TODAY)
SNAP = registry.snapshot_kpis(PACK_NAY)
c("ảnh chụp hôm nay có hai KPI dùng làm lệch chuẩn (khác 0, đủ lớn)", SNAP.get(KPI_A, 0) >= 10_000_000
	and SNAP.get(KPI_B, 0) >= 20, {k: SNAP.get(k) for k in (KPI_A, KPI_B)})
c("hai KPI không thuộc nhóm bỏ qua (cộng dồn / theo kỳ)", not any(__import__("bc.ai.detectors.kpi", fromlist=["x"])
	.bo_qua(p) for p in (KPI_A, KPI_B)))
A0, B0 = SNAP[KPI_A], SNAP[KPI_B]
KPI_CD = "tong-quan.summary.rows[0].sales"     # cộng dồn năm tài chính (KPI_TICH_LUY) → kpi.lech_chuan bỏ qua
c("KPI cộng dồn dùng để soát có giá trị hôm nay", (SNAP.get(KPI_CD) or 0) > 0, SNAP.get(KPI_CD))
for i in range(1, 61):
	ngay = TODAY - datetime.timedelta(days=i)
	s = dict(SNAP)
	s[KPI_CD] = round(SNAP[KPI_CD] * 0.5)      # luỹ kế: nửa giá trị hôm nay suốt lịch sử — vẫn KHÔNG được báo
	if ngay < d(2026, 9, 1):
		s[KPI_A], s[KPI_B] = round(A0 * 0.4), B0 - 20
	elif ngay < d(2026, 10, 19):
		s[KPI_A], s[KPI_B] = round(A0 * 0.5), B0 - 10
	insert(RUN, run_type="ngay", step="tong", status="ok", started=D.combine(ngay, datetime.time(5, 30)),
		finished=D.combine(ngay, datetime.time(5, 40)), kpis=json.dumps(s))

# Mô hình giả: chép mọi đề bài (theo nhà cung cấp / loại).
GOI = []      # {provider, kind: viet | phan_bien | ban_tin, system, user, obj, model}
DEM = {"claude": 0, "openai": 0}


def viet(obj):
	"""Người viết: chép lời quy tắc làm lời của mình (E5 — lời quy tắc phải qua được bộ soát)."""
	out = []
	for t in obj["tin_hieu"]:
		tt, _, bd = t["loi_quy_tac"].partition(" — ")
		out.append({"signal": t["id"], "severity": t["muc"], "priority": 3, "title": tt, "body": bd or tt,
			"advice": ["Bộ phận phụ trách rà soát trong tuần này."]})
	return {"insights": out}


def phan_bien(obj):
	"""Phản biện: nhận định đầu nghi-ngo (note không số), còn lại dong-y."""
	return {"reviews": [{"id": n["id"], "verdict": "nghi-ngo" if i == 0 else "dong-y",
		"note": "Cần kiểm tra thêm nguồn gốc con số này." if i == 0 else ""} for i, n in enumerate(obj["nhan_dinh"])]}


def ban_tin(obj):
	"""Bản tin: một mục / phần, số chỉ qua placeholder của gói bản tin."""
	gt = [(p, k) for p, k in sorted(obj["kieu"].items()) if p.endswith(".gia_tri")]
	nd = obj["nhan_dinh"]
	return {"title": "Kỳ qua có vài chỉ số cần theo dõi",
		"dang_chu_y": [f"Giá trị cuối kỳ là {{{{{p}|{k}}}}}, cần theo dõi thêm." for p, k in gt[:2]],
		"viec_ton": ["Còn việc tồn cần xử lý sớm."] if nd else [],
		"uu_tien": ["Phòng Kế toán rà soát công nợ quá hạn."]}


def fake_call(provider, model, system, user, schema_name, schema, max_tokens=16000, timeout=300):
	obj = json.loads(user)
	DEM[provider] += 1
	kind = {"ghi_nhan_dinh": "viet", "phan_bien": "phan_bien", "ban_tin": "ban_tin"}[schema_name]
	GOI.append({"provider": provider, "kind": kind, "system": system, "user": user, "obj": obj, "model": model})
	data = {"viet": viet, "phan_bien": phan_bien, "ban_tin": ban_tin}[kind](obj)
	served = {"claude": model, "openai": OPENAI_MODEL + "-2026-09-30"}[provider]
	return {"data": data, "tokens_in": 1000, "tokens_out": 100, "model": served}


llm.call = fake_call


def R(key):
	r = frappe.db.sql(f"SELECT * FROM `tab{INSIGHT}` WHERE BINARY signal_key = %s", (key,), as_dict=True)
	return r[0] if r else None


def as_user(u, fn):
	cu = frappe.session.user
	frappe.session.user = u
	try:
		return fn()
	finally:
		frappe.session.user = cu


# Danh sách cấm trong mọi đề bài
TEN_DOI_TAC = sorted({x for r in frappe.db.sql("SELECT name, customer_name FROM `tabCustomer`") for x in r if x}
	| {x for r in frappe.db.sql("SELECT name, supplier_name FROM `tabSupplier`") for x in r if x}
	| {x for (x,) in frappe.db.sql("SELECT DISTINCT custom_mt_chain FROM `tabCustomer`") if x})
TEN_DOI_TAC = [x for x in TEN_DOI_TAC if len(x) >= 5]
NGUOI_DS = sorted({x for r in frappe.db.sql("""SELECT name, first_name, last_name, full_name FROM `tabUser`
	WHERE name NOT IN ('Administrator', 'Guest')""") for x in r if x and len(x) >= 5}
	| {x for r in frappe.db.sql("SELECT employee_name, first_name FROM `tabEmployee`") for x in r if x and len(x) >= 5})
c("có tên đối tác / tên người để soát (luật không rỗng nghĩa)", KH_TEN in TEN_DOI_TAC and NCC_TEN in TEN_DOI_TAC
	and "Saigon Co.op" in TEN_DOI_TAC and NGUOI_TEN in NGUOI_DS and len(NGUOI_DS) >= 4, (len(TEN_DOI_TAC), NGUOI_DS[:6]))


def lo(goi, ds):
	return sorted({x for g in goi for x in ds if x in g["user"] or x in g["system"]})


def so_cua_mang(pack, mang):
	"""Số 'đặc trưng' của một mảng: lá số |v| ≥ 10 (dạng JSON) không xuất hiện ở mảng nào khác của gói."""
	def la(v, out):
		if isinstance(v, dict):
			for x in v.values():
				la(x, out)
		elif isinstance(v, (list, tuple)):
			for x in v:
				la(x, out)
		elif isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) >= 10:
			out.add(json.dumps(v))
		return out
	cua = la(pack.get(mang), set())
	khac = set()
	for k, v in pack.items():
		if k != mang:
			la(v, khac)
	return cua - khac


# ═══════════════════════════════════════════════════════════════════════════
print("B. Lượt ngày: AI bật, có khoá Claude + OpenAI, không mảng ẩn")
out = pipeline.run_daily()
eq("lượt chạy ok, bước AI ok", (out.get("status"), out.get("ai")), ("ok", "ok"))
c("không mạng", not MANG, MANG)
KS = ("ct.huy_nhieu", "ct.ghi_lui", "ct.but_toan_tay_lon", "gia.ban_lech", "gia.chiet_khau_cao", "gia.mua_tang")
ks = {k: R(k) for k in KS}
eq("6 tín hiệu kiểm soát mở, mảng tro-ly, nhóm-lọc lãnh đạo, route rỗng",
	{k: (r.status, r.section, r.audience, r.route) if r else None for k, r in ks.items()},
	{k: ("mo", "tro-ly", "lanh-dao", "") for k in KS})
la_a, la_b = R(f"kpi.lech_chuan:{KPI_A}"), R(f"kpi.lech_chuan:{KPI_B}")
eq("kpi.lech_chuan: hai tín hiệu, mỗi cái ở mảng của KPI (cong-no / nhan-su)",
	[(r.section, r.status) if r else None for r in (la_a, la_b)], [("cong-no", "mo"), ("nhan-su", "mo")])
eq("không KPI nào khác lệch chuẩn (lịch sử phẳng)", sorted(r[0] for r in frappe.db.sql(
	f"SELECT signal_key FROM `tab{INSIGHT}` WHERE rule = 'kpi.lech_chuan'")),
	sorted([f"kpi.lech_chuan:{KPI_A}", f"kpi.lech_chuan:{KPI_B}"]))
VIET1 = [g for g in GOI if g["kind"] == "viet"]
PB1 = [g for g in GOI if g["kind"] == "phan_bien"]
nhom = [g["obj"]["nhom"] for g in VIET1]
c("người viết được gọi cho kiem-soat, tai-chinh (có lệch chuẩn công nợ) và nhan-su", {"kiem-soat", "tai-chinh"} <= set(nhom)
	and any("nhan-su" in g["obj"]["pack"] for g in VIET1), nhom)
eq("phản biện: đúng một lượt / nhóm người viết có lời AI, cùng thứ tự", [g["obj"]["nhom"] for g in PB1],
	[g["obj"]["nhom"] for g in VIET1 if any(t for t in g["obj"]["tin_hieu"])])
c("đề bài kiem-soat: khối chung_tu + gia, KHÔNG khối kpi (NO_SEND)", next((sorted(k for k in g["obj"]["pack"]["tro-ly"]
	if k != "_ai") for g in VIET1 if g["obj"]["nhom"] == "kiem-soat"), None) == ["chung_tu", "gia"])
c("lời AI đã lưu cho cả 6 tín hiệu kiểm soát và 2 tín hiệu lệch chuẩn (lời quy tắc chép lại qua được soát)",
	all(R(k).source == "ai" for k in (*KS, f"kpi.lech_chuan:{KPI_A}", f"kpi.lech_chuan:{KPI_B}")),
	{k: R(k).source for k in (*KS, f"kpi.lech_chuan:{KPI_A}")})
_loi = (ks["gia.ban_lech"].body or "") + (ks["gia.ban_lech"].title or "") + (ks["gia.chiet_khau_cao"].body or "")
# dòng của detector mang mã khách (customer của chứng từ) — mã cũng là định danh thật, mô hình chỉ thấy mã giả
c("lời lưu có định danh thật của khách (mã giả đã hoàn nguyên), không mã giả", (KH_ID in _loi or KH_TEN in _loi)
	and not frappe.db.sql(
	f"SELECT name FROM `tab{INSIGHT}` WHERE CONCAT(IFNULL(title,''), IFNULL(body,''), IFNULL(advice,'')) REGEXP "
	"'KH#[0-9]|NCC#[0-9]'"), (ks["gia.ban_lech"].title, ks["gia.ban_lech"].body))
co_vd = frappe.db.sql(f"SELECT signal_key, review_verdict, review_note FROM `tab{INSIGHT}` WHERE IFNULL(review_verdict, '') "
	"!= ''", as_dict=True)
c("phản biện đã ghi verdict (≥ 1 nghi-ngo có note, còn lại dong-y)", any(r.review_verdict == "nghi-ngo"
	and r.review_note == "Cần kiểm tra thêm nguồn gốc con số này." for r in co_vd) and any(r.review_verdict == "dong-y"
	for r in co_vd), co_vd)
rv = frappe.db.sql(f"SELECT step, provider, status, run_id FROM `tab{RUN}` WHERE step LIKE 'review:%%'", as_dict=True)
eq("dòng Run phản biện: một / nhóm, openai, ok, run_id = dòng tổng", sorted((r.step, r.provider, r.status, r.run_id)
	for r in rv), sorted((f"review:{g['obj']['nhom']}", "openai", "ok", out["run"]) for g in PB1))
c("phản biện nhận NGUYÊN gói người viết (pack + kieu cùng nhóm)", all(any(p["obj"]["du_lieu"]["pack"] == v["obj"]["pack"]
	for v in VIET1 if v["obj"]["nhom"] == p["obj"]["nhom"]) for p in PB1) and PB1)

# ═══════════════════════════════════════════════════════════════════════════
print("C. Bản tin tuần / tháng (AI) — nhận định của kỳ")
# Đưa vài nhận định về quá khứ để kỳ có việc "tồn" và "mới": ct.* mở từ 10/10 (tồn ≥ 7 ngày), lệch chuẩn từ 20/10.
frappe.db.sql(f"UPDATE `tab{INSIGHT}` SET first_seen = '2026-10-10 05:30:00' WHERE rule LIKE 'ct.%%'")
frappe.db.sql(f"UPDATE `tab{INSIGHT}` SET first_seen = '2026-10-20 05:30:00' WHERE rule = 'kpi.lech_chuan'")
# Lớp chặn thứ hai: quy tắc hiện có chỉ đặt tên khách trong THÂN lời; một tiêu đề có tên (quy tắc sau này) vẫn phải được
# che trước khi vào đề bài bản tin (mask_text).
frappe.db.sql(f"UPDATE `tab{INSIGHT}` SET rule_title = %s, first_seen = '2026-10-21 05:30:00' WHERE signal_key = 'gia.ban_lech'", (f"Bán thấp giá cho {KH_TEN}",))
GOI.clear()
bt = brief.run_brief("tuan")
bm = brief.run_brief("thang")
eq("run_brief tuần / tháng: ok, nguồn ai", [(b["status"], b["source"], b["ai"]) for b in (bt, bm)],
	[("ok", "ai", "ok"), ("ok", "ai", "ok")])
BT1 = [g for g in GOI if g["kind"] == "ban_tin"]
eq("hai lượt gọi claude (model deep), schema ban_tin", [(g["provider"], g["model"], g["obj"]["loai"]) for g in BT1],
	[("claude", "claude-opus-5-5", "tuan"), ("claude", "claude-opus-5-5", "thang")])
tuan_pack = BT1[0]["obj"]["pack"] if BT1 else {}
c("gói tuần có KPI công nợ với phép so tuần trước (lịch sử nạp tay) — số do Python tính sẵn",
	"d_tuan_pct" in json.dumps(tuan_pack) and AN in tuan_pack, sorted(tuan_pack))
c("tiêu đề có tên khách đã thành mã giả trong đề bài bản tin", BT1 and any(n["tieu_de"].startswith("Bán thấp giá cho KH#")
	for n in BT1[0]["obj"]["nhan_dinh"]), BT1 and [n["tieu_de"] for n in BT1[0]["obj"]["nhan_dinh"]])
c("nhận định của kỳ gửi bản tin: chỉ id / mức / tình trạng / số ngày / mảng / tiêu đề", BT1 and BT1[0]["obj"]["nhan_dinh"]
	and all(sorted(n) == ["id", "mang", "muc", "so_ngay", "tieu_de", "tinh_trang"] for n in BT1[0]["obj"]["nhan_dinh"]))
B_T = frappe.db.sql(f"SELECT * FROM `tab{BRIEF}` WHERE brief_type = 'tuan'", as_dict=True)
B_M = frappe.db.sql(f"SELECT * FROM `tab{BRIEF}` WHERE brief_type = 'thang'", as_dict=True)
eq("BC AI Brief tuần 26/10 (kỳ 19/10 → 25/10) + tháng 1/10 (kỳ tháng 9), nguồn ai, model deep",
	[(str(b.brief_date), str(b.period_from), str(b.period_to), b.source, b.model) for b in (*B_T, *B_M)],
	[("2026-10-26", "2026-10-19", "2026-10-25", "ai", "claude-opus-5-5"),
		("2026-10-01", "2026-09-01", "2026-09-30", "ai", "claude-opus-5-5")])
for b, g in zip((*B_T, *B_M), BT1):
	thay = set(g["obj"]["pack"]) | {n["mang"] for n in g["obj"]["nhan_dinh"]}
	eq(f"bản tin {b.brief_type}: mỗi mục AI mang MỌI mảng mô hình đã thấy (gói ∪ mảng của nhận định đã gửi)",
		{frozenset(it["sections"]) for p in json.loads(b.body)["parts"] for it in p["items"]}, {frozenset(thay)})
c("dòng Run ban-tin:tuan / ban-tin:thang, không dòng tổng mới", sorted(r[0] for r in frappe.db.sql(
	f"SELECT step FROM `tab{RUN}` WHERE step LIKE 'ban-tin:%%'")) == ["ban-tin:thang", "ban-tin:tuan"])

# ═══════════════════════════════════════════════════════════════════════════
print("D. get_feed — người xem / quản trị, không mảng ẩn")
fa = as_user("Administrator", api.get_feed)
fv = as_user("viewer@example.com", api.get_feed)
eq("bản tin: cả hai vai thấy tuần + tháng, nguồn ai", ([(b["type"], b["source"]) for b in fv["briefs"]],
	[(b["type"], b["source"]) for b in fa["briefs"]]), ([("tuan", "ai"), ("thang", "ai")], [("tuan", "ai"), ("thang", "ai")]))
c("người xem: bản tin không model / sections; quản trị có model", all("model" not in b and "sections_used" not in b
	for b in fv["briefs"]) and all(b.get("model") == "claude-opus-5-5" for b in fa["briefs"]))
eq("số mục người xem = số mục lưu (không mảng nào ẩn)", [sum(len(p["items"]) for p in b["parts"]) for b in fv["briefs"]],
	[sum(len(p["items"]) for p in json.loads(b.body)["parts"]) for b in (*B_T, *B_M)])
vks = [x for x in fv["insights"] if x["group"] == "kiem-soat"]
eq("người xem: 6 nhận định nhóm Kiểm soát, không chứng từ / ghi chú phản biện", sorted((x["group_label"], "documents" in x,
	"review_note" in x) for x in vks), [("Kiểm soát", False, False)] * 6)
aks = {x["signal_key"]: x for x in fa["insights"] if x["group"] == "kiem-soat"}
c("quản trị: chứng từ của từng tín hiệu kiểm soát (≤ 20)", all(aks.get(k, {}).get("documents") for k in KS)
	and {"doctype": "Journal Entry", "name": "E2E-JE-LON"} in aks["ct.but_toan_tay_lon"]["documents"],
	{k: aks.get(k, {}).get("documents") for k in KS})
c("quản trị thấy review_note; người xem chỉ thấy verdict", any(x.get("review_note") for x in fa["insights"])
	and any(x.get("review_verdict") == "nghi-ngo" for x in fv["insights"]))
c("chuỗi trả về: không khoá, không mã giả", not any(s in json.dumps([fa, fv], ensure_ascii=False, default=str)
	for s in (KEY, OKEY, "KH#0", "NCC#0")))

# ═══════════════════════════════════════════════════════════════════════════
print(f"E. Ẩn mảng {AN}: người xem mất lời dùng số của mảng đó (cả bản tin AI cũ); quản trị vẫn đủ")
single("BC Settings", hidden_sections=AN)
fv2 = as_user("viewer@example.com", api.get_feed)
fa2 = as_user("Administrator", api.get_feed)
secs = {r.name: set(filter(None, (r.sections_used or "").splitlines())) | {r.section} for r in frappe.db.sql(
	f"SELECT name, section, sections_used FROM `tab{INSIGHT}`", as_dict=True)}
c("người xem: không nhận định nào có mảng ẩn trong sections_used", fv2["insights"] and not [x["id"] for x in fv2["insights"]
	if AN in secs.get(x["id"], set())])
c("người xem: lệch chuẩn công nợ biến mất, lệch chuẩn nhân sự còn", la_a.name not in {x["id"] for x in fv2["insights"]}
	and la_b.name in {x["id"] for x in fv2["insights"]})
eq("người xem: bản tin AI cũ (mô hình đã thấy mảng công nợ) không còn mục nào → vắng", fv2["briefs"], [])
eq("quản trị vẫn thấy hai bản tin + lệch chuẩn công nợ", ([b["type"] for b in fa2["briefs"]],
	la_a.name in {x["id"] for x in fa2["insights"]}), (["tuan", "thang"], True))

print(f"F. Lượt ngày + bản tin lần hai khi {AN} đang ẩn")
GOI.clear()
out2 = pipeline.run_daily()
bt2, bm2 = brief.run_brief("tuan"), brief.run_brief("thang")
eq("lượt chạy + hai bản tin ok, nguồn ai", (out2["status"], out2["ai"], bt2["source"], bm2["source"]), ("ok", "ok", "ai", "ai"))
GOI2 = list(GOI)
SO_AN = so_cua_mang(PACK_NAY, AN)    # gói dựng lúc chưa ẩn (collect chạy dưới người gọi: mảng ẩn → _error)
c("có số đặc trưng của mảng ẩn để soát (luật không rỗng nghĩa)", len(SO_AN) >= 3, sorted(SO_AN)[:5])
c("đối chứng: lượt B / C (mảng chưa ẩn) CÓ gửi số đặc trưng của mảng đó (cách dò bắt được)", any(re.search(
	r"[:,\[]" + re.escape(s) + r"[,}\]]", g["user"]) for g in VIET1 + BT1 for s in SO_AN))
eq("không đề bài nào (viết / phản biện / bản tin) chứa số đặc trưng của mảng ẩn",
	sorted({s for g in GOI2 for s in SO_AN if re.search(r"[:,\[]" + re.escape(s) + r"[,}\]]", g["user"])}), [])
eq("không đề bài nào chứa khoá / path của mảng ẩn", [g["kind"] for g in GOI2 if f'"{AN}"' in g["user"]
	or f"{AN}." in g["user"]], [])
c("lần hai có đủ ba loại đề bài", {g["kind"] for g in GOI2} == {"viet", "phan_bien", "ban_tin"}, {g["kind"] for g in GOI2})
fv3 = as_user("viewer@example.com", api.get_feed)
eq("người xem thấy lại bản tin (viết không có mảng ẩn)", [b["type"] for b in fv3["briefs"]], ["tuan", "thang"])
single("BC Settings", hidden_sections="")

# ═══════════════════════════════════════════════════════════════════════════
print("G. Riêng tư trên MỌI đề bài của MỌI nhà cung cấp (lượt B, C, F)")
TAT_CA = VIET1 + PB1 + BT1 + GOI2
eq("số lượt gọi: claude (viết + bản tin) và openai (phản biện) đều có", sorted({g["provider"] for g in TAT_CA}),
	["claude", "openai"])
eq("không tên khách / NCC / chuỗi MT", lo(TAT_CA, TEN_DOI_TAC), [])
eq("không tên người / email / nhân viên", lo(TAT_CA, NGUOI_DS), [])
eq("không khoá", lo(TAT_CA, [KEY, OKEY, "sk-ant", "sk-proj"]), [])
c("tên đối tác của chứng từ kiểm soát đã thành mã giả trong đề bài", any("KH#" in g["user"] and "NCC#" in g["user"]
	for g in TAT_CA if g["kind"] == "viet"))

print("H. Không gì của đề bài nằm trong bảng nào")
BANG = {t: frappe.db.sql(f"SELECT * FROM `tab{t}`", as_dict=True) for t in (INSIGHT, RUN, BRIEF, "Error Log")
	if frappe.db.sql("SHOW TABLES LIKE %s", (f"tab{t}",))}
BANG["frappe.log_error"] = list(getattr(frappe, "LOGGED", []))
TXT = json.dumps(BANG, ensure_ascii=False, default=str)
MAU = {'"tin_hieu"', '"nhan_dinh"', '"du_lieu"', '"pack"', '"kieu"', "loi_quy_tac", KEY, OKEY}
for g in TAT_CA:   # câu đầu của mỗi system prompt (vai trò) — không nằm trong bảng nào
	MAU.add(g["system"].strip().splitlines()[0][:60])
eq("không mẩu đề bài / system prompt / khoá trong BC AI Insight / Run / Brief / Error Log", sorted(m for m in MAU
	if m in TXT), [])
c("không mã giả còn sót trong lời đã lưu", not re.search(r"(KH|NCC)#\d{4}", json.dumps([BANG[INSIGHT], BANG[BRIEF]],
	ensure_ascii=False, default=str)))

# ═══════════════════════════════════════════════════════════════════════════
print("I. AI tắt + không khoá: cùng chuỗi → tín hiệu quy tắc + bản tin theo quy tắc, KHÔNG lượt gọi nào")
single("BC Settings", ai_enabled=0)
frappe.conf.pop("bc_ai_anthropic_key", None)
frappe.conf.pop("bc_ai_openai_key", None)
GOI.clear()
DEM.update(claude=0, openai=0)
frappe.db.sql(f"DELETE FROM `tab{BRIEF}`")
TRUOC = {r[0] for r in frappe.db.sql(f"SELECT name FROM `tab{RUN}`")}
out3 = pipeline.run_daily()
bt3, bm3 = brief.run_brief("tuan"), brief.run_brief("thang")
eq("không một lượt gọi mô hình nào", (DEM, GOI), ({"claude": 0, "openai": 0}, []))
eq("lượt ngày ok, bước AI tat; bản tin nguồn quy-tac, AI tat", (out3["status"], out3["ai"], bt3["source"], bt3["ai"],
	bm3["source"], bm3["ai"]), ("ok", "tat", "quy-tac", "tat", "quy-tac", "tat"))
c("tín hiệu kiểm soát + lệch chuẩn vẫn mở", all(R(k).status in ("mo", "dang-xu-ly") for k in (*KS,
	f"kpi.lech_chuan:{KPI_A}", f"kpi.lech_chuan:{KPI_B}")))
eq("dòng Run mới: tổng ok + ai tat + ban-tin:* tat; không phản biện, không dòng nhóm", sorted((r.step, r.status)
	for r in frappe.db.sql(f"SELECT name, step, status FROM `tab{RUN}`", as_dict=True) if r.name not in TRUOC),
	[("ai", "tat"), ("ban-tin:thang", "tat"), ("ban-tin:tuan", "tat"), ("tong", "ok")])
fv4 = as_user("viewer@example.com", api.get_feed)
eq("người xem: hai bản tin theo quy tắc", [(b["type"], b["source"]) for b in fv4["briefs"]],
	[("tuan", "quy-tac"), ("thang", "quy-tac")])
mt = next((b for b in fv4["briefs"] if b["type"] == "tuan"), {"parts": []})
c("bản tin tuần theo quy tắc: có KPI đáng chú ý và việc tồn (ct.* mở từ 10/10)", any(p["key"] == "dang_chu_y" and p["items"]
	for p in mt["parts"]) and any(p["key"] == "viec_ton" and p["items"] for p in mt["parts"]), mt["parts"])
c("không mạng suốt bộ thử", not MANG, MANG)

frappe.db.sql(f"DROP DATABASE IF EXISTS `{DB}`")
c.done()
