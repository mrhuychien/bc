# -*- coding: utf-8 -*-
"""bc.ai.budget — chi phí và trần chi (đặc tả §5.5).

Chi phí = tokens_in × price_in + tokens_out × price_out (USD / 1 triệu token, BC Settings.ai_prices theo ĐÚNG tên
model). Model chưa khai giá → None ("chưa khai giá"). Kỳ = từ ngày ai_cycle_day_<provider> gần nhất (mặc định 1) đến
nay. Đã chi ≥ trần mềm (ai_cap_<provider>_usd, mặc định 90) → không gọi. Chặn cứng: ≤ MAX_CALLS_PER_DAY lượt gọi /
ngày / provider, kể cả khi chưa khai giá. Số đã chi / số lượt lấy từ BC AI Run (dòng có provider).
"""

from __future__ import annotations

MAX_CALLS_PER_DAY = 30
DEFAULT_CAP_USD = 90.0


def price_of(model: str):
	"""(price_in, price_out) của model theo BC Settings.ai_prices, hoặc None nếu chưa khai (dòng giá 0/0 = chưa khai)."""
	raise NotImplementedError


def cost(model: str, tokens_in: int, tokens_out: int):
	"""Chi phí USD (float, làm tròn 6 số lẻ) hoặc None nếu chưa khai giá."""
	raise NotImplementedError


def cycle_start(provider: str, today=None):
	"""Ngày bắt đầu kỳ credit hiện tại (date). Ngày kỳ > số ngày của tháng → ngày cuối tháng."""
	raise NotImplementedError


def cap(provider: str) -> float:
	"""Trần mềm USD / kỳ (ô trống → 90; đặt 0 = chặn mọi lượt gọi)."""
	raise NotImplementedError


def spent(provider: str, today=None) -> float:
	"""Tổng cost_usd của BC AI Run thuộc provider từ đầu kỳ đến nay."""
	raise NotImplementedError


def calls_today(provider: str, today=None) -> int:
	"""Số lượt gọi mô hình hôm nay của provider (dòng BC AI Run có provider, mọi trạng thái đã thật sự gọi mạng)."""
	raise NotImplementedError


def can_call(provider: str, today=None) -> tuple:
	"""(được_gọi: bool, lý_do: "" | "vuot-tran" | "qua-so-luot")."""
	raise NotImplementedError
