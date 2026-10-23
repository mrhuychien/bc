# -*- coding: utf-8 -*-
"""Chuẩn hoá tên tỉnh về 34 tỉnh/thành sau sáp nhập 07/2025 (NQ 202/2025/QH15).

Bảng tra lấy từ app pkd (đã chạy thật trên site): tên cũ (63) hay mới (34) đều gộp
đúng — so khớp không dấu, bỏ tiền tố Tỉnh/TP. Không nhận diện được → "Khác".
"""

from __future__ import annotations

import re
import unicodedata

import frappe

# Cột tỉnh trên Sales Invoice (fieldname có dấu dễ lệch → dò cả 2). Identifier nội
# suy vào SQL nên CHỈ lấy từ whitelist này.
PROV_COLUMNS = ("custom_tỉnh", "custom_tinh")
GENERIC_TERRITORIES = {"", "vietnam", "viet nam", "all territories", "tat ca", "khac"}

# Tỉnh CŨ (63) → tỉnh MỚI (34). Tên mới map về chính nó khi build bảng tra.
OLD_TO_NEW = {
	"Hà Nội": "Hà Nội", "Cao Bằng": "Cao Bằng", "Lạng Sơn": "Lạng Sơn",
	"Quảng Ninh": "Quảng Ninh", "Lai Châu": "Lai Châu", "Điện Biên": "Điện Biên",
	"Sơn La": "Sơn La", "Thanh Hóa": "Thanh Hóa", "Nghệ An": "Nghệ An",
	"Hà Tĩnh": "Hà Tĩnh", "Thừa Thiên Huế": "Huế",
	"Tuyên Quang": "Tuyên Quang", "Hà Giang": "Tuyên Quang",
	"Lào Cai": "Lào Cai", "Yên Bái": "Lào Cai",
	"Thái Nguyên": "Thái Nguyên", "Bắc Kạn": "Thái Nguyên",
	"Phú Thọ": "Phú Thọ", "Vĩnh Phúc": "Phú Thọ", "Hòa Bình": "Phú Thọ",
	"Bắc Ninh": "Bắc Ninh", "Bắc Giang": "Bắc Ninh",
	"Hưng Yên": "Hưng Yên", "Thái Bình": "Hưng Yên",
	"Hải Phòng": "Hải Phòng", "Hải Dương": "Hải Phòng",
	"Ninh Bình": "Ninh Bình", "Hà Nam": "Ninh Bình", "Nam Định": "Ninh Bình",
	"Quảng Trị": "Quảng Trị", "Quảng Bình": "Quảng Trị",
	"Đà Nẵng": "Đà Nẵng", "Quảng Nam": "Đà Nẵng",
	"Quảng Ngãi": "Quảng Ngãi", "Kon Tum": "Quảng Ngãi",
	"Gia Lai": "Gia Lai", "Bình Định": "Gia Lai",
	"Khánh Hòa": "Khánh Hòa", "Ninh Thuận": "Khánh Hòa",
	"Lâm Đồng": "Lâm Đồng", "Đắk Nông": "Lâm Đồng", "Bình Thuận": "Lâm Đồng",
	"Đắk Lắk": "Đắk Lắk", "Phú Yên": "Đắk Lắk",
	"TP. Hồ Chí Minh": "TP. Hồ Chí Minh", "Bình Dương": "TP. Hồ Chí Minh",
	"Bà Rịa-Vũng Tàu": "TP. Hồ Chí Minh",
	"Đồng Nai": "Đồng Nai", "Bình Phước": "Đồng Nai",
	"Tây Ninh": "Tây Ninh", "Long An": "Tây Ninh",
	"Cần Thơ": "Cần Thơ", "Sóc Trăng": "Cần Thơ", "Hậu Giang": "Cần Thơ",
	"Vĩnh Long": "Vĩnh Long", "Bến Tre": "Vĩnh Long", "Trà Vinh": "Vĩnh Long",
	"Đồng Tháp": "Đồng Tháp", "Tiền Giang": "Đồng Tháp",
	"An Giang": "An Giang", "Kiên Giang": "An Giang",
	"Cà Mau": "Cà Mau", "Bạc Liêu": "Cà Mau",
}

# Cách viết đời thường hay gặp trong dữ liệu nhập tay.
ALIASES = {
	"tphcm": "TP. Hồ Chí Minh", "tp hcm": "TP. Hồ Chí Minh", "hcm": "TP. Hồ Chí Minh",
	"sai gon": "TP. Hồ Chí Minh", "saigon": "TP. Hồ Chí Minh",
	"vung tau": "TP. Hồ Chí Minh", "ba ria": "TP. Hồ Chí Minh",
	"ba ria vung tau": "TP. Hồ Chí Minh",
	"hue": "Huế", "tt hue": "Huế",
	"daklak": "Đắk Lắk", "dac lac": "Đắk Lắk", "kontum": "Quảng Ngãi",
	"bac can": "Thái Nguyên", "vinh phuc": "Phú Thọ",
}


def _norm(s: str) -> str:
	"""lower → bỏ dấu (NFD) → đ→d → bỏ ký tự lạ → bỏ tiền tố tỉnh/tp → gọn space."""
	s = (s or "").strip().lower()
	s = unicodedata.normalize("NFD", s)
	s = "".join(c for c in s if unicodedata.category(c) != "Mn")
	s = s.replace("đ", "d")
	s = re.sub(r"[^a-z0-9 ]+", " ", s)
	s = re.sub(r"\s+", " ", s).strip()
	s = re.sub(r"^(tinh|thanh pho|tp|t p)\s+", "", s)
	return s


def _canon_table() -> dict:
	table = {}
	for old, new in OLD_TO_NEW.items():
		table[_norm(old)] = new
		table[_norm(new)] = new
	for k, v in ALIASES.items():
		table[_norm(k)] = v
	return table


CANON = _canon_table()


def canon(raw: str | None) -> str | None:
	"""Tên tỉnh chuẩn (34) hoặc None."""
	if not raw:
		return None
	n = _norm(raw)
	if n in CANON:
		return CANON[n]
	# Chuỗi dài (vd "Quận 1, TP Hồ Chí Minh") → tìm tên tỉnh dài nhất xuất hiện bên trong.
	for key in sorted(CANON, key=len, reverse=True):
		if len(key) >= 3 and re.search(rf"\b{re.escape(key)}\b", n):
			return CANON[key]
	return None


def province_column() -> str | None:
	for col in PROV_COLUMNS:
		try:
			if frappe.db.has_column("Sales Invoice", col):
				return col
		except Exception:
			continue
	return None


def resolve(prov_value=None, territory=None, customer_name=None) -> str:
	"""Ưu tiên cột tỉnh trên hoá đơn → territory (nếu không generic) → dò trong tên khách."""
	for v in (prov_value, territory if _norm(territory or "") not in GENERIC_TERRITORIES else None, customer_name):
		c = canon(v)
		if c:
			return c
	return "Khác"
