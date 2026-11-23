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
"""

from __future__ import annotations

INSIGHT = "BC AI Insight"
RUN = "BC AI Run"
OPEN = ("mo", "dang-xu-ly")
KEEP_CLOSED_DAYS = 180
KEEP_RUN_DAYS = 180


def sync_signals(items: list, ran, now) -> dict:
	"""Đồng bộ tín hiệu theo quy tắc của một lượt chạy.

	items: tín hiệu ĐÃ dựng lời — dict {"key", "rule", "section", "audience", "severity", "route", "title", "body",
	"paths": [..], "sections_used": [..], "documents": [..]}. ran: tập mã quy tắc đã chạy (gồm quy tắc đang tắt) —
	Insight (rule ≠ "ai") của các quy tắc này không còn trong items thì đóng. Trả {"new", "kept", "reopened", "closed",
	"muted", "names": {key: name}}."""
	raise NotImplementedError


def open_for_llm(sections, limit: int) -> list:
	"""Tín hiệu gửi mô hình của một nhóm: Insight rule ≠ "ai", status mo / dang-xu-ly, section ∈ sections; đỏ trước rồi
	first_seen mới trước; tối đa `limit`. Mỗi dòng: {"name", "signal_key", "rule", "section", "severity", "status",
	"first_seen", "admin_note", "paths": [..]}."""
	raise NotImplementedError


def apply_ai(name: str, *, title: str, body: str, advice: list, severity: str, priority: int, paths: list,
		sections_used: list, now) -> None:
	"""Gắn lời AI vào Insight của một tín hiệu: source ai, text_at now, needs_check 0. severity = max(mức đang có, mức
	mô hình) — mô hình không hạ được mức đỏ. paths / sections_used = HỢP của quy tắc và lời AI."""
	raise NotImplementedError


def mark_rejected(name: str) -> None:
	"""Lời AI lượt này cho Insight bị loại: needs_check 1, giữ lời quy tắc."""
	raise NotImplementedError


def sync_ai_free(sections, items: list, now) -> dict:
	"""Nhận định TỰ DO của mô hình cho một nhóm (rule "ai", source "ai", audience lanh-dao).

	items: [{"key": "ai:<path bỏ chỉ số>", "section", "route", "severity", "priority", "title", "body", "advice": [..],
	"paths", "sections_used"}] (nơi gọi đã cắt ≤ 3). Upsert theo key như tín hiệu; Insight rule "ai" đang mở có section
	∈ sections mà không còn trong items → dong (kể cả khi items rỗng: lượt gọi lỗi / AI tắt). bo-qua còn hạn: giữ.
	Trả {"new", "kept", "closed"}."""
	raise NotImplementedError


def rerank() -> None:
	"""Đánh `rank` 1..n cho Insight mo / dang-xu-ly: đỏ trước, priority cao trước, first_seen cũ trước, signal_key."""
	raise NotImplementedError


def start_run(run_type: str, step: str, provider: str | None = None, model: str | None = None, now=None,
		run_id: str | None = None) -> str:
	"""Tạo dòng BC AI Run (started = now) → name. Một lượt chạy = 1 dòng tổng (step "tong", status ok | loi = sức khoẻ
	của bước quy tắc) + các dòng con mang run_id = name dòng tổng: một dòng / lượt gọi mô hình (step = tên nhóm, có
	provider + model; status ok | loi | het-credit) hoặc MỘT dòng step "ai" khi cả bước AI bị bỏ (status tat |
	khong-khoa | vuot-tran, có provider, không token). Dòng tổng: run_id = chính nó (đặt sau khi tạo)."""
	raise NotImplementedError


def finish_run(name: str, *, status: str, now=None, tokens_in: int = 0, tokens_out: int = 0, cost_usd=None,
		signals: int = 0, insights_ai: int = 0, rejected: int = 0, error: str | None = None, kpis: dict | None = None,
		model: str | None = None) -> None:
	"""Chốt dòng Run. cost_usd None = chưa khai giá (cost_known 0, cost_usd 0). error cắt 300 ký tự (nơi gọi đã xoá
	khoá). Không lưu đề bài, không lưu gói số."""
	raise NotImplementedError


def cleanup(now) -> dict:
	"""Xoá Insight dong quá KEEP_CLOSED_DAYS ngày (theo closed_on) và Run quá KEEP_RUN_DAYS ngày (theo started). Trả số
	dòng đã xoá."""
	raise NotImplementedError
