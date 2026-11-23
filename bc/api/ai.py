# -*- coding: utf-8 -*-
"""bc.api.ai — Trợ lý AI: màn #/tro-ly (người xem + quản trị) và #/ai (chỉ quản trị). Đặc tả §6, §7, §8.

Luật đọc (get_feed / get_badge — dùng chung _rows, nên chấm đỏ trên menu luôn khớp số thẻ trên màn):
- Đọc thẳng BC AI Insight, KHÔNG run_cached (kết quả phụ thuộc vai + mảng đang ẩn — cache dùng chung sẽ lộ).
- Người xem: chỉ audience lanh-dao, status mo / dang-xu-ly; nhận định bị bỏ khi mảng chính HOẶC bất kỳ mảng nào
  trong sections_used đang ẩn. Không bao giờ trả chứng từ, ghi chú quản trị, lời phản biện, cờ needs_check, khoá tín
  hiệu, quy tắc, hạn bỏ qua, audience, sections_used — và không trả số lượng bị lọc.
- Quản trị: mọi audience, status mo / dang-xu-ly / bo-qua (closed=1 thêm dong đã đóng trong 30 ngày), đủ trường.
- Thứ tự: rank tăng dần (0 / trống xếp cuối), rồi đỏ trước vàng, rồi first_seen cũ trước.
- counts {do, vang} đếm trên nhận định ĐANG MỞ (mo / dang-xu-ly) đã trả. Bản tin ngày ghép lúc đọc từ danh sách đã
  lọc: 5 nhận định lanh-dao đang mở đầu tiên.
- meta.stale: không có lượt tổng ok nào, hoặc lượt ok gần nhất kết thúc CÁCH NAY HƠN 26 giờ (đúng 26 giờ chưa cũ).
- Mỗi nhận định có `stale` (cả hai vai): đang mở (mo / dang-xu-ly) mà last_seen TRƯỚC `started` của lượt tổng ok mới
  nhất — lượt ok gần nhất không làm mới nó (quy tắc không chạy được, số còn là số ngày last_seen). meta.stale_count =
  số nhận định stale trong danh sách đã lọc của người gọi.

Khoá API: chỉ trả có / không (bc.ai.llm.has_key); lỗi của lượt gọi thử đã qua bc.ai.llm.clean.
Module bc.ai.{llm, budget, store} nạp muộn trong hàm (bộ thử thay bằng bản giả).
"""

from __future__ import annotations

import datetime
import json

import frappe
from frappe import _
from frappe.utils import cint, cstr, date_diff, flt, get_datetime, getdate, now_datetime

from bc.ai import daily_model, registry
from bc.api._common import _guard, get_settings, hidden_sections, is_admin

INSIGHT = "BC AI Insight"
RUN = "BC AI Run"
RULE_DT = "BC AI Rule"
DT = "BC Settings"
OPEN = ("mo", "dang-xu-ly")
STATUSES = ("mo", "dang-xu-ly", "bo-qua")       # trạng thái quản trị đặt tay (dong chỉ do bộ chạy)
CLOSED_DAYS = 30            # closed=1: dong trong 30 ngày gần nhất
STALE_HOURS = 26
BRIEF_MAX = 5
NOTE_MAX = 500
MUTE_MAX = 365
KHOA_SAI_DANG = "khoá khai sai dạng (lẫn dấu cách / xuống dòng) — dán lại vào site_config"
TEST_MAX_TOKENS = 2048      # thinking tính vào max_tokens — nhỏ hơn dễ dừng vì max_tokens
TEST_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"],
	"additionalProperties": False}
RUN_FIELDS = ("run_type", "step", "run_id", "provider", "model", "started", "finished", "status", "tokens_in",
	"tokens_out", "cost_usd", "cost_known", "signals", "insights_ai", "rejected", "error")
_COLS = ("name, signal_key, rule, section, route, sections_used, audience, severity, status, source, title, body, "
	"advice, documents, `rank`, first_seen, last_seen, closed_on, mute_until, admin_note, review_verdict, review_note, "
	"needs_check")


def _admin_guard():
	"""Chỉ System Manager. Gọi ở DÒNG ĐẦU mọi method quản trị."""
	if not is_admin():
		frappe.throw(_("Chỉ quản trị (System Manager) được cấu hình Trợ lý AI."), frappe.PermissionError)


# ─── Đọc nhận định ───────────────────────────────────────────────────────────
def _lines(text) -> list:
	"""Small Text mỗi dòng một mục → list dòng không rỗng."""
	return [x.strip() for x in cstr(text).splitlines() if x.strip()]


def _json_list(v) -> list:
	if isinstance(v, list):
		return v
	try:
		x = json.loads(v) if v else []
	except (TypeError, ValueError):
		return []
	return x if isinstance(x, list) else []


def _today():
	return getdate(now_datetime())


def _ok_started():
	"""started của lượt tổng ok mới nhất (None khi chưa có)."""
	r = frappe.db.sql(f"""SELECT started FROM `tab{RUN}` WHERE step = 'tong' AND status = 'ok'
		ORDER BY started DESC LIMIT 1""")
	return r[0][0] if r and r[0][0] else None


def _is_stale(r, ok_started) -> bool:
	"""Đang mở mà lượt ok gần nhất không làm mới (last_seen < started của lượt đó)."""
	seen = r.get("last_seen")
	return bool(r.get("status") in OPEN and seen and ok_started
		and get_datetime(seen) < get_datetime(ok_started))


_CHUA = object()


def _shape(r, admin: bool, today=None, ok_started=_CHUA) -> dict:
	"""Một nhận định ra API. Người xem: đúng 17 trường; quản trị: thêm 9 trường quản trị.
	ok_started: started của lượt tổng ok mới nhất (truyền khi đã đọc sẵn — không thì đọc ở đây)."""
	today = today or _today()
	if ok_started is _CHUA:
		ok_started = _ok_started()
	sec = cstr(r.get("section"))
	g = registry.group_of(sec)
	first = r.get("first_seen")
	d = {"id": r.get("name"), "section": sec, "section_label": registry.SECTION_LABELS.get(sec, sec), "group": g,
		"group_label": registry.GROUPS[g]["label"] if g else "", "severity": r.get("severity"),
		"title": cstr(r.get("title")), "body": cstr(r.get("body")), "advice": _lines(r.get("advice")),
		"route": cstr(r.get("route")), "source": r.get("source"), "status": r.get("status"),
		"days": max(0, date_diff(today, first)) if first else 0, "first_seen": first,
		"last_seen": r.get("last_seen"), "review_verdict": cstr(r.get("review_verdict")),
		"stale": _is_stale(r, ok_started)}
	if admin:
		d.update({"documents": _json_list(r.get("documents")), "admin_note": cstr(r.get("admin_note")),
			"review_note": cstr(r.get("review_note")), "needs_check": cint(r.get("needs_check")),
			"signal_key": r.get("signal_key"), "rule": r.get("rule"), "mute_until": r.get("mute_until"),
			"audience": r.get("audience"), "sections_used": _lines(r.get("sections_used"))})
	return d


def _order(r):
	rank = cint(r.get("rank"))
	first = r.get("first_seen")
	return (rank if rank > 0 else float("inf"), 0 if r.get("severity") == "do" else 1,
		get_datetime(first) if first else datetime.datetime.max)


def _rows(admin: bool, closed=0) -> list:
	"""Dòng Insight người gọi được thấy, đã xếp thứ tự (dict thô từ DB)."""
	if admin:
		where, p = "status IN %(st)s", {"st": STATUSES}
		if cint(closed):
			where = f"({where} OR (status = 'dong' AND closed_on >= %(tu)s))"
			p["tu"] = now_datetime() - datetime.timedelta(days=CLOSED_DAYS)
	else:
		where, p = "status IN %(st)s AND audience = 'lanh-dao'", {"st": OPEN}
	rows = frappe.db.sql(f"SELECT {_COLS} FROM `tab{INSIGHT}` WHERE {where}", p, as_dict=True)
	if not admin:
		an = hidden_sections()
		rows = [r for r in rows if cstr(r.get("section")) not in an
			and not any(s in an for s in _lines(r.get("sections_used")))]
	return sorted(rows, key=_order)


def _counts(rows) -> dict:
	open_ = [r for r in rows if r.get("status") in OPEN]
	return {"do": sum(r.get("severity") == "do" for r in open_), "vang": sum(r.get("severity") == "vang" for r in open_)}


def _brief(rows, today) -> dict | None:
	"""Bản tin ngày ghép lúc đọc (đặc tả §6.3) từ danh sách ĐÃ lọc theo người gọi."""
	ld = [r for r in rows if r.get("audience") == "lanh-dao" and r.get("status") in OPEN]
	if not ld:
		return None
	return {"title": f"Sáng {today.day}/{today.month}/{today.year}: {len(ld)} việc cần chú ý",
		"date": today.isoformat(),
		"items": [{"id": r.get("name"), "title": cstr(r.get("title")), "severity": r.get("severity")}
			for r in ld[:BRIEF_MAX]]}


def _meta(rows=(), ok_started=None) -> dict:
	"""rows: danh sách đã lọc của người gọi (đếm stale_count); ok_started: started của lượt tổng ok mới nhất."""
	from bc.ai import jobs
	last = frappe.db.sql(f"SELECT started FROM `tab{RUN}` WHERE step = 'tong' ORDER BY started DESC LIMIT 1")
	ok = frappe.db.sql(f"""SELECT finished FROM `tab{RUN}` WHERE step = 'tong' AND status = 'ok'
		ORDER BY started DESC LIMIT 1""")
	last_ok = ok[0][0] if ok and ok[0][0] else None
	stale = last_ok is None or now_datetime() - get_datetime(last_ok) > datetime.timedelta(hours=STALE_HOURS)
	return {"last_run": last[0][0] if last else None, "last_ok": last_ok, "stale": bool(stale), "ai_on": _ai_on(),
		"as_of": last_ok, "running": bool(jobs.is_running()),
		"stale_count": sum(_is_stale(r, ok_started) for r in rows)}


def _ai_on() -> bool:
	from bc.ai import llm
	return bool(cint(get_settings().get("ai_enabled"))) and bool(llm.has_key("claude"))


@frappe.whitelist()
def get_feed(refresh=0, closed=0):
	"""Nhận định cho người gọi (đã lọc theo vai và mảng ẩn) → {meta, brief, counts, insights[]}.
	Không cache dùng chung: kết quả phụ thuộc vai và mảng đang ẩn (refresh nhận cho đồng bộ với method báo cáo)."""
	_guard("tro-ly")
	admin = is_admin()
	today = _today()
	rows = _rows(admin, closed if admin else 0)
	since = _ok_started()
	return {"meta": _meta(rows, since), "brief": _brief(rows, today), "counts": _counts(rows),
		"insights": [_shape(r, admin, today, since) for r in rows]}


@frappe.whitelist()
def get_badge(refresh=0):
	"""Số nhận định đỏ / vàng sau lọc — chấm đỏ trên menu. Cùng bộ lọc với get_feed."""
	_guard("tro-ly")
	return _counts(_rows(is_admin()))


# ─── Quản trị ────────────────────────────────────────────────────────────────
def _load_rules():
	"""registry.load(); một file quy tắc hỏng không được làm chết màn quản trị (ghi Error Log, dùng phần đã nạp)."""
	try:
		registry.load()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "bc.ai nạp quy tắc")
		frappe.clear_last_message()


def _open_by_rule() -> dict:
	rows = frappe.db.sql(f"SELECT rule, COUNT(*) FROM `tab{INSIGHT}` WHERE status IN %(st)s GROUP BY rule",
		{"st": OPEN})
	return {r[0]: cint(r[1]) for r in rows}


def _rule_shape(rd, override: dict | None, n_open: int) -> dict:
	cfg = registry.Cfg(rd, override)
	return {"key": rd.key, "label": rd.label, "section": rd.section,
		"section_label": registry.SECTION_LABELS.get(rd.section, rd.section), "audience": rd.audience, "unit": rd.unit,
		"lower": bool(rd.lower), "vang_default": rd.vang, "do_default": rd.do, "vang": cfg.vang, "do": cfg.do,
		"disabled": bool(cfg.disabled), "open": cint(n_open)}


def _budget_claude(model: str) -> dict:
	from bc.ai import budget
	return {"spent": flt(budget.spent("claude")), "cap": flt(budget.cap("claude")),
		"cycle_start": budget.cycle_start("claude"), "calls_today": cint(budget.calls_today("claude")),
		"max_calls": budget.MAX_CALLS_PER_DAY, "price_known": budget.price_of(model) is not None}


def _insights_where(where: str, p: dict) -> list:
	today, since = _today(), _ok_started()
	rows = frappe.db.sql(f"SELECT {_COLS} FROM `tab{INSIGHT}` WHERE {where}", p, as_dict=True)
	return [_shape(r, True, today, since) for r in sorted(rows, key=_order)]


@frappe.whitelist()
def get_admin():
	"""Trạng thái cấu hình, chi phí, quy tắc, lượt chạy (chỉ quản trị). Khoá API: chỉ có / không.
	models.claude + price_known theo bc.ai.daily_model() (ô trống → model mặc định — đúng model lượt chạy gọi)."""
	_admin_guard()
	from bc.ai import jobs, llm
	s = get_settings()
	models = {"claude": daily_model(), "claude_deep": cstr(s.get("ai_claude_model_deep")),
		"openai": cstr(s.get("ai_openai_model"))}
	_load_rules()
	ov, n_open = registry.overrides_from_settings(), _open_by_rule()
	runs = frappe.db.sql(f"SELECT {', '.join(RUN_FIELDS)} FROM `tab{RUN}` ORDER BY started DESC, creation DESC LIMIT 20",
		as_dict=True)
	return {
		"keys": {"claude": bool(llm.has_key("claude")), "openai": bool(llm.has_key("openai"))},
		# có khai nhưng sai dạng (dán lẫn dấu cách / xuống dòng) → màn nói rõ, không báo "chưa có"
		"keys_bad": {"claude": bool(llm.key_malformed("claude")), "openai": bool(llm.key_malformed("openai"))},
		"enabled": bool(cint(s.get("ai_enabled"))),
		"models": models,
		"budget": {"claude": _budget_claude(models["claude"])},
		"running": bool(jobs.is_running()),
		"runs": [{k: r.get(k) for k in RUN_FIELDS} for r in runs],
		"rules": [_rule_shape(rd, ov.get(k), n_open.get(k, 0)) for k, rd in registry.RULES.items()],
		"rejected": _insights_where("status IN %(st)s AND needs_check = 1", {"st": OPEN}),
		"muted": _insights_where("status = 'bo-qua'", {}),
		"settings_url": "/app/bc-settings",
	}


@frappe.whitelist(methods=["POST"])
def run_now():
	"""Chạy lượt ngày ngay (chỉ quản trị): xếp hàng run_daily (run_type tay). Đang chạy → ValidationError."""
	_admin_guard()
	from bc.ai import jobs
	if not jobs.enqueue_run("tay"):
		frappe.throw(_("Trợ lý đang chạy — chờ lượt hiện tại xong rồi thử lại."))
	return {"queued": True}


@frappe.whitelist(methods=["POST"])
def set_status(insight, status, mute_days=None, note=None):
	"""Đổi trạng thái một nhận định (chỉ quản trị). status: mo | dang-xu-ly | bo-qua (dong chỉ do bộ chạy).
	bo-qua: mute_days trống = bỏ qua hẳn (mute_until trống), không thì hôm nay + mute_days (1..365); trạng thái khác
	xoá mute_until. note None = giữ, chuỗi (kể cả rỗng) = ghi admin_note (cắt 500). Trả nhận định dạng quản trị."""
	_admin_guard()
	status = cstr(status).strip()
	if status not in STATUSES:
		frappe.throw(_("Trạng thái không hợp lệ."))
	cur = frappe.db.sql(f"SELECT status FROM `tab{INSIGHT}` WHERE name = %(n)s", {"n": cstr(insight)})
	if not cur:
		frappe.throw(_("Không tìm thấy nhận định."))
	if cur[0][0] == "dong":
		frappe.throw(_("Nhận định đã đóng — không đổi trạng thái được."))
	f = {"status": status, "mute_until": None}
	if status == "bo-qua" and cstr(mute_days).strip():
		try:
			n = int(cstr(mute_days).strip())
		except ValueError:
			n = 0
		if not 1 <= n <= MUTE_MAX:
			frappe.throw(_("Số ngày bỏ qua phải từ 1 đến 365."))
		f["mute_until"] = _today() + datetime.timedelta(days=n)
	if note is not None:
		f["admin_note"] = cstr(note)[:NOTE_MAX]
	frappe.db.set_value(INSIGHT, cstr(insight), f)
	r = frappe.db.sql(f"SELECT {_COLS} FROM `tab{INSIGHT}` WHERE name = %(n)s", {"n": cstr(insight)}, as_dict=True)
	return _shape(r[0], True)


def _nguong(v, ten: str) -> float:
	try:
		x = float(cstr(v).strip())
	except ValueError:
		x = -1.0
	if x < 0 or x != x or x == float("inf"):
		frappe.throw(_("Ngưỡng {0} phải là số không âm (0 = dùng mặc định).").format(ten))
	return x


@frappe.whitelist(methods=["POST"])
def set_rule(rule_key, disabled=None, threshold=None, threshold_red=None):
	"""Tắt / đổi ngưỡng một quy tắc (chỉ quản trị) — dòng BC Settings.ai_rules theo rule_key (chưa có thì thêm).
	Chỉ đổi tham số được truyền; ngưỡng 0 = về mặc định. Trả quy tắc dạng get_admin."""
	_admin_guard()
	from bc.api.sections import _an
	_load_rules()
	key = cstr(rule_key).strip()
	rd = registry.RULES.get(key)
	if not rd:
		frappe.throw(_("Quy tắc không tồn tại: {0}").format(key or "—"))
	if not frappe.get_meta(DT).has_field("ai_rules"):
		frappe.throw(_("Chưa chạy bench migrate cho BC Settings — chưa đổi được quy tắc."))
	f = {}
	if disabled is not None:
		f["disabled"] = 1 if _an(disabled) else 0
	if threshold is not None:
		f["threshold"] = _nguong(threshold, "vàng")
	if threshold_red is not None:
		f["threshold_red"] = _nguong(threshold_red, "đỏ")
	cu = frappe.db.sql(f"""SELECT name FROM `tab{RULE_DT}` WHERE parent = %(p)s AND parenttype = %(p)s
		AND parentfield = 'ai_rules' AND rule_key = %(k)s ORDER BY idx DESC""", {"p": DT, "k": key})
	if cu:
		if f:
			frappe.db.set_value(RULE_DT, cu[0][0], f)   # dòng sau thắng (overrides_from_settings) → sửa dòng cuối
	else:
		idx = frappe.db.sql(f"""SELECT MAX(idx) FROM `tab{RULE_DT}` WHERE parent = %(p)s AND parenttype = %(p)s
			AND parentfield = 'ai_rules'""", {"p": DT})
		frappe.get_doc({"doctype": RULE_DT, "parent": DT, "parenttype": DT, "parentfield": "ai_rules",
			"idx": cint(idx[0][0] if idx else 0) + 1, "rule_key": key, "disabled": f.get("disabled", 0),
			"threshold": f.get("threshold", 0), "threshold_red": f.get("threshold_red", 0)}).insert(ignore_permissions=True)
	frappe.clear_document_cache(DT, DT)
	return _rule_shape(rd, registry.overrides_from_settings().get(key), _open_by_rule().get(key, 0))


@frappe.whitelist(methods=["POST"])
def test_connection(provider):
	"""Gọi thử một lượt tối thiểu tới nhà cung cấp (chỉ quản trị) → {ok, model, error}; luôn ghi một BC AI Run
	(run_type tay, step test — tính vào giới hạn lượt gọi / ngày). Không khoá → khong-khoa; vượt trần → vuot-tran."""
	_admin_guard()
	from bc.ai import budget, llm, store
	provider = cstr(provider).strip()
	if provider not in ("claude", "openai"):
		frappe.throw(_("Nhà cung cấp không hợp lệ."))
	model = daily_model() if provider == "claude" else cstr(get_settings().get("ai_openai_model")).strip()
	if not llm.has_key(provider):
		run = store.start_run("tay", "test", provider=provider, model=model)
		loi = KHOA_SAI_DANG if llm.key_malformed(provider) else "chưa có khoá"
		store.finish_run(run, status="khong-khoa", error=loi)
		return {"ok": False, "model": model, "error": loi}
	ok, why = budget.can_call(provider)
	if not ok:
		msg = "quá số lượt gọi hôm nay" if why == "qua-so-luot" else "đã chi tới trần kỳ này"
		run = store.start_run("tay", "test", provider=provider, model=model)
		store.finish_run(run, status="vuot-tran", error=msg)
		return {"ok": False, "model": model, "error": msg}
	run = store.start_run("tay", "test", provider=provider, model=model)
	try:
		res = llm.call(provider, model, "Bạn kiểm tra kết nối. Chỉ trả JSON theo schema.",
			'Trả đúng {"ok": true}.', "ket_noi", TEST_SCHEMA, max_tokens=TEST_MAX_TOKENS, timeout=60)
	except llm.LLMError as e:
		m = e.model or model
		store.finish_run(run, status=llm.run_status(e.kind), tokens_in=e.tokens_in, tokens_out=e.tokens_out,
			cost_usd=budget.cost(m, e.tokens_in, e.tokens_out), error=llm.clean(e.message), model=e.model or None)
		return {"ok": False, "model": m, "error": llm.clean(e.message)}
	m = res.get("model") or model
	ti, to = cint(res.get("tokens_in")), cint(res.get("tokens_out"))
	good = (res.get("data") or {}).get("ok") is True
	store.finish_run(run, status="ok", tokens_in=ti, tokens_out=to, cost_usd=budget.cost(m, ti, to),
		error=None if good else "mô hình không trả ok", model=m)
	return {"ok": good, "model": m, "error": "" if good else "mô hình không trả ok"}
