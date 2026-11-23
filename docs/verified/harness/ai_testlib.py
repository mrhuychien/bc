"""Tiện ích chung cho các bộ thử Trợ lý AI (test_ai_*.py).

- goi("cn.get_receivables", ...)   gọi method bc.api thật dưới Administrator, refresh=1 → payload
- kiem_loi(sig, pack)              lỗi của LỜI một tín hiệu: placeholder không phân giải được / sai kiểu so với giá trị
- chay(pack, only, overrides)      run_rules chỉ với module quy tắc của bộ thử (không import module agent khác đang viết)
"""
from __future__ import annotations

import datetime
import decimal
import importlib

import frappe

ADMIN, VIEWER = "Administrator", "viewer@example.com"


def goi(dotted: str, **kw):
	"""bc.api.<module>.<method>(refresh=1, **kw) dưới Administrator."""
	mod, fn = dotted.split(".")
	cu = frappe.session.user
	frappe.session.user = ADMIN
	try:
		return getattr(importlib.import_module(f"bc.api.{mod}"), fn)(refresh=1, **kw)
	finally:
		frappe.session.user = cu


def chi_module(*modules):
	"""Chỉ nạp các module quy tắc / detector này (vd chi_module("bc.ai.rules.cn")) — module khác có thể đang viết dở."""
	from bc.ai import registry
	registry._MODULES = tuple(modules)
	registry.load()
	return registry


def _khop(value, kind) -> bool:
	if kind in ("tien", "so", "pct"):
		if isinstance(value, decimal.Decimal):      # cột Float đọc bằng SQL thô — render.fmt cũng nhận
			return value.is_finite()
		return isinstance(value, (int, float)) and not isinstance(value, bool)
	if kind == "ngay":
		if isinstance(value, (datetime.date, datetime.datetime)):
			return True
		try:
			datetime.date.fromisoformat(str(value)[:10])
			return isinstance(value, str)
		except ValueError:
			return False
	if kind == "chu":
		return isinstance(value, str) and len(value) <= 120
	return False


def kiem_loi(sig, pack) -> list:
	"""[] nếu mọi placeholder trong title / detail của tín hiệu phân giải được trên pack và giá trị khớp kiểu."""
	from bc.ai import registry
	loi = []
	for path, kind in registry.placeholders((sig.title or "") + " " + (sig.detail or "")):
		if kind not in registry.KINDS:
			loi.append(f"kieu-la:{kind}")
			continue
		try:
			v = registry.resolve(pack, path)
		except registry.PathError:
			loi.append(f"path:{path}")
			continue
		if not _khop(v, kind):
			loi.append(f"kieu:{path}={v!r}|{kind}")
	if "{{" in registry.PLACEHOLDER.sub("", (sig.title or "") + (sig.detail or "")):
		loi.append("cu-phap")
	return loi
