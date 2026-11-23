# -*- coding: utf-8 -*-
"""bc.ai.redact — mã giả khách / nhà cung cấp trước khi gửi gói số cho mô hình (đặc tả §5.4).

Bảng ánh xạ dựng MỖI LƯỢT từ tabCustomer (name, customer_name) và tabSupplier (name, supplier_name) → "KH#0001…",
"NCC#0001…" (một đối tác một mã, cả mã chứng từ lẫn tên hiển thị cùng về mã đó). Chỉ thay chuỗi BẰNG ĐÚNG một tên
(không thay chuỗi con). Bảng không lưu, không gửi. Path luôn phân giải trên pack GỐC (bc.ai.render) nên số / tên chèn
vào lời là thật.

Chi tiết:
- "Bằng đúng" = bằng nhau sau khi bỏ khoảng trắng hai đầu (phân biệt hoa / thường, dấu). Chỉ thay GIÁ TRỊ chuỗi —
  khoá dict giữ nguyên (path phải phân giải như nhau trên bản gốc và bản che), số / ngày / None không đụng tới.
- Hai đối tác trùng một chuỗi (khách và NCC cùng tên, hai khách trùng tên hiển thị): chuỗi về mã của đối tác đứng
  TRƯỚC trong danh sách (khách trước NCC, trong mỗi loại theo `name` tăng dần). Hoàn nguyên vẫn ra đúng chuỗi đó.
- Mã giả trong lời chỉ được nhận khi đứng riêng thành một từ ("KH#0001," được; "KH#00012", "KH#0001x" không) — mã
  không có trong bảng (mô hình bịa) để nguyên cho lint của bc.ai.render bắt.
"""

from __future__ import annotations

import re

import frappe

# (DocType, cột tên hiển thị, tiền tố mã giả) — thứ tự = thứ tự ưu tiên khi trùng chuỗi.
NGUON = (("Customer", "customer_name", "KH"), ("Supplier", "supplier_name", "NCC"))

TEN_TOI_THIEU = 4        # mask_text: tên ngắn hơn không thay trong chữ tự do
_MA = re.compile(r"(?<![\w#])[A-Za-z]+#\d+(?![\w#])")     # dạng mã giả chuẩn: KH#0001, NCC#0012


class Mask:
	"""Bộ mã giả của một lượt chạy. Mask() rỗng = không che gì (ai_mask_parties tắt)."""

	def __init__(self, parties=None):
		"""parties: [(mã_giả, tên_hiển_thị, {các chuỗi cần thay})]."""
		self._ma: dict = {}      # chuỗi cần thay (đã bỏ khoảng trắng hai đầu) → mã giả
		self._ten: dict = {}     # mã giả → tên hiển thị thật
		for ma, ten, chuoi in (parties or ()):
			ma = str(ma)
			if ma in self._ten:
				continue
			ds = [s.strip() for s in (chuoi or ()) if isinstance(s, str) and s.strip()]
			self._ten[ma] = ten.strip() if isinstance(ten, str) and ten.strip() else (sorted(ds)[0] if ds else ma)
			for s in ds:
				self._ma.setdefault(s, ma)      # trùng chuỗi: đối tác đứng trước giữ
		# Mã không theo dạng chuẩn (nơi gọi tự đặt) → soát bằng biểu thức riêng, dài trước.
		le = sorted((m for m in self._ten if not _MA.fullmatch(m)), key=len, reverse=True)
		self._le = re.compile(r"(?<![\w#])(?:" + "|".join(map(re.escape, le)) + r")(?![\w#])") if le else None
		self._tu_do = None       # biểu thức cho mask_text, dựng khi cần

	def mask(self, obj):
		"""Bản SAO sâu của obj (dict / list / scalar), mọi chuỗi (giá trị, KHÔNG phải khoá dict) bằng đúng một tên đã
		biết → mã giả. Không đổi obj gốc."""
		if isinstance(obj, dict):
			return {k: self.mask(v) for k, v in obj.items()}
		if isinstance(obj, list):
			return [self.mask(v) for v in obj]
		if isinstance(obj, tuple):
			return tuple(self.mask(v) for v in obj)
		if isinstance(obj, str):
			return self._ma.get(obj.strip(), obj)
		return obj

	def mask_text(self, text) -> str:
		"""Chữ TỰ DO (ghi chú của quản trị): thay mọi tên đã biết xuất hiện như chuỗi con → mã giả, tên dài trước.
		Chỉ thay tên từ TEN_TOI_THIEU ký tự (tên quá ngắn dễ trùng một phần của từ khác) và chỉ khi tên đứng riêng,
		không dính chữ / số hai bên. Là che HẾT SỨC: tên gọi tắt, tên viết khác hồ sơ không nhận ra được."""
		text = "" if text is None else str(text)
		if not self._ma or not text:
			return text
		if self._tu_do is None:
			ds = sorted((s for s in self._ma if len(s) >= TEN_TOI_THIEU), key=len, reverse=True)
			self._tu_do = re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, ds)) + r")(?!\w)") if ds else False
		if not self._tu_do:
			return text
		return self._tu_do.sub(lambda m: self._ma[m.group(0)], text)

	def _thay(self, text, fn) -> str:
		text = "" if text is None else str(text)
		if not self._ten:
			return text
		text = _MA.sub(lambda m: fn(m.group(0)) if m.group(0) in self._ten else m.group(0), text)
		if self._le is not None:
			text = self._le.sub(lambda m: fn(m.group(0)), text)
		return text

	def unmask(self, text: str) -> str:
		"""Thay mọi mã giả ĐÃ BIẾT trong text về tên hiển thị thật."""
		return self._thay(text, lambda ma: self._ten[ma])

	def strip(self, text: str) -> str:
		"""Bỏ mọi mã giả ĐÃ BIẾT khỏi text (thay bằng dấu cách) — để lint không bắt nhầm chữ số trong mã giả; mã giả lạ
		(mô hình bịa) giữ nguyên để lint bắt."""
		return self._thay(text, lambda ma: " ")


def _doi_tac(doctype: str, cot: str) -> list:
	"""[(name, tên hiển thị)] của một DocType, sắp theo `name` ở Python (không phụ thuộc collation của DB). Thiếu
	bảng → []; thiếu cột tên → chỉ dùng `name`."""
	if not frappe.db.table_exists(doctype):
		return []
	chon = f"`name`, `{cot}`" if frappe.db.has_column(doctype, cot) else "`name`, NULL"
	rows = frappe.db.sql(f"SELECT {chon} FROM `tab{doctype}`")
	return sorted(((r[0], r[1]) for r in rows if r[0]), key=lambda r: r[0])


def build(enabled: bool = True) -> Mask:
	"""Mask từ tabCustomer / tabSupplier (đọc mềm: thiếu bảng thì bỏ). enabled False → Mask rỗng. Mã đánh số theo thứ
	tự `name` tăng dần (ổn định trong một lượt)."""
	if not enabled:
		return Mask()
	parties = []
	for doctype, cot, tien_to in NGUON:
		for i, (name, ten) in enumerate(_doi_tac(doctype, cot), 1):
			parties.append((f"{tien_to}#{i:04d}", ten or name, {name, ten}))
	return Mask(parties)
