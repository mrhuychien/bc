# -*- coding: utf-8 -*-
"""bc.ai.jobs — điểm vào scheduler / nút "Chạy ngay" của Trợ lý AI: CHỈ xếp hàng job nền, không tính gì ở đây.

Chống chạy trùng hai lớp: `job_id` + deduplicate của frappe.enqueue (job đang chờ / đang chạy thì không xếp nữa) và
khoá cache LOCK_KEY do bc.ai.pipeline.run_daily giữ trong lúc chạy (LOCK_TTL giây — job chết giữa chừng thì khoá tự
hết). Khoá KHÔNG mang tiền tố "bc:" vì lưu BC Settings xoá mọi khoá "bc:*".
Cron trong hooks.py chạy theo múi giờ của site (System Settings › Time Zone) — v16 so cron với now_datetime().

Bản tin tuần / tháng (P2, bc.ai.brief.run_brief): job id riêng từng loại (BRIEF_JOB_IDS) và MỘT khoá riêng
BRIEF_LOCK_KEY (bc.ai.brief giữ trong lúc chạy) — bản tin không chặn lượt ngày và ngược lại; hai loại bản tin không chạy
chồng nhau.
"""

from __future__ import annotations

import frappe

JOB_ID = "bc_ai_daily"
LOCK_KEY = "bcai:lock"
LOCK_TTL = 1800          # giây
JOB_TIMEOUT = 1800       # giây — bằng trần của một lượt chạy (bc.ai.pipeline tự dừng gọi mô hình trước mốc này)

BRIEF_KINDS = ("tuan", "thang")
BRIEF_JOB_IDS = {"tuan": "bc_ai_brief_tuan", "thang": "bc_ai_brief_thang"}
BRIEF_LOCK_KEY = "bcai:lock:brief"   # bc.ai.brief.run_brief giữ (đặt / xoá) — chung cho hai loại bản tin
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
def brief_running(kind: str) -> bool:
	"""Một bản tin đang chạy (khoá BRIEF_LOCK_KEY — loại nào cũng vậy) hoặc job bản tin loại `kind` đang chờ / chạy.
	Không xét khoá của lượt ngày. kind ∉ BRIEF_KINDS → ValueError."""
	if kind not in BRIEF_KINDS:
		raise ValueError(f"bc.ai: loại bản tin không hợp lệ: {kind}")
	if frappe.cache().get_value(BRIEF_LOCK_KEY):
		return True
	try:
		from frappe.utils.background_jobs import is_job_enqueued
		return bool(is_job_enqueued(BRIEF_JOB_IDS[kind]))
	except Exception:  # Redis hàng đợi không nối được → như is_running
		return False


def enqueue_brief(kind: str) -> bool:
	"""Xếp job bc.ai.brief.run_brief(kind=kind) vào hàng `long`. kind ∉ BRIEF_KINDS → ValueError. Đang có bản tin chạy /
	job loại này đang chờ → không xếp, trả False."""
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
