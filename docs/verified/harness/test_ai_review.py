"""Trợ lý AI P2 — bước 7 phản biện (bc.ai.review, hợp đồng P2 §2.2) qua pipeline.run_daily THẬT.

Chỉ thay: collect.build (gói số dựng tay), quy tắc / detector (đăng ký trong file này) và bc.ai.llm.call (mô hình giả
cho CẢ HAI nhà cung cấp: claude = người viết, openai = người phản biện; mọi đề bài được chép lại để soát). Bảng thật,
review.run_group thật, render / mask / store thật. Mạng bị chặn ở tầng socket. Kỳ vọng tính tay, ghi trong comment.

Chạy: BC_TEST_DB=bc_test_ai_p2a_rv python3 -B test_ai_review.py
"""
import copy
import datetime
import json
import socket

from seed import Check, bc_settings, child, insert, reset, single
from paths import DB

import frappe  # noqa: E402  (giả)
import frappe.utils as futils  # noqa: E402

c = Check()
INSIGHT, RUN = "BC AI Insight", "BC AI Run"
KEY = "sk-ant-api03-KHOAGIA-p2rv-8Rw2LmQ"
OKEY = "sk-proj-KHOAGIA-p2rv-Openai_77aa"
TEN = "Đại lý Minh Phát"          # tên thật của khách NPP-A — không được rời máy chủ
TON_KHO = 5432109876              # số của mảng ton-kho (đang ẩn) — không được tới mô hình nào
KPI_BI_MAT = 424242               # khối tro-ly.kpi (NO_SEND) — không được tới mô hình nào
CAT = 987654321                   # top_overdue[33] — phần tử bị cắt khỏi đề bài người viết (giữ 30 đầu)
OPENAI_MODEL = "gpt-6.2-astra"


def eq(label, got, want):
	c(label, got == want, f"\n      được: {got!r}\n      cần : {want!r}")


class MangBiChan(RuntimeError):
	pass


def _chan(fn):
	def g(self, addr, *a, **k):
		if self.family in (socket.AF_INET, socket.AF_INET6):
			raise MangBiChan(f"bộ thử chặn mạng: {addr}")
		return fn(self, addr, *a, **k)
	return g


def _dns(*a, **k):
	raise MangBiChan("bộ thử chặn DNS")


socket.socket.connect, socket.socket.connect_ex = _chan(socket.socket.connect), _chan(socket.socket.connect_ex)
socket.getaddrinfo = socket.create_connection = _dns

reset(only={INSIGHT, RUN, "BC AI Brief", "Customer", "BC AI Rule", "BC AI Model Price", "BC Tet Date", "BC Hidden Item",
	"BC Share Link"})

from bc.ai import collect, llm, pipeline, registry, render, review, store  # noqa: E402

registry.load()
registry._MODULES = ()
registry.RULES.clear()
registry.DETECTORS.clear()


@registry.detector("t_tl", section="tro-ly")
def _d_tl(ctx):
	return {"dem": 7, "ghi_lui": 3}


@registry.detector("kpi", section="tro-ly")
def _d_kpi(ctx):
	return {"so_ngay": KPI_BI_MAT}


@registry.rule("p2r.cn", section="cong-no", sources=("cong-no.receivables",))
def _r_cn(pack, cfg):
	return [cfg.signal("vang", "Khách {{cong-no.receivables.top_overdue[0].customer|chu}} quá hạn "
		"{{cong-no.receivables.top_overdue[0].overdue|tien}}")]


@registry.rule("p2r.tong", section="cong-no", sources=("cong-no.receivables",))
def _r_tong(pack, cfg):
	return [cfg.signal("vang", "Phải thu {{cong-no.receivables.kpis.receivable|tien}}")]


@registry.rule("p2r.ks", section="tro-ly", sources=("tro-ly.t_tl",), route="")
def _r_ks(pack, cfg):
	return [cfg.signal("vang", "Có {{tro-ly.t_tl.dem|so}} chứng từ bị huỷ trong tuần")]


@registry.rule("p2r.lui", section="tro-ly", sources=("tro-ly.t_tl",), route="")
def _r_lui(pack, cfg):
	return [cfg.signal("vang", "Có {{tro-ly.t_tl.ghi_lui|so}} chứng từ ghi lùi ngày")]


TOP = [{"customer": TEN, "customer_id": "NPP-A", "overdue": 50000000}] + [
	{"customer": f"Khách lẻ {chr(65 + i % 26)}{chr(65 + i // 26)}", "customer_id": f"KL-{i}", "overdue": 1000000 + i}
	for i in range(1, 35)]
TOP[33]["overdue"] = CAT
PACK0 = {
	"cong-no": {"receivables": {"kpis": {"overdue": 120000000, "overdue_pct": 35.0, "receivable": 340000000},
		"top_overdue": TOP}},
	"ton-kho": {"overview": {"value": {"totals": {"value": TON_KHO}}}},
}

bc_settings(ai_enabled=1, ai_mask_parties=1, ai_cap_claude_usd=90, ai_cap_openai_usd=90, ai_openai_model="",
	hidden_sections="ton-kho")
child("BC Settings", "BC Settings", "BC AI Model Price", "ai_prices", [
	{"model": "claude-sonnet-5-5", "price_in": 3, "price_out": 15},
	{"model": OPENAI_MODEL, "price_in": 1.25, "price_out": 10}])
insert("Customer", name="NPP-A", customer_name=TEN)
frappe.conf["bc_ai_anthropic_key"] = KEY
frappe.session.user = "viewer@example.com"
collect.build = lambda today: copy.deepcopy(PACK0)

VIET, PB = [], []      # đề bài người viết / phản biện đã gửi
MODE = {"rv": None, "viet": "a", "rv_loi": None}


def S(obj, rule):
	return next((t["id"] for t in obj["tin_hieu"] if t["rule"] == rule), None)


def nguoi_viet(obj):
	ins = []
	if obj["nhom"] == "tai-chinh":
		code = obj["pack"]["cong-no"]["receivables"]["top_overdue"][0]["customer"]
		ins = [{"signal": S(obj, "p2r.cn"), "severity": "do", "priority": 4,
				"title": f"Khách {code} quá hạn {{{{cong-no.receivables.top_overdue[0].overdue|tien}}}}",
				"body": ("Cần nhắc {{cong-no.receivables.top_overdue[0].customer|chu}} thanh toán trong tuần này."
					if MODE["viet"] == "a" else "Khoản quá hạn của {{cong-no.receivables.top_overdue[0].customer|chu}} "
					"cần xử lý trước cuối tháng."),
				"advice": [f"Phòng Kế toán gọi điện cho {code} trong tuần."]},
			# trích phần tử ĐÃ BỊ CẮT khỏi đề bài người viết (render vẫn điền được từ gói đầy đủ)
			{"signal": S(obj, "p2r.tong"), "severity": "vang", "priority": 2,
				"title": "Khoản nhỏ cuối danh sách {{cong-no.receivables.top_overdue[33].overdue|tien}}",
				"body": "Khoản cuối danh sách là {{cong-no.receivables.top_overdue[33].overdue|tien}}.", "advice": []},
			{"signal": None, "severity": "vang", "priority": 2,
				"title": "Tỷ lệ nợ quá hạn ở mức {{cong-no.receivables.kpis.overdue_pct|pct}}",
				"body": "Tỷ lệ nợ quá hạn đang là {{cong-no.receivables.kpis.overdue_pct|pct}} tổng phải thu.",
				"advice": []}]
	elif obj["nhom"] == "kiem-soat":
		ins = [{"signal": S(obj, "p2r.ks"), "severity": "vang", "priority": 3,
				"title": "Có {{tro-ly.t_tl.dem|so}} chứng từ bị huỷ trong tuần",
				"body": "Số chứng từ bị huỷ trong tuần là {{tro-ly.t_tl.dem|so}}, cần rà soát lý do.", "advice": []},
			# trích khối NO_SEND tro-ly.kpi (không có trong đề bài người viết, render vẫn điền được)
			{"signal": S(obj, "p2r.lui"), "severity": "vang", "priority": 2,
				"title": "Ghi lùi {{tro-ly.t_tl.ghi_lui|so}} chứng từ",
				"body": "Lịch sử theo dõi đã có {{tro-ly.kpi.so_ngay|so}} ngày.", "advice": []}]
	return {"data": {"insights": [x for x in ins if x["signal"] is not False]}, "tokens_in": 1000, "tokens_out": 100,
		"model": "claude-sonnet-5-5"}


def theo_tieu_de(obj, tu):
	return next((n["id"] for n in obj["nhan_dinh"] if tu in n["tieu_de"]), None)


def rv_chuan(obj):
	"""Phản biện mặc định: tai-chinh — N(p2r.cn) nghi-ngo + note có mã giả và placeholder; tự do dong-y; id lạ, id
	trùng, verdict ngoài enum bị bỏ. kiem-soat — p2r.ks nghi-ngo, note viết tay số → note bỏ, verdict giữ."""
	if obj["nhom"] == "tai-chinh":
		code = obj["du_lieu"]["pack"]["cong-no"]["receivables"]["top_overdue"][0]["customer"]
		n_cn, n_td = theo_tieu_de(obj, "Khách"), theo_tieu_de(obj, "Tỷ lệ")
		return [{"id": n_cn, "verdict": "nghi-ngo",
				"note": f"Chưa có số cho thấy {code} sẽ trả, tỷ lệ {{{{cong-no.receivables.kpis.overdue_pct|pct}}}} "
					"là của cả nhóm."},
			{"id": n_cn, "verdict": "dong-y", "note": "trùng — bỏ"},
			{"id": n_td, "verdict": "xanh", "note": "verdict lạ — bỏ"},
			{"id": "N99", "verdict": "nghi-ngo", "note": "id lạ — bỏ"},
			{"id": n_td, "verdict": "dong-y", "note": ""}]
	if obj["nhom"] == "kiem-soat":
		return [{"id": theo_tieu_de(obj, "bị huỷ"), "verdict": "nghi-ngo", "note": "Nợ 5 tỷ không liên quan."}]
	return []


def fake_call(provider, model, system, user, schema_name, schema, max_tokens=16000, timeout=300):
	obj = json.loads(user)
	if provider == "claude":
		VIET.append({"nhom": obj["nhom"], "user": user, "obj": obj, "system": system})
		return nguoi_viet(obj)
	PB.append({"nhom": obj["nhom"], "user": user, "obj": obj, "system": system, "model": model, "schema_name": schema_name,
		"schema": schema, "timeout": timeout, "max_tokens": max_tokens})
	if MODE["rv_loi"]:
		e = MODE["rv_loi"](obj)
		if e is not None:
			raise e
	return {"data": {"reviews": (MODE["rv"] or rv_chuan)(obj)}, "tokens_in": 2000, "tokens_out": 300,
		"model": OPENAI_MODEL + "-2026-09-30"}


llm.call = fake_call


def chay(model=OPENAI_MODEL, rv=None, rv_loi=None, viet="a", xoa_run=True):
	single("BC Settings", ai_openai_model=model)
	MODE.update(rv=rv, rv_loi=rv_loi, viet=viet)
	VIET.clear()
	PB.clear()
	if xoa_run:
		frappe.db.sql(f"DELETE FROM `tab{RUN}`")
	out = pipeline.run_daily()
	c(f"(lượt chạy ok — {model or 'không model'})", out.get("status") == "ok", out)
	return out


def R(key):
	rows = frappe.db.sql(f"SELECT * FROM `tab{INSIGHT}` WHERE BINARY signal_key = %s", (key,), as_dict=True)
	return rows[0] if rows else None


def rv_rows(out):
	return frappe.db.sql(f"""SELECT * FROM `tab{RUN}` WHERE run_id = %s AND step LIKE 'review:%%' ORDER BY started, name""",
		(out["run"],), as_dict=True)


def loi_text():
	return json.dumps(frappe.LOGGED, ensure_ascii=False, default=str)


FREE = "ai:cong-no.receivables.kpis.overdue_pct"

# ═══════════════════════════════════════════════════════════════════════════
print("1. Không model OpenAI (mặc định) → không gọi, không dòng Run")
frappe.conf["bc_ai_openai_key"] = OKEY
out = chay(model="")
eq("người viết vẫn được gọi (tai-chinh, kiem-soat)", [v["nhom"] for v in VIET], ["tai-chinh", "kiem-soat"])
eq("không lượt gọi openai nào", PB, [])
eq("không dòng Run review:*", rv_rows(out), [])
c("verdict trống trên mọi Insight", not frappe.db.sql(f"SELECT name FROM `tab{INSIGHT}` WHERE IFNULL(review_verdict, '') != ''"))

# ═══════════════════════════════════════════════════════════════════════════
print("2. Lượt phản biện chuẩn")
n_log = len(frappe.LOGGED)
out = chay()
eq("hai lượt gọi openai: tai-chinh rồi kiem-soat (MỘT lượt / nhóm)", [p["nhom"] for p in PB], ["tai-chinh", "kiem-soat"])
p_tc = PB[0] if PB else {}
v_tc = VIET[0] if VIET else {}
eq("tên model / schema / max_tokens gửi đi", (p_tc.get("model"), p_tc.get("schema_name"), p_tc.get("schema"),
	p_tc.get("max_tokens")), (OPENAI_MODEL, "phan_bien", review.SCHEMA, 16000))
c("timeout trong khoảng 30–300 s", PB and all(30 <= p["timeout"] <= 300 for p in PB), [p.get("timeout") for p in PB])
eq("đề bài phản biện: đúng 3 khoá nhom / du_lieu / nhan_dinh", sorted(p_tc.get("obj", {})), ["du_lieu", "nhan_dinh", "nhom"])
eq("du_lieu = NGUYÊN pack + kieu của đề bài người viết (cùng nhóm)",
	[p["obj"]["du_lieu"] == {"pack": v["obj"]["pack"], "kieu": v["obj"]["kieu"]} for p, v in zip(PB, VIET)], [True, True])
c("du_lieu.pack có cắt 30 phần tử như người viết (35 dòng → _cat ghi 5)", PB and len(p_tc["obj"]["du_lieu"]["pack"]["cong-no"]
	["receivables"]["top_overdue"]) == 30 and p_tc["obj"]["du_lieu"]["pack"]["cong-no"]["receivables"]["_cat"]
	== {"top_overdue": 5})
nd = p_tc.get("obj", {}).get("nhan_dinh", [])
eq("nhan_dinh tai-chinh: id N1.., muc, tieu_de / noi_dung / khuyen_nghi = lời đã thay số CÒN mã giả; KHÔNG lời trích "
	"phần tử đã bị cắt", nd, [
	{"id": "N1", "muc": "do", "tieu_de": "Khách KH#0001 quá hạn 50 triệu",
		"noi_dung": "Cần nhắc KH#0001 thanh toán trong tuần này.",
		"khuyen_nghi": ["Phòng Kế toán gọi điện cho KH#0001 trong tuần."]},
	{"id": "N2", "muc": "vang", "tieu_de": "Tỷ lệ nợ quá hạn ở mức 35,0%",
		"noi_dung": "Tỷ lệ nợ quá hạn đang là 35,0% tổng phải thu.", "khuyen_nghi": []}])
eq("nhan_dinh kiem-soat: chỉ p2r.ks (lời trích khối NO_SEND tro-ly.kpi không gửi)",
	[n["tieu_de"] for n in PB[1]["obj"]["nhan_dinh"]] if len(PB) > 1 else None, ["Có 7 chứng từ bị huỷ trong tuần"])
tong = R("p2r.tong")
lui = R("p2r.lui")
c("lời trích phần tử bị cắt / khối NO_SEND bị loại ngay ở bước 6 (pipeline: path phải có trong gói đã gửi) — "
	"không lưu, giữ lời quy tắc, needs_check", tong is not None and tong.source == "quy-tac" and tong.needs_check
	and "988 triệu" not in (tong.title or "") and lui is not None and lui.source == "quy-tac" and lui.needs_check
	and "424.242" not in (lui.body or ""), (tong and (tong.source, tong.title), lui and (lui.source, lui.body)))
ALL = "\n".join(p["user"] + p["system"] for p in PB)
c("RIÊNG TƯ: không đề bài phản biện nào chứa tên khách thật", TEN not in ALL)
c("RIÊNG TƯ: không số của mảng đang ẩn (ton-kho) ở bất kỳ dạng nào", "ton-kho" not in ALL and str(TON_KHO) not in ALL
	and "5,4 tỷ" not in ALL and "5.432" not in ALL)
c("RIÊNG TƯ: không số của khối NO_SEND (tro-ly.kpi) ở bất kỳ dạng nào", str(KPI_BI_MAT) not in ALL and "424.242" not in ALL
	and '"kpi"' not in ALL)
c("RIÊNG TƯ: không số của phần tử đã bị cắt (top_overdue[33])", str(CAT) not in ALL and "988 triệu" not in ALL)
VALL = "\n".join(v["user"] for v in VIET)


def la(obj, out=None):
	out = set() if out is None else out
	if isinstance(obj, dict):
		for v in obj.values():
			la(v, out)
	elif isinstance(obj, list):
		for v in obj:
			la(v, out)
	else:
		out.add(json.dumps(obj, ensure_ascii=False))
	return out


c("mọi giá trị lá trong du_lieu của phản biện đều có trong đề bài người viết", PB and la([p["obj"]["du_lieu"]
	for p in PB]) <= la([v["obj"] for v in VIET]))
c("mã giả trong nhan_dinh đều có trong đề bài người viết", all(m in VALL for m in __import__("re").findall(
	r"KH#\d+|NCC#\d+", json.dumps([p["obj"]["nhan_dinh"] for p in PB], ensure_ascii=False))))
c("system prompt phản biện: cố định, không số liệu kinh doanh, có luật placeholder của người viết",
	PB and PB[0]["system"] == review.system_prompt() and "{{path|kiểu}}" in PB[0]["system"]
	and "dong-y" in PB[0]["system"] and "nghi-ngo" in PB[0]["system"] and not any(s in PB[0]["system"]
	for s in ("120000000", "35,0", "KH#0001")))

cn, td, ks = R("p2r.cn"), R(FREE), R("p2r.ks")
# note tai-chinh: "Chưa có số cho thấy KH#0001 sẽ trả, tỷ lệ {{…overdue_pct|pct}} là của cả nhóm." → mã → tên thật,
# 35.0 → "35,0%"
eq("p2r.cn: nghi-ngo, note đã thay số + đổi mã thành tên thật (chỉ quản trị thấy)", (cn.review_verdict, cn.review_note),
	("nghi-ngo", f"Chưa có số cho thấy {TEN} sẽ trả, tỷ lệ 35,0% là của cả nhóm."))
eq("nhận định tự do: dong-y, note rỗng (id trùng / verdict lạ / id lạ bị bỏ, không ghi đè)",
	(td.review_verdict, td.review_note), ("dong-y", ""))
eq("p2r.ks: note viết tay số ('5 tỷ') bị bỏ, verdict GIỮ", (ks.review_verdict, ks.review_note), ("nghi-ngo", ""))
eq("Insight không gửi (p2r.tong, p2r.lui): không verdict", (tong.review_verdict or "", lui.review_verdict or ""), ("", ""))
eq("phản biện không đổi lời / mức / trạng thái / nguồn", [(r.title, r.severity, r.status, r.source, r.needs_check)
	for r in (cn, ks)], [(f"Khách {TEN} quá hạn 50 triệu", "do", "mo", "ai", 0),
	("Có 7 chứng từ bị huỷ trong tuần", "vang", "mo", "ai", 0)])
rows = rv_rows(out)
# tai-chinh: cost = (2000 × 1,25 + 300 × 10) / 1e6 = (2500 + 3000) / 1e6 = 0,0055 (model trả lời có hậu tố ngày → chưa
# khai giá → giá model đã yêu cầu)
eq("dòng Run: review:<nhóm>, openai, run_id = dòng tổng, model THỰC, token, chi phí, insights_ai = verdict ghi, "
	"rejected = note bỏ, signals = số nhận định gửi", [(r.step, r.provider, r.run_type, r.run_id, r.model, r.status,
	r.tokens_in, r.tokens_out, round(float(r.cost_usd), 6), r.cost_known, r.signals, r.insights_ai, r.rejected)
	for r in rows], [
	("review:tai-chinh", "openai", "ngay", out["run"], OPENAI_MODEL + "-2026-09-30", "ok", 2000, 300, 0.0055, 1, 2, 2, 0),
	("review:kiem-soat", "openai", "ngay", out["run"], OPENAI_MODEL + "-2026-09-30", "ok", 2000, 300, 0.0055, 1, 1, 1, 1)])
eq("error của dòng trống (lời ngoài đề bài người viết đã bị loại ở bước 6, không tới phản biện)", [r.error for r in rows],
	[None, None])
c("không Error Log mới", len(frappe.LOGGED) == n_log, frappe.LOGGED[n_log:])
SAU = frappe.db.sql(f"SELECT * FROM `tab{RUN}`", as_dict=True)
c("KHÔNG lưu đề bài: không dòng Run nào chứa pack / nhan_dinh / tên / khoá", not any(s in json.dumps(SAU,
	ensure_ascii=False, default=str) for s in ("nhan_dinh", "du_lieu", TEN, KEY, OKEY, "top_overdue")))
c("render.forget_source đã chạy (không còn đề bài trong bộ nhớ)", render._nguon.cache_info().currsize == 0)
c("tổng lượt chạy: số liệu người viết không đổi vì phản biện (accepted / rejected của out)", out["ai"] == "ok")

# ═══════════════════════════════════════════════════════════════════════════
print("3. Lời AI mới hôm sau xoá verdict cũ; insight không được nhắc giữ verdict trống")
futils.FAKE_TODAY = datetime.date(2026, 10, 28)
out = chay(model="", viet="b")
cn2, ks2 = R("p2r.cn"), R("p2r.ks")
eq("p2r.cn có lời mới → verdict + note về rỗng", (cn2.review_verdict or "", cn2.review_note or "", cn2.body),
	("", "", f"Khoản quá hạn của {TEN} cần xử lý trước cuối tháng."))
eq("p2r.ks được viết lại (cùng lời) → cũng về rỗng (lời mới = phản biện cũ hết nghĩa)", ks2.review_verdict or "", "")
out = chay(rv=lambda obj: [{"id": "N1", "verdict": "dong-y", "note": ""}] if obj["nhom"] == "tai-chinh" else [])
eq("chỉ N1 được nhắc: p2r.cn dong-y, tự do trống, kiem-soat trống", [(R(k).review_verdict or "") for k in
	("p2r.cn", FREE, "p2r.ks")], ["dong-y", "", ""])
eq("kiem-soat không verdict nào → dòng ok, insights_ai 0", [(r.step, r.status, r.insights_ai) for r in rv_rows(out)],
	[("review:tai-chinh", "ok", 1), ("review:kiem-soat", "ok", 0)])
futils.FAKE_TODAY = datetime.date(2026, 10, 27)

# ═══════════════════════════════════════════════════════════════════════════
print("4. Không khoá / khoá sai dạng → MỘT dòng khong-khoa rồi im lặng")
for nhan, k in (("không khoá", ""), ("khoá sai dạng", "sk-proj-abc def")):
	frappe.conf["bc_ai_openai_key"] = k
	out = chay()
	eq(f"{nhan}: không lượt gọi openai", PB, [])
	eq(f"{nhan}: đúng MỘT dòng khong-khoa (nhóm đầu có lời), provider openai, không token",
		[(r.step, r.status, r.provider, r.tokens_in, r.cost_usd) for r in rv_rows(out)],
		[("review:tai-chinh", "khong-khoa", "openai", 0, 0)])
	eq(f"{nhan}: người viết vẫn chạy đủ", [v["nhom"] for v in VIET], ["tai-chinh", "kiem-soat"])
c("khoá sai dạng: error nói rõ, không chép khoá", rv_rows(out)[0].error == "khoá OpenAI khai sai dạng")
frappe.conf["bc_ai_openai_key"] = OKEY

# ═══════════════════════════════════════════════════════════════════════════
print("5. Vượt trần / quá lượt gọi → MỘT dòng vuot-tran rồi im lặng")
single("BC Settings", ai_cap_openai_usd=0)
out = chay()
eq("trần 0: không gọi openai, một dòng vuot-tran", (PB, [(r.step, r.status, r.error) for r in rv_rows(out)]),
	([], [("review:tai-chinh", "vuot-tran", None)]))
single("BC Settings", ai_cap_openai_usd=90)
frappe.db.sql(f"DELETE FROM `tab{RUN}`")
for i in range(30):
	insert(RUN, run_type="ngay", step="review:x", provider="openai", status="ok", started="2026-10-27 01:00:00",
		cost_usd=0)
out = chay(xoa_run=False)
eq("30 lượt openai hôm nay: không gọi, một dòng vuot-tran 'quá số lượt gọi trong ngày'",
	(PB, [(r.step, r.status, r.error) for r in rv_rows(out)]),
	([], [("review:tai-chinh", "vuot-tran", "quá số lượt gọi trong ngày")]))
eq("… người viết (claude) không bị ảnh hưởng", [v["nhom"] for v in VIET], ["tai-chinh", "kiem-soat"])

# ═══════════════════════════════════════════════════════════════════════════
print("6. Hết credit → het-credit rồi im lặng; lỗi khác → loi, nhóm sau vẫn phản biện")


def credit(obj):
	e = llm.LLMError("credit", f"HTTP 429 insufficient_quota (credit_balance_exhausted): {OKEY}")
	e.tokens_in, e.tokens_out, e.model = 0, 0, ""
	return e


out = chay(rv_loi=credit)
eq("credit: MỘT lượt gọi (tai-chinh), kiem-soat im lặng", [p["nhom"] for p in PB], ["tai-chinh"])
rr = rv_rows(out)
eq("… một dòng het-credit", [(r.step, r.status) for r in rr], [("review:tai-chinh", "het-credit")])
c("… error đã xoá khoá", rr and OKEY not in (rr[0].error or "") and "***" in rr[0].error, rr and rr[0].error)


def http_tc(obj):
	if obj["nhom"] == "tai-chinh":
		e = llm.LLMError("refusal", "mô hình từ chối trả lời")
		e.tokens_in, e.tokens_out, e.model = 500, 7, OPENAI_MODEL
		return e
	return None


out = chay(rv_loi=http_tc)
eq("refusal ở tai-chinh → dòng loi (token đã tính tiền), kiem-soat VẪN được phản biện",
	[(r.step, r.status, r.tokens_in, r.tokens_out, r.error) for r in rv_rows(out)],
	[("review:tai-chinh", "loi", 500, 7, "mô hình từ chối trả lời"), ("review:kiem-soat", "ok", 2000, 300, None)])
# chi phí lượt hỏng: (500 × 1,25 + 7 × 10) / 1e6 = (625 + 70) / 1e6 = 0,000695
c("… chi phí lượt hỏng 0,000695", round(float(rv_rows(out)[0].cost_usd), 6) == 0.000695, rv_rows(out)[0].cost_usd)

# ═══════════════════════════════════════════════════════════════════════════
print("7. Phản biện hỏng (lỗi không lường) → bước 1–6 nguyên vẹn, Error Log chỉ tên loại lỗi")
n_log = len(frappe.LOGGED)


def bung(obj):
	if obj["nhom"] == "tai-chinh":
		return RuntimeError(f"BI-MAT-LOI {TEN} {OKEY}")
	return None


out = chay(rv_loi=bung)
cn3 = R("p2r.cn")
eq("lời người viết vẫn lưu (bước 5–6 đã commit)", (cn3.source, cn3.title, cn3.review_verdict or ""),
	("ai", f"Khách {TEN} quá hạn 50 triệu", ""))
eq("dòng nhóm người viết ok; dòng phản biện tai-chinh loi 'lỗi không lường: RuntimeError'; kiem-soat vẫn ok",
	([(r.step, r.status) for r in frappe.db.sql(f"SELECT step, status FROM `tab{RUN}` WHERE run_id = %s AND step IN "
		"('tai-chinh', 'kiem-soat')", (out["run"],), as_dict=True)],
	[(r.step, r.status, r.error) for r in rv_rows(out)]),
	([("tai-chinh", "ok"), ("kiem-soat", "ok")], [("review:tai-chinh", "loi",
		"lỗi không lường: RuntimeError"), ("review:kiem-soat", "ok", None)]))
moi = frappe.LOGGED[n_log:]
c("Error Log 'bc.ai phản biện nhóm tai-chinh', chỉ tên loại lỗi (không lời lỗi, không tên, không khoá)",
	moi and any("phản biện nhóm tai-chinh" in json.dumps(x, ensure_ascii=False, default=str) for x in moi)
	and "BI-MAT-LOI" not in loi_text() and OKEY not in loi_text() and TEN not in loi_text(), moi)


goc_set = store.set_review
dem = {"n": 0}


def set_hong(*a, **k):
	dem["n"] += 1
	if dem["n"] == 2:
		raise ValueError("hỏng giữa chừng")
	return goc_set(*a, **k)


SU = []
goc_rb, goc_fin = frappe.db.rollback, store.finish_run
frappe.db.rollback = lambda: SU.append(("rollback",))


def fin_ghi(name, **k):
	SU.append(("finish", name, k.get("status")))
	return goc_fin(name, **k)


store.set_review = set_hong
store.finish_run = fin_ghi
out = chay()
store.set_review, store.finish_run, frappe.db.rollback = goc_set, goc_fin, goc_rb
rv0 = rv_rows(out)[0]
eq("áp hỏng ở verdict thứ 2 → dòng loi 'lỗi không lường: ValueError', lời người viết nguyên vẹn",
	(R("p2r.cn").source, rv0.status, rv0.error), ("ai", "loi", "lỗi không lường: ValueError"))
i_fin = next((i for i, x in enumerate(SU) if x[0] == "finish" and x[1] == rv0.name), None)
c("… rollback (bỏ verdict ghi dở) chạy TRƯỚC khi chốt + commit dòng loi (DB thử autocommit: soát thứ tự)",
	i_fin is not None and ("rollback",) in SU[:i_fin] and SU[i_fin - 1] == ("rollback",), SU)

# ═══════════════════════════════════════════════════════════════════════════
print("8. Ghi chú: path ngoài đề bài người viết / mã lạ / sai kiểu → bỏ note, giữ verdict")


def rv_ghi_chu(obj):
	if obj["nhom"] == "tai-chinh":
		return [{"id": "N1", "verdict": "nghi-ngo", "note": "Khoản {{cong-no.receivables.top_overdue[33].overdue|tien}} "
				"chưa được xét."},   # phần tử đã bị cắt khỏi đề bài
			{"id": "N2", "verdict": "nghi-ngo", "note": "Cần đối chiếu với KH#0099 trước."}]   # mã không có trong đề bài
	return [{"id": "N1", "verdict": "dong-y", "note": "Kỳ trước có {{tro-ly.kpi.so_ngay|so}} ngày."}]   # NO_SEND


out = chay(rv=rv_ghi_chu)
eq("ba note bị bỏ, ba verdict giữ", [(R(k).review_verdict, R(k).review_note or "") for k in ("p2r.cn", FREE, "p2r.ks")],
	[("nghi-ngo", ""), ("nghi-ngo", ""), ("dong-y", "")])
eq("rejected đếm note bỏ (2 + 1)", [(r.insights_ai, r.rejected) for r in rv_rows(out)], [(2, 2), (1, 1)])


def rv_kieu(obj):
	if obj["nhom"] == "tai-chinh":
		return [{"id": "N1", "verdict": "nghi-ngo", "note": "Quá hạn {{cong-no.receivables.kpis.overdue|pct}} là sai kiểu."},
			{"id": "N2", "verdict": "dong-y", "note": "Ghi\nnhiều dòng   vẫn gộp một dòng."}]
	return []


out = chay(rv=rv_kieu)
eq("note sai kiểu (tiền viết pct) bị bỏ; note nhiều dòng gộp một dòng", [(R(k).review_verdict, R(k).review_note or "")
	for k in ("p2r.cn", FREE)], [("nghi-ngo", ""), ("dong-y", "Ghi nhiều dòng vẫn gộp một dòng.")])

out = chay(rv=lambda obj: [{"id": "N1", "verdict": "nghi-ngo", "note": "Cần kiểm phiếu SR900 trước khi kết luận."}]
	if obj["nhom"] == "tai-chinh" else [])
eq("note chép mã chứng từ KHÔNG có trong đề bài phản biện (SR900) → bỏ note, giữ verdict (nguon = đề bài phản biện)",
	(R("p2r.cn").review_verdict, R("p2r.cn").review_note or "", rv_rows(out)[0].rejected), ("nghi-ngo", "", 1))

out = chay(rv=lambda obj: [{"id": "N1", "verdict": "nghi-ngo", "note": "Khoản nợ này đã kéo dài 45 ngày, không phải mới."},
	{"id": "N2", "verdict": "nghi-ngo", "note": "Việc này đã kéo dài chín mươi ngày."}]
	if obj["nhom"] == "tai-chinh" else [])
eq("note nêu thời hạn viết tay ('45 ngày', 'chín mươi ngày' — phản biện không có số ngày để đối chiếu) → bỏ note, giữ "
	"verdict", [(R(k).review_verdict, R(k).review_note or "") for k in ("p2r.cn", FREE)] + [rv_rows(out)[0].rejected],
	[("nghi-ngo", ""), ("nghi-ngo", ""), 2])
c("system phản biện cấm thời hạn viết tay", "chín mươi ngày" in review.system_prompt())

# ═══════════════════════════════════════════════════════════════════════════
print("9. Gọi thẳng run_group: rỗng / hết giờ / im lặng theo state / trần độ dài")
frappe.db.sql(f"DELETE FROM `tab{RUN}`")
single("BC Settings", ai_openai_model=OPENAI_MODEL)
PB.clear()
MODE.update(rv=lambda obj: [], rv_loi=None)
user_tc = json.dumps({"nhom": "tai-chinh", "pack": {"cong-no": {"receivables": {"kpis": {"overdue_pct": 35.0}}}},
	"tin_hieu": [], "kieu": {}}, ensure_ascii=False)
V1 = [{"key": FREE, "severity": "vang", "title": "Tỷ lệ nợ quá hạn ở mức 35,0%", "body": "x", "advice": []}]
KW = dict(group="tai-chinh", user=user_tc, mask=None, pack=copy.deepcopy(PACK0), sections={"cong-no"}, kinds=None,
	run=None, run_type="tay", now=futils.now_datetime(), today=futils.getdate())
review.run_group(viet=[], con=1000, state={}, **KW)
review.run_group(viet=V1, con=59, state={}, **KW)
review.run_group(viet=V1, con=1000, state={review.STATE_KEY: "het-credit"}, **KW)
review.run_group(viet=[{"key": "khong-co", "severity": "vang", "title": "t", "body": "b", "advice": []}], con=1000,
	state={}, **KW)
eq("viet rỗng / còn 59 s / state đã dừng / khoá không có Insight → không gọi, không dòng",
	(PB, frappe.db.sql(f"SELECT COUNT(*) FROM `tab{RUN}`")[0][0]), ([], 0))
st = {}
review.run_group(viet=V1, con=1000, state=st, **KW)
eq("con 1000: gọi, timeout = min(300, (1000 − 60) / 3 = 313) = 300; run_type tay", (len(PB), PB[0]["timeout"],
	frappe.db.sql(f"SELECT run_type FROM `tab{RUN}`")[0][0], st), (1, 300, "tay", {}))
PB.clear()
review.run_group(viet=V1, con=150, state={}, **KW)
eq("con 150: timeout = max(30, (150 − 60) / 3 = 30) = 30", PB[0]["timeout"], 30)
big = [{"key": FREE, "severity": "vang", "title": "T" * 50, "body": "B" * 400, "advice": []}] * 5
txt, n, _p = review.build_user("tai-chinh", user_tc, [(f"N{i}", v) for i, v in enumerate(big, 1)], max_chars=1500)
c("trần độ dài: bỏ nhận định từ cuối tới khi vừa (giữ ≥ 1)", len(txt) <= 1500 and 1 <= n < 5, (len(txt), n))
txt, n, _p = review.build_user("tai-chinh", user_tc, [(f"N{i}", v) for i, v in enumerate(big, 1)], max_chars=10)
eq("trần quá nhỏ: vẫn giữ một nhận định", n, 1)
_d = json.loads(review.build_user("tai-chinh", user_tc, [("N1", V1[0])])[0])
eq("build_user: không kèm tin_hieu (chỉ pack + kieu)", sorted(_d["du_lieu"]), ["kieu", "pack"])
# Lớp chặn thứ hai (bước 6 của pipeline đã loại lời trích path ngoài gói đã gửi): _chon vẫn tự bỏ lời có path của
# Insight không phân giải trên gói người viết nhận.
_ok, _bo = review._chon(V1, json.loads(user_tc)["pack"])
_ko, _bo2 = review._chon(V1, {"cong-no": {"receivables": {"kpis": {}}}})
eq("_chon: path của Insight có trong gói đã gửi → gửi; thiếu → không gửi (đếm)", ([i for i, _v in _ok], _bo,
	_ko, _bo2), (["N1"], 0, [], 1))

frappe.db.sql(f"DROP DATABASE IF EXISTS `{DB}`")
c.done()
