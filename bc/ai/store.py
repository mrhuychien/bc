# -*- coding: utf-8 -*-
"""bc.ai.store — ghi / đóng / xếp hạng BC AI Insight, nhật ký BC AI Run, dọn dữ liệu cũ (đặc tả §4, §6).

Chỉ ghi DocType của chính bc. Mọi field JSON (paths, documents, kpis) tự json.dumps trước khi ghi và json.loads khi
đọc (v16 chỉ tự chuyển dict, không chuyển list). Ghi bằng frappe.get_doc({...}).insert(ignore_permissions=True) và
frappe.db.set_value(doctype, name, {...}) — chạy được cả trên site thật lẫn bộ thử.

Vòng đời theo signal_key:
- mới → tạo, status mo, first_seen = now, seen_count 1;
- còn → cập nhật last_seen, severity, paths, lời (về lời quy tắc, source quy-tac, advice rỗng, needs_check 0, priority
  0); seen_count + 1 tối đa một lần / ngày;
- quy tắc ĐÃ CHẠY mà không còn tín hiệu → dong, closed_on = now; quy tắc không chạy được → giữ nguyên;
- dong rồi xuất hiện lại → mo, first_seen = now, seen_count 1;
- dang-xu-ly giữ nguyên trạng thái khi tín hiệu còn;
- bo-qua: không tự đóng / mở khi còn hạn (mute_until trống = bỏ qua hẳn, hoặc mute_until ≥ hôm nay) — vẫn cập nhật
  lời + last_seen khi còn tín hiệu; hết hạn: còn tín hiệu → mo, hết tín hiệu (quy tắc đã chạy) → dong.

Chi tiết đã chốt ở đây (nơi khác dựa vào):
- "Hôm nay" = ngày của `now` truyền vào (không đọc đồng hồ máy) — seen_count, hạn bỏ qua, mốc dọn đều theo đó.
- seen_count đếm NGÀY còn thấy tín hiệu: chỉ + 1 khi ngày của `now` sau ngày của last_seen (chạy nhiều lượt một ngày
  không đội số); tín hiệu đang bo-qua vẫn đếm. Hết hạn bỏ qua mà còn tín hiệu → mo nhưng GIỮ first_seen / seen_count
  (việc vẫn kéo dài từ đó tới nay — khác với dong rồi xuất hiện lại là một đợt mới).
- signal_key cắt 140 ký tự (độ dài cột + unique), title / rule_title cắt 200. Khoá so theo đúng collation của cột
  (utf8mb4_unicode_ci: không phân biệt hoa thường / dấu) để không bao giờ chèn trùng chỉ mục unique.
- sections_used lưu mỗi dòng một mã, luôn GỒM mảng chính của nhận định (lời không có path nào vẫn ẩn theo mảng).
- Dòng Run mới tạo mang status "loi" + error "chưa hoàn tất" (DANG_CHAY), finished trống: job chết giữa chừng
  thì dòng tự nói là lỗi, không bao giờ bị đọc nhầm thành lượt chạy tốt. finish_run ghi đè cả hai (error None
  xoá lời; gọi được cho lượt gọi mô hình hỏng kèm tokens / model, status loi | het-credit). Nơi đọc muốn biết
  "đang chạy / dở dang" thì xét finished trống.
- Dọn theo NGÀY LỊCH: xoá dòng có ngày đóng (Insight) / ngày bắt đầu (Run) TRƯỚC ngày (hôm nay − 180). Đúng 180 ngày
  trước (bất kể giờ) → còn giữ; 181 ngày → xoá. Ngoại lệ (P2): dòng tổng mang ảnh chụp KPI giữ KEEP_KPI_DAYS (400) ngày
  — bản tin tháng cần 12 tháng; BC AI Brief giữ 400 ngày theo brief_date.
- Phản biện (P2): review_verdict / review_note thuộc về MỘT lời AI. Lời mới (apply_ai, nhận định tự do được ghi lại) hoặc
  lời quy tắc đặt lại (sync_signals, source quy-tac) → xoá cả hai; chỉ set_review ghi chúng.
- Dòng Run của phản biện: step "review:<nhóm>", provider openai, run_id = dòng tổng của lượt ngày. Dòng Run của bản tin:
  step "ban-tin:tuan" | "ban-tin:thang", run_type "tuan" | "thang", KHÔNG có dòng tổng (run_id trống) — meta.last_ok /
  stale / ht.ai_loi vẫn chỉ nói về lượt ngày.
"""

from __future__ import annotations

import datetime
import json

import frappe
from frappe.utils import cint, cstr, flt, get_datetime, getdate, now_datetime

INSIGHT = "BC AI Insight"
RUN = "BC AI Run"
OPEN = ("mo", "dang-xu-ly")
KEEP_CLOSED_DAYS = 180
KEEP_RUN_DAYS = 180
KEEP_KPI_DAYS = 400      # dòng tổng có ảnh chụp KPI + BC AI Brief (bản tin tháng so 12 tháng trước)
BRIEF = "BC AI Brief"
BRIEF_TYPES = ("ngay", "tuan", "thang")
BRIEF_SOURCES = ("ai", "quy-tac")
VERDICTS = ("dong-y", "nghi-ngo")
NOTE_LEN = 300           # review_note

KEY_LEN = 140            # signal_key: Data(140), unique
TITLE_LEN = 200          # title, rule_title: Data(200)
DATA_LEN = 140           # các field Data còn lại
ERROR_LEN = 300          # BC AI Run.error
DOCS_MAX = 20            # chứng từ kèm một tín hiệu
RUN_TYPES = ("ngay", "tuan", "tay", "hoi-dap", "thang")
RUN_STATUSES = ("ok", "loi", "het-credit", "vuot-tran", "tat", "khong-khoa")
DANG_CHAY = "chưa hoàn tất"      # dòng Run chưa chốt (đang chạy / job chết giữa chừng)
_MUC = {"vang": 1, "do": 2}          # đỏ nặng hơn vàng
_AUDIENCES = ("lanh-dao", "quan-tri")
_COT = ("name, signal_key, rule, section, status, severity, priority, seen_count, first_seen, last_seen, "
	"mute_until, title, paths, sections_used")


# ─── Tiện ích ────────────────────────────────────────────────────────────────
def _cat(v, n: int) -> str:
	return cstr(v)[:n]


def _uniq(values) -> list:
	"""Bỏ trống + trùng, giữ thứ tự."""
	return list(dict.fromkeys(x for x in (cstr(v).strip() for v in (values or [])) if x))


def _dump(values) -> str:
	return json.dumps(list(values or []), ensure_ascii=False, default=str)


def _load(v) -> list:
	"""Field JSON (danh sách) → list; trống / hỏng → []."""
	if isinstance(v, (list, tuple)):
		return list(v)
	if not v:
		return []
	try:
		out = json.loads(v)
	except (TypeError, ValueError):
		return []
	return out if isinstance(out, list) else []


def _dong(values) -> str:
	"""Danh sách → mỗi dòng một mục (xuống dòng bên trong một mục đổi thành dấu cách)."""
	return "\n".join(_uniq(" ".join(cstr(v).split()) for v in (values or [])))


def _tach(text) -> list:
	return _uniq(cstr(text).splitlines())


def _lo(seq, n: int = 500):
	seq = list(seq)
	for i in range(0, len(seq), n):
		yield tuple(seq[i:i + n])


def _rows(where: str, params: dict) -> list:
	return frappe.db.sql(f"SELECT {_COT} FROM `tab{INSIGHT}` WHERE {where}", params, as_dict=True)


def _con_han(row, today) -> bool:
	"""bo-qua còn hiệu lực: mute_until trống = bỏ qua hẳn; có ngày thì tới HẾT ngày đó."""
	return not row.get("mute_until") or getdate(row.get("mute_until")) >= today


# ─── Upsert chung cho tín hiệu quy tắc và nhận định tự do ────────────────────
def _tim(keys) -> dict:
	"""{khoá: dòng Insight} của các khoá đã cắt — khớp ĐÚNG chuỗi (một truy vấn cho cả lô)."""
	have: dict = {}
	for lo in _lo(keys):
		for r in _rows("signal_key IN %(keys)s", {"keys": lo}):
			have[r.signal_key] = r
	return have


def _tim_mot(key: str):
	"""Dòng mà DB coi là CÙNG khoá (collation của cột: không phân biệt hoa thường / dấu) — hỏi ngay trước khi chèn nên
	thấy cả dòng vừa chèn trong lô này; không bao giờ chèn trùng chỉ mục unique."""
	r = _rows("signal_key = %(key)s LIMIT 1", {"key": key})
	return r[0] if r else None


def _con(row, now, today) -> tuple:
	"""Tín hiệu CÒN trên một dòng đã có → (field trạng thái cần ghi, loại: kept | reopened | muted)."""
	if row.status == "dong":   # một đợt mới
		return {"status": "mo", "first_seen": now, "last_seen": now, "seen_count": 1, "closed_on": None,
			"mute_until": None}, "reopened"
	seen = cint(row.seen_count)
	if not row.last_seen or getdate(row.last_seen) < today:   # tối đa + 1 / ngày
		seen += 1
	f = {"last_seen": now, "seen_count": max(seen, 1)}
	if row.status == "bo-qua":
		if _con_han(row, today):
			return f, "muted"
		f.update(status="mo", mute_until=None)   # hết hạn bỏ qua mà còn tín hiệu → hiện lại
		return f, "reopened"
	if row.status not in OPEN:   # trạng thái lạ (sửa tay trên Desk) → coi như đang mở
		f["status"] = "mo"
	return f, "kept"


def _upsert(items, loi, now) -> tuple:
	"""Ghi các mục theo khoá. `loi(item)` → field lời + phân loại. Trả (đếm theo loại, {khoá gốc: name}, tập name đã
	chạm). Hai mục trùng khoá (sau khi cắt / theo collation) → mục ĐẦU thắng."""
	today = getdate(now)
	dem = {"new": 0, "kept": 0, "reopened": 0, "muted": 0}
	can: dict = {}      # khoá đã cắt → mục
	goc: dict = {}      # khoá gốc → khoá đã cắt
	for it in items or []:
		raw = cstr(it.get("key")).strip()
		if raw:
			goc[raw] = raw[:KEY_LEN]
			can.setdefault(raw[:KEY_LEN], it)
	have = _tim(list(can))
	ten: dict = {}      # khoá đã cắt → name
	cham: set = set()
	for k, it in can.items():
		row = have.get(k) or _tim_mot(k)
		if row is not None and row.name in cham:   # khoá khác chữ nhưng DB coi là một → đã xử lý
			ten[k] = row.name
			continue
		f = loi(it)
		if row is None:
			doc = frappe.get_doc({"doctype": INSIGHT, "signal_key": k, "status": "mo", "first_seen": now,
				"last_seen": now, "seen_count": 1, "rank": 0, "closed_on": None, "mute_until": None, **f})
			doc.insert(ignore_permissions=True)
			ten[k] = doc.name
			dem["new"] += 1
		else:
			st, loai = _con(row, now, today)
			frappe.db.set_value(INSIGHT, row.name, {**f, **st})
			ten[k] = row.name
			dem[loai] += 1
		cham.add(ten[k])
	return dem, {raw: ten[k] for raw, k in goc.items()}, cham


def _dong_vang(rows, cham: set, now) -> int:
	"""Đóng các dòng không còn được nêu: đang mở, hoặc bo-qua đã hết hạn. bo-qua còn hạn / bỏ qua hẳn: giữ."""
	today, n = getdate(now), 0
	for r in rows:
		if r.name in cham or r.status == "dong":
			continue
		if r.status == "bo-qua" and _con_han(r, today):
			continue
		frappe.db.set_value(INSIGHT, r.name, {"status": "dong", "closed_on": now, "mute_until": None})
		n += 1
	return n


def _muc(v, default: str = "vang") -> str:
	return v if v in _MUC else default


def _sections(it, section: str) -> str:
	return "\n".join(_uniq([*(it.get("sections_used") or []), section]))


# ─── Tín hiệu theo quy tắc ───────────────────────────────────────────────────
def sync_signals(items: list, ran, now) -> dict:
	"""Đồng bộ tín hiệu theo quy tắc của một lượt chạy.

	items: tín hiệu ĐÃ dựng lời — dict {"key", "rule", "section", "audience", "severity", "route", "title", "body",
	"paths": [..], "sections_used": [..], "documents": [..]}. ran: tập mã quy tắc đã chạy (gồm quy tắc đang tắt) —
	Insight (rule ≠ "ai") của các quy tắc này không còn trong items thì đóng. Trả {"new", "kept", "reopened", "closed",
	"muted", "names": {key: name}}."""
	now = get_datetime(now)

	def loi(it) -> dict:
		section, title = _cat(it.get("section"), DATA_LEN), _cat(it.get("title"), TITLE_LEN)
		return {"rule": _cat(it.get("rule"), DATA_LEN), "section": section, "route": _cat(it.get("route"), DATA_LEN),
			"audience": it.get("audience") if it.get("audience") in _AUDIENCES else "lanh-dao",
			"severity": _muc(it.get("severity")), "source": "quy-tac", "title": title, "rule_title": title,
			"body": cstr(it.get("body")), "advice": "", "priority": 0, "needs_check": 0, "text_at": now,
			"review_verdict": "", "review_note": "",   # lời quy tắc đặt lại → phản biện của lời cũ hết nghĩa
			"paths": _dump(_uniq(it.get("paths"))), "documents": _dump(list(it.get("documents") or [])[:DOCS_MAX]),
			"sections_used": _sections(it, section)}

	dem, names, cham = _upsert(items, loi, now)
	closed = 0
	for lo in _lo(sorted({cstr(r) for r in (ran or ()) if r and r != "ai"})):
		closed += _dong_vang(_rows("rule IN %(rules)s AND IFNULL(status, '') != 'dong'", {"rules": lo}), cham, now)
	return {**dem, "closed": closed, "names": names}


def open_for_llm(sections, limit: int) -> list:
	"""Tín hiệu gửi mô hình của một nhóm: Insight rule ≠ "ai", status mo / dang-xu-ly, section ∈ sections; đỏ trước rồi
	first_seen mới trước; tối đa `limit`. Mỗi dòng: {"name", "signal_key", "rule", "section", "severity", "status",
	"first_seen", "admin_note", "paths": [..]}."""
	sections, limit = tuple(_uniq(sections)), cint(limit)
	if not sections or limit <= 0:
		return []
	rows = frappe.db.sql(f"""SELECT name, signal_key, rule, section, severity, status, first_seen, admin_note, paths
		FROM `tab{INSIGHT}` WHERE IFNULL(rule, '') != 'ai' AND status IN %(open)s AND section IN %(sections)s""",
		{"open": OPEN, "sections": sections}, as_dict=True)
	# đỏ trước; trong một mức: first_seen MỚI trước (hai lượt sắp ổn định: khoá → thời điểm giảm dần → mức)
	rows = sorted(rows, key=lambda r: cstr(r.signal_key))
	rows = sorted(rows, key=lambda r: r.first_seen or datetime.datetime.min, reverse=True)
	rows = sorted(rows, key=lambda r: 0 if r.severity == "do" else 1)
	return [{"name": r.name, "signal_key": r.signal_key, "rule": r.rule, "section": r.section, "severity": r.severity,
		"status": r.status, "first_seen": r.first_seen, "admin_note": r.admin_note, "paths": _load(r.paths)}
		for r in rows[:limit]]


BO_QUA, DANG_MO = "bo-qua", "mo"     # giá trị của blocked_paths


def blocked_paths(sections, now) -> dict:
	"""Path (đã bỏ chỉ số mảng) mà nhận định TỰ DO của mô hình không được nêu lại, của các Insight có section ∈
	sections → {path: "bo-qua" | "mo"}:
	- "bo-qua": Insight (mọi rule, kể cả "ai") đang bo-qua còn hạn (mute_until trống hoặc ≥ ngày của `now`) — quản
	  trị đã tắt chủ đề này, nhận định tự do trên cùng số là lách lệnh tắt;
	- "mo": tín hiệu quy tắc (rule ≠ "ai") đang mo / dang-xu-ly — nhận định tự do chỉ lặp lại tín hiệu đó.
	Một path có cả hai → "bo-qua"."""
	from bc.ai.registry import strip_index

	sections = tuple(_uniq(sections))
	if not sections:
		return {}
	today = getdate(now)
	rows = frappe.db.sql(f"""SELECT rule, status, mute_until, paths FROM `tab{INSIGHT}`
		WHERE section IN %(sections)s AND (status = 'bo-qua' OR (status IN %(open)s AND IFNULL(rule, '') != 'ai'))""",
		{"sections": sections, "open": OPEN}, as_dict=True)
	out: dict = {}
	for r in rows:
		if r.status == "bo-qua":
			if not _con_han(r, today):
				continue
			loai = BO_QUA
		else:
			loai = DANG_MO
		for p in _load(r.paths):
			p = strip_index(cstr(p)).strip()
			if p and out.get(p) != BO_QUA:
				out[p] = loai
	return out


# ─── Lời AI ──────────────────────────────────────────────────────────────────
def apply_ai(name: str, *, title: str, body: str, advice: list, severity: str, priority: int, paths: list,
		sections_used: list, now) -> None:
	"""Gắn lời AI vào Insight của một tín hiệu: source ai, text_at now, needs_check 0, xoá phản biện của lời cũ. severity = max(mức đang có, mức
	mô hình) — mô hình không hạ được mức đỏ. paths / sections_used = HỢP của quy tắc và lời AI."""
	r = _rows("name = %(name)s", {"name": name})
	if not r:
		raise frappe.DoesNotExistError(f"{INSIGHT} {name} không tồn tại")
	row = r[0]
	cu = _muc(row.severity)
	moi = _muc(severity, cu)   # mức lạ từ mô hình → giữ mức đang có
	frappe.db.set_value(INSIGHT, name, {
		"title": _cat(title, TITLE_LEN).strip() or row.title, "body": cstr(body), "advice": _dong(advice),
		"source": "ai", "text_at": get_datetime(now), "needs_check": 0, "review_verdict": "", "review_note": "",
		"severity": moi if _MUC[moi] > _MUC[cu] else cu, "priority": cint(priority),
		"paths": _dump(_uniq([*_load(row.paths), *(paths or [])])),
		"sections_used": "\n".join(_uniq([*_tach(row.sections_used), *(sections_used or [])])),
	})


def mark_rejected(name: str) -> None:
	"""Lời AI lượt này cho Insight bị loại: needs_check 1, giữ lời quy tắc."""
	frappe.db.set_value(INSIGHT, name, {"needs_check": 1})


def set_review(signal_key: str, verdict: str, note: str = "") -> bool:
	"""Ghi kết quả phản biện cho Insight có signal_key (khớp ĐÚNG chuỗi, đã cắt KEY_LEN): verdict ∈ VERDICTS (khác →
	ValueError), note = lời ĐÃ qua render.render_text (nơi gọi lo; rỗng được), gộp một dòng, cắt ≤ NOTE_LEN ký tự không
	cắt giữa số. Chỉ ghi review_verdict / review_note — không đụng lời, mức, trạng thái. Trả False khi không có Insight
	đó."""
	from bc.ai.render import _cat as cat_an_toan

	if verdict not in VERDICTS:
		raise ValueError(f"bc.ai: kết quả phản biện không hợp lệ: {verdict}")
	k = cstr(signal_key).strip()[:KEY_LEN]
	row = _tim([k]).get(k) if k else None
	if row is None:
		return False
	frappe.db.set_value(INSIGHT, row.name, {"review_verdict": verdict,
		"review_note": cat_an_toan(" ".join(cstr(note).split()), NOTE_LEN)})
	return True


def sync_ai_free(sections, items: list, now) -> dict:
	"""Nhận định TỰ DO của mô hình cho một nhóm (rule "ai", source "ai", audience lanh-dao).

	items: [{"key": "ai:<path bỏ chỉ số>", "section", "route", "severity", "priority", "title", "body", "advice": [..],
	"paths", "sections_used"}] (nơi gọi đã cắt ≤ 3). Upsert theo key như tín hiệu; Insight rule "ai" đang mở có section
	∈ sections mà không còn trong items → dong (kể cả khi items rỗng: lượt gọi lỗi / AI tắt). bo-qua còn hạn: giữ.
	Trả {"new", "kept", "closed"}."""
	now = get_datetime(now)

	def loi(it) -> dict:
		section = _cat(it.get("section"), DATA_LEN)
		return {"rule": "ai", "section": section, "route": _cat(it.get("route"), DATA_LEN), "audience": "lanh-dao",
			"severity": _muc(it.get("severity")), "source": "ai", "title": _cat(it.get("title"), TITLE_LEN),
			"rule_title": "", "body": cstr(it.get("body")), "advice": _dong(it.get("advice")),
			"priority": cint(it.get("priority")), "needs_check": 0, "text_at": now, "review_verdict": "", "review_note": "",
			"paths": _dump(_uniq(it.get("paths"))), "documents": _dump([]), "sections_used": _sections(it, section)}

	dem, _names, cham = _upsert(items, loi, now)
	closed = 0
	for lo in _lo(_uniq(sections)):
		closed += _dong_vang(_rows("rule = 'ai' AND section IN %(sections)s AND IFNULL(status, '') != 'dong'",
			{"sections": lo}), cham, now)
	# new = tạo mới + đóng rồi được nêu lại (một đợt mới); kept = đang có và vẫn được nêu (kể cả đang bo-qua)
	return {"new": dem["new"] + dem["reopened"], "kept": dem["kept"] + dem["muted"], "closed": closed}


def rerank() -> None:
	"""Đánh `rank` 1..n cho Insight mo / dang-xu-ly: đỏ trước, priority cao trước, first_seen cũ trước, signal_key."""
	rows = frappe.db.sql(f"""SELECT name, signal_key, status, severity, priority, first_seen, `rank`
		FROM `tab{INSIGHT}` WHERE status IN %(open)s OR `rank` != 0""", {"open": OPEN}, as_dict=True)
	mo = sorted((r for r in rows if r.status in OPEN), key=lambda r: (0 if r.severity == "do" else 1,
		-cint(r.priority), r.first_seen or datetime.datetime.max, cstr(r.signal_key)))
	moi = {r.name: i for i, r in enumerate(mo, 1)}
	for r in rows:   # dòng không còn mở (bo-qua, dong) về 0 để không chen vào thứ tự
		if cint(r.get("rank")) != moi.get(r.name, 0):
			frappe.db.set_value(INSIGHT, r.name, {"rank": moi.get(r.name, 0)})


# ─── Nhật ký lượt chạy ───────────────────────────────────────────────────────
def start_run(run_type: str, step: str, provider: str | None = None, model: str | None = None, now=None,
		run_id: str | None = None) -> str:
	"""Tạo dòng BC AI Run (started = now) → name. Một lượt chạy = 1 dòng tổng (step "tong", status ok | loi = sức khoẻ
	của bước quy tắc) + các dòng con mang run_id = name dòng tổng: một dòng / lượt gọi mô hình (step = tên nhóm, có
	provider + model; status ok | loi | het-credit) hoặc MỘT dòng step "ai" khi cả bước AI bị bỏ (status tat |
	khong-khoa | vuot-tran, có provider, không token). Dòng tổng: run_id = chính nó (đặt sau khi tạo)."""
	if run_type not in RUN_TYPES:
		raise ValueError(f"bc.ai: loại lượt chạy không hợp lệ: {run_type}")
	tong = step == "tong"
	doc = frappe.get_doc({"doctype": RUN, "run_type": run_type, "step": _cat(step, DATA_LEN),
		"run_id": None if tong else (_cat(run_id, DATA_LEN) or None), "provider": _cat(provider, DATA_LEN) or None,
		"model": _cat(model, DATA_LEN) or None, "started": get_datetime(now) if now else now_datetime(),
		"finished": None, "status": "loi", "error": DANG_CHAY, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0,
		"cost_known": 0, "signals": 0, "insights_ai": 0, "rejected": 0})
	doc.insert(ignore_permissions=True)
	if tong:
		frappe.db.set_value(RUN, doc.name, {"run_id": doc.name})
	return doc.name


def finish_run(name: str, *, status: str, now=None, tokens_in: int = 0, tokens_out: int = 0, cost_usd=None,
		signals: int = 0, insights_ai: int = 0, rejected: int = 0, error: str | None = None, kpis: dict | None = None,
		model: str | None = None) -> None:
	"""Chốt dòng Run. cost_usd None = chưa khai giá (cost_known 0, cost_usd 0). error cắt 300 ký tự (nơi gọi đã xoá
	khoá). Không lưu đề bài, không lưu gói số."""
	if status not in RUN_STATUSES:
		raise ValueError(f"bc.ai: kết quả lượt chạy không hợp lệ: {status}")
	f = {"status": status, "finished": get_datetime(now) if now else now_datetime(), "tokens_in": cint(tokens_in),
		"tokens_out": cint(tokens_out), "cost_usd": 0 if cost_usd is None else flt(cost_usd),
		"cost_known": 0 if cost_usd is None else 1, "signals": cint(signals), "insights_ai": cint(insights_ai),
		"rejected": cint(rejected), "error": _cat(error, ERROR_LEN) or None}
	if kpis is not None:
		f["kpis"] = json.dumps(kpis, ensure_ascii=False, default=str)
	if model:
		f["model"] = _cat(model, DATA_LEN)
	frappe.db.set_value(RUN, name, f)


# ─── Dọn ─────────────────────────────────────────────────────────────────────
def _moc(now, days: int) -> datetime.datetime:
	"""00:00 của ngày (hôm nay − days): dòng TRƯỚC mốc này mới bị xoá."""
	return datetime.datetime.combine(getdate(now) - datetime.timedelta(days=days), datetime.time())


def _xoa(doctype: str, where: str, params: dict) -> int:
	names = [r[0] for r in frappe.db.sql(f"SELECT name FROM `tab{doctype}` WHERE {where}", params)]
	for lo in _lo(names):
		frappe.db.delete(doctype, {"name": ("in", list(lo))})
	return len(names)


_CO_KPI = "step = 'tong' AND IFNULL(kpis, '') NOT IN ('', '{}', 'null')"   # dòng tổng mang ảnh chụp KPI


def cleanup(now) -> dict:
	"""Xoá Insight dong quá KEEP_CLOSED_DAYS ngày (theo closed_on), Run quá KEEP_RUN_DAYS ngày (theo started) — trừ dòng
	tổng có ảnh chụp KPI: giữ KEEP_KPI_DAYS ngày — và BC AI Brief có brief_date quá KEEP_KPI_DAYS ngày (cùng cách đếm
	ngày lịch). Trả số dòng đã xoá {"insights", "runs"} (+ "briefs" khi có bản tin bị xoá)."""
	moc, moc_kpi = _moc(now, KEEP_RUN_DAYS), _moc(now, KEEP_KPI_DAYS)
	out = {
		"insights": _xoa(INSIGHT, "status = 'dong' AND IFNULL(closed_on, modified) < %(moc)s",
			{"moc": _moc(now, KEEP_CLOSED_DAYS)}),
		"runs": _xoa(RUN, f"IFNULL(started, creation) < %(moc)s AND NOT ({_CO_KPI} AND IFNULL(started, creation) >= "
			"%(moc_kpi)s)", {"moc": moc, "moc_kpi": moc_kpi}),
	}
	briefs = _xoa(BRIEF, "IFNULL(brief_date, creation) < %(moc_kpi)s", {"moc_kpi": moc_kpi}) \
		if frappe.db.table_exists(BRIEF) else 0   # site chưa migrate DocType mới: bỏ qua
	if briefs:
		out["briefs"] = briefs
	return out


# ─── Bản tin tuần / tháng (BC AI Brief) ──────────────────────────────────────
def brief_key(brief_type: str, brief_date) -> str:
	"""Khoá duy nhất của một bản tin: "<loại>:<yyyy-mm-dd>"."""
	return f"{brief_type}:{getdate(brief_date).isoformat()}"


def _parts(parts) -> list:
	"""Chuẩn hoá phần thân: [{"key", "title", "items": [{"text", "sections": [..]}]}] — bỏ mục chữ rỗng."""
	out = []
	for p in parts or []:
		if not isinstance(p, dict):
			continue
		items = []
		for it in p.get("items") or []:
			if not isinstance(it, dict):
				continue
			text = cstr(it.get("text")).strip()
			if text:
				items.append({"text": text, "sections": _uniq(it.get("sections") or [])})
		out.append({"key": cstr(p.get("key")), "title": cstr(p.get("title")), "items": items})
	return out


def upsert_brief(brief_type: str, brief_date, *, title: str, parts: list, sections_used, source: str,
		model: str | None = None, period_from=None, period_to=None) -> str:
	"""Ghi một bản tin — MỘT dòng / (loại, ngày) theo brief_key: có rồi → ghi đè mọi field; chưa có → tạo. Trả name.

	brief_type ∈ BRIEF_TYPES, source ∈ BRIEF_SOURCES (sai → ValueError). parts = [{"key", "title", "items": [{"text":
	lời ĐÃ thay số và kiểm, "sections": [mảng mà lời đó dựa vào]}]}] → body JSON {"parts": …} (mục chữ rỗng bị bỏ).
	sections_used: hợp mọi mảng (mỗi dòng một mã). title gộp một dòng, cắt TITLE_LEN không cắt giữa số. model: mô hình
	thực trả lời (quy-tac: None). Không lưu đề bài, không lưu gói số."""
	from bc.ai.render import _cat as cat_an_toan

	if brief_type not in BRIEF_TYPES:
		raise ValueError(f"bc.ai: loại bản tin không hợp lệ: {brief_type}")
	if source not in BRIEF_SOURCES:
		raise ValueError(f"bc.ai: nguồn bản tin không hợp lệ: {source}")
	key = brief_key(brief_type, brief_date)
	f = {"brief_type": brief_type, "brief_date": getdate(brief_date),
		"period_from": getdate(period_from) if period_from else None,
		"period_to": getdate(period_to) if period_to else None,
		"title": cat_an_toan(" ".join(cstr(title).split()), TITLE_LEN),
		"body": json.dumps({"parts": _parts(parts)}, ensure_ascii=False, default=str),
		"sections_used": "\n".join(_tach(sections_used) if isinstance(sections_used, str) else _uniq(sections_used)),
		"source": source, "model": _cat(model, DATA_LEN) or None}
	have = frappe.db.sql(f"SELECT name FROM `tab{BRIEF}` WHERE brief_key = %s ORDER BY creation LIMIT 1", (key,))
	if have:
		frappe.db.set_value(BRIEF, have[0][0], f)
		return have[0][0]
	doc = frappe.get_doc({"doctype": BRIEF, "brief_key": key, **f})
	doc.insert(ignore_permissions=True)
	return doc.name


def latest_briefs(types=("tuan", "thang"), limit: int = 1) -> list:
	"""Bản tin mới nhất: tối đa `limit` dòng / loại, theo thứ tự `types` rồi brief_date mới trước. Mỗi dòng: {"name",
	"brief_type", "brief_date" (date), "period_from", "period_to" (date | None), "title", "parts": [{"key", "title",
	"items": [{"text", "sections": [..]}]}], "sections_used": [..], "source", "model"}. KHÔNG lọc mảng ẩn — nơi gọi (API)
	lọc theo người xem."""
	out = []
	for t in _uniq(types):
		rows = frappe.db.sql(f"""SELECT name, brief_type, brief_date, period_from, period_to, title, body, sections_used,
			source, model FROM `tab{BRIEF}` WHERE brief_type = %s ORDER BY brief_date DESC, modified DESC LIMIT %s""",
			(t, max(0, cint(limit))), as_dict=True)
		for r in rows:
			try:
				body = json.loads(r.body or "{}")
			except (TypeError, ValueError):
				body = {}
			out.append({"name": r.name, "brief_type": r.brief_type,
				"brief_date": getdate(r.brief_date) if r.brief_date else None,
				"period_from": getdate(r.period_from) if r.period_from else None,
				"period_to": getdate(r.period_to) if r.period_to else None, "title": cstr(r.title),
				"parts": _parts(body.get("parts") if isinstance(body, dict) else []),
				"sections_used": _tach(r.sections_used), "source": cstr(r.source), "model": cstr(r.model)})
	return out
