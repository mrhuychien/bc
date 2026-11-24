# -*- coding: utf-8 -*-
"""bc.ai.budget — chi phí và trần chi (đặc tả §5.5).

Chi phí = tokens_in × price_in + tokens_out × price_out (USD / 1 triệu token, BC Settings.ai_prices theo ĐÚNG tên
model). Model chưa khai giá → None ("chưa khai giá"). Kỳ = từ ngày ai_cycle_day_<provider> gần nhất (mặc định 1) đến
nay. Đã chi ≥ trần mềm (ai_cap_<provider>_usd, mặc định 90) → không gọi. Chặn cứng: ≤ MAX_CALLS_PER_DAY lượt gọi /
ngày / provider, kể cả khi chưa khai giá. Số đã chi / số lượt lấy từ BC AI Run (dòng có provider).

Bẫy đã xử lý:
- Trần là Float: "chưa từng đặt" (không có dòng trong tabSingles → 90) KHÁC "đặt 0" (chặn mọi lượt gọi) — doc đọc ra
  đều là 0 nên phải đọc thẳng tabSingles. Quản trị xoá trắng ô rồi lưu trên Desk = Frappe ghi 0 = chặn.
- Ngày kỳ lớn hơn số ngày của tháng (31 trong tháng 30 ngày, 30 trong tháng 2) → ngày cuối tháng đó.
- Hôm nay chưa tới ngày kỳ của tháng này → kỳ bắt đầu từ ngày kỳ của THÁNG TRƯỚC.
- Dòng tổng của lượt chạy (step "tong") và dòng "bước AI bị bỏ" (step "ai": tắt / thiếu khoá / vượt trần) không phải
  lượt gọi mạng → không đếm vào số lượt trong ngày.
- Hỏi đáp (P3, run_type "hoi-dap", MỘT dòng / câu hỏi, số lượt gọi thật ở kpis.goi): KHÔNG tính vào 30 lượt / ngày của
  lượt chạy sáng; giới hạn riêng MAX_QA_CALLS_PER_DAY lượt gọi / ngày (qa_calls_today — câu chưa xong giữ chỗ đủ
  QA_RESERVE lượt). Chi phí hỏi đáp VẪN tính vào trần chi theo kỳ của Claude (spent đếm mọi dòng có provider).
Mọi mốc ngày truyền từ Python (không NOW() / CURDATE() trong SQL).
"""

from __future__ import annotations

import calendar
import datetime
import json

import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

from bc.api._common import get_settings, setting_int

MAX_CALLS_PER_DAY = 30
MAX_QA_CALLS_PER_DAY = 300                    # hỏi đáp: lượt gọi / ngày, riêng (đặc tả P3 §6)
QA_RUN = "hoi-dap"                            # run_type của dòng hỏi đáp
QA_RESERVE = 7                                # câu chưa xong giữ chỗ = số lượt gọi tối đa / câu (bc.ai.qa.MAX_CALLS)
DEFAULT_CAP_USD = 90.0
RUN = "BC AI Run"
NOT_CALLS = ("tong", "ai")                    # step của dòng không gọi mạng
CALLED = ("ok", "loi", "het-credit")          # status của dòng đã thật sự gọi mạng


def price_of(model: str):
	"""(price_in, price_out) của model theo BC Settings.ai_prices, hoặc None nếu chưa khai (dòng giá 0/0 = chưa khai)."""
	model = str(model or "").strip()
	found = None
	for r in (get_settings().get("ai_prices") or []):
		if model and str(r.get("model") or "").strip() == model:   # đúng tên, phân biệt hoa thường; dòng sau thắng
			found = (flt(r.get("price_in")), flt(r.get("price_out")))
	if not found or (found[0] <= 0 and found[1] <= 0):
		return None
	return found


def cost(model: str, tokens_in: int, tokens_out: int):
	"""Chi phí USD (float, làm tròn 6 số lẻ) hoặc None nếu chưa khai giá."""
	p = price_of(model)
	if p is None:
		return None
	return round((cint(tokens_in) * p[0] + cint(tokens_out) * p[1]) / 1_000_000, 6)


def _day_in(year: int, month: int, day: int) -> datetime.date:
	return datetime.date(year, month, min(day, calendar.monthrange(year, month)[1]))


def cycle_start(provider: str, today=None):
	"""Ngày bắt đầu kỳ credit hiện tại (date). Ngày kỳ > số ngày của tháng → ngày cuối tháng."""
	today = getdate(today or nowdate())
	day = min(max(setting_int(f"ai_cycle_day_{provider}", 1), 1), 31)   # trống / 0 / âm → 1
	start = _day_in(today.year, today.month, day)
	if today >= start:
		return start
	year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
	return _day_in(year, month, day)


def cap(provider: str) -> float:
	"""Trần mềm USD / kỳ (ô trống → 90; đặt 0 = chặn mọi lượt gọi)."""
	r = frappe.db.sql("SELECT value FROM `tabSingles` WHERE doctype = %s AND field = %s",
		("BC Settings", f"ai_cap_{provider}_usd"))
	if not r or r[0][0] is None or str(r[0][0]).strip() == "":
		return DEFAULT_CAP_USD
	return max(flt(r[0][0]), 0.0)


def spent(provider: str, today=None) -> float:
	"""Tổng cost_usd của BC AI Run thuộc provider từ đầu kỳ đến nay."""
	today = getdate(today or nowdate())
	r = frappe.db.sql(
		f"""SELECT SUM(cost_usd) FROM `tab{RUN}`
			WHERE provider = %(p)s AND started >= %(tu)s AND started < %(den)s""",
		{"p": provider, "tu": str(cycle_start(provider, today)), "den": str(add_days(today, 1))})
	return flt(r[0][0]) if r else 0.0


def calls_today(provider: str, today=None) -> int:
	"""Số lượt gọi mô hình hôm nay của provider (dòng BC AI Run có provider, mọi trạng thái đã thật sự gọi mạng) — TRỪ
	hỏi đáp (run_type hoi-dap: giới hạn riêng, qa_calls_today)."""
	today = getdate(today or nowdate())
	r = frappe.db.sql(
		f"""SELECT COUNT(*) FROM `tab{RUN}`
			WHERE provider = %(p)s AND IFNULL(step, '') NOT IN %(bo)s AND status IN %(goi)s
				AND IFNULL(run_type, '') != %(qa)s AND started >= %(tu)s AND started < %(den)s""",
		{"p": provider, "bo": NOT_CALLS, "goi": CALLED, "qa": QA_RUN, "tu": str(today), "den": str(add_days(today, 1))})
	return cint(r[0][0]) if r else 0


def _goi(kpis) -> int:
	"""kpis.goi của dòng hỏi đáp (số lượt gọi thật); hỏng / thiếu → 0."""
	try:
		d = json.loads(kpis) if isinstance(kpis, (str, bytes)) else kpis
	except ValueError:
		return 0
	return max(cint(d.get("goi")), 0) if isinstance(d, dict) else 0


def qa_calls_today(today=None) -> int:
	"""Số lượt gọi mô hình của hỏi đáp hôm nay (mọi người): câu đã xong → kpis.goi; câu chưa xong (finished trống) giữ
	chỗ max(goi, QA_RESERVE) — hai câu cùng lúc không vượt được trần ngày."""
	today = getdate(today or nowdate())
	rows = frappe.db.sql(
		f"""SELECT kpis, finished FROM `tab{RUN}` WHERE run_type = %(qa)s AND started >= %(tu)s AND started < %(den)s""",
		{"qa": QA_RUN, "tu": str(today), "den": str(add_days(today, 1))})
	return sum(_goi(k) if f else max(_goi(k), QA_RESERVE) for k, f in rows)


def can_call_qa(provider: str, today=None, need: int = 0) -> tuple:
	"""Hỏi đáp: (được_gọi, "" | "vuot-tran" | "qua-so-luot"). Cùng trần chi theo kỳ với lượt ngày; số lượt gọi theo
	MAX_QA_CALLS_PER_DAY (need = số lượt sắp giữ chỗ — câu mới: QA_RESERVE; trong lúc chạy: 0, đã giữ chỗ)."""
	if spent(provider, today) >= cap(provider):
		return False, "vuot-tran"
	if qa_calls_today(today) + cint(need) > MAX_QA_CALLS_PER_DAY:
		return False, "qua-so-luot"
	return True, ""


def can_call(provider: str, today=None) -> tuple:
	"""(được_gọi: bool, lý_do: "" | "vuot-tran" | "qua-so-luot")."""
	if spent(provider, today) >= cap(provider):   # trần 0 → 0 ≥ 0 → chặn
		return False, "vuot-tran"
	if calls_today(provider, today) >= MAX_CALLS_PER_DAY:
		return False, "qua-so-luot"
	return True, ""
