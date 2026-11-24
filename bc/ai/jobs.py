# -*- coding: utf-8 -*-
"""bc.ai.jobs — điểm vào scheduler / nút "Chạy ngay" của Trợ lý AI: CHỈ xếp hàng job nền, không tính gì ở đây.

Chống chạy trùng hai lớp: `job_id` + deduplicate của frappe.enqueue (job đang chờ / đang chạy thì không xếp nữa) và
khoá cache LOCK_KEY do bc.ai.pipeline.run_daily giữ trong lúc chạy (LOCK_TTL giây — job chết giữa chừng thì khoá tự
hết). Khoá KHÔNG mang tiền tố "bc:" vì lưu BC Settings xoá mọi khoá "bc:*".
Cron trong hooks.py chạy theo múi giờ của site (System Settings › Time Zone) — v16 so cron với now_datetime().

Bản tin tuần / tháng (P2, bc.ai.brief.run_brief): job id riêng từng loại (BRIEF_JOB_IDS) và khoá riêng TỪNG LOẠI
brief_lock_key(kind) = "bcai:lock:brief:<loại>" (bc.ai.brief giữ trong lúc chạy) — bản tin không chặn lượt ngày và ngược
lại; hai loại bản tin chạy độc lập: thứ Hai trùng ngày 2, bản tin tuần (06:00, tới 1800 s, có thể chờ sau lượt ngày) còn
chạy lúc 07:00 thì bản tin tháng VẪN được xếp và chạy (khoá chung trước đây làm mất bản tin tháng đó — không ai xếp lại).
Cùng một loại thì không chạy chồng (job_id + deduplicate, và khoá của loại đó).
"""

from __future__ import annotations

import frappe

JOB_ID = "bc_ai_daily"
LOCK_KEY = "bcai:lock"
LOCK_TTL = 1800          # giây
JOB_TIMEOUT = 1800       # giây — bằng trần của một lượt chạy (bc.ai.pipeline tự dừng gọi mô hình trước mốc này)

BRIEF_KINDS = ("tuan", "thang")
BRIEF_JOB_IDS = {"tuan": "bc_ai_brief_tuan", "thang": "bc_ai_brief_thang"}
BRIEF_LOCK_KEY = "bcai:lock:brief"   # tiền tố; khoá thật của từng loại: brief_lock_key(kind)
BRIEF_LOCK_TTL = 1800    # giây
BRIEF_TIMEOUT = 1800     # giây / job bản tin


def is_running() -> bool:
	"""Một lượt chạy đang chờ trong hàng đợi hoặc đang chạy."""
	if frappe.cache().get_value(LOCK_KEY):
		return True
	try:
		from frappe.utils.background_jobs import is_job_enqueued
		return bool(is_job_enqueued(JOB_ID))
	except Exception:  # Redis hàng đợi không nối được → coi như không có job (enqueue sẽ tự báo lỗi nếu cần)
		return False


def enqueue_run(run_type: str = "ngay") -> bool:
	"""Xếp một lượt chạy vào hàng đợi `long`. Đang có lượt chạy → không xếp, trả False."""
	if is_running():
		return False
	frappe.enqueue("bc.ai.pipeline.run_daily", queue="long", timeout=JOB_TIMEOUT, job_id=JOB_ID, deduplicate=True,
		run_type=run_type)
	return True


def daily():
	"""Scheduler 05:30 hằng ngày (hooks.py)."""
	enqueue_run("ngay")


# ─── Bản tin tuần / tháng (P2) ───────────────────────────────────────────────
def brief_lock_key(kind: str) -> str:
	"""Khoá cache bc.ai.brief.run_brief(kind) giữ trong lúc chạy — riêng từng loại. kind ∉ BRIEF_KINDS → ValueError."""
	if kind not in BRIEF_KINDS:
		raise ValueError(f"bc.ai: loại bản tin không hợp lệ: {kind}")
	return f"{BRIEF_LOCK_KEY}:{kind}"


def brief_running(kind: str) -> bool:
	"""Bản tin loại `kind` đang chạy (khoá brief_lock_key(kind)) hoặc job loại đó đang chờ / chạy. Không xét khoá của
	lượt ngày, không xét loại bản tin kia. kind ∉ BRIEF_KINDS → ValueError."""
	if frappe.cache().get_value(brief_lock_key(kind)):
		return True
	try:
		from frappe.utils.background_jobs import is_job_enqueued
		return bool(is_job_enqueued(BRIEF_JOB_IDS[kind]))
	except Exception:  # Redis hàng đợi không nối được → như is_running
		return False


def enqueue_brief(kind: str) -> bool:
	"""Xếp job bc.ai.brief.run_brief(kind=kind) vào hàng `long`. kind ∉ BRIEF_KINDS → ValueError. Bản tin loại này đang
	chạy / đang chờ → không xếp, trả False (loại kia đang chạy thì vẫn xếp)."""
	if brief_running(kind):
		return False
	frappe.enqueue("bc.ai.brief.run_brief", queue="long", timeout=BRIEF_TIMEOUT, job_id=BRIEF_JOB_IDS[kind],
		deduplicate=True, kind=kind)
	return True


def weekly():
	"""Scheduler thứ Hai 06:00 (hooks.py): bản tin tuần."""
	enqueue_brief("tuan")


def monthly():
	"""Scheduler 07:00 ngày 2 hằng tháng (hooks.py): bản tin tháng."""
	enqueue_brief("thang")
