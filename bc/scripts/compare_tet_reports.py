# -*- coding: utf-8 -*-
"""Đối chiếu Query Report cũ ↔ method bc.api mới, CÙNG NGÀY (SPEC 3b bước 3).

    bench --site a.rongvanghoanggia.com execute bc.scripts.compare_tet_reports.run      # 4 report Tết
    bench --site a.rongvanghoanggia.com execute bc.scripts.compare_tet_reports.run_kd   # report KD

Diff phải RỖNG (sai số ≤ 1 đồng / 1 hộp) mới được bật tet_compare_mode = tet_aligned.
Chạy ở chế độ calendar (mặc định) — script tự tạm ép calendar nếu Settings đang khác.

Cột report cũ khớp với key mới qua COLUMN_MAP (nhãn hoặc fieldname cột, so khớp
không dấu/không phân biệt hoa thường). Cột chưa map → script in danh sách cột report
cũ để bổ sung map; KHÔNG suy diễn.
"""

from __future__ import annotations

import re
import unicodedata

import frappe
from frappe.desk.query_report import run as run_report
from frappe.utils import flt

TOLERANCE = 1.0

# report → (method, key mới, [nhãn cột key cũ], {key số mới: [nhãn cột cũ ứng viên]})
TET_PAIRS = {
	"Tet NPP Tang Truong": ("bc.api.tet.get_npp_growth", "customer", ["khach hang", "npp", "customer", "ten khach"], {
		"this_year": ["nam nay", "this year", "2026", "hien tai"],
		"last_year": ["nam truoc", "last year", "cung ky"],
	}),
	"Tet NPP Hang Tet": ("bc.api.tet.get_npp_detail", "customer", ["khach hang", "npp", "customer"], {
		"last_year": ["nam truoc", "nt"],
		"last_year_out": ["nt di", "nam truoc di"],
		"this_year": ["nam nay"],
		"total_in": ["tong nhap", "tong di"],
		"total_return": ["tong ve", "tra ve"],
	}),
	"Tet Sieu thi MT": ("bc.api.tet.get_mt_detail", "customer", ["sieu thi", "khach hang", "customer"], {
		"last_year": ["nam truoc", "nt"],
		"last_year_out": ["nt di", "nam truoc di"],
		"this_year": ["nam nay"],
		"total_in": ["tong nhap", "tong di"],
		"total_return": ["tong ve", "tra ve"],
	}),
	"Tet Ma Hang": ("bc.api.tet.get_items", "item_code", ["ma hang", "item code", "item_code", "ma"], {
		"value": ["gia tri", "doanh so"],
		"plan": ["ke hoach"],
		"net_boxes": ["thuc ban", "hop thuc", "con lai"],
		"boxes_out": ["hop di", "hop xuat", "so hop di"],
		"boxes_back": ["hop ve", "so hop ve"],
		"mt": ["mt"],
		"gt": ["gt"],
	}),
}

KD_PAIRS = {
	"Dashboard KD Ngay": ("bc.api.kd.get_daily", "date", ["ngay", "date", "posting date"], {
		"sales": ["doanh so", "ban ra", "sales"],
		"returns": ["tra ve", "tra hang", "returns"],
		"orders": ["so don", "don hang", "orders"],
	}),
	"Dashboard KD Tinh Thanh": ("bc.api.kd.get_provinces", "province", ["tinh", "tinh thanh", "province"], {
		"sales": ["doanh so", "sales"],
	}),
	"Dashboard KD Nganh Hang": ("bc.api.kd.get_item_groups", "item_group", ["nganh hang", "nhom hang", "item group"], {
		"amount": ["doanh so", "gia tri", "amount"],
	}),
	"Dashboard KD Top KH": ("bc.api.kd.get_top_customers", "customer", ["khach hang", "customer"], {
		"amount": ["doanh so", "gia tri", "amount"],
	}),
	"Dashboard KD Tong Quan": ("bc.api.kd.get_summary", "period", ["ky", "period"], {
		"sales": ["doanh so", "ban ra", "sales"],
		"returns": ["tra ve", "returns"],
	}),
	"Dashboard KD Kenh Ban": ("bc.api.kd.get_channels", "channel", ["kenh", "channel"], {
		"sales": ["doanh so", "ban ra", "sales"],
		"returns": ["tra ve", "returns"],
	}),
}


def _plain(s) -> str:
	s = unicodedata.normalize("NFD", str(s or "").lower())
	s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
	s = re.sub(r"\(.*?\)|%", " ", s)
	return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _old_rows(report: str) -> tuple[list[str], list[dict]]:
	res = run_report(report, filters={}, ignore_prepared_report=True)
	cols = []
	for c in res.get("columns") or []:
		if isinstance(c, dict):
			cols.append(c.get("label") or c.get("fieldname"))
		else:  # "Label:Type/Options:Width"
			cols.append(str(c).split(":")[0])
	rows = []
	for r in res.get("result") or []:
		if isinstance(r, dict):
			rows.append({_plain(k): v for k, v in r.items()})
		elif isinstance(r, (list, tuple)):
			rows.append({_plain(cols[i]): v for i, v in enumerate(r) if i < len(cols)})
	return cols, rows


def _find(cands, available):
	for c in cands:
		pc = _plain(c)
		for a in available:
			if a == pc:
				return a
	for c in cands:
		pc = _plain(c)
		for a in available:
			if pc and pc in a:
				return a
	return None


def compare(report: str, method: str, new_key: str, old_key_cands, numeric_map) -> int:
	print(f"\n=== {report}  ↔  {method}")
	if not frappe.db.exists("Report", report):
		print("  !! report không tồn tại trên site")
		return 1
	cols, old = _old_rows(report)
	available = sorted({k for r in old for k in r})
	new = frappe.get_attr(method)(refresh=1)["rows"]
	okey = _find(old_key_cands, available)
	if not okey:
		print(f"  !! không xác định được cột key. Cột report cũ: {cols}")
		return 1
	mapping = {nk: _find(c, available) for nk, c in numeric_map.items()}
	missing = [k for k, v in mapping.items() if not v]
	if missing:
		print(f"  ?? chưa map được {missing} — cột report cũ: {cols}")
	old_by = {_plain(r.get(okey)): r for r in old if r.get(okey) not in (None, "")}
	new_by = {_plain(r.get(new_key)): r for r in new}
	diffs = 0
	for k in sorted(set(old_by) | set(new_by)):
		o, n = old_by.get(k), new_by.get(k)
		if o is None or n is None:
			# Dòng chỉ có 1 bên mà toàn số 0 thì bỏ qua (report cũ hay in dòng rỗng).
			side = n if o is None else o
			vals = [flt(side.get(nk if o is None else mapping[nk])) for nk in mapping if mapping[nk]]
			if any(abs(v) > TOLERANCE for v in vals):
				diffs += 1
				print(f"  ≠ {k}: chỉ có ở {'MỚI' if o is None else 'CŨ'}")
			continue
		for nk, ok in mapping.items():
			if not ok:
				continue
			a, b = flt(o.get(ok)), flt(n.get(nk))
			if abs(a - b) > TOLERANCE:
				diffs += 1
				print(f"  ≠ {k} · {nk}: cũ={a:,.0f} mới={b:,.0f} (lệch {b - a:,.0f})")
	print(f"  → {len(old_by)} dòng cũ / {len(new_by)} dòng mới · {diffs} lệch" + ("  ✅" if not diffs and not missing else ""))
	return diffs + len(missing)


def _run(pairs: dict) -> int:
	settings = frappe.get_single("BC Settings")
	forced = settings.tet_compare_mode != "calendar"
	if forced:
		print("(tạm so ở chế độ calendar để khớp hành vi CURDATE cũ)")
		frappe.db.set_single_value("BC Settings", "tet_compare_mode", "calendar")
		frappe.clear_document_cache("BC Settings", "BC Settings")
	try:
		total = sum(compare(name, *spec) for name, spec in pairs.items())
	finally:
		if forced:
			frappe.db.set_single_value("BC Settings", "tet_compare_mode", settings.tet_compare_mode)
			frappe.clear_document_cache("BC Settings", "BC Settings")
		frappe.db.rollback()
	print(f"\nTỔNG: {total} điểm lệch/chưa map" + (" — diff rỗng ✅" if not total else ""))
	return total


def run():
	return _run(TET_PAIRS)


def run_kd():
	return _run(KD_PAIRS)
