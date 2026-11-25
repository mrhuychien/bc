"""Trợ lý AI — bc.api.ai (đặc tả §6, §7, §9.6, §9.8, §9.9; hợp đồng chung §1, §3).

Kỳ vọng TÍNH TAY (phép tính ghi trong comment). bc.ai.store còn đang được viết → thay bằng bản giả ghi lời gọi;
bc.ai.llm.call thay bằng bản giả (không ra mạng — bản giả mặc định ném lỗi nếu bị gọi ngoài ý muốn); bc.ai.budget và
phần còn lại của bc.ai.llm (has_key, LLMError, clean, run_status) dùng THẬT. registry._MODULES = () và ba quy tắc giả
đăng ký ngay ở đây (không nạp file quy tắc của agent khác).

Hôm nay giả = 2026-10-27 10:30.
Chạy: BC_TEST_DB=bc_test_ai_api python3 -B test_ai_api.py
"""
import datetime
import importlib.util
import json
import os
import re
import sys
import types

from seed import Check, bc_settings, child, insert, reset, single

import frappe  # noqa: E402  (giả)
from frappe.utils import background_jobs  # noqa: E402

import bc.ai  # noqa: E402
from bc.ai import jobs, llm, registry  # noqa: E402
from bc.api import ai  # noqa: E402

c = Check()
D = datetime.datetime
ADMIN, VIEWER = "Administrator", "viewer@example.com"
INSIGHT, RUN = "BC AI Insight", "BC AI Run"
SECRET = "sk-ant-api03-BIMAT-chi-de-thu-9f8e7d6c5b4a"
MODEL = "claude-sonnet-5-5"


def raises(fn, exc, *a, **k):
	"""True nếu fn(*a, **k) ném ĐÚNG loại exc (PermissionError không phải ValidationError trong frappe giả)."""
	try:
		fn(*a, **k)
	except exc:
		return True
	except Exception as e:  # noqa: BLE001
		print("    (ném lỗi khác:", type(e).__name__, e, ")")
		return False
	return False


def as_(user):
	frappe.session.user = user


# ─── Bản giả ─────────────────────────────────────────────────────────────────
class FakeStore(types.ModuleType):
	def __init__(self):
		super().__init__("bc.ai.store")
		self.calls = []

	def start_run(self, run_type, step, provider=None, model=None, now=None, run_id=None):
		self.calls.append(("start", {"run_type": run_type, "step": step, "provider": provider, "model": model}))
		return f"RUN-{len(self.calls)}"

	def finish_run(self, name, **kw):
		self.calls.append(("finish", dict(kw, name=name)))


store = FakeStore()
# Bản tin (P2): đọc / ghi BC AI Brief bằng store THẬT (nạp riêng từ file — bản giả vẫn giữ start_run / finish_run).
_spec = importlib.util.spec_from_file_location("bc_ai_store_that", os.path.join(os.path.dirname(bc.ai.__file__), "store.py"))
store_that = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(store_that)
store.latest_briefs = store_that.latest_briefs
sys.modules["bc.ai.store"] = store
bc.ai.store = store

LLM_CALLS = []


def call_cam(*a, **k):
	raise AssertionError("bc.ai.llm.call bị gọi ngoài ý muốn")


def set_call(fn):
	def wrap(*a, **k):
		LLM_CALLS.append((a, k))
		return fn(*a, **k)
	llm.call = wrap


llm.call = call_cam

# ─── Quy tắc giả ─────────────────────────────────────────────────────────────
registry._MODULES = ()
registry.RULES.clear()


@registry.rule("t.a", section="cong-no", sources="cong-no.x", vang=10, do=20, unit="%", label="Quá hạn")
def _ra(pack, cfg):
	return []


@registry.rule("t.b", section="ton-kho", sources="ton-kho.x", vang=5, lower=True, label="Tồn")
def _rb(pack, cfg):
	return []


@registry.rule("t.c", section="he-thong", sources="he-thong.x", audience="quan-tri", vang=1)
def _rc(pack, cfg):
	return []


# ─── Dữ liệu ─────────────────────────────────────────────────────────────────
reset(only={INSIGHT, RUN, "BC AI Brief", "BC AI Rule", "BC AI Model Price", "BC Tet Date", "BC Hidden Item", "BC Share Link"})
bc_settings(ai_enabled=1, ai_claude_model=MODEL, ai_claude_model_deep="claude-opus-5-5", ai_openai_model="",
	ai_cap_claude_usd=50, ai_cycle_day_claude=1)
child("BC Settings", "BC Settings", "BC AI Model Price", "ai_prices",
	[{"model": MODEL, "price_in": 3, "price_out": 15}])
frappe.conf["bc_ai_anthropic_key"] = SECRET
frappe.ENQUEUE_RUN = False


def ins(name, **f):
	base = {"signal_key": f"k.{name}", "rule": "t.x", "section": "cong-no", "route": "#/cong-no",
		"sections_used": f.get("section", "cong-no"), "audience": "lanh-dao", "severity": "vang", "status": "mo",
		"source": "quy-tac", "title": f"Tiêu đề {name}", "body": f"Thân {name}", "advice": "", "documents": "[]",
		"rank": 0, "first_seen": D(2026, 10, 20, 8, 0), "last_seen": D(2026, 10, 27, 5, 30), "needs_check": 0,
		"seen_count": 1, "priority": 0}
	base.update(f)
	insert(INSIGHT, name, **base)


ins("IA", rule="t.a", severity="do", rank=2, advice="Gọi khách\n\n  Thu tiền  ",
	documents=json.dumps([{"doctype": "Sales Invoice", "name": "SI-1"}]), admin_note="ghi chú A", review_note="pb A",
	review_verdict="nghi-ngo")
ins("IB", section="tong-quan", sections_used="tong-quan\nphai-tra", status="dang-xu-ly", rank=1,
	first_seen=D(2026, 10, 26, 23, 0))
ins("IC", section="ton-kho", sections_used="ton-kho", rank=0, first_seen=D(2026, 10, 1, 9, 0))
ins("ID", rule="t.a", section="ton-kho", sections_used="ton-kho", severity="do", rank=0,
	first_seen=D(2026, 10, 25, 9, 0))
ins("IE", section="he-thong", sections_used="he-thong", audience="quan-tri", severity="do", rank=3)
ins("IF", rule="t.a", severity="do", status="bo-qua", rank=0, first_seen=D(2026, 10, 10, 9, 0), needs_check=1)
ins("IG", status="dong", closed_on=D(2026, 10, 10, 9, 0), first_seen=D(2026, 9, 1, 9, 0))
ins("IH", status="dong", closed_on=D(2026, 9, 20, 9, 0))
ins("II", section="nhan-su", sections_used="", rank=4, needs_check=1, first_seen=D(2026, 10, 28, 9, 0))
ins("IJ", section="ngay", sections_used="ngay", rank=0, first_seen=D(2026, 10, 15, 9, 0))

VIEW_KEYS = {"id", "section", "section_label", "group", "group_label", "severity", "title", "body", "advice", "route",
	"source", "status", "days", "first_seen", "last_seen", "review_verdict", "stale"}
ADMIN_KEYS = VIEW_KEYS | {"documents", "admin_note", "review_note", "needs_check", "signal_key", "rule", "mute_until",
	"audience", "sections_used"}


def ids(feed):
	return [x["id"] for x in feed["insights"]]


print("1. Lọc + thứ tự")
as_(VIEWER)
f = ai.get_feed(refresh=1)
# Người xem: lanh-dao, mo/dang-xu-ly → A B C D I J (E quan-tri, F bo-qua, G H dong bị bỏ).
# rank > 0 trước: B(1) A(2) I(4); rank 0: D (đỏ) trước C, J (vàng); C first_seen 01/10 cũ hơn J 15/10.
c("người xem: đúng tập + thứ tự", ids(f) == ["IB", "IA", "II", "ID", "IC", "IJ"], ids(f))
c("người xem: closed=1 bị bỏ qua", ids(ai.get_feed(closed=1)) == ids(f))
# đỏ: A, D = 2; vàng: B, I, C, J = 4
c("người xem: counts", f["counts"] == {"do": 2, "vang": 4}, f["counts"])
c("người xem: badge = counts", ai.get_badge(refresh=1) == {"do": 2, "vang": 4})
c("người xem: khoá mỗi nhận định đúng 17 trường", all(set(x) == VIEW_KEYS for x in f["insights"]),
	[sorted(set(x) ^ VIEW_KEYS) for x in f["insights"]][:1])
c("người xem: không có số bị lọc ở mức trên", set(f) == {"meta", "brief", "briefs", "counts", "insights"}, set(f))
c("chưa có lượt ok: không thẻ nào stale, stale_count 0", not any(x.get("stale") for x in f["insights"])
	and f["meta"].get("stale_count") == 0, f["meta"])
a = f["insights"][1]
c("trường của A", (a["section"], a["section_label"], a["group"], a["group_label"], a["severity"], a["advice"],
	a["route"], a["source"], a["status"], a["review_verdict"], a["title"]) == ("cong-no", "Phải thu", "tai-chinh",
	"Công nợ", "do", ["Gọi khách", "Thu tiền"], "#/cong-no", "quy-tac", "mo", "nghi-ngo", "Tiêu đề IA"), a)
# days: 27/10 − 20/10 = 7; B: 27 − 26 = 1 (theo ngày lịch, dù 23:00); I first_seen 28/10 (tương lai) → 0
c("days theo ngày lịch, ≥ 0", (a["days"], f["insights"][0]["days"], f["insights"][2]["days"]) == (7, 1, 0),
	(a["days"], f["insights"][0]["days"], f["insights"][2]["days"]))
c("mảng không thuộc nhóm (thoi-gian-thuc) → group None", ai._shape({"section": "thoi-gian-thuc"}, False)["group"]
	is None)

as_(ADMIN)
g = ai.get_feed()
# Quản trị: + E (quan-tri, rank 3), + F (bo-qua, rank 0, đỏ, 10/10 cũ hơn D 25/10 → F trước D)
c("quản trị: đúng tập + thứ tự", ids(g) == ["IB", "IA", "IE", "II", "IF", "ID", "IC", "IJ"], ids(g))
# counts chỉ trên đang mở: đỏ A E D = 3 (F bo-qua không đếm); vàng B I C J = 4
c("quản trị: counts", g["counts"] == {"do": 3, "vang": 4}, g["counts"])
c("quản trị: badge = counts", ai.get_badge() == {"do": 3, "vang": 4})
c("quản trị: khoá đúng 26 trường", all(set(x) == ADMIN_KEYS for x in g["insights"]))
ga = g["insights"][1]
c("quản trị: trường riêng của A", (ga["documents"], ga["admin_note"], ga["review_note"], ga["needs_check"],
	ga["signal_key"], ga["rule"], ga["mute_until"], ga["audience"], ga["sections_used"]) == (
	[{"doctype": "Sales Invoice", "name": "SI-1"}], "ghi chú A", "pb A", 0, "k.IA", "t.a", None, "lanh-dao",
	["cong-no"]), ga)
c("quản trị: sections_used nhiều dòng → list", g["insights"][0]["sections_used"] == ["tong-quan", "phai-tra"])
gc = ai.get_feed(closed=1)
# + G (dong 10/10 = 17 ngày trước ≤ 30; rank 0 vàng first_seen 01/09 → trước C); H (dong 20/09 = 37 ngày) không
c("quản trị closed=1: thêm dong ≤ 30 ngày", ids(gc) == ["IB", "IA", "IE", "II", "IF", "ID", "IG", "IC", "IJ"], ids(gc))
c("closed=1: counts không đổi (dong không mở)", gc["counts"] == {"do": 3, "vang": 4})

print("2. Bản tin")
as_(VIEWER)
b = f["brief"]
# lanh-dao đang mở của người xem: B A I D C J = 6; 5 đầu: B A I D C
c("bản tin: tiêu đề", b["title"] == "Sáng 27/10/2026: 6 việc cần chú ý", b["title"])
c("bản tin: 5 mục đầu", [x["id"] for x in b["items"]] == ["IB", "IA", "II", "ID", "IC"], b["items"])
c("bản tin: dạng mục", b["items"][1] == {"id": "IA", "title": "Tiêu đề IA", "severity": "do"}, b["items"][1])
c("bản tin: ngày", b["date"] == "2026-10-27")
# quản trị: E là quan-tri, F bo-qua → không vào bản tin; vẫn 6 việc
c("bản tin quản trị: bỏ quan-tri + bo-qua", g["brief"]["title"] == "Sáng 27/10/2026: 6 việc cần chú ý"
	and "IE" not in [x["id"] for x in g["brief"]["items"]])

print("3. Mảng ẩn")
single("BC Settings", hidden_sections="phai-tra")
as_(VIEWER)
# B có phai-tra trong sections_used (mảng chính tong-quan không ẩn) → mất
c("ẩn phai-tra: B (sections_used) biến mất với người xem", ids(ai.get_feed()) == ["IA", "II", "ID", "IC", "IJ"])
c("ẩn phai-tra: badge người xem bỏ B (vàng 4 → 3)", ai.get_badge() == {"do": 2, "vang": 3})
c("ẩn phai-tra: bản tin 5 việc", ai.get_feed()["brief"]["title"].endswith(": 5 việc cần chú ý"))
as_(ADMIN)
c("ẩn phai-tra: quản trị vẫn thấy B", "IB" in ids(ai.get_feed()))
single("BC Settings", hidden_sections="nhan-su")
as_(VIEWER)
# I: section nhan-su, sections_used trống → ẩn theo chính mảng của nó
c("ẩn nhan-su: I (mảng chính, sections_used trống) biến mất", ids(ai.get_feed()) == ["IB", "IA", "ID", "IC", "IJ"])
single("BC Settings", hidden_sections="tro-ly")
c("ẩn tro-ly: người xem get_feed → PermissionError", raises(ai.get_feed, frappe.PermissionError))
c("ẩn tro-ly: người xem get_badge → PermissionError", raises(ai.get_badge, frappe.PermissionError))
as_(ADMIN)
c("ẩn tro-ly: quản trị vẫn đọc", len(ids(ai.get_feed())) == 8)
single("BC Settings", hidden_sections="")
as_(VIEWER)
c("bỏ ẩn: 6 lại", len(ids(ai.get_feed())) == 6)

print("4. Không có insight")
frappe.db.sql(f"UPDATE `tab{INSIGHT}` SET audience = 'quan-tri' WHERE audience = 'lanh-dao'")
f0 = ai.get_feed()
c("người xem không còn gì: brief None, counts 0", (f0["brief"], f0["counts"], f0["insights"]) ==
	(None, {"do": 0, "vang": 0}, []), f0)
frappe.db.sql(f"UPDATE `tab{INSIGHT}` SET audience = 'lanh-dao' WHERE name != 'IE'")

print("5. meta")
m = ai.get_feed()["meta"]
c("chưa có lượt nào: last_run/last_ok None, stale", (m["last_run"], m["last_ok"], m["as_of"], m.get("stale")) ==
	(None, None, None, True), m)
c("ai_on: bật + có khoá", m["ai_on"] is True and m["running"] is False, m)
insert(RUN, "R1", run_type="ngay", step="tong", started=D(2026, 10, 26, 8, 0), finished=D(2026, 10, 26, 8, 30),
	status="ok", provider=None, cost_usd=0, tokens_in=0, tokens_out=0)
insert(RUN, "R2", run_type="ngay", step="tong", started=D(2026, 10, 27, 5, 30), finished=None, status="loi",
	error="chưa hoàn tất", cost_usd=0, tokens_in=0, tokens_out=0)
insert(RUN, "R3", run_type="ngay", step="kinh-doanh", run_id="R2", provider="claude", model=MODEL,
	started=D(2026, 10, 27, 6, 0), finished=D(2026, 10, 27, 6, 1), status="ok", cost_usd=0.5, cost_known=1,
	tokens_in=1000, tokens_out=200)
m = ai.get_feed()["meta"]
# last_run = started của dòng tong mới nhất (R2, dở dang); last_ok = finished của tong ok mới nhất (R1 08:30 26/10)
c("last_run / last_ok / as_of", (m["last_run"], m["last_ok"], m["as_of"]) == (D(2026, 10, 27, 5, 30),
	D(2026, 10, 26, 8, 30), D(2026, 10, 26, 8, 30)), m)
# 27/10 10:30 − 26/10 08:30 = 26 giờ đúng → chưa cũ (cũ = HƠN 26 giờ)
c("stale: đúng 26 giờ → chưa cũ", m.get("stale") is False)
frappe.utils.FAKE_NOW_TIME = datetime.time(10, 30, 1)
c("stale: 26 giờ 1 giây → cũ", ai.get_feed()["meta"].get("stale") is True)
frappe.utils.FAKE_NOW_TIME = datetime.time(10, 30, 0)
single("BC Settings", ai_enabled=0)
c("ai_on: tắt → False", ai.get_feed()["meta"]["ai_on"] is False)
single("BC Settings", ai_enabled=1)
frappe.conf.pop("bc_ai_anthropic_key")
c("ai_on: không khoá → False", ai.get_feed()["meta"]["ai_on"] is False)
frappe.conf["bc_ai_anthropic_key"] = SECRET
frappe.cache().set_value(jobs.LOCK_KEY, 1)
c("running: khoá chạy → True", ai.get_feed()["meta"]["running"] is True)
frappe.cache().delete_value(jobs.LOCK_KEY)

print("5b. Thẻ cũ (stale): lượt ok gần nhất không làm mới")
# Lượt tổng ok mới nhất = R1 started 26/10 08:00 (R2 27/10 05:30 là loi — không tính).
frappe.db.sql(f"UPDATE `tab{INSIGHT}` SET last_seen = %s WHERE name = 'IC'", (D(2026, 10, 25, 5, 30),))
frappe.db.sql(f"UPDATE `tab{INSIGHT}` SET last_seen = %s WHERE name = 'IJ'", (D(2026, 10, 26, 8, 0),))
frappe.db.sql(f"UPDATE `tab{INSIGHT}` SET last_seen = %s WHERE name = 'ID'", (D(2026, 10, 26, 9, 0),))
frappe.db.sql(f"UPDATE `tab{INSIGHT}` SET last_seen = %s WHERE name IN ('IF', 'IG')", (D(2026, 10, 1, 5, 30),))
as_(VIEWER)
fs = ai.get_feed()
sv = {x["id"]: x.get("stale") for x in fs["insights"]}
# IC 25/10 < 26/10 08:00 → cũ; IJ = đúng started → chưa cũ; ID 26/10 09:00 (sau R1, trước R2 loi) → chưa cũ
c("stale: last_seen trước started lượt ok mới nhất → True, bằng / sau → False",
	sv == {"IB": False, "IA": False, "II": False, "ID": False, "IC": True, "IJ": False}, sv)
c("stale: meta.stale_count người xem = 1", fs["meta"].get("stale_count") == 1, fs["meta"])
as_(ADMIN)
ga5 = ai.get_feed(closed=1)
sa = {x["id"]: x.get("stale") for x in ga5["insights"]}
# IF bo-qua, IG dong: last_seen cũ nhưng không mở → không stale
c("stale quản trị: chỉ IC; bo-qua / dong không tính", [k for k, v in sa.items() if v] == ["IC"]
	and sa["IF"] is False and sa["IG"] is False and ga5["meta"].get("stale_count") == 1, sa)
c("stale: set_status trả cùng cờ", ai.set_status("IC", "dang-xu-ly").get("stale") is True
	and ai.set_status("IC", "bo-qua").get("stale") is False)
ai.set_status("IC", "mo")
single("BC Settings", hidden_sections="ton-kho")
as_(VIEWER)
c("stale_count đếm sau lọc mảng ẩn (IC ton-kho ẩn → 0)", ai.get_feed()["meta"].get("stale_count") == 0)
single("BC Settings", hidden_sections="")
as_(ADMIN)
c("stale_count quản trị vẫn 1 khi ẩn mảng (quản trị thấy hết)", ai.get_feed()["meta"].get("stale_count") == 1)
insert(RUN, "R0", run_type="ngay", step="tong", started=D(2026, 10, 25, 5, 0), finished=D(2026, 10, 25, 5, 10),
	status="ok", provider=None, cost_usd=0, tokens_in=0, tokens_out=0)
c("so với lượt ok MỚI NHẤT (R1), không phải lượt ok cũ hơn", ai.get_feed()["meta"].get("stale_count") == 1)
frappe.db.sql(f"DELETE FROM `tab{RUN}` WHERE name = 'R0'")
frappe.db.sql(f"UPDATE `tab{INSIGHT}` SET last_seen = %s WHERE name IN ('IC', 'IJ', 'ID', 'IF', 'IG')",
	(D(2026, 10, 27, 5, 30),))
c("làm mới lại → không còn stale", ai.get_feed(closed=1)["meta"].get("stale_count") == 0)

print("6. Người xem bị chặn mọi method quản trị (§9.9)")
as_(VIEWER)
for name, fn, args in (("get_admin", ai.get_admin, ()), ("run_now", ai.run_now, ()),
		("set_status", ai.set_status, ("IA", "mo")), ("set_rule", ai.set_rule, ("t.a",)),
		("test_connection", ai.test_connection, ("claude",))):
	c(f"người xem {name} → PermissionError", raises(fn, frappe.PermissionError, *args))
c("người xem không làm đổi gì (A vẫn mo)", frappe.db.get_value(INSIGHT, "IA", "status") == "mo")
as_("Guest")
c("Guest get_feed → PermissionError", raises(ai.get_feed, frappe.PermissionError))

print("7. get_admin")
as_(ADMIN)
ad = ai.get_admin()
c("khoá: chỉ có / không", ad["keys"] == {"claude": True, "openai": False}, ad["keys"])
c("enabled + models", ad["enabled"] is True and ad["models"] == {"claude": MODEL, "claude_deep": "claude-opus-5-5",
	"openai": ""}, ad["models"])
# spent = R3 0.5 (claude, từ 01/10); calls_today = 1 (R3 step nhóm, ok, hôm nay); giá đã khai; trần 50
# openai: chưa có dòng Run nào, trần mặc định 90, model trống → price_known False
c("budget claude + openai", ad["budget"] == {"claude": {"spent": 0.5, "cap": 50.0, "cycle_start": datetime.date(2026, 10, 1),
	"calls_today": 1, "max_calls": 30, "price_known": True}, "openai": {"spent": 0.0, "cap": 90.0,
	"cycle_start": datetime.date(2026, 10, 1), "calls_today": 0, "max_calls": 30, "price_known": False}}, ad["budget"])
c("runs: mới trước, đúng trường (+ step_label)", [r["started"] for r in ad["runs"]] == [D(2026, 10, 27, 6, 0),
	D(2026, 10, 27, 5, 30), D(2026, 10, 26, 8, 0)] and set(ad["runs"][0]) == set(ai.RUN_FIELDS) | {"step_label"},
	ad["runs"][:1])
c("runs: R3 đủ số", (ad["runs"][0]["provider"], ad["runs"][0]["tokens_in"], ad["runs"][0]["cost_usd"],
	ad["runs"][0]["run_id"]) == ("claude", 1000, 0.5, "R2"))
c("rules: đúng thứ tự đăng ký", [r["key"] for r in ad["rules"]] == ["t.a", "t.b", "t.c"])
# t.a: đang mở A (mo) + D (mo) = 2; F bo-qua không đếm
c("rules: t.a đủ trường", ad["rules"][0] == {"key": "t.a", "label": "Quá hạn", "section": "cong-no",
	"section_label": "Phải thu", "audience": "lanh-dao", "unit": "%", "lower": False, "vang_default": 10,
	"do_default": 20, "vang": 10, "do": 20, "disabled": False, "open": 2}, ad["rules"][0])
c("rules: t.b lower, không đỏ, 0 mở", (ad["rules"][1]["lower"], ad["rules"][1]["do"], ad["rules"][1]["open"],
	ad["rules"][1]["label"]) == (True, None, 0, "Tồn"))
c("rules: t.c label mặc định = key, quan-tri", (ad["rules"][2]["label"], ad["rules"][2]["audience"],
	ad["rules"][2]["section_label"]) == ("t.c", "quan-tri", "Hệ thống"))
# needs_check: I (mo) có; F (bo-qua) có nhưng không mở → chỉ I
c("rejected: chỉ nhận định MỞ cần kiểm", [x["id"] for x in ad["rejected"]] == ["II"]
	and set(ad["rejected"][0]) == ADMIN_KEYS)
c("muted: bo-qua", [x["id"] for x in ad["muted"]] == ["IF"])
c("settings_url", ad["settings_url"] == "/app/bc-settings")
c("running False", ad["running"] is False)
for i in range(22):
	insert(RUN, f"RX{i:02d}", run_type="ngay", step="tong", started=D(2026, 9, 1, 0, i), status="ok", cost_usd=0,
		tokens_in=0, tokens_out=0)
ad = ai.get_admin()
c("runs: tối đa 20, vẫn mới nhất trước", len(ad["runs"]) == 20 and ad["runs"][0]["started"] == D(2026, 10, 27, 6, 0))
c("không lộ khoá trong get_admin", SECRET not in json.dumps(ad, default=str))

print("8. set_rule")
VE = frappe.ValidationError
c("rule_key lạ → lỗi", raises(ai.set_rule, VE, "khong.co", threshold=1))
c("disabled lạ → lỗi", raises(ai.set_rule, VE, "t.a", disabled="maybe"))
c("ngưỡng âm → lỗi", raises(ai.set_rule, VE, "t.a", threshold=-1))
c("ngưỡng chữ → lỗi", raises(ai.set_rule, VE, "t.a", threshold_red="abc"))


def rule_rows():
	return frappe.db.sql("SELECT rule_key, disabled, threshold, threshold_red, idx, parent, parenttype, parentfield "
		"FROM `tabBC AI Rule` ORDER BY idx", as_dict=True)


c("lỗi không ghi gì", rule_rows() == [])
frappe.DOC_CACHE_CLEARED.clear()
r = ai.set_rule("t.a", threshold="15")
rows = rule_rows()
c("thêm dòng mới idx 1, đúng cha", len(rows) == 1 and (rows[0].idx, rows[0].parent, rows[0].parenttype,
	rows[0].parentfield, rows[0].threshold, rows[0].disabled) == (1, "BC Settings", "BC Settings", "ai_rules", 15, 0),
	rows)
c("trả quy tắc dạng get_admin: vàng 15, đỏ mặc định 20", (r["key"], r["vang"], r["do"], r["vang_default"],
	r["disabled"], r["open"]) == ("t.a", 15, 20, 10, False, 2), r)
c("xoá cache BC Settings", ("BC Settings", "BC Settings") in frappe.DOC_CACHE_CLEARED)
r = ai.set_rule("t.a", disabled="true")
rows = rule_rows()
c("cập nhật: vẫn 1 dòng, chỉ đổi disabled", len(rows) == 1 and (rows[0].disabled, rows[0].threshold) == (1, 15)
	and r["disabled"] is True and r["vang"] == 15, rows)
r = ai.set_rule("t.a", threshold=0, disabled=0, threshold_red=25)
c("ngưỡng 0 = về mặc định; bật lại; đỏ 25", (r["vang"], r["do"], r["disabled"]) == (10, 25, False), r)
r = ai.set_rule("t.b", threshold_red="3.5")
rows = rule_rows()
c("quy tắc thứ hai → dòng idx 2", [(x.rule_key, x.idx, x.threshold_red) for x in rows] == [("t.a", 1, 25), ("t.b", 2,
	3.5)] and r["do"] == 3.5, rows)
c("get_admin thấy ghi đè", ai.get_admin()["rules"][0]["do"] == 25)
_gm = frappe.get_meta
frappe.get_meta = lambda dt, cached=True: types.SimpleNamespace(has_field=lambda f: False)
try:
	c("chưa migrate (không có ai_rules) → lỗi, không ghi", raises(ai.set_rule, VE, "t.c", threshold=1)
		and len(rule_rows()) == 2)
finally:
	frappe.get_meta = _gm

print("9. set_status")
c("status lạ → lỗi", raises(ai.set_status, VE, "IA", "xyz"))
c("status dong (tay) → lỗi", raises(ai.set_status, VE, "IA", "dong"))
c("insight không có → lỗi", raises(ai.set_status, VE, "KHONG-CO", "mo"))
c("insight đã dong → lỗi", raises(ai.set_status, VE, "IG", "mo"))
c("mute_days 0 → lỗi", raises(ai.set_status, VE, "IA", "bo-qua", mute_days=0))
c("mute_days 366 → lỗi", raises(ai.set_status, VE, "IA", "bo-qua", mute_days="366"))
c("mute_days chữ → lỗi", raises(ai.set_status, VE, "IA", "bo-qua", mute_days="abc"))
c("lỗi không đổi gì", frappe.db.get_value(INSIGHT, "IA", "status") == "mo")
s = ai.set_status("IA", "bo-qua", mute_days="7")
# 27/10 + 7 = 03/11
c("bo-qua 7 ngày → mute_until 03/11, dạng quản trị", (s["status"], s["mute_until"], s["admin_note"]) ==
	("bo-qua", datetime.date(2026, 11, 3), "ghi chú A") and set(s) == ADMIN_KEYS, s)
as_(VIEWER)
c("bo-qua: người xem không còn thấy A", "IA" not in ids(ai.get_feed()))
as_(ADMIN)
s = ai.set_status("IA", "bo-qua", mute_days=365)
# 27/10/2026 + 365 = 27/10/2027
c("365 ngày được", s["mute_until"] == datetime.date(2027, 10, 27), s["mute_until"])
s = ai.set_status("IA", "bo-qua", mute_days="", note="")
c("mute_days trống → bỏ qua hẳn; note '' xoá ghi chú", (s["mute_until"], s["admin_note"]) == (None, ""), s)
ai.set_status("IA", "bo-qua", mute_days=30)
s = ai.set_status("IA", "dang-xu-ly", mute_days=30, note="x" * 600)
c("dang-xu-ly: xoá mute_until (bỏ qua mute_days); note cắt 500", (s["status"], s["mute_until"],
	len(s["admin_note"])) == ("dang-xu-ly", None, 500), (s["status"], s["mute_until"]))
s = ai.set_status("IA", "mo")
c("mo: note None giữ ghi chú", (s["status"], len(s["admin_note"])) == ("mo", 500))
c("dòng DB khớp", frappe.db.get_value(INSIGHT, "IA", ["status", "mute_until"], as_dict=True) ==
	{"status": "mo", "mute_until": None})
s = ai.set_status("IF", "mo")
c("bo-qua → mo xoá hạn", s["status"] == "mo" and s["mute_until"] is None)

print("10. run_now")
frappe.ENQUEUED.clear()
background_jobs.FAKE_ENQUEUED_IDS.clear()
c("run_now → queued", ai.run_now() == {"queued": True})
c("xếp run_daily run_type tay", frappe.ENQUEUED[-1][0] == "bc.ai.pipeline.run_daily"
	and frappe.ENQUEUED[-1][2] == {"run_type": "tay"}, frappe.ENQUEUED)
frappe.cache().set_value(jobs.LOCK_KEY, 1)
c("đang chạy → ValidationError, không xếp thêm", raises(ai.run_now, VE) and len(frappe.ENQUEUED) == 1)
frappe.cache().delete_value(jobs.LOCK_KEY)

print("11. test_connection")
c("provider lạ → lỗi", raises(ai.test_connection, VE, "gemini"))
store.calls.clear()
frappe.conf.pop("bc_ai_anthropic_key")
t = ai.test_connection("claude")
c("không khoá → khong-khoa", t == {"ok": False, "model": MODEL, "error": "chưa có khoá"}, t)
c("không khoá: Run ghi tay/test + khong-khoa, không gọi mô hình", store.calls[0] == ("start", {"run_type": "tay",
	"step": "test", "provider": "claude", "model": MODEL}) and store.calls[1][1]["status"] == "khong-khoa", store.calls)
frappe.conf["bc_ai_anthropic_key"] = SECRET
store.calls.clear()
single("BC Settings", ai_cap_claude_usd=0.4)   # đã chi 0.5 ≥ 0.4 → vượt trần
t = ai.test_connection("claude")
c("vượt trần → vuot-tran, không gọi", t["ok"] is False and store.calls[-1][1]["status"] == "vuot-tran"
	and store.calls[0][1]["step"] == "test", store.calls)
single("BC Settings", ai_cap_claude_usd=50)
store.calls.clear()
set_call(lambda *a, **k: {"data": {"ok": True}, "tokens_in": 100, "tokens_out": 50, "model": MODEL})
t = ai.test_connection("claude")
c("gọi được → ok", t == {"ok": True, "model": MODEL, "error": ""}, t)
a_, k_ = LLM_CALLS[-1]
c("gọi đúng provider / model / schema / max_tokens 2048", (a_[0], a_[1], a_[5], k_.get("max_tokens")) == ("claude",
	MODEL, {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"],
	"additionalProperties": False}, 2048), (a_[:2], k_))
fin = store.calls[-1][1]
# cost = (100×3 + 50×15) / 1e6 = 1050 / 1e6 = 0.00105
single("BC Settings", ai_claude_model="")
ad0 = ai.get_admin()
# ô model trống → bc.ai.daily_model() = model mặc định (đúng model lượt chạy gọi) → có giá
c("model trống: get_admin models.claude = mặc định, price_known theo mặc định",
	(ad0["models"]["claude"], ad0["budget"]["claude"]["price_known"]) == (bc.ai.DEFAULT_CLAUDE_MODEL, True),
	(ad0["models"], ad0["budget"]))
LLM_CALLS.clear()
t0 = ai.test_connection("claude")
c("model trống: Thử kết nối gọi model mặc định", (t0["model"], LLM_CALLS[-1][0][1] if LLM_CALLS else None,
	store.calls[-2][1]["model"]) == (bc.ai.DEFAULT_CLAUDE_MODEL,) * 3, (t0, store.calls[-2:]))
single("BC Settings", ai_claude_model="claude-khac-1")
ad0 = ai.get_admin()
c("model khác chưa khai giá → price_known False", (ad0["models"]["claude"], ad0["budget"]["claude"]["price_known"]) ==
	("claude-khac-1", False))
single("BC Settings", ai_claude_model=MODEL)
c("Run ok: tokens + chi phí", (fin["status"], fin["tokens_in"], fin["tokens_out"], fin["cost_usd"], fin["name"]) ==
	("ok", 100, 50, 0.00105, "RUN-1"), fin)


def loi_credit(*a, **k):
	e = llm.LLMError("credit", f"hết credit, khoá {SECRET} bị từ chối")
	e.tokens_in, e.tokens_out, e.model = 7, 3, MODEL
	raise e


store.calls.clear()
set_call(loi_credit)
t = ai.test_connection("claude")
fin = store.calls[-1][1]
# cost = (7×3 + 3×15)/1e6 = 66/1e6 = 0.000066
c("LLMError credit → het-credit, tokens của lượt hỏng", (t["ok"], fin["status"], fin["tokens_in"], fin["tokens_out"],
	fin["cost_usd"]) == (False, "het-credit", 7, 3, 0.000066), (t, fin))
c("lỗi không lộ khoá (trả về + Run.error)", SECRET not in json.dumps(t) and SECRET not in str(fin["error"])
	and "hết credit" in t["error"], (t, fin))
set_call(lambda *a, **k: (_ for _ in ()).throw(llm.LLMError("schema", "sai cấu trúc")))
t = ai.test_connection("claude")
c("LLMError schema → Run loi", store.calls[-1][1]["status"] == "loi" and t["ok"] is False)
set_call(lambda *a, **k: {"data": {"ok": False}, "tokens_in": 1, "tokens_out": 1, "model": "claude-x"})
t = ai.test_connection("claude")
c("mô hình trả ok false → ok False, model thực trả lời", (t["ok"], t["model"]) == (False, "claude-x"), t)
store.calls.clear()
t = ai.test_connection("openai")
c("openai không khoá → khong-khoa, model trống", (t["ok"], t["model"], store.calls[-1][1]["status"]) ==
	(False, "", "khong-khoa"), t)
frappe.conf["bc_ai_openai_key"] = "sk-proj-GIAthuOpenAI0123456789abcdef"
store.calls.clear()
LLM_CALLS.clear()
t = ai.test_connection("openai")
c("openai có khoá, model trống → báo chưa đặt model, không gọi, không ghi Run", (t["ok"], t["model"], "chưa đặt model"
	in t["error"], LLM_CALLS, store.calls) == (False, "", True, [], []), (t, store.calls))
frappe.conf.pop("bc_ai_openai_key")

print("12. Lộ khoá: không method nào trả khoá (§9.8)")
llm.call = call_cam
out = []
as_(ADMIN)
out += [ai.get_feed(), ai.get_feed(closed=1), ai.get_badge(), ai.get_admin(), ai.set_status("IB", "dang-xu-ly"),
	ai.set_rule("t.c", threshold=2)]
set_call(loi_credit)
out.append(ai.test_connection("claude"))
background_jobs.FAKE_ENQUEUED_IDS.clear()
out.append(ai.run_now())
as_(VIEWER)
out += [ai.get_feed(), ai.get_badge()]
c("khoá không có trong mọi kết quả", all(SECRET not in json.dumps(x, default=str) for x in out))
c("khoá không có trong tham số finish_run / log_error", SECRET not in json.dumps(store.calls, default=str)
	and SECRET not in json.dumps(frappe.LOGGED, default=str))
# Khoá dán lẫn xuống dòng: máy chủ coi như chưa có khoá nhưng màn quản trị phải nói đúng lý do, không lộ mảnh khoá nào
print("12. khoá khai sai dạng")
as_(ADMIN)
DAU, DUOI = SECRET[:12], "Tk9RvDUOIkhoaBIMAT0123456789"
frappe.conf["bc_ai_anthropic_key"] = DAU + "\n" + DUOI
store.calls.clear()
LLM_CALLS.clear()
set_call(lambda *a, **k: {"data": {"ok": True}, "tokens_in": 1, "tokens_out": 1, "model": MODEL})
ad2 = ai.get_admin()
c("khoá sai dạng: keys.claude False, keys_bad.claude True", ad2["keys"]["claude"] is False
	and ad2["keys_bad"] == {"claude": True, "openai": False}, (ad2["keys"], ad2.get("keys_bad")))
t = ai.test_connection("claude")
c("khoá sai dạng: Thử kết nối nói rõ lý do, không gọi mô hình", t == {"ok": False, "model": MODEL,
	"error": ai.KHOA_SAI_DANG} and not LLM_CALLS and "sai dạng" in ai.KHOA_SAI_DANG, (t, len(LLM_CALLS)))
c("khoá sai dạng: Run khong-khoa, cùng lời", store.calls[-1][1]["status"] == "khong-khoa"
	and store.calls[-1][1]["error"] == ai.KHOA_SAI_DANG, store.calls)
c("khoá sai dạng: không mảnh khoá nào trong kết quả / Run / log", all(m not in json.dumps([ad2, t, store.calls,
	frappe.LOGGED], default=str) for m in (DAU, DUOI)))
frappe.conf["bc_ai_anthropic_key"] = SECRET
ad3 = ai.get_admin()
c("khoá đúng dạng: keys_bad đều False", ad3["keys"]["claude"] is True
	and ad3["keys_bad"] == {"claude": False, "openai": False}, ad3.get("keys_bad"))
frappe.conf.pop("bc_ai_anthropic_key")
c("không khai khoá: keys_bad False (chưa có ≠ sai dạng)", ai.get_admin()["keys_bad"]["claude"] is False)
frappe.conf["bc_ai_anthropic_key"] = SECRET


print("13. P2 — bản tin tuần / tháng trong get_feed")
as_(ADMIN)
single("BC Settings", hidden_sections="")
c("chưa có bản tin → briefs []", ai.get_feed()["briefs"] == [])
as_(VIEWER)
c("chưa có bản tin → briefs [] (người xem)", ai.get_feed()["briefs"] == [])
ALL3 = ["tong-quan", "ton-kho", "cong-no"]
# Tuần 19/10–25/10 (brief_date thứ Hai 26/10 = 1 ngày trước 27/10); bản cũ hơn 12/10 cùng loại không được chọn
store_that.upsert_brief("tuan", datetime.date(2026, 10, 12), title="Tuần cũ", source="quy-tac", sections_used=["cong-no"],
	period_from=datetime.date(2026, 10, 5), period_to=datetime.date(2026, 10, 11),
	parts=[{"key": "dang_chu_y", "title": "Điều đáng chú ý", "items": [{"text": "Mục tuần cũ", "sections": ["cong-no"]}]}])
store_that.upsert_brief("tuan", datetime.date(2026, 10, 26), title="Doanh số tuần chững lại", source="ai",
	model="claude-opus-5-5", sections_used=ALL3, period_from=datetime.date(2026, 10, 19),
	period_to=datetime.date(2026, 10, 25), parts=[
		{"key": "dang_chu_y", "title": "Điều đáng chú ý", "items": [{"text": "Doanh số giảm nhẹ", "sections": ALL3},
			{"text": "Tồn kho tăng", "sections": ALL3}]},
		{"key": "viec_ton", "title": "Việc tồn chưa xử lý", "items": [{"text": "Công nợ quá hạn kéo dài", "sections": ALL3}]},
		{"key": "uu_tien", "title": "Ưu tiên tuần tới", "items": []}])
# Tháng 9 (brief_date 01/10 = 26 ngày trước) — bản quy tắc, mỗi mục chỉ mang mảng của nó
store_that.upsert_brief("thang", datetime.date(2026, 10, 1), title="Tháng 9: phải trả tăng", source="quy-tac",
	sections_used=["tong-quan", "phai-tra", "cong-no"], period_from=datetime.date(2026, 9, 1),
	period_to=datetime.date(2026, 9, 30), parts=[
		{"key": "dang_chu_y", "title": "Điều đáng chú ý", "items": [{"text": "Doanh số tháng tăng", "sections": ["tong-quan"]},
			{"text": "Phải trả tăng", "sections": ["phai-tra"]}]},
		{"key": "viec_ton", "title": "Việc tồn chưa xử lý", "items": [{"text": "Hoá đơn NCC chưa đối chiếu", "sections": ["phai-tra"]}]},
		{"key": "uu_tien", "title": "Ưu tiên tháng tới", "items": [{"text": "Thu nợ quá hạn", "sections": ["cong-no"]}]}])
BV_KEYS = {"type", "date", "period_from", "period_to", "title", "source", "parts"}


def keys_deep(x):
	if isinstance(x, dict):
		return set(x) | set().union(*(keys_deep(v) for v in x.values())) if x else set()
	if isinstance(x, list):
		return set().union(*(keys_deep(v) for v in x)) if x else set()
	return set()


bv = ai.get_feed()["briefs"]
c("người xem: tuần mới nhất rồi tháng (một bản mỗi loại)", [(b["type"], b["date"]) for b in bv] == [("tuan", "2026-10-26"),
	("thang", "2026-10-01")], bv)
c("người xem: đúng 7 khoá, không model / sections ở bất kỳ mức nào", all(set(b) == BV_KEYS for b in bv)
	and not keys_deep(bv) & {"model", "sections", "sections_used"}, [sorted(keys_deep(b)) for b in bv])
w = bv[0]
c("tuần: kỳ, tiêu đề, nguồn, mục là chữ thuần, phần rỗng bị bỏ", (w["period_from"], w["period_to"], w["title"],
	w["source"], w["parts"]) == ("2026-10-19", "2026-10-25", "Doanh số tuần chững lại", "ai", [
	{"key": "dang_chu_y", "title": "Điều đáng chú ý", "items": ["Doanh số giảm nhẹ", "Tồn kho tăng"]},
	{"key": "viec_ton", "title": "Việc tồn chưa xử lý", "items": ["Công nợ quá hạn kéo dài"]}]), w)
c("tháng: đủ ba phần khi không ẩn mảng", [len(p["items"]) for p in bv[1]["parts"]] == [2, 1, 1]
	and bv[1]["title"] == "Tháng 9: phải trả tăng", bv[1])
c("bản tin ngày (brief) không đổi dạng", set(ai.get_feed()["brief"]) == {"title", "date", "items"})
as_(ADMIN)
ba = ai.get_feed()["briefs"]
c("quản trị: thêm model + sections_used", [set(b) for b in ba] == [BV_KEYS | {"model", "sections_used"}] * 2
	and (ba[0]["model"], ba[0]["sections_used"], ba[1]["model"]) == ("claude-opus-5-5", ALL3, ""), ba)
c("quản trị: mục cũng là chữ (không sections từng mục)", all(isinstance(t, str) for b in ba for p in b["parts"]
	for t in p["items"]))
single("BC Settings", hidden_sections="phai-tra")
as_(VIEWER)
bv = ai.get_feed()["briefs"]
m9 = bv[1] if len(bv) == 2 else {}
# tháng: bỏ "Phải trả tăng" + cả phần viec_ton (chỉ có mục phai-tra); tiêu đề → tiêu đề trung tính của kỳ
c("ẩn phai-tra: mục dùng mảng ẩn bị bỏ, phần rỗng bị bỏ", m9.get("parts") == [
	{"key": "dang_chu_y", "title": "Điều đáng chú ý", "items": ["Doanh số tháng tăng"]},
	{"key": "uu_tien", "title": "Ưu tiên tháng tới", "items": ["Thu nợ quá hạn"]}], m9)
c("ẩn phai-tra: tiêu đề (dựng trên mọi mảng) → tiêu đề trung tính 'Bản tin tháng 9/2026'",
	m9.get("title") == "Bản tin tháng 9/2026", m9.get("title"))
c("ẩn phai-tra: không chữ nào của mục ẩn trong kết quả người xem", "Phải trả" not in json.dumps(bv, ensure_ascii=False)
	and "Hoá đơn NCC" not in json.dumps(bv, ensure_ascii=False))
c("ẩn phai-tra: bản tuần nguyên vẹn", bv[0]["title"] == "Doanh số tuần chững lại" and len(bv[0]["parts"]) == 2)
as_(ADMIN)
c("ẩn phai-tra: quản trị vẫn thấy đủ", [len(p["items"]) for p in ai.get_feed()["briefs"][1]["parts"]] == [2, 1, 1])
single("BC Settings", hidden_sections="ton-kho")
as_(VIEWER)
bv = ai.get_feed()["briefs"]
c("ẩn ton-kho: bản tuần AI (mọi mục mang ton-kho) vắng hẳn, tháng còn", [b["type"] for b in bv] == ["thang"], bv)
single("BC Settings", hidden_sections="tong-quan\ncong-no\nphai-tra")
c("mọi mục tháng bị ẩn → bản tháng vắng", [b["type"] for b in ai.get_feed()["briefs"]] == [], ai.get_feed()["briefs"])
single("BC Settings", hidden_sections="")
# Hạn hiển thị: tuần ≤ 14 ngày, tháng ≤ 45 ngày (theo brief_date, ngày lịch)
B = "BC AI Brief"
frappe.db.sql(f"UPDATE `tab{B}` SET brief_date = %s WHERE brief_key = 'tuan:2026-10-26'", (datetime.date(2026, 10, 13),))
frappe.db.sql(f"UPDATE `tab{B}` SET brief_date = %s WHERE brief_key = 'thang:2026-10-01'", (datetime.date(2026, 9, 12),))
c("tuần 14 ngày + tháng 45 ngày → còn hiện", [b["type"] for b in ai.get_feed()["briefs"]] == ["tuan", "thang"])
frappe.db.sql(f"UPDATE `tab{B}` SET brief_date = %s WHERE brief_key = 'tuan:2026-10-26'", (datetime.date(2026, 10, 12),))
frappe.db.sql(f"DELETE FROM `tab{B}` WHERE brief_key = 'tuan:2026-10-12'")
frappe.db.sql(f"UPDATE `tab{B}` SET brief_date = %s WHERE brief_key = 'thang:2026-10-01'", (datetime.date(2026, 9, 11),))
c("tuần 15 ngày + tháng 46 ngày → không hiện", ai.get_feed()["briefs"] == [], ai.get_feed()["briefs"])
as_(ADMIN)
c("quá hạn: quản trị cũng không thấy ở #/tro-ly", ai.get_feed()["briefs"] == [])
frappe.db.sql(f"UPDATE `tab{B}` SET brief_date = %s WHERE brief_key = 'tuan:2026-10-26'", (datetime.date(2026, 10, 26),))
frappe.db.sql(f"UPDATE `tab{B}` SET brief_date = %s WHERE brief_key = 'thang:2026-10-01'", (datetime.date(2026, 10, 1),))
store_that.upsert_brief("tuan", datetime.date(2026, 10, 27), title="Rỗng", source="quy-tac", sections_used=[],
	parts=[{"key": "dang_chu_y", "title": "Điều đáng chú ý", "items": []}])
c("bản tin mới nhất không có mục nào → vắng (cả quản trị)", [b["type"] for b in ai.get_feed()["briefs"]] == ["thang"])
frappe.db.sql(f"DELETE FROM `tab{B}` WHERE brief_key = 'tuan:2026-10-27'")

print("14. P2 — nhóm Kiểm soát")
ins("KS1", rule="ct.huy_nhieu", section="tro-ly", sections_used="tro-ly", route="#/tro-ly", severity="vang", rank=0,
	documents=json.dumps([{"doctype": "Sales Invoice", "name": "SI-9"}]), title="Huỷ chứng từ tăng")
as_(VIEWER)
fv = ai.get_feed()
k = next((x for x in fv["insights"] if x["id"] == "KS1"), None)
c("kiểm soát (người xem): group kiem-soat, nhãn 'Kiểm soát', route trống, không chứng từ", k is not None and (k["group"],
	k["group_label"], k["section_label"], k["route"]) == ("kiem-soat", "Kiểm soát", "Kiểm soát", "")
	and set(k) == VIEW_KEYS, k)
as_(ADMIN)
ka = next(x for x in ai.get_feed()["insights"] if x["id"] == "KS1")
c("kiểm soát (quản trị): chứng từ có, route trống", ka["documents"] == [{"doctype": "Sales Invoice", "name": "SI-9"}]
	and ka["route"] == "" and ka["section_label"] == "Kiểm soát", ka)
c("set_status trả cùng dạng kiểm soát", ai.set_status("KS1", "dang-xu-ly")["section_label"] == "Kiểm soát")
c("nhóm không phải kiểm soát giữ route của nó", ai._shape({"section": "cong-no", "route": "#/cong-no"}, False)["route"]
	== "#/cong-no")
frappe.db.sql(f"DELETE FROM `tab{INSIGHT}` WHERE name = 'KS1'")

print("15. P2 — get_admin: bản tin, phản biện, OpenAI")
as_(ADMIN)
single("BC Settings", ai_openai_model="gpt-5-x", ai_cap_openai_usd=20, ai_cycle_day_openai=1)
child("BC Settings", "BC Settings", "BC AI Model Price", "ai_prices", [{"model": "gpt-5-x", "price_in": 1, "price_out": 4}])
frappe.clear_document_cache("BC Settings", "BC Settings")
insert(RUN, "RV1", run_type="ngay", step="review:kinh-doanh", run_id="R2", provider="openai", model="gpt-5-x",
	started=D(2026, 10, 27, 7, 0), finished=D(2026, 10, 27, 7, 1), status="ok", cost_usd=0.2, cost_known=1,
	tokens_in=900, tokens_out=100, insights_ai=2, rejected=1)
insert(RUN, "RV2", run_type="ngay", step="review:kiem-soat", run_id="R2", provider="openai", model="gpt-5-x",
	started=D(2026, 10, 27, 7, 2), finished=D(2026, 10, 27, 7, 2), status="khong-khoa", cost_usd=0, tokens_in=0,
	tokens_out=0)
insert(RUN, "RB1", run_type="tuan", step="ban-tin:tuan", provider="claude", model="claude-opus-5-5",
	started=D(2026, 10, 27, 7, 5), finished=D(2026, 10, 27, 7, 6), status="ok", cost_usd=0.3, cost_known=1,
	tokens_in=10, tokens_out=10)
insert(RUN, "RB2", run_type="thang", step="ban-tin:thang", provider="claude", started=D(2026, 10, 27, 7, 6),
	finished=D(2026, 10, 27, 7, 6), status="tat", cost_usd=0, tokens_in=0, tokens_out=0)
ad = ai.get_admin()
c("step_label từng loại", (ai._step_label("review:kinh-doanh"), ai._step_label("review:kiem-soat"),
	ai._step_label("ban-tin:tuan"), ai._step_label("ban-tin:thang"), ai._step_label("tong"), ai._step_label("ai"),
	ai._step_label("test"), ai._step_label("kho-sx"), ai._step_label("la")) == ("Phản biện · Kinh doanh",
	"Phản biện · Kiểm soát", "Bản tin tuần", "Bản tin tháng", "Tổng hợp", "Bước AI", "Thử kết nối", "Kho & SX", "la"))
c("runs: 4 dòng mới (phản biện, bản tin) đứng đầu, đúng nhãn", [(r["step"], r["step_label"]) for r in ad["runs"][:4]] == [
	("ban-tin:thang", "Bản tin tháng"), ("ban-tin:tuan", "Bản tin tuần"), ("review:kiem-soat", "Phản biện · Kiểm soát"),
	("review:kinh-doanh", "Phản biện · Kinh doanh")], [(r["step"], r["step_label"]) for r in ad["runs"][:4]])
# openai: spent 0.2 (RV1; RV2 0), calls_today 1 (RV1 ok; RV2 khong-khoa không gọi mạng), trần 20, giá đã khai
c("budget openai như Claude", ad["budget"]["openai"] == {"spent": 0.2, "cap": 20.0,
	"cycle_start": datetime.date(2026, 10, 1), "calls_today": 1, "max_calls": 30, "price_known": True}, ad["budget"]["openai"])
c("models.openai = model đang đặt", ad["models"]["openai"] == "gpt-5-x")
# Bản tin quản trị: tuần 26/10 (AI, 3 mục) + tháng 01/10 (quy tắc, 4 mục) — mới trước
c("briefs quản trị: loại, ngày, kỳ, nguồn, model, số mục", ad["briefs"] == [
	{"type": "tuan", "date": "2026-10-26", "period_from": "2026-10-19", "period_to": "2026-10-25",
		"title": "Doanh số tuần chững lại", "source": "ai", "model": "claude-opus-5-5", "items": 3},
	{"type": "thang", "date": "2026-10-01", "period_from": "2026-09-01", "period_to": "2026-09-30",
		"title": "Tháng 9: phải trả tăng", "source": "quy-tac", "model": "", "items": 4}], ad["briefs"])
for i in range(8):
	store_that.upsert_brief("tuan", datetime.date(2026, 8, 3) + datetime.timedelta(days=7 * i), title=f"T{i}",
		source="quy-tac", sections_used=[], parts=[{"key": "dang_chu_y", "title": "x", "items": [{"text": "a",
		"sections": []}]}])
ad = ai.get_admin()
c("briefs quản trị: tối đa 6, mới trước (cả hai loại)", len(ad["briefs"]) == 6 and [b["date"] for b in ad["briefs"]] ==
	sorted([b["date"] for b in ad["briefs"]], reverse=True) and ad["briefs"][0]["date"] == "2026-10-26"
	and any(b["type"] == "thang" for b in ad["briefs"]), [(b["type"], b["date"]) for b in ad["briefs"]])
c("briefs_running: chưa có bản tin chạy", ad["briefs_running"] == {"tuan": False, "thang": False})
frappe.cache().set_value(jobs.brief_lock_key("tuan"), 1)
c("briefs_running: khoá bản tin tuần → chỉ tuần True (khoá riêng từng loại)", ai.get_admin()["briefs_running"]
	== {"tuan": True, "thang": False})
frappe.cache().delete_value(jobs.brief_lock_key("tuan"))

print("16. P2 — run_brief")
as_(VIEWER)
frappe.ENQUEUED.clear()
background_jobs.FAKE_ENQUEUED_IDS.clear()
c("người xem run_brief → PermissionError, không xếp", raises(ai.run_brief, frappe.PermissionError, "tuan")
	and not frappe.ENQUEUED)
as_(ADMIN)
for bad in ("ngay", "", "TUAN", "tuan;thang", None):
	c(f"kind sai {bad!r} → ValidationError, không xếp", raises(ai.run_brief, VE, bad) and not frappe.ENQUEUED)
c("tuan → queued True", ai.run_brief("tuan") == {"queued": True})
c("xếp bc.ai.brief.run_brief(kind=tuan), job id riêng, hàng long", frappe.ENQUEUED[-1][0] == "bc.ai.brief.run_brief"
	and frappe.ENQUEUED[-1][2] == {"kind": "tuan"} and frappe.ENQUEUED[-1][1]["job_id"] == jobs.BRIEF_JOB_IDS["tuan"]
	and frappe.ENQUEUED[-1][1]["queue"] == "long", frappe.ENQUEUED)
background_jobs.FAKE_ENQUEUED_IDS.add(jobs.BRIEF_JOB_IDS["tuan"])
c("tuan đang chờ → queued False, không xếp thêm", ai.run_brief("tuan") == {"queued": False} and len(frappe.ENQUEUED) == 1)
c("thang (loại khác) vẫn xếp được", ai.run_brief(" thang ") == {"queued": True} and frappe.ENQUEUED[-1][2] == {"kind": "thang"})
background_jobs.FAKE_ENQUEUED_IDS.clear()
frappe.cache().set_value(jobs.brief_lock_key("thang"), 1)
c("khoá bản tin tháng đang giữ → queued False", ai.run_brief("thang") == {"queued": False} and len(frappe.ENQUEUED) == 2)
frappe.cache().delete_value(jobs.brief_lock_key("thang"))
frappe.cache().set_value(jobs.LOCK_KEY, 1)
c("lượt ngày đang chạy không chặn bản tin", ai.run_brief("tuan") == {"queued": True})
frappe.cache().delete_value(jobs.LOCK_KEY)
background_jobs.FAKE_ENQUEUED_IDS.clear()
_src = open(ai.__file__, encoding="utf-8").read()
c("run_brief chỉ nhận POST, guard quản trị ở dòng đầu", re.search(r'@frappe\.whitelist\(methods=\["POST"\]\)\ndef run_brief\(kind\):\n'
	r'\t"""(?:(?!""")[\s\S])*"""\n\t_admin_guard\(\)', _src) is not None)

print("17. Dấu build shell = www/bc.py = bc-p10-r1")
PKG = os.path.dirname(os.path.dirname(bc.ai.__file__))
js = open(os.path.join(PKG, "public", "bc", "shell.js"), encoding="utf-8").read()
py = open(os.path.join(PKG, "www", "bc.py"), encoding="utf-8").read()
mj, mp = re.search(r"const BUILD = '([^']+)'", js), re.search(r'SHELL_BUILD = "([^"]+)"', py)
c("BUILD (shell.js) = SHELL_BUILD (www/bc.py) = bc-p10-r1", mj and mp and mj.group(1) == mp.group(1) == "bc-p10-r1",
	(mj and mj.group(1), mp and mp.group(1)))

llm.call = call_cam
try:
	llm.call("claude", MODEL, "", "", "x", {})
	c("bản giả chặn gọi mạng ngoài ý muốn", False)
except AssertionError:
	c("bản giả chặn gọi mạng ngoài ý muốn", True)

c.done()
