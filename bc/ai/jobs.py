# -*- coding: utf-8 -*-
"""bc.ai.jobs — điểm vào scheduler / nút "Chạy ngay" của Trợ lý AI: CHỈ xếp hàng job nền, không tính gì ở đây.

Chống chạy trùng hai lớp: `job_id` + deduplicate của frappe.enqueue (job đang chờ / đang chạy thì không xếp nữa) và
khoá cache LOCK_KEY do bc.ai.pipeline.run_daily giữ trong lúc chạy (LOCK_TTL giây — job chết giữa chừng thì khoá tự
hết). Khoá KHÔNG mang tiền tố "bc:" vì lưu BC Settings xoá mọi khoá "bc:*".
Cron trong hooks.py chạy theo múi giờ của site (System Settings › Time Zone) — v16 so cron với now_datetime().
"""

from __future__ import annotations

import frappe

JOB_ID = "bc_ai_daily"
LOCK_KEY = "bcai:lock"
LOCK_TTL = 1800          # giây
JOB_TIMEOUT = 1800       # giây — bằng trần của một lượt chạy (bc.ai.pipeline tự dừng gọi mô hình trước mốc này)


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
