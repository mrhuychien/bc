"""Trợ lý AI P2 — NỀN dùng chung (hợp đồng P2 §1): registry (nhóm kiem-soat, detector theo mảng, Cfg.signal(section=…),
NO_SEND, KPI_TICH_LUY), pipeline (detector tro-ly ở bước 2, _apply trả lời đã lưu bản CÒN mã giả, review.run_group
trong try / except riêng, tín hiệu dùng số của mảng ẩn không gửi), store (xoá phản biện khi lời đổi, set_review, giữ
ảnh chụp KPI 400 ngày, BC AI Brief), render.render_text + "masked", jobs bản tin (khoá riêng), các module khung.

Phần pipeline chạy run_daily THẬT trên bảng thật, chỉ thay: collect.build (gói số dựng tay), quy tắc / detector (đăng ký
trong file này), bc.ai.llm.call (mô hình giả) và bc.ai.review.run_group (bản ghi lời gọi). Mạng bị chặn ở tầng socket.
Kỳ vọng tính tay, ghi trong comment.

Chạy: BC_TEST_DB=bc_test_ai_p2n python3 -B test_ai_p2_nen.py
"""
import copy
import datetime
import inspect
import json
import socket

from seed import Check, bc_settings, child, insert, reset, single
from paths import DB

import frappe  # noqa: E402  (giả)

c = Check()
D = datetime.datetime
INSIGHT, RUN, BRIEF = "BC AI Insight", "BC AI Run", "BC AI Brief"
KEY = "sk-ant-api03-KHOAGIA-p2nen-8Rw2LmQ"
TEN = "Đại lý Minh Phát"          # tên thật của khách NPP-A — không được rời máy chủ


def eq(label, got, want):
	c(label, got == want, f"\n      được: {got!r}\n      cần : {want!r}")


def nem(fn, loi=Exception):
	try:
		fn()
	except loi:
		return True
	except BaseException:  # noqa: BLE001
		return False
	return False


# Chặn mạng (MariaDB qua unix socket vẫn chạy).
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

reset(only={INSIGHT, RUN, BRIEF, "Customer", "BC AI Rule", "BC AI Model Price", "BC Tet Date", "BC Hidden Item",
	"BC Share Link"})
c("chặn mạng: MariaDB vẫn chạy, socket AF_INET nổ", frappe.db.sql("SELECT 1")[0][0] == 1
	and nem(lambda: socket.socket(socket.AF_INET).connect(("127.0.0.1", 9)), MangBiChan))

from bc import hooks  # noqa: E402
from bc.ai import brief, jobs, pipeline, registry, render, redact, review, store  # noqa: E402
from bc.ai import collect, llm  # noqa: E402
from bc.ai.llm import openai as llm_openai  # noqa: E402

# ═══════════════════════════════════════════════════════════════════════════
print("A. registry")
G = list(registry.GROUPS)
eq("nhóm kiem-soat đứng ngay trước he-thong (cuối danh sách)", G[-2:], ["kiem-soat", "he-thong"])
eq("kiem-soat = Kiểm soát, mảng tro-ly, lanh-dao", registry.GROUPS["kiem-soat"],
	{"label": "Kiểm soát", "sections": ("tro-ly",), "audience": "lanh-dao"})
c("hằng số KIEM_SOAT / TRO_LY", (registry.KIEM_SOAT, registry.TRO_LY) == ("kiem-soat", "tro-ly"))
eq("group_of(tro-ly) = kiem-soat; nhóm cũ giữ nguyên", [registry.group_of(s) for s in ("tro-ly", "cong-no", "he-thong")],
	["kiem-soat", "tai-chinh", "he-thong"])
c("_MODULES có rules.ks + detectors chung_tu / gia / kpi (và giữ module cũ)", {"bc.ai.rules.ks", "bc.ai.detectors.chung_tu",
	"bc.ai.detectors.gia", "bc.ai.detectors.kpi", "bc.ai.rules.cn", "bc.ai.detectors.he_thong"} <= set(registry._MODULES))
registry.load()
c("load() nạp được mọi module; mọi detector thật là DetectorDef — he-thong, trừ chung_tu / gia / kpi ở tro-ly (P2 §3)",
	registry.DETECTORS and all(isinstance(d, registry.DetectorDef) and d.name == n and d.section == ("tro-ly" if n in
	("chung_tu", "gia", "kpi") else "he-thong") for n, d in registry.DETECTORS.items()),
	{n: getattr(d, "section", d) for n, d in registry.DETECTORS.items()})
c("NO_SEND: giữ van-chuyen.overview_truoc, thêm (tro-ly, kpi)", {("van-chuyen", "overview_truoc"), ("tro-ly", "kpi")}
	== set(registry.NO_SEND))
c("KPI_TICH_LUY: frozenset các path của KPIS (agent detector điền — test_ai_kpi.py soát nội dung)",
	isinstance(registry.KPI_TICH_LUY, frozenset) and registry.KPI_TICH_LUY <= {p for p, _k, _l in registry.KPIS})

# Từ đây chỉ dùng quy tắc / detector của file này.
registry._MODULES = ()
registry.RULES.clear()
registry.DETECTORS.clear()
CTX = []


@registry.detector("t_ht")
def _d_ht(ctx):
	return {"ok": 1}


@registry.detector("t_tl", section="tro-ly")
def _d_tl(ctx):
	CTX.append(ctx)
	p = ctx["pack"] or {}
	return {"dem": 7, "thay_cong_no": 1 if "cong-no" in p else 0, "thay_he_thong": 1 if "t_ht" in (p.get("he-thong")
		or {}) else 0}


@registry.detector("kpi", section="tro-ly")
def _d_kpi(ctx):
	return {"so_ngay": 424242}


def _d_loi(ctx):
	raise RuntimeError("detector hỏng")


eq("detector: mặc định he-thong, khai tro-ly giữ mảng", {n: d.section for n, d in registry.DETECTORS.items()},
	{"t_ht": "he-thong", "t_tl": "tro-ly", "kpi": "tro-ly"})
c("detector: mảng lạ → ValueError", nem(lambda: registry.detector("x", section="khong-co"), ValueError))
_kh = lambda ctx: {}  # noqa: E731
_kh.__module__ = "module.khac"
c("detector: trùng tên ở module khác → ValueError", nem(lambda: registry.detector("t_tl", section="tro-ly")(_kh), ValueError))
NOW = D(2026, 10, 27, 5, 30)
P0 = {"cong-no": {"x": 1}, "he-thong": {"t_ht": {"ok": 1}}}
eq("run_detectors(now): chỉ detector he-thong", registry.run_detectors(NOW), {"t_ht": {"ok": 1}})
CTX.clear()
eq("run_detectors(now, tro-ly, pack): chỉ detector tro-ly, đọc được pack", registry.run_detectors(NOW, "tro-ly", P0),
	{"t_tl": {"dem": 7, "thay_cong_no": 1, "thay_he_thong": 1}, "kpi": {"so_ngay": 424242}})
c("ctx = {now, today, pack}: pack là CHÍNH gói đã dựng, today là ngày của now", CTX and CTX[0]["pack"] is P0
	and CTX[0]["today"] == datetime.date(2026, 10, 27) and CTX[0]["now"] == NOW and set(CTX[0]) == {"now", "today", "pack"})
registry.detector("t_loi", section="tro-ly")(_d_loi)
n_log = len(frappe.LOGGED)
eq("detector tro-ly ném lỗi → {_error: True}, detector khác vẫn chạy",
	registry.run_detectors(NOW, "tro-ly", P0)["t_loi"], {"_error": True})
c("… có Error Log", len(frappe.LOGGED) > n_log)
del registry.DETECTORS["t_loi"]


# Cfg.signal(section=…)
@registry.rule("p2.kpi", section="tro-ly", sources=("tro-ly.t_tl",), label="KPI lệch chuẩn")
def _r_kpi(pack, cfg):
	return [cfg.signal("vang", "Phải thu quá hạn {{cong-no.receivables.kpis.overdue|tien}} khác thường so với trung vị "
		"{{@trung_vi|tien}} của 28 ngày qua", obj="cong-no.receivables.kpis.overdue", section="cong-no",
		tinh={"trung_vi": 80000000})]


@registry.rule("p2.ks", section="tro-ly", sources=("tro-ly.t_tl",), route="")
def _r_ks(pack, cfg):
	return [cfg.signal("vang", "Có {{tro-ly.t_tl.dem|so}} chứng từ bị huỷ trong tuần")]


@registry.rule("p2.cn", section="cong-no", sources=("cong-no.receivables",))
def _r_cn(pack, cfg):
	return [cfg.signal("vang", "Khách {{cong-no.receivables.top_overdue[0].customer|chu}} quá hạn "
		"{{cong-no.receivables.top_overdue[0].overdue|tien}}")]


@registry.rule("p2.an", section="cong-no", sources=("cong-no.receivables",))
def _r_an(pack, cfg):   # lời dùng số của ton-kho → sections_used có ton-kho
	return [cfg.signal("vang", "Nợ quá hạn {{cong-no.receivables.kpis.overdue|tien}} trong khi tồn kho "
		"{{ton-kho.overview.value.totals.value|tien}}")]


@registry.rule("p2.ht", section="he-thong", sources=("he-thong.t_ht",), audience="quan-tri")
def _r_ht(pack, cfg):
	return [cfg.signal("vang", "Detector hệ thống chạy")]


cfg = registry.Cfg(registry.RULES["p2.kpi"])
s1 = cfg.signal("vang", "x", section="cong-no", obj="a")
s2 = cfg.signal("vang", "x")
s3 = cfg.signal("vang", "x", section="cong-no", route="#/khac")
s4 = cfg.signal("vang", "x", section="he-thong")
eq("Cfg.signal(section=cong-no): mảng + route theo TÍN HIỆU, rule / key theo quy tắc",
	(s1.section, s1.route, s1.rule, s1.key), ("cong-no", "#/cong-no", "p2.kpi", "p2.kpi:a"))
eq("không truyền section: mảng + route của quy tắc", (s2.section, s2.route), ("tro-ly", "#/tro-ly"))
eq("route truyền tay thắng; section he-thong → route rỗng", (s3.route, s4.route), ("#/khac", ""))
c("section lạ → ValueError", nem(lambda: cfg.signal("vang", "x", section="khong-co"), ValueError))


@registry.rule("p2.sai", section="cong-no", sources=("cong-no.receivables",))
def _r_sai(pack, cfg):   # dựng Signal tay với mảng lạ → quy tắc không chạy được
	return [registry.Signal(key="p2.sai", rule="p2.sai", section="khong-co", audience="lanh-dao", severity="vang",
		title="x")]


PACK0 = {
	"cong-no": {"receivables": {"kpis": {"overdue": 120000000, "overdue_pct": 35.0, "receivable": 340000000},
		"top_overdue": [{"customer": TEN, "customer_id": "NPP-A", "overdue": 50000000}]}},
	"ton-kho": {"overview": {"value": {"totals": {"value": 5000000000}}}},
}
pk = copy.deepcopy(PACK0)
pk["he-thong"] = registry.run_detectors(NOW)
pk["tro-ly"] = registry.run_detectors(NOW, "tro-ly", pk)
rr = registry.run_rules(pk)
by = {s.key: s for s in rr.signals}
sk = by.get("p2.kpi:cong-no.receivables.kpis.overdue")
TP = "cong-no._ai.p2_kpi_cong_no_receivables_kpis_overdue.trung_vi"
c("run_rules: tín hiệu kpi mang mảng cong-no, route #/cong-no", sk is not None and (sk.section, sk.route)
	== ("cong-no", "#/cong-no"), sk)
c("số tự tính nằm ở <mảng TÍN HIỆU>._ai (không ở tro-ly._ai), path trong lời", sk is not None and TP in sk.paths
	and registry.resolve(pk, TP) == 80000000 and "_ai" not in pk["tro-ly"], sk and sk.paths)
eq("tín hiệu không đổi mảng: tro-ly, route rỗng như quy tắc khai", (by["p2.ks"].section, by["p2.ks"].route), ("tro-ly", ""))
eq("Signal dựng tay với mảng lạ → quy tắc không chạy được (loi), quy tắc khác vẫn chạy", rr.not_run.get("p2.sai"), "loi")
del registry.RULES["p2.sai"]
kd = registry.kind_map(rr.signals)
c("kind_map nhận kiểu của path số tự tính theo mảng tín hiệu", kd.get(TP) == "tien" and kd.get("tro-ly.t_tl.dem") == "so")

# ═══════════════════════════════════════════════════════════════════════════
print("B. render.render_text + masked")
mk = redact.Mask([("KH#0001", TEN, {TEN, "NPP-A"})])
mk.begin()
gui = mk.mask(PACK0)
mk.restrict(json.dumps(gui, ensure_ascii=False))
C = mk.mask(TEN)
eq("mã giả của khách", C, "KH#0001")
r = render.render_text(f"Nhắc {C} trả {{{{cong-no.receivables.top_overdue[0].overdue|tien}}}} ngay", PACK0, {"cong-no"}, mk)
eq("text: số thay + mã → tên thật; masked: số thay, CÒN mã", (r["ok"], r["text"], r["masked"]),
	(True, f"Nhắc {TEN} trả 50 triệu ngay", "Nhắc KH#0001 trả 50 triệu ngay"))
eq("khoá kết quả", sorted(r), ["errors", "masked", "ok", "paths", "sections_used", "text"])
eq("paths / sections_used", (r["paths"], r["sections_used"]), (["cong-no.receivables.top_overdue[0].overdue"], ["cong-no"]))
gui_truoc = set(mk._gui)
r = render.render_text("Cần nhắc {{cong-no.receivables.top_overdue[0].customer|chu}} thanh toán.", PACK0, {"cong-no"}, mk)
eq("placeholder chu mang tên khách: text = tên thật, masked = mã giả",
	(r["ok"], r["text"], r["masked"]), (True, f"Cần nhắc {TEN} thanh toán.", "Cần nhắc KH#0001 thanh toán."))
c("dựng masked không đổi tập mã 'đã gửi' của mask", mk._gui == gui_truoc)
# Khách thứ hai: có trong bộ mã nhưng KHÔNG có trong đề bài đã gửi (dòng bị cắt) → masked vẫn che bằng mã của nó, và mã
# đó không được thành "đã gửi" (lời mô hình viết mã này sau đó vẫn không được hoàn nguyên thành tên).
mk2 = redact.Mask([("KH#0001", TEN, {TEN, "NPP-A"}), ("KH#0002", "Siêu thị Xuân Hoa", {"Siêu thị Xuân Hoa"})])
mk2.begin()
mk2.restrict(json.dumps(mk2.mask(PACK0), ensure_ascii=False))
PB = {"cong-no": {"x": [{"customer": "Siêu thị Xuân Hoa"}]}}
r = render.render_text("Cần nhắc {{cong-no.x[0].customer|chu}} thanh toán.", PB, {"cong-no"}, mk2)
eq("chu của khách CHƯA gửi: text tên thật, masked mã giả", (r["text"], r["masked"]),
	("Cần nhắc Siêu thị Xuân Hoa thanh toán.", "Cần nhắc KH#0002 thanh toán."))
eq("… mã KH#0002 không thành 'đã gửi': unmask để nguyên", mk2.unmask("KH#0002 và KH#0001"), f"KH#0002 và {TEN}")
r = render.render_text("Dòng đầu\n  tỷ lệ {{cong-no.receivables.kpis.overdue_pct|pct}} cao  ", PACK0, {"cong-no"}, mk,
	one_line=False)
eq("one_line=False: giữ xuống dòng, gọt hai đầu", (r["ok"], r["text"]), (True, "Dòng đầu\n  tỷ lệ 35,0% cao"))
eq("one_line=True (mặc định): gộp một dòng", render.render_text("A\nB", PACK0, None)["text"], "A B")
r = render.render_text("Nợ quá hạn 5 tỷ.", PACK0, {"cong-no"}, mk)
c("số trần → ok False, lỗi so-tran", not r["ok"] and any(e.startswith("so-tran") for e in r["errors"]), r["errors"])
eq("lời rỗng → lỗi rong", render.render_text("   ", PACK0, None)["errors"], ["rong"])
c("path ngoài tập mảng → ngoai-nhom", "ngoai-nhom:ton-kho.overview.value.totals.value" in render.render_text(
	"Tồn {{ton-kho.overview.value.totals.value|tien}} cao", PACK0, {"cong-no"})["errors"])
c("kinds: số đếm viết thành pct → kieu", any(e.startswith("kieu:") for e in render.render_text(
	"Tỷ lệ {{cong-no.receivables.kpis.receivable|pct}} cao", PACK0, {"cong-no"}, kinds={})["errors"]))
c("nguon: mã không có trong đề bài → so-tran", any(e.startswith("so-tran:") for e in render.render_text(
	"Kiểm phiếu SR900 ngay", PACK0, None, nguon='{"x": "khác"}')["errors"]))
render.forget_source()
raw = {"title": f"Khách {C} quá hạn {{{{cong-no.receivables.top_overdue[0].overdue|tien}}}}",
	"body": "Cần nhắc {{cong-no.receivables.top_overdue[0].customer|chu}} thanh toán.",
	"advice": [f"- Gọi {C} trong tuần.", "  "]}
ri = render.render_insight(raw, PACK0, {"cong-no"}, mk, kinds={})
eq("render_insight: lời lưu tên thật", (ri["ok"], ri["title"], ri["body"], ri["advice"]),
	(True, f"Khách {TEN} quá hạn 50 triệu", f"Cần nhắc {TEN} thanh toán.", [f"Gọi {TEN} trong tuần."]))
eq("render_insight: masked = {title, body, advice} còn mã giả", ri["masked"], {"title": "Khách KH#0001 quá hạn 50 triệu",
	"body": "Cần nhắc KH#0001 thanh toán.", "advice": ["Gọi KH#0001 trong tuần."]})

# ═══════════════════════════════════════════════════════════════════════════
print("C. pipeline.run_daily: detector tro-ly, nhóm kiem-soat, lời đã lưu bản che, phản biện")
bc_settings(ai_enabled=1, ai_mask_parties=1, ai_cap_claude_usd=90, ai_openai_model="", hidden_sections="ton-kho")
child("BC Settings", "BC Settings", "BC AI Model Price", "ai_prices",
	[{"model": "claude-sonnet-5-5", "price_in": 3, "price_out": 15}])
insert("Customer", name="NPP-A", customer_name=TEN)
frappe.conf["bc_ai_anthropic_key"] = KEY
frappe.session.user = "viewer@example.com"
collect.build = lambda today: copy.deepcopy(PACK0)

PACKS = []
_run_rules = registry.run_rules


def _bat_pack(pack, *a, **k):
	PACKS.append(pack)
	return _run_rules(pack, *a, **k)


registry.run_rules = _bat_pack
GOI, RV = [], []
MODE = {"review": "ghi", "loi_nhom": None}


def S(obj, rule):
	return next(t["id"] for t in obj["tin_hieu"] if t["rule"] == rule)


def fake_call(provider, model, system, user, schema_name, schema, max_tokens=16000, timeout=300):
	obj = json.loads(user)
	GOI.append({"nhom": obj["nhom"], "user": user, "obj": obj, "provider": provider})
	if MODE["loi_nhom"] == obj["nhom"]:
		raise llm.LLMError("http", "máy chủ lỗi")
	ins = []
	if obj["nhom"] == "tai-chinh":
		code = obj["pack"]["cong-no"]["receivables"]["top_overdue"][0]["customer"]
		ins = [{"signal": S(obj, "p2.cn"), "severity": "do", "priority": 4,
				"title": f"Khách {code} quá hạn {{{{cong-no.receivables.top_overdue[0].overdue|tien}}}}",
				"body": "Cần nhắc {{cong-no.receivables.top_overdue[0].customer|chu}} thanh toán trong tuần này.",
				"advice": [f"Phòng Kế toán gọi điện cho {code} trong tuần."]},
			{"signal": None, "severity": "vang", "priority": 2,
				"title": "Tỷ lệ nợ quá hạn ở mức {{cong-no.receivables.kpis.overdue_pct|pct}}",
				"body": "Tỷ lệ nợ quá hạn đang là {{cong-no.receivables.kpis.overdue_pct|pct}} tổng phải thu.",
				"advice": []}]
	elif obj["nhom"] == "kiem-soat":
		ins = [{"signal": S(obj, "p2.ks"), "severity": "vang", "priority": 3,
			"title": "Có {{tro-ly.t_tl.dem|so}} chứng từ bị huỷ trong tuần",
			"body": "Số chứng từ bị huỷ trong tuần là {{tro-ly.t_tl.dem|so}}, cần rà soát lý do.", "advice": []}]
	return {"data": {"insights": ins}, "tokens_in": 1000, "tokens_out": 100, "model": model}


def fake_review(**kw):
	RV.append(kw)
	if MODE["review"] == "nem":
		raise RuntimeError("BI-MAT-LOI phản biện hỏng " + KEY)


llm.call = fake_call
review.run_group = fake_review


def chay():
	GOI.clear()
	RV.clear()
	PACKS.clear()
	return pipeline.run_daily()


def R(key):
	rows = frappe.db.sql(f"SELECT * FROM `tab{INSIGHT}` WHERE BINARY signal_key = %s", (key,), as_dict=True)
	return rows[0] if rows else None


out = chay()
eq("lượt chạy ok", out.get("status"), "ok")
pk = PACKS[0] if PACKS else {}
eq("bước 2: pack[he-thong] = detector he-thong; pack[tro-ly] = detector tro-ly (thấy gói đã dựng, kể cả he-thong)",
	(sorted(pk.get("he-thong", {})), {k: v for k, v in pk.get("tro-ly", {}).items() if k != "_ai"}),
	(["t_ht"], {"t_tl": {"dem": 7, "thay_cong_no": 1, "thay_he_thong": 1}, "kpi": {"so_ngay": 424242}}))
NHOM = [g["nhom"] for g in GOI]
eq("nhóm được gọi: tai-chinh, kiem-soat, he-thong (kho-sx: ton-kho đang ẩn)", NHOM, ["tai-chinh", "kiem-soat", "he-thong"])
gks = next((g for g in GOI if g["nhom"] == "kiem-soat"), None)
c("đề bài kiem-soat: có pack tro-ly (t_tl), tín hiệu p2.ks", gks is not None and "t_tl" in gks["obj"]["pack"].get("tro-ly", {})
	and [t["rule"] for t in gks["obj"]["tin_hieu"]] == ["p2.ks"])
c("đề bài kiem-soat: KHÔNG có khối kpi (NO_SEND) — không lộ lịch sử KPI", gks is not None
	and "kpi" not in gks["obj"]["pack"]["tro-ly"] and "424242" not in gks["user"])
gtc = next((g for g in GOI if g["nhom"] == "tai-chinh"), None)
eq("đề bài tai-chinh: tín hiệu kpi (mảng cong-no) + p2.cn; KHÔNG p2.an (lời dùng số ton-kho đang ẩn)",
	sorted(t["rule"] for t in gtc["obj"]["tin_hieu"]) if gtc else None, ["p2.cn", "p2.kpi"])
c("không đề bài nào chứa tên khách thật", not any(TEN in g["user"] for g in GOI))

ROW = R("p2.kpi:cong-no.receivables.kpis.overdue")
c("Insight kpi: section cong-no, route #/cong-no, sections_used chỉ cong-no, path số tự tính đúng mảng",
	ROW is not None and (ROW.section, ROW.route, ROW.sections_used) == ("cong-no", "#/cong-no", "cong-no")
	and TP in json.loads(ROW.paths), ROW and (ROW.section, ROW.route, ROW.sections_used, ROW.paths))
c("lời quy tắc của tín hiệu kpi đã thay số (120 triệu, trung vị 80 triệu)", ROW is not None
	and "120 triệu" in ROW.title and "80 triệu" in ROW.title, ROW and ROW.title)

# get_feed: nhóm / ẩn theo mảng của tín hiệu.
from bc.api import ai as api  # noqa: E402

frappe.session.user = "Administrator"
feed = {x["signal_key"]: x for x in api.get_feed()["insights"]}
eq("get_feed (quản trị): tín hiệu kpi thuộc nhóm tai-chinh, p2.ks thuộc kiem-soat (nhãn Kiểm soát)",
	[(feed.get(k) or {}).get(f) for k in ("p2.kpi:cong-no.receivables.kpis.overdue", "p2.ks") for f in ("group", "group_label")],
	["tai-chinh", "Công nợ", "kiem-soat", "Kiểm soát"])
frappe.session.user = "viewer@example.com"
single("BC Settings", hidden_sections="cong-no")
vfeed = {x["id"] for x in api.get_feed()["insights"]}
c("người xem, ẩn cong-no: mất tín hiệu kpi (mảng của TÍN HIỆU), còn p2.ks", ROW is not None and ROW.name not in vfeed
	and R("p2.ks").name in vfeed)
single("BC Settings", hidden_sections="ton-kho")

# _apply → viet; review.run_group
eq("review.run_group: một lần / lượt gọi nhóm thành công, đúng thứ tự", [k.get("group") for k in RV], NHOM)
KW = {"group", "viet", "user", "mask", "pack", "sections", "kinds", "run", "run_type", "now", "today", "con", "state"}
c("tham số TỪ KHOÁ đúng bộ của hợp đồng", RV and all(set(k) == KW for k in RV), [sorted(k) for k in RV])
c("user = đúng đề bài cuối người viết đã nhận (từng nhóm)", RV and all(k["user"] == g["user"] for k, g in zip(RV, GOI)))
c("run = dòng tổng, run_type ngay, today = ngày của now", RV and all(k["run"] == out["run"] and k["run_type"] == "ngay"
	and k["today"] == k["now"].date() for k in RV))
c("state: CÙNG một dict qua mọi nhóm của lượt", RV and isinstance(RV[0]["state"], dict)
	and all(k["state"] is RV[0]["state"] for k in RV))
c("con: số giây còn lại (0 < con ≤ JOB_TIMEOUT − MARGIN)", RV and all(0 < k["con"] <= jobs.JOB_TIMEOUT - pipeline.MARGIN
	for k in RV), [k["con"] for k in RV])
rtc = next((k for k in RV if k["group"] == "tai-chinh"), None)
c("tai-chinh: sections = {cong-no} (mảng mô hình đã thấy), kinds là dict, pack đầy đủ, mask có unmask", rtc is not None
	and set(rtc["sections"]) == {"cong-no"} and isinstance(rtc["kinds"], dict) and rtc["pack"].get("ton-kho")
	and hasattr(rtc["mask"], "unmask"))
V = rtc["viet"] if rtc else []
eq("viet tai-chinh: tín hiệu được gắn lời + nhận định tự do, theo thứ tự lưu",
	[(v["key"], v["severity"]) for v in V], [("p2.cn", "do"), ("ai:cong-no.receivables.kpis.overdue_pct", "vang")])
c("mỗi mục viet đúng 5 khoá key / severity / title / body / advice", V and all(set(v) == {"key", "severity", "title", "body",
	"advice"} for v in V))
eq("viet p2.cn: số đã thay, CÒN mã giả (cả mã mô hình viết lẫn chu của tên khách)", V[0] if V else None,
	{"key": "p2.cn", "severity": "do", "title": "Khách KH#0001 quá hạn 50 triệu",
	"body": "Cần nhắc KH#0001 thanh toán trong tuần này.", "advice": ["Phòng Kế toán gọi điện cho KH#0001 trong tuần."]})
c("viet: không tên thật, không placeholder", not any(TEN in json.dumps(v, ensure_ascii=False) or "{{" in json.dumps(v)
	for v in V))
eq("viet tự do: số đã thay", (V[1]["title"], V[1]["body"]) if len(V) > 1 else None,
	("Tỷ lệ nợ quá hạn ở mức 35,0%", "Tỷ lệ nợ quá hạn đang là 35,0% tổng phải thu."))
cn = R("p2.cn")
c("lời ĐÃ LƯU của p2.cn: tên thật, không mã giả", cn is not None and cn.source == "ai" and TEN in cn.title
	and TEN in cn.body and TEN in cn.advice and "KH#" not in (cn.title + cn.body + cn.advice), cn and (cn.title, cn.body))
rks = next((k for k in RV if k["group"] == "kiem-soat"), None)
eq("viet kiem-soat", rks and rks["viet"], [{"key": "p2.ks", "severity": "vang", "title": "Có 7 chứng từ bị huỷ trong tuần",
	"body": "Số chứng từ bị huỷ trong tuần là 7, cần rà soát lý do.", "advice": []}])
eq("viet he-thong rỗng (mô hình không viết gì) — vẫn gọi phản biện một lần", [k["viet"] for k in RV if k["group"] == "he-thong"],
	[[]])


def chup():
	ins = frappe.db.sql(f"""SELECT signal_key, status, source, severity, title, body, advice, needs_check, review_verdict,
		review_note FROM `tab{INSIGHT}` ORDER BY signal_key""", as_dict=True)
	runs = frappe.db.sql(f"""SELECT step, status, provider, signals, insights_ai, rejected, error FROM `tab{RUN}`
		WHERE run_id = %s ORDER BY step""", (out2["run"],), as_dict=True)
	return [dict(x) for x in ins], [dict(x) for x in runs]


out2 = chay()
A = chup()
MODE["review"] = "nem"
frappe.LOGGED.clear()
out2 = chay()
B = chup()
eq("phản biện NÉM ở mọi nhóm: lượt chạy vẫn ok", out2.get("status"), "ok")
eq("… mọi Insight (lời, mức, trạng thái, phản biện) y hệt khi phản biện không lỗi", B[0], A[0])
eq("… mọi dòng Run của lượt y hệt (không dòng ai loi, nhóm vẫn ok)", B[1], A[1])
eq("… vẫn gọi đủ 3 nhóm và 3 lần phản biện", ([g["nhom"] for g in GOI], len(RV)), (NHOM, 3))
lg = [x for x in frappe.LOGGED if "phản biện" in json.dumps(x, ensure_ascii=False, default=str)]
c("… Error Log 'bc.ai phản biện nhóm …' mỗi nhóm, chỉ tên loại lỗi (không lời lỗi, không khoá)", len(lg) == 3
	and all("RuntimeError" in json.dumps(x, default=str) and "BI-MAT-LOI" not in json.dumps(x, ensure_ascii=False, default=str)
	and KEY not in json.dumps(x, default=str) for x in lg), lg)
MODE["review"] = "ghi"
MODE["loi_nhom"] = "kiem-soat"
chay()
eq("lượt gọi nhóm hỏng (LLMError) → không phản biện nhóm đó", [k["group"] for k in RV], ["tai-chinh", "he-thong"])
MODE["loi_nhom"] = None

# ═══════════════════════════════════════════════════════════════════════════
print("D. store: phản biện bị xoá khi lời đổi; set_review")
chay()
FREE = "ai:cong-no.receivables.kpis.overdue_pct"
for k in ("p2.cn", FREE, "p2.kpi:cong-no.receivables.kpis.overdue", "p2.an"):
	c(f"set_review({k}) → True", store.set_review(k, "nghi-ngo", "Chưa thấy số chứng minh nguyên nhân") is True)
r0 = R("p2.cn")
eq("set_review chỉ ghi verdict + note (lời, mức, trạng thái giữ nguyên)",
	(r0.review_verdict, r0.review_note, r0.title, r0.severity, r0.status, r0.source),
	("nghi-ngo", "Chưa thấy số chứng minh nguyên nhân", cn.title, cn.severity, "mo", "ai"))
c("set_review: verdict ngoài enum → ValueError", nem(lambda: store.set_review("p2.cn", "sai", ""), ValueError))
c("set_review: khoá không có → False", store.set_review("khong-co", "dong-y", "") is False)
dai = "Ghi chú " + "rất dài " * 40 + "còn 1,6 tỷ chưa rõ"
store.set_review("p2.cn", "dong-y", dai)
n = R("p2.cn").review_note
c("note > 300 ký tự: cắt ≤ 300, kết '…', không cắt giữa số", len(n) <= 300 and n.endswith("…") and "1,6" not in n, n[-30:])
store.set_review("p2.cn", "nghi-ngo", "x")
chay()   # AI bật: p2.cn có lời AI mới, tự do được ghi lại, kpi / an về lời quy tắc
eq("lượt sau (AI bật): mọi phản biện cũ bị xoá (lời AI mới / lời quy tắc đặt lại / tự do ghi lại)",
	[(R(k).review_verdict or "", R(k).review_note or "") for k in ("p2.cn", FREE, "p2.kpi:cong-no.receivables.kpis.overdue",
	"p2.an")], [("", "")] * 4)
# Từng nơi ghi lời, gọi thẳng (tách khỏi nhau).
nm = R("p2.cn").name
store.set_review("p2.cn", "nghi-ngo", "a")
store.apply_ai(nm, title="T", body="B", advice=[], severity="vang", priority=1, paths=[], sections_used=[], now=NOW)
eq("apply_ai xoá phản biện", (R("p2.cn").review_verdict or "", R("p2.cn").review_note or ""), ("", ""))
store.set_review("p2.cn", "nghi-ngo", "a")
store.sync_signals([{"key": "p2.cn", "rule": "p2.cn", "section": "cong-no", "audience": "lanh-dao", "severity": "vang",
	"route": "#/cong-no", "title": "Lời quy tắc", "body": "", "paths": [], "sections_used": ["cong-no"], "documents": []}],
	{"p2.cn"}, NOW)
eq("sync_signals (lời quy tắc, source quy-tac) xoá phản biện", (R("p2.cn").source, R("p2.cn").review_verdict or "",
	R("p2.cn").review_note or ""), ("quy-tac", "", ""))
store.set_review(FREE, "dong-y", "a")
store.sync_ai_free(("cong-no", "phai-tra"), [{"key": FREE, "section": "cong-no", "route": "#/cong-no", "severity": "vang",
	"priority": 1, "title": "T", "body": "B", "advice": [], "paths": [], "sections_used": []}], NOW)
eq("sync_ai_free (tự do ghi lại) xoá phản biện", (R(FREE).review_verdict or "", R(FREE).review_note or ""), ("", ""))
store.set_review("p2.ks", "dong-y", "z")
bc_settings(ai_enabled=0)
chay()
eq("AI tắt: lời quy tắc đặt lại → phản biện bị xoá", (R("p2.ks").source, R("p2.ks").review_verdict or ""), ("quy-tac", ""))
eq("RUN_TYPES có thang; VERDICTS", (store.RUN_TYPES, store.VERDICTS),
	(("ngay", "tuan", "tay", "hoi-dap", "thang"), ("dong-y", "nghi-ngo")))
c("start_run nhận run_type thang, step ban-tin:thang không cần dòng tổng", frappe.db.get_value(RUN, store.start_run("thang",
	"ban-tin:thang", provider="claude", now=NOW), "run_id") in (None, ""))

# ═══════════════════════════════════════════════════════════════════════════
print("E. store.cleanup: dòng tổng có KPI giữ 400 ngày, Run khác 180, BC AI Brief 400")
frappe.db.sql(f"DELETE FROM `tab{INSIGHT}`")
frappe.db.sql(f"DELETE FROM `tab{RUN}`")
frappe.db.sql(f"DELETE FROM `tab{BRIEF}`")
# NOW = 27/10/2026: lùi 180 ngày → 30/04/2026 (test_ai_store); lùi 400 ngày: 365 ngày → 27/10/2025, thêm 35 ngày
# (27 ngày về 30/09, 8 ngày về 22/09) → mốc 22/09/2025 00:00.
K = json.dumps({"cong-no.receivables.kpis.overdue": 1})
for name, step, started, kpis in (
		("K-400", "tong", "2025-09-22 00:00:00", K),          # đúng 400 ngày, có KPI → giữ
		("K-401", "tong", "2025-09-21 23:59:59", K),          # 401 ngày → xoá
		("K-200", "tong", "2026-04-10 08:00:00", K),          # 200 ngày, có KPI → giữ
		("N-180", "tong", "2026-04-30 00:00:00", None),       # đúng 180 ngày → giữ
		("N-181", "tong", "2026-04-29 23:59:59", None),       # 181 ngày, không KPI → xoá
		("E-200", "tong", "2026-04-10 08:00:00", "{}"),       # ảnh chụp rỗng = không KPI → xoá
		("C-200", "tai-chinh", "2026-04-10 08:00:00", K),     # dòng con (không phải tổng) → 180 ngày → xoá
		("M-moi", "ban-tin:thang", "2026-10-02 07:00:00", None)):   # mới → giữ
	insert(RUN, name=name, run_type="ngay", step=step, run_id=name, started=started, status="ok", kpis=kpis)
for name, d in (("B-400", "2025-09-22"), ("B-401", "2025-09-21"), ("B-moi", "2026-10-26")):
	insert(BRIEF, name=name, brief_key=f"tuan:{d}", brief_type="tuan", brief_date=d, title=name, source="quy-tac")
kq = store.cleanup(NOW)
eq("trả về: 4 Run, 1 bản tin, 0 Insight", kq, {"insights": 0, "runs": 4, "briefs": 1})
eq("Run còn lại", sorted(frappe.db.sql_list(f"SELECT name FROM `tab{RUN}`")), ["K-200", "K-400", "M-moi", "N-180"])
eq("Brief còn lại", sorted(frappe.db.sql_list(f"SELECT name FROM `tab{BRIEF}`")), ["B-400", "B-moi"])
eq("chạy lại: không còn gì (không khoá briefs khi 0)", store.cleanup(NOW), {"insights": 0, "runs": 0})
eq("hằng số", (store.KEEP_KPI_DAYS, store.KEEP_RUN_DAYS, store.KEEP_CLOSED_DAYS), (400, 180, 180))

# ═══════════════════════════════════════════════════════════════════════════
print("F. store.upsert_brief / latest_briefs")
frappe.db.sql(f"DELETE FROM `tab{BRIEF}`")
PARTS = [{"key": "dang_chu_y", "title": "Điều đáng chú ý", "items": [{"text": "Phải thu tăng 12,5%.", "sections": ["cong-no"]},
	{"text": "  ", "sections": ["x"]}]}, {"key": "viec_ton", "title": "Việc tồn chưa xử lý", "items": []}]
n1 = store.upsert_brief("tuan", datetime.date(2026, 10, 26), title="Tuần 19–25/10", parts=PARTS,
	sections_used=["cong-no", "cong-no", "ton-kho"], source="ai", model="claude-opus-5-5",
	period_from="2026-10-19", period_to="2026-10-25")
n2 = store.upsert_brief("tuan", "2026-10-26", title="Tuần 19–25/10 (chạy lại)", parts=[], sections_used="cong-no",
	source="quy-tac", period_from="2026-10-19", period_to="2026-10-25")
eq("cùng loại + ngày: MỘT dòng, cùng name, ghi đè", (n1 == n2, frappe.db.sql(f"SELECT COUNT(*) FROM `tab{BRIEF}`")[0][0]),
	(True, 1))
row = frappe.db.sql(f"SELECT * FROM `tab{BRIEF}` WHERE name = %s", (n1,), as_dict=True)[0]
eq("dòng sau khi ghi đè", (row.brief_key, row.brief_type, str(row.brief_date), row.title, row.source, row.model,
	row.sections_used), ("tuan:2026-10-26", "tuan", "2026-10-26", "Tuần 19–25/10 (chạy lại)", "quy-tac", None, "cong-no"))
n3 = store.upsert_brief("thang", "2026-10-26", title="Tháng", parts=PARTS, sections_used=["cong-no", "ton-kho"],
	source="ai", model="m")
n4 = store.upsert_brief("tuan", "2026-10-19", title="Tuần trước", parts=PARTS, sections_used=[], source="quy-tac")
c("khác loại / khác ngày → dòng riêng", len({n1, n3, n4}) == 3 and frappe.db.sql(f"SELECT COUNT(*) FROM `tab{BRIEF}`")[0][0] == 3)
c("loại / nguồn lạ → ValueError", nem(lambda: store.upsert_brief("nam", NOW, title="x", parts=[], sections_used=[],
	source="ai"), ValueError) and nem(lambda: store.upsert_brief("tuan", NOW, title="x", parts=[], sections_used=[],
	source="khac"), ValueError))
lb = store.latest_briefs()
eq("latest_briefs(): mỗi loại 1, theo thứ tự types, mới nhất", [(x["brief_type"], x["brief_date"]) for x in lb],
	[("tuan", datetime.date(2026, 10, 26)), ("thang", datetime.date(2026, 10, 26))])
eq("latest_briefs(limit=5, types=(tuan,))", [x["name"] for x in store.latest_briefs(("tuan",), 5)], [n1, n4])
t = lb[1]
eq("dạng một dòng", sorted(t), ["brief_date", "brief_type", "model", "name", "parts", "period_from", "period_to",
	"sections_used", "source", "title"])
eq("parts đọc lại: bỏ mục chữ rỗng, giữ phần rỗng; sections_used là list", (t["parts"], t["sections_used"]),
	([{"key": "dang_chu_y", "title": "Điều đáng chú ý", "items": [{"text": "Phải thu tăng 12,5%.", "sections": ["cong-no"]}]},
	{"key": "viec_ton", "title": "Việc tồn chưa xử lý", "items": []}], ["cong-no", "ton-kho"]))
eq("kỳ của bản tin tuần", (lb[0]["period_from"], lb[0]["period_to"]), (datetime.date(2026, 10, 19), datetime.date(2026, 10, 25)))
nt = store.upsert_brief("tuan", "2026-11-02", title="Bản tin " + "dài " * 60 + "còn 1,6 tỷ", parts=[], sections_used=[],
	source="quy-tac")
tt = frappe.db.get_value(BRIEF, nt, "title")
c("title > 200: cắt không giữa số", len(tt) <= 200 and "1,6" not in tt and tt.endswith("…"))
c("BC AI Brief: không cột đề bài / gói số", not {"prompt", "pack", "user", "system"} & set(frappe.db.get_table_columns(BRIEF)))
dtj = json.load(open(inspect.getfile(store).replace("ai/store.py", "bc/doctype/bc_ai_brief/bc_ai_brief.json"), encoding="utf-8"))
fd = {f["fieldname"]: f for f in dtj["fields"]}
c("DocType BC AI Brief: hash, chỉ System Manager, brief_key unique, Select đúng options", dtj["autoname"] == "hash"
	and [p["role"] for p in dtj["permissions"]] == ["System Manager"] and fd["brief_key"].get("unique") == 1
	and fd["brief_type"]["options"] == "ngay\ntuan\nthang" and fd["source"]["options"] == "ai\nquy-tac"
	and fd["body"]["fieldtype"] == "Long Text" and fd["title"].get("length") == 200)

# ═══════════════════════════════════════════════════════════════════════════
print("G. jobs: bản tin — job id + khoá riêng, không chặn lượt ngày và ngược lại")
from frappe.utils import background_jobs as bj  # noqa: E402

frappe.ENQUEUE_RUN = False
frappe.cache().store.clear()
bj.FAKE_ENQUEUED_IDS.clear()
c("khoá bản tin khác khoá lượt ngày, không tiền tố bc:", jobs.BRIEF_LOCK_KEY == "bcai:lock:brief"
	and jobs.BRIEF_LOCK_KEY != jobs.LOCK_KEY and not jobs.BRIEF_LOCK_KEY.startswith("bc:"))
eq("job id riêng từng loại", jobs.BRIEF_JOB_IDS, {"tuan": "bc_ai_brief_tuan", "thang": "bc_ai_brief_thang"})
frappe.cache().set_value(jobs.LOCK_KEY, 1)
c("lượt ngày đang giữ khoá → bản tin vẫn xếp được", not jobs.brief_running("tuan") and jobs.enqueue_brief("tuan") is True)
eq("… đúng job", frappe.ENQUEUED[-1], ("bc.ai.brief.run_brief", {"queue": "long", "timeout": jobs.BRIEF_TIMEOUT,
	"job_id": "bc_ai_brief_tuan", "deduplicate": True}, {"kind": "tuan"}))
frappe.cache().delete_value(jobs.LOCK_KEY)
frappe.cache().set_value(jobs.BRIEF_LOCK_KEY, 1)
c("bản tin giữ khoá → lượt ngày vẫn xếp được", not jobs.is_running() and jobs.enqueue_run("ngay") is True)
c("bản tin giữ khoá → bản tin khác (kể cả loại kia) không xếp", jobs.brief_running("thang")
	and jobs.enqueue_brief("thang") is False)
frappe.cache().delete_value(jobs.BRIEF_LOCK_KEY)
bj.FAKE_ENQUEUED_IDS.add("bc_ai_brief_tuan")
c("job tuần đang chờ → tuần không xếp, tháng xếp được", jobs.enqueue_brief("tuan") is False
	and jobs.enqueue_brief("thang") is True and frappe.ENQUEUED[-1][2] == {"kind": "thang"})
bj.FAKE_ENQUEUED_IDS.clear()
c("loại lạ → ValueError", nem(lambda: jobs.enqueue_brief("nam"), ValueError) and nem(lambda: jobs.brief_running("x"),
	ValueError))
frappe.ENQUEUED.clear()
jobs.weekly()
jobs.monthly()
eq("weekly / monthly xếp đúng loại", [(m, k["job_id"], kw) for m, k, kw in frappe.ENQUEUED],
	[("bc.ai.brief.run_brief", "bc_ai_brief_tuan", {"kind": "tuan"}), ("bc.ai.brief.run_brief", "bc_ai_brief_thang",
	{"kind": "thang"})])
eq("hooks: cron ngày + tuần (thứ Hai 06:00) + tháng (07:00 ngày 2)", hooks.scheduler_events["cron"],
	{"30 5 * * *": ["bc.ai.jobs.daily"], "0 6 * * 1": ["bc.ai.jobs.weekly"], "0 7 2 * *": ["bc.ai.jobs.monthly"]})

# ═══════════════════════════════════════════════════════════════════════════
print("H. Module khung: chữ ký chốt")
import importlib  # noqa: E402

review = importlib.reload(review)
eq("review.run_group: chỉ tham số từ khoá, đúng bộ", [(p.name, p.kind.name) for p in
	inspect.signature(review.run_group).parameters.values()], [(k, "KEYWORD_ONLY") for k in ("group", "viet", "user", "mask",
	"pack", "sections", "kinds", "run", "run_type", "now", "today", "con", "state")])
c("review.run_group khung trả None", review.run_group(group="g", viet=[], user="{}", mask=None, pack={}, sections=set(),
	kinds=None, run=None, run_type="ngay", now=NOW, today=NOW.date(), con=100, state={}) is None)
eq("brief.run_brief(kind): chữ ký chốt (thân: test_ai_brief.py)", list(inspect.signature(brief.run_brief).parameters),
	["kind"])
eq("llm.openai.call: cùng chữ ký anthropic.call", list(inspect.signature(llm_openai.call).parameters),
	["model", "system", "user", "schema_name", "schema", "max_tokens", "timeout"])
e = None
try:
	llm_openai.call("m", "s", "u", "phan_bien", {})
except llm.LLMError as x:
	e = x
c("llm.openai.call khung → LLMError no_key", e is not None and e.kind == "no_key")

# ═══════════════════════════════════════════════════════════════════════════
frappe.db.sql(f"DROP DATABASE IF EXISTS `{DB}`")
c.done()
