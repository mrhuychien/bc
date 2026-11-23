# -*- coding: utf-8 -*-
"""bc.ai.redact — mã giả khách / nhà cung cấp trước khi gửi gói số cho mô hình (đặc tả §5.4, quyết định D2–D4).

Bảng ánh xạ dựng MỖI LƯỢT từ tabCustomer (name, customer_name) và tabSupplier (name, supplier_name) → "KH#0001…",
"NCC#0001…" (một đối tác một mã, cả mã chứng từ lẫn tên hiển thị cùng về mã đó). Thêm: tên hiển thị CHÉP TRÊN HOÁ ĐƠN
đã duyệt (Sales Invoice.customer_name, Purchase Invoice.supplier_name — ERPNext không sửa lại khi đổi tên đối tác) là
bí danh của CÙNG mã; đối tác chỉ có trên hoá đơn (không còn hồ sơ) vẫn được một mã. Bảng không lưu, không gửi. Path
luôn phân giải trên pack GỐC (bc.ai.render) nên số / tên chèn vào lời là thật.

Chi tiết:
- mask (gói số): chuỗi BẰNG ĐÚNG một tên (sau khi bỏ khoảng trắng hai đầu; phân biệt hoa / thường, dấu) → mã. Chuỗi
  không bằng tên nào → mask_text (tên nằm giữa câu). Khoá dict giữ nguyên (path phải phân giải như nhau trên bản gốc
  và bản che); số / ngày / None không đụng tới.
- Đóng chặt theo khoá (D2): chuỗi khác rỗng nằm dưới khoá trong PARTY_KEYS mà không phải tên đã biết → vẫn ra mã: dùng
  mã của đối tác cùng dòng (khoá *_id / khoá đối tác khác của dict đó bằng đúng một tên đã biết) nếu có, không thì
  một mã MỚI (đánh số tiếp sau mã có sẵn) — hoàn nguyên ra đúng chuỗi đó.
- mask_text (chữ tự do, và mọi chuỗi không khớp đúng trong gói số — D3): thay tên đã biết đứng riêng thành từ (không
  dính chữ / số hai bên), chỉ tên ≥ 2 từ (dãy chữ / số: "NPP-B" là 2 từ) hoặc ≥ 6 ký tự (tên ngắn một từ dễ trùng
  chữ thường). Tên dài thắng.
- Hai đối tác trùng một chuỗi: chuỗi về mã của đối tác đứng TRƯỚC (khách trước NCC, trong mỗi loại theo `name` tăng
  dần; tên trên hồ sơ trước bí danh từ hoá đơn). Hoàn nguyên vẫn ra đúng tên hiển thị của mã đó.
- Chỉ mã ĐÃ GỬI mới được hoàn nguyên / bỏ (D4): mọi mã do mask / mask_text phát ra được ghi lại; begin() xoá bản ghi
  (nơi gọi gọi trước khi dựng đề bài mỗi nhóm). Mask chưa từng begin() cũng vậy: mã chỉ tính là đã gửi khi đã phát ra.
  Mã không có trong bản ghi (mô hình bịa / liệt kê) để nguyên cho lint của bc.ai.render bắt.
- Mã giả trong lời chỉ được nhận khi đứng riêng thành một từ ("KH#0001," được; "KH#00012", "KH#0001x" không).
"""

from __future__ import annotations

import re

import frappe

# (DocType, cột tên hiển thị, tiền tố mã giả, (DocType hoá đơn, cột mã đối tác, cột tên chép)) — thứ tự = ưu tiên.
NGUON = (
	("Customer", "customer_name", "KH", ("Sales Invoice", "customer", "customer_name")),
	("Supplier", "supplier_name", "NCC", ("Purchase Invoice", "supplier", "supplier_name")),
)

# Khoá trong payload bc.api.* chứa TÊN / mã khách, NCC (đã soát kd, tet, cn, vc, attp: "customer", "customer_id",
# "chain" của cong-no; "supplier" của phai-tra). Không có khoá chứa tên hàng, kho, hãng xe, xe, bộ phận, tỉnh.
PARTY_KEYS = {"customer", "customer_name", "customer_id", "khach", "khach_hang", "chain"}
SUPPLIER_KEYS = {"supplier", "supplier_name", "supplier_id", "ncc", "nha_cung_cap"}

TEN_TOI_THIEU = 6        # mask_text: tên MỘT từ ngắn hơn không thay trong chữ tự do (tên ≥ 2 từ thì luôn thay;
                         # "từ" = dãy chữ / số: "NPP-B", "Co.op", "Hà An" là 2 từ — "Hùng", "ABC" là 1)
_MA = re.compile(r"(?<![\w#])[A-Za-z]+#\d+(?![\w#])")     # dạng mã giả chuẩn: KH#0001, NCC#0012
_TU = re.compile(r"\w+")


def _tien_to(ma: str) -> str | None:
	m = re.fullmatch(r"([A-Za-z]+)#(\d+)", ma)
	return m.group(1) if m else None


class Mask:
	"""Bộ mã giả của một lượt chạy. Mask() rỗng = không che gì (ai_mask_parties tắt)."""

	def __init__(self, parties=None, on=None):
		"""parties: [(mã_giả, tên_hiển_thị, {các chuỗi cần thay})]. on: bật đóng chặt theo khoá (mặc định: có parties)."""
		self._ma: dict = {}      # chuỗi cần thay (đã bỏ khoảng trắng hai đầu) → mã giả
		self._ten: dict = {}     # mã giả → tên hiển thị thật
		self._gui: set = set()   # mã đã phát ra (đã gửi) từ lần begin() gần nhất
		self._so: dict = {}      # tiền tố → số lớn nhất đã dùng (mã mới đánh tiếp)
		self.on = bool(parties) if on is None else bool(on)   # Mask() rỗng: tắt che, kể cả theo khoá
		for ma, ten, chuoi in (parties or ()):
			ma = str(ma)
			if ma in self._ten:
				continue
			ds = [s.strip() for s in (chuoi or ()) if isinstance(s, str) and s.strip()]
			self._ten[ma] = ten.strip() if isinstance(ten, str) and ten.strip() else (sorted(ds)[0] if ds else ma)
			self._dem(ma)
			for s in ds:
				self._ma.setdefault(s, ma)      # trùng chuỗi: đối tác đứng trước giữ
		self._dung_lai()

	# ── nội bộ ──
	def _dem(self, ma: str) -> None:
		m = re.fullmatch(r"([A-Za-z]+)#(\d+)", ma)
		if m:
			self._so[m.group(1)] = max(self._so.get(m.group(1), 0), int(m.group(2)))

	def _dung_lai(self) -> None:
		"""Dựng lại chỉ mục (sau khi thêm chuỗi / mã)."""
		# Mã không theo dạng chuẩn (nơi gọi tự đặt) → soát bằng biểu thức riêng, dài trước.
		le = sorted((m for m in self._ten if not _MA.fullmatch(m)), key=len, reverse=True)
		self._le = re.compile(r"(?<![\w#])(?:" + "|".join(map(re.escape, le)) + r")(?![\w#])") if le else None
		self._chi_muc = None     # mask_text: {từ đầu: [tên, dài trước]}, dựng khi cần

	def _alias(self, s, ma: str) -> None:
		"""Thêm chuỗi s làm bí danh của mã (đã có chuỗi đó thì giữ mã cũ)."""
		s = s.strip() if isinstance(s, str) else ""
		if s and ma in self._ten and s not in self._ma:
			self._ma[s] = ma
			self._chi_muc = None

	def _phat(self, ma: str) -> str:
		self._gui.add(ma)
		return ma

	def _ma_moi(self, s: str, tien_to: str) -> str:
		"""Chuỗi dưới khoá đối tác không khớp tên nào → mã mới, hoàn nguyên ra đúng chuỗi đó."""
		n = self._so.get(tien_to, 0) + 1
		ma = f"{tien_to}#{n:04d}"
		while ma in self._ten:
			n += 1
			ma = f"{tien_to}#{n:04d}"
		self._so[tien_to] = n
		self._ten[ma] = s
		self._ma[s] = ma
		self._chi_muc = None
		return ma

	def _chi_muc_ten(self) -> dict:
		if self._chi_muc is None:
			cm: dict = {}
			for s in self._ma:
				if not (len(_TU.findall(s)) >= 2 or len(s) >= TEN_TOI_THIEU):
					continue
				m = _TU.match(s)
				cm.setdefault(m.group(0) if m else "", []).append(s)     # "" = tên mở đầu bằng ký tự không phải chữ
			for ds in cm.values():
				ds.sort(key=len, reverse=True)
			self._chi_muc = cm
		return self._chi_muc

	# ── công khai ──
	def begin(self) -> None:
		"""Bắt đầu một đề bài mới: quên các mã đã gửi trước đó (chỉ mã gửi SAU lần này mới được hoàn nguyên)."""
		self._gui = set()

	def mask(self, obj):
		"""Bản SAO sâu của obj (dict / list / scalar): chuỗi bằng đúng một tên → mã giả; chuỗi khác → mask_text; chuỗi
		dưới khoá đối tác (PARTY_KEYS / SUPPLIER_KEYS) chưa biết → mã cùng dòng hoặc mã mới. Không đổi obj gốc."""
		return self._mask(obj, None, None)

	def _mask(self, obj, key, dong):
		if isinstance(obj, dict):
			return {k: self._mask(v, k, obj) for k, v in obj.items()}
		if isinstance(obj, list):
			return [self._mask(v, key, None) for v in obj]
		if isinstance(obj, tuple):
			return tuple(self._mask(v, key, None) for v in obj)
		if isinstance(obj, str):
			s = obj.strip()
			ma = self._ma.get(s)
			if ma is not None:
				return self._phat(ma)
			tien_to = "KH" if key in PARTY_KEYS else "NCC" if key in SUPPLIER_KEYS else None
			if tien_to and s and self.on:
				ma = self._cung_dong(dong, key, tien_to)
				if ma is None:
					ma = self._ma_moi(s, tien_to)
				else:
					self._alias(s, ma)
				return self._phat(ma)
			return self.mask_text(obj)
		return obj

	def _cung_dong(self, dong, key, tien_to):
		"""Mã của đối tác cùng dòng (dict chứa chuỗi): khoá *_id trước, rồi các khoá đối tác khác cùng loại."""
		if not isinstance(dong, dict):
			return None
		khoa = PARTY_KEYS if tien_to == "KH" else SUPPLIER_KEYS
		ung = sorted((k for k in dong if k != key and isinstance(k, str) and (k in khoa or k.endswith("_id"))
			and (k in khoa or k[:-3] in khoa)), key=lambda k: (not k.endswith("_id"), k))
		for k in ung:
			v = dong.get(k)
			ma = self._ma.get(v.strip()) if isinstance(v, str) else None
			if ma is not None and _tien_to(ma) in (tien_to, None):
				return ma
		return None

	def mask_text(self, text) -> str:
		"""Chữ TỰ DO: thay mọi tên đã biết đứng riêng thành từ → mã giả (tên dài trước). Chỉ tên ≥ 2 từ hoặc ≥
		TEN_TOI_THIEU ký tự. Là che HẾT SỨC: tên gọi tắt, tên viết khác hồ sơ không nhận ra được. Nhanh: chỉ xét tên có
		từ đầu trùng một từ của câu (không dò cả bảng bằng một biểu thức)."""
		text = "" if text is None else str(text)
		if not self._ma or not text:
			return text
		cm = self._chi_muc_ten()
		if not cm:
			return text
		le = cm.get("")          # tên mở đầu bằng ký tự không phải chữ: soát bằng tìm chuỗi con
		out, i, n = [], 0, len(text)
		vi_tri = [(m.start(), m.group(0)) for m in _TU.finditer(text)]
		if le:
			for s in le:
				j = text.find(s)
				while j >= 0:
					vi_tri.append((j, None))
					j = text.find(s, j + 1)
			vi_tri.sort(key=lambda x: x[0])
		for a, tu in vi_tri:
			if a < i:
				continue
			ung = cm.get(tu, ()) if tu is not None else le
			for s in ung:
				b = a + len(s)
				if text.startswith(s, a) and not (a > 0 and _la_chu(text[a - 1])) and not (b < n and _la_chu(text[b])):
					out.append(text[i:a])
					out.append(self._phat(self._ma[s]))
					i = b
					break
		if i == 0:
			return text
		out.append(text[i:])
		return "".join(out)

	def _thay(self, text, fn) -> str:
		text = "" if text is None else str(text)
		if not self._gui:
			return text
		text = _MA.sub(lambda m: fn(m.group(0)) if m.group(0) in self._gui else m.group(0), text)
		if self._le is not None:
			text = self._le.sub(lambda m: fn(m.group(0)) if m.group(0) in self._gui else m.group(0), text)
		return text

	def unmask(self, text: str) -> str:
		"""Thay mã giả ĐÃ GỬI trong text về tên hiển thị thật; mã khác để nguyên."""
		return self._thay(text, lambda ma: self._ten[ma])

	def strip(self, text: str) -> str:
		"""Bỏ mã giả ĐÃ GỬI khỏi text (thay bằng dấu cách) — để lint không bắt nhầm chữ số trong mã giả; mã khác (mô
		hình bịa / chưa gửi) giữ nguyên để lint bắt."""
		return self._thay(text, lambda ma: " ")


def _la_chu(ch: str) -> bool:
	return ch.isalnum() or ch == "_"


def _doc(sql: str) -> list:
	try:
		return list(frappe.db.sql(sql))
	except Exception:
		return []


def _doi_tac(doctype: str, cot: str) -> list:
	"""[(name, tên hiển thị)] của một DocType, sắp theo `name` ở Python (không phụ thuộc collation của DB). Thiếu
	bảng → []; thiếu cột tên → chỉ dùng `name`."""
	if not frappe.db.table_exists(doctype):
		return []
	chon = f"`name`, `{cot}`" if frappe.db.has_column(doctype, cot) else "`name`, NULL"
	rows = _doc(f"SELECT {chon} FROM `tab{doctype}`")
	return sorted(((r[0], r[1]) for r in rows if r[0]), key=lambda r: r[0])


def _ten_hoa_don(doctype: str, cot_ma: str, cot_ten: str) -> list:
	"""[(mã đối tác, tên chép trên hoá đơn đã duyệt)] — đọc mềm: thiếu bảng / cột → []."""
	if not frappe.db.table_exists(doctype) or not frappe.db.has_column(doctype, cot_ma):
		return []
	ten = f"`{cot_ten}`" if frappe.db.has_column(doctype, cot_ten) else "NULL"
	co_ds = frappe.db.has_column(doctype, "docstatus")
	rows = _doc(f"SELECT DISTINCT `{cot_ma}`, {ten} FROM `tab{doctype}`" + (" WHERE docstatus = 1" if co_ds else ""))
	return sorted(((r[0], r[1]) for r in rows if r[0]), key=lambda r: (str(r[0]), str(r[1] or "")))


def build(enabled: bool = True) -> Mask:
	"""Mask từ tabCustomer / tabSupplier + tên chép trên hoá đơn đã duyệt (đọc mềm: thiếu bảng / cột thì bỏ). enabled
	False → Mask rỗng. Mã đánh số theo `name` tăng dần (ổn định trong một lượt); đối tác chỉ có trên hoá đơn đánh số
	tiếp sau, cũng theo mã tăng dần."""
	if not enabled:
		return Mask()
	parties, bi_danh = [], []
	for doctype, cot, tien_to, (hd, cot_ma, cot_ten) in NGUON:
		ho_so = _doi_tac(doctype, cot)
		ma_cua = {}
		for i, (name, ten) in enumerate(ho_so, 1):
			ma_cua[name] = f"{tien_to}#{i:04d}"
			parties.append((ma_cua[name], ten or name, {name, ten}))
		hoa_don = _ten_hoa_don(hd, cot_ma, cot_ten)
		them = sorted({str(ma) for ma, _t in hoa_don if ma not in ma_cua})
		for j, name in enumerate(them, len(ho_so) + 1):
			ten = next((t for m, t in hoa_don if str(m) == name and isinstance(t, str) and t.strip()), None)
			ma_cua[name] = f"{tien_to}#{j:04d}"
			parties.append((ma_cua[name], ten or name, {name}))
		bi_danh += [(ma_cua[str(m)], t) for m, t in hoa_don if str(m) in ma_cua]
	mask = Mask(parties, on=True)
	for ma, ten in bi_danh:        # sau hồ sơ: tên trên hồ sơ của đối tác khác thắng bí danh
		mask._alias(ten, ma)
	return mask
