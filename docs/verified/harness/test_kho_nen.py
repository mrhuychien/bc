"""Nền dùng chung nhóm Kho (bc.api.kho) + sổ kho giả (seed_kho) + Thời gian thực (bc.api.live) trên MariaDB thật.

Chỉ thử phần NỀN mà bốn bộ thử màn (test_kho_ton / han / kk / nhap) không phủ — mỗi ca ứng với một phát hiện review:
- XR-COMP-3  bộ chặn import (AST) trên bc/api/kho.py VÀ mọi bc/api/kho_*.py: chỉ thư viện chuẩn, frappe, bc và đúng danh
             sách helper THUẦN của sx (đặc tả Kho §5), mỗi import sx bọc try/except ImportError; không gọi import động;
             sau_kiem_ke.xu_ly chỉ được GỌI với chay = 0 ghi rõ (chay=1 ghi DB — §2 W1, §5 "every chay=1 call").
- XC-2       alias SQL trùng tên method của dict (items, keys, values, get…) — dòng as_dict là frappe._dict, `r.items` trả
             method chứ không phải cột; live._warehouses / live._feed đếm "Số mã có tồn" / "+N mã" phải đúng.
- XR-T2      kho NHÓM cấu hình cho từng vai trò (kho_tp, trả về, cách ly, xưởng, BTP, NVL, POS Profile, BC sx_warehouse)
             bung xuống kho lá theo lft/rgt.
- XR-T3      thứ tự vai trò "khớp đầu tiên": tra_ve > cach_ly > di_duong > tp > cua_hang > xuong/btp/nvl > khac khi các
             quy tắc chồng nhau (kho trả về / cách ly / đi đường / shop POS nằm TRONG cây TP; kho Transit bị đánh dấu trả về).
- XR-T6      POS Profile đã tắt không làm kho thành "Cửa hàng".
- XR-T4      nhóm con dưới "Hàng truyền thống" vẫn là truyền thống (GROUP_CASE + _tp_by_group) — K1 by_group, K2.
- XR-T7      carton_total ngữ nghĩa RÒNG có dấu với mã tồn âm (có / không hệ số thùng) + bất biến Σ q = Σ thùng × hệ số + lẻ.
- XR-T8      ngưỡng dòng Bin 1e-6 với số lượng lẻ (−0,5 kg / 0,25 kg giá trị 0 được tính; 0,0000005 kg thì không).
- XR-T5      giá vốn dự phòng nấc "sổ kho": dòng sổ SỐNG MỚI NHẤT có đơn giá > 0 (hai đơn giá dương khác nhau → lấy mới).
- XR-T1      seed_kho.recon ghi dòng kiểm kê CÓ lô thành HAI chân như ERPNext v16 (xuất −current_qty, nhập +qty).
- SEC-1      kho.month_period kẹp tháng chọn (≥ 01/2000, ≤ 10 năm trước, không tương lai) — kho_kk / kho_nhap không 500.

Mỗi kịch bản reset DB và dựng trên seed_kho.base(k) (cây kho / nhóm hàng / SX Settings / POS chuẩn) + phần riêng tên NEN-.
base(k) KHÔNG đổi — số của bốn bộ thử màn giữ nguyên. Số kỳ vọng TÍNH TAY ở chú thích (hôm nay 27/10/2026).

Chạy: BC_TEST_DB=bc_test_kho_nen python3 -B test_kho_nen.py
Thử phá: BC_APP_ROOT=<bản bc đã sửa hỏng> … phải đỏ (xem README).
"""
import ast
import datetime
import glob
import os
import re
import sys

from seed import Check, bc_settings, insert, reset, single
from seed_kho import (BTP, CACH_LY, CH1, CH2, CH_GROUP, DI_DUONG, G_NL, G_TET, G_TRAD, KHO_CU, NVL, ROOT, TODAY, TP,
	TRA_VE, XUONG, K, base, bin_of)
from paths import BC_ROOT

import frappe  # noqa: E402  (fake)

API = os.path.join(BC_ROOT, "bc", "api")

# ═══ Kho NEN- (kịch bản vai trò) ═══
W_TPG = "NEN-TP tổng - HGC"            # nhóm — SX Settings.kho_tp
W_TPC = "NEN-TP chính - HGC"           # lá trong cây TP → tp
W_TVG = "NEN-Trả về tổng - HGC"        # nhóm TRONG cây TP — SX Settings.kho_hang_tra_ve
W_TV1 = "NEN-Trả về 1 - HGC"           # → tra_ve (trả về thắng tp)
W_CLG = "NEN-Cách ly tổng - HGC"       # nhóm TRONG cây TP — SX Settings.kho_cach_ly
W_CL1 = "NEN-Cách ly 1 - HGC"          # → cach_ly (cách ly thắng tp)
W_TPDD = "NEN-TP đi đường - HGC"       # Transit TRONG cây TP → di_duong (đi đường thắng tp)
W_SHOP = "NEN-Shop nhà máy - HGC"      # lá TP có POS Profile đang dùng → tp (tp thắng cửa hàng)
W_TVDV = "NEN-Trả về đang về - HGC"    # Transit + is_rejected_warehouse → tra_ve (trả về thắng đi đường)
W_CHG = "NEN-Chuỗi CH - HGC"           # nhóm — POS Profile trỏ vào NHÓM
W_CHC1 = "NEN-CH chuỗi 1 - HGC"        # → cua_hang
W_CHDONG = "NEN-CH đã đóng - HGC"      # dưới Cửa hàng - HGC, POS Profile ĐÃ TẮT → khac
W_XG, W_X1 = "NEN-Xưởng tổng - HGC", "NEN-Xưởng 1 - HGC"    # SX Settings.kho_xuong = nhóm
W_BG, W_B1 = "NEN-BTP tổng - HGC", "NEN-BTP 1 - HGC"        # SX Settings.kho_btp = nhóm
W_NG, W_N1 = "NEN-NVL tổng - HGC", "NEN-NVL 1 - HGC"        # SX Settings.kho_nvl = nhóm
G_TRAD_CON = "NEN-Bánh nướng truyền thống"                  # nhóm CON của Hàng truyền thống

DICT_METHODS = ("items", "keys", "values", "get", "copy", "pop", "popitem", "update", "clear", "setdefault", "fromkeys")
# Đặc tả Kho §5 — helper THUẦN của sx được import (đọc mềm). Mọi thứ khác của sx (và app khác) bị cấm.
SX_ALLOW = {
	"sx.utils": {"items_tp", "nhom_tp", "han_dung"},
	"sx.api.khotp": {"tran_con_lai"},
	"sx.sx.doctype.sx_kiem_ke.sx_kiem_ke": {"ton_lo"},
	"sx.api.sau_kiem_ke": {"xu_ly"},
	"sx.api.tonam": {"_dong_am"},
}
SX_DENY_NAMES = {"_dong_du", "ma_lo_ton_cu", "prefix_lo", "gia_von_hien", "ghi_gia_tu_tinh"}
DYNAMIC_IMPORT = {"import_module", "__import__", "get_attr", "call", "get_module"}
# Helper sx được phép import NHƯNG chỉ khi gọi với tham số này = hằng 0 (ghi rõ): tên → (tham số, vị trí đối số).
# sx/api/sau_kiem_ke.py: def xu_ly(phieu=None, kho=None, ma=None, chay=0, bo=None) — ghi DB dưới `if cint(chay)`.
SX_CALL_RULES = {"xu_ly": ("chay", 3)}
# Chỗ được dùng tên helper có điều kiện mà KHÔNG gọi (chỉ kiểm có import được không): `is None`, `not`, điều kiện if.
_TEST_PARENTS = (ast.Compare, ast.UnaryOp, ast.If, ast.IfExp, ast.While, ast.Assert)


def fresh():
	reset()
	bc_settings()
	k = K()
	base(k)
	return k


# ═══════════════════════════════════════════════════════════════════════════
# A. Bộ chặn tĩnh (AST)
# ═══════════════════════════════════════════════════════════════════════════
def _parents(tree):
	par = {}
	for n in ast.walk(tree):
		for ch in ast.iter_child_nodes(n):
			par[ch] = n
	return par


def _catches_import_error(t: ast.Try) -> bool:
	for h in t.handlers:
		names = [h.type] if not isinstance(h.type, ast.Tuple) else list(h.type.elts)
		if h.type is None or any(isinstance(x, ast.Name) and x.id in ("ImportError", "ModuleNotFoundError", "Exception")
				for x in names):
			return True
	return False


def import_violations(path: str) -> list:
	"""Mọi import / gọi import động vi phạm danh sách cho phép (đặc tả Kho §5) trong một file nguồn."""
	src = open(path, encoding="utf-8").read()
	tree = ast.parse(src)
	par = _parents(tree)
	std = set(sys.stdlib_module_names)
	bad = []
	fn = os.path.basename(path)

	def guarded(node):
		p = par.get(node)
		while p is not None:
			if isinstance(p, ast.Try) and node_in(p.body, node) and _catches_import_error(p):
				return True
			p = par.get(p)
		return False

	def node_in(body, node):
		return any(node is x or any(node is y for y in ast.walk(x)) for x in body)

	# Tên cục bộ gắn với helper có điều kiện gọi (kể cả `from … import xu_ly as soat`) → tên gốc.
	ruled = {r: r for r in SX_CALL_RULES}
	for n in ast.walk(tree):
		if isinstance(n, ast.ImportFrom):
			for a in n.names:
				if a.name in SX_CALL_RULES:
					ruled[a.asname or a.name] = a.name

	def zero(e):
		return isinstance(e, ast.Constant) and type(e.value) in (int, bool) and e.value == 0

	def call_rule(n, base):
		param, pos = SX_CALL_RULES[base]
		kw = {k.arg: k.value for k in n.keywords}
		p_arg = n.args[pos] if len(n.args) > pos else None
		splat = None in kw or any(isinstance(a, ast.Starred) for a in n.args)
		val = kw.get(param, p_arg)
		if splat or val is None or not zero(val):
			bad.append(f"{fn}:{n.lineno} gọi {ast.unparse(n)} — {base} chỉ được gọi với {param}=0 ghi rõ")

	for n in ast.walk(tree):
		if isinstance(n, ast.Import):
			for a in n.names:
				root = a.name.split(".")[0]
				if root not in std and root not in ("frappe", "bc"):
					bad.append(f"{fn}:{n.lineno} import {a.name}")
		elif isinstance(n, ast.ImportFrom):
			mod = n.module or ""
			root = mod.split(".")[0]
			if n.level or root in std or root in ("frappe", "bc", "__future__"):
				continue
			allowed = SX_ALLOW.get(mod, set()) if root == "sx" else set()
			for a in n.names:
				if a.name not in allowed:
					bad.append(f"{fn}:{n.lineno} from {mod} import {a.name}")
			if root == "sx" and not guarded(n):
				bad.append(f"{fn}:{n.lineno} from {mod} import … không bọc try/except ImportError")
		elif isinstance(n, ast.Call):
			name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None)
			if name in DYNAMIC_IMPORT:
				arg = n.args[0] if n.args else None
				s = arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None
				if s is None or not s.startswith("bc."):
					mod, _, attr = (s or "").rpartition(".")
					# helper có điều kiện gọi (xu_ly) không được lấy động: lời gọi sau đó không kiểm được tham số.
					if not (s and attr in SX_ALLOW.get(mod, set()) and attr not in SX_CALL_RULES):
						bad.append(f"{fn}:{n.lineno} {name}({ast.unparse(arg) if arg is not None else ''})")
			if isinstance(n.func, ast.Name) and n.func.id in ruled:
				call_rule(n, ruled[n.func.id])
			elif isinstance(n.func, ast.Attribute) and n.func.attr in SX_CALL_RULES:
				call_rule(n, n.func.attr)
		elif isinstance(n, (ast.Name, ast.Attribute)):
			ident = n.id if isinstance(n, ast.Name) else n.attr
			if ident in SX_DENY_NAMES:
				bad.append(f"{fn}:{n.lineno} dùng {ident}")
			# xu_ly đưa đi như giá trị (partial(xu_ly, chay=1), f = xu_ly, truyền làm đối số…) → không kiểm được chay.
			base = ruled.get(ident) if isinstance(n, ast.Name) else (ident if ident in SX_CALL_RULES else None)
			if base and isinstance(n.ctx, ast.Load):
				p = par.get(n)
				if not ((isinstance(p, ast.Call) and p.func is n) or isinstance(p, _TEST_PARENTS)):
					bad.append(f"{fn}:{n.lineno} dùng {ident} như giá trị ({ast.unparse(p) if p is not None else ident})"
						f" — chỉ được gọi trực tiếp với {SX_CALL_RULES[base][0]}=0")
	return bad


def _docstrings(tree) -> set:
	out = set()
	for n in ast.walk(tree):
		if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body \
				and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant):
			out.add(id(n.body[0].value))
	return out


ALIAS_RE = re.compile(r"\bAS\s+`?(" + "|".join(DICT_METHODS) + r")`?(?![\w(])", re.I)


def dict_name_violations(path: str) -> list:
	"""(1) alias SQL trong chuỗi (không tính docstring) trùng tên method dict; (2) đọc thuộc tính `.items` / `.get`… mà
	không gọi (dòng frappe._dict trả method dict, không phải cột)."""
	src = open(path, encoding="utf-8").read()
	tree = ast.parse(src)
	par = _parents(tree)
	docs = _docstrings(tree)
	fn = os.path.basename(path)
	bad = []
	for n in ast.walk(tree):
		if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
			for m in ALIAS_RE.finditer(n.value):
				bad.append(f"{fn}:{n.lineno} alias SQL '{m.group(0).strip()}'")
		elif isinstance(n, ast.Attribute) and n.attr in DICT_METHODS and isinstance(n.ctx, ast.Load):
			p = par.get(n)
			if not (isinstance(p, ast.Call) and p.func is n):
				bad.append(f"{fn}:{n.lineno} đọc .{n.attr} không gọi ({ast.unparse(n)})")
	return bad


def static_checks(c):
	files = [os.path.join(API, "kho.py")] + sorted(glob.glob(os.path.join(API, "kho_*.py")))
	c("XR-COMP-3 quét đủ kho.py + 4 file kho_*.py", [os.path.basename(f) for f in files]
		== ["kho.py", "kho_han.py", "kho_kk.py", "kho_nhap.py", "kho_ton.py"], files)
	v = [x for f in files for x in import_violations(f)]
	c("XR-COMP-3 kho.py + kho_*.py chỉ import thư viện chuẩn / frappe / bc / helper sx THUẦN trong danh sách §5 (bọc"
		" try/except ImportError); không _dong_du / ma_lo_ton_cu / prefix_lo / gia_von_hien / ghi_gia_tu_tinh, không import động;"
		" xu_ly chỉ gọi với chay=0",
		not v, v)
	# Bộ chặn tự kiểm: mẫu vi phạm phải bị bắt (kể cả khi chú thích / docstring nhắc tên helper cấm thì KHÔNG bị bắt).
	probe = os.path.join(os.environ.get("TMPDIR", "/tmp"), f"nen_probe_{os.getpid()}.py")
	XL = "try:\n\tfrom sx.api.sau_kiem_ke import xu_ly\nexcept ImportError:\n\txu_ly = None\n"
	samples = {
		"try:\n\tfrom sx.utils import items_tp, prefix_lo\nexcept ImportError:\n\tpass": True,  # tên cấm, module được phép
		"try:\n\tfrom sx.api.lo_cu import _dong_du\nexcept ImportError:\n\tpass": True,
		"try:\n\tfrom sx.sx.doctype.sx_kiem_ke.sx_kiem_ke import ma_lo_ton_cu\nexcept ImportError:\n\tpass": True,
		"try:\n\timport sx.utils\nexcept ImportError:\n\tpass": True,                      # không kiểm được tên
		"from ketoan.api import mt_debt": True,                                                  # app khác
		"x = frappe.get_attr('sx.api.mfg.gia_von_hien')": True,                                  # import động
		"from sx.utils import items_tp": True,                                                   # đúng tên, KHÔNG bọc try
		"try:\n\tfrom sx.utils import items_tp\nexcept ImportError:\n\titems_tp = None": False,
		'"""Không import lo_cu._dong_du / utils.prefix_lo."""\nimport re  # prefix_lo': False,  # chỉ nhắc tên
		# sau_kiem_ke.xu_ly: import được phép, nhưng chỉ GỌI với chay=0 ghi rõ (chay=1 ghi phiếu bù vào DB).
		XL + "r = xu_ly(chay=1)": True,
		XL + "r = xu_ly(phieu='P', chay=True)": True,
		XL + "r = xu_ly(None, None, None, 1)": True,                        # chay = đối số thứ 4
		XL + "r = xu_ly(phieu='P')": True,                                  # không ghi rõ chay
		XL + "r = xu_ly(phieu='P', **kw)": True,                            # không kiểm được
		XL + "import functools\nf = functools.partial(xu_ly, chay=1)": True,  # đưa đi như giá trị
		"try:\n\tfrom sx.api.sau_kiem_ke import xu_ly as soat\nexcept ImportError:\n\tsoat = None\nr = soat(chay=1)": True,
		"x = frappe.get_attr('sx.api.sau_kiem_ke.xu_ly')": True,             # lấy động → lời gọi không kiểm được
		XL + "r = xu_ly(phieu='P', chay=0) if xu_ly is not None else None": False,
		XL + "r = xu_ly(None, None, None, False) if not xu_ly is None else None": False,
	}
	got = {}
	for s in samples:
		with open(probe, "w", encoding="utf-8") as fh:
			fh.write(s + "\n")
		got[s] = bool(import_violations(probe))
	os.remove(probe)
	c("XR-COMP-3 bộ chặn bắt đúng mẫu vi phạm, không bắt nhầm chú thích / import bọc try", got == samples,
		{s: g for s, g in got.items() if g != samples[s]})

	allf = sorted(glob.glob(os.path.join(API, "*.py")))
	d = [x for f in allf for x in dict_name_violations(f)]
	c(f"XC-2 bc/api/*.py ({len(allf)} file): không alias SQL / đọc thuộc tính trùng tên method dict"
		" (items, keys, values, get, copy, pop, update, clear, setdefault, fromkeys)", not d and len(allf) > 10, d)


# ═══════════════════════════════════════════════════════════════════════════
# B. Vai trò kho: kho nhóm, chồng quy tắc, POS đã tắt (XR-T2, XR-T3, XR-T6)
# ═══════════════════════════════════════════════════════════════════════════
def seed_roles(k):
	k.wh(W_TPG, ROOT, group=True)
	k.wh(W_TPC, W_TPG)
	k.wh(W_TVG, W_TPG, group=True)
	k.wh(W_TV1, W_TVG)
	k.wh(W_CLG, W_TPG, group=True)
	k.wh(W_CL1, W_CLG)
	k.wh(W_TPDD, W_TPG, warehouse_type="Transit")
	k.wh(W_SHOP, W_TPG)
	k.wh(W_TVDV, ROOT, warehouse_type="Transit", is_rejected_warehouse=1)
	k.wh(W_CHG, ROOT, group=True)
	k.wh(W_CHC1, W_CHG)
	k.wh(W_CHDONG, CH_GROUP)
	k.wh(W_XG, ROOT, group=True)
	k.wh(W_X1, W_XG)
	k.wh(W_BG, ROOT, group=True)
	k.wh(W_B1, W_BG)
	k.wh(W_NG, ROOT, group=True)
	k.wh(W_N1, W_NG)
	insert("POS Profile", name="NEN-POS shop nhà máy", company="HGC", warehouse=W_SHOP, disabled=0)
	insert("POS Profile", name="NEN-POS chuỗi", company="HGC", warehouse=W_CHG, disabled=0)       # trỏ vào kho NHÓM
	insert("POS Profile", name="NEN-POS đã đóng", company="HGC", warehouse=W_CHDONG, disabled=1)  # cửa hàng đã đóng
	single("SX Settings", kho_tp=W_TPG, kho_hang_tra_ve=W_TVG, kho_cach_ly=W_CLG, kho_xuong=W_XG, kho_btp=W_BG, kho_nvl=W_NG)
	k.item("NEN-TP1", "Bánh vai trò NEN", G_TRAD, carton=10, custom_sx_nhom="TP")
	# Mỗi kho một số hộp khác nhau × 10.000 đ (tổng theo vai trò phân biệt được).
	for w, q in ((TP, 20), (W_TPC, 100), (W_TV1, 5), (W_CL1, 3), (W_TPDD, 10), (W_SHOP, 7), (W_TVDV, 4), (W_CHC1, 6),
			(W_CHDONG, 8), (W_X1, 2), (W_B1, 1), (W_N1, 9), (CH1, 11), (TRA_VE, 12)):
		k.receipt("NEN-TP1", w, q, q * 10_000, "2026-10-01")


def roles_checks(c):
	k = fresh()
	seed_roles(k)
	k.finalize()
	from bc.api import kho
	whs = kho.warehouses("HGC")
	leaf = {w.name: w.role for w in whs if not w.is_group}
	# Kho chuẩn của base(k) sau khi SX Settings trỏ sang nhóm NEN-: Thành phẩm vẫn tp (BC Settings.sx_warehouse = _wh());
	# Hàng trả về / Kho cách ly / Xưởng / BTP / NVL chuẩn không còn được cấu hình (không đánh dấu trả về) → khac.
	expect = {
		TP: "tp", TRA_VE: "khac", CACH_LY: "khac", XUONG: "khac", BTP: "khac", NVL: "khac", DI_DUONG: "di_duong",
		KHO_CU: "khac", CH1: "cua_hang", CH2: "cua_hang",
		W_TPC: "tp",            # XR-T2: lá của kho_tp NHÓM (W5 _subtree = chính nút → khac)
		W_TV1: "tra_ve",        # XR-T2 nhóm trả về + XR-T3 trả về cấu hình nằm trong cây TP (W16 → tp)
		W_CL1: "cach_ly",       # XR-T2 nhóm cách ly + XR-T3 cách ly trong cây TP (W15 → tp)
		W_TPDD: "di_duong",     # XR-T3 Transit trong cây TP (W3 tp trước Transit → tp)
		W_SHOP: "tp",           # XR-T3 shop POS là lá TP (W17 cửa hàng trước tp → cua_hang)
		W_TVDV: "tra_ve",       # XR-T3 Transit + is_rejected_warehouse (W1 Transit trước → di_duong)
		W_CHC1: "cua_hang",     # XR-T2 POS Profile trỏ vào kho NHÓM
		W_CHDONG: "khac",       # XR-T6 POS Profile đã tắt (W6 bỏ lọc disabled → cua_hang)
		W_X1: "xuong", W_B1: "btp", W_N1: "nvl",   # XR-T2 nhóm xưởng / BTP / NVL
	}
	c("XR-T2/T3/T6 vai trò từng kho lá (kho nhóm bung theo lft/rgt; khớp đầu tiên tra_ve > cach_ly > di_duong > tp >"
		" cua_hang > xuong/btp/nvl; POS đã tắt không là cửa hàng)", leaf == expect,
		{n: (leaf.get(n), r) for n, r in expect.items() if leaf.get(n) != r} or sorted(set(leaf) ^ set(expect)))
	c("XR-T2 kho nhóm có trong danh sách (is_group = 1), kho RV không", all(next(w for w in whs if w.name == g).is_group == 1
		for g in (W_TPG, W_TVG, W_CLG, W_CHG, W_XG, W_BG, W_NG)) and not [w for w in whs if w.name.endswith("- RV")])

	rows = [r for r in kho.bin_rows("HGC") if r.item_code == "NEN-TP1"]
	role_v = {}
	for r in rows:
		role_v[r.role] = role_v.get(r.role, 0.0) + r.value
	# Hộp × 10.000: tp = Thành phẩm 20 + TP chính 100 + Shop nhà máy 7 = 127 → 1.270.000; cua_hang = chuỗi 1 6 + CH Bạch Đằng
	# 11 = 170.000; di_duong = TP đi đường 10 = 100.000; tra_ve = Trả về 1 5 + Trả về đang về 4 = 90.000; cach_ly = 3 = 30.000;
	# xuong 20.000, btp 10.000, nvl 90.000; khac = CH đã đóng 8 + Hàng trả về chuẩn 12 = 200.000. Tổng 1.980.000.
	c("XR-T2/T3/T6 bin_rows: giá trị theo vai trò", role_v == {"tp": 1_270_000, "cua_hang": 170_000, "di_duong": 100_000,
		"tra_ve": 90_000, "cach_ly": 30_000, "xuong": 20_000, "btp": 10_000, "nvl": 90_000, "khac": 200_000}, role_v)
	sell = sum(r.value for r in rows if r.sellable)
	c("XR-T2/T3 bin_rows: bán được = 1.980.000 − trả về 90.000 − cách ly 30.000 = 1.860.000", sell == 1_860_000, sell)

	from bc.api import kho_ton
	v = kho_ton.get_overview(refresh=1)["value"]
	t = v["totals"]
	br = {x["key"]: x["value"] for x in v["by_role"]}
	c("XR-T2/T3 K1 tổng 1.980.000, bán được 1.860.000, không bán được 120.000, đi đường 100.000",
		(t["value"], t["value_sellable"], t["value_unsellable"], t["value_transit"]) == (1_980_000, 1_860_000, 120_000, 100_000), t)
	# san_xuat = 20.000 + 10.000 + 90.000 = 120.000; khong_ban = 90.000 + 30.000 = 120.000
	c("XR-T2/T3/T6 K1 theo khu vực kho", br == {"tp": 1_270_000, "cua_hang": 170_000, "di_duong": 100_000,
		"san_xuat": 120_000, "khong_ban": 120_000, "khac": 200_000}, br)

	# BC Settings.sx_warehouse là kho NHÓM (live._finished_stock hỗ trợ), SX Settings.kho_tp là lá chuẩn: lá trong cây
	# NEN-TP tổng vẫn tp (qua _wh()), trả về / cách ly / đi đường trong cây giữ vai trò riêng.
	frappe.db.set_single_value("BC Settings", "sx_warehouse", W_TPG)
	frappe.db.set_single_value("SX Settings", "kho_tp", TP)
	leaf2 = {w.name: w.role for w in kho.warehouses("HGC") if not w.is_group}
	c("XR-T2 BC sx_warehouse = kho nhóm: TP chính / Shop nhà máy / Thành phẩm là tp; trả về, cách ly, đi đường giữ vai trò",
		{n: leaf2[n] for n in (W_TPC, W_SHOP, TP, W_TV1, W_CL1, W_TPDD)} == {W_TPC: "tp", W_SHOP: "tp", TP: "tp",
		W_TV1: "tra_ve", W_CL1: "cach_ly", W_TPDD: "di_duong"}, {n: leaf2[n] for n in (W_TPC, W_SHOP, TP, W_TV1, W_CL1, W_TPDD)})


# ═══════════════════════════════════════════════════════════════════════════
# C. Nhóm con truyền thống, thùng ròng có dấu, dòng Bin lẻ, giá vốn mới nhất (XR-T4, XR-T7, XR-T8, XR-T5)
# ═══════════════════════════════════════════════════════════════════════════
def seed_misc(k):
	k.group(G_TRAD_CON, G_TRAD)
	tp = {"custom_sx_nhom": "TP"}
	k.item("NEN-T1", "Bánh nướng NEN", G_TRAD_CON, carton=10, **tp)   # nhóm CON của truyền thống, 10 hộp / thùng
	k.item("NEN-T2", "Bánh dẻo NEN", G_TRAD, carton=4, **tp)          # 4 hộp / thùng — tồn âm
	k.item("NEN-T3", "Bánh pía NEN", G_TRAD, **tp)                    # CHƯA khai thùng — tồn âm
	k.item("NEN-R", "Bơ NEN", G_NL, uom="Kg", custom_sx_nhom="NVL")
	k.item("NEN-Q", "Muối NEN", G_NL, uom="Kg", custom_sx_nhom="NVL")
	k.item("NEN-Q2", "Đường NEN", G_NL, uom="Kg", custom_sx_nhom="NVL")
	k.item("NEN-Q3", "Bột NEN", G_NL, uom="Kg", custom_sx_nhom="NVL")
	k.receipt("NEN-T1", TP, 100, 1_000_000, "2026-10-01")             # +100 hộp × 10.000
	k.sale("NEN-T2", TP, 8, 40_000, "2026-10-10")                     # bán khi chưa có hàng → Bin (−8, −40.000)
	k.sale("NEN-T3", TP, 4, 20_000, "2026-10-10")                     # → Bin (−4, −20.000)
	# NEN-R ở NVL: +10 @5.000 (01/07) → −10 (15/07) → +10 @7.000 (01/10) → −10 (03/10) → +5 / −5 giá 0 (05/10) → Bin NVL
	# (0, 0, đơn giá 0); CH Tuệ Tĩnh −2 giá trị 0 (06/10) → Bin (−2, 0, 0). Không Bin nào có đơn giá > 0, Item không có giá →
	# nấc "sổ kho": dòng sống mới nhất có đơn giá > 0 là 03/10 (7.000) — KHÔNG phải 01/07 (5.000).
	k.receipt("NEN-R", NVL, 10, 50_000, "2026-07-01")
	k.sale("NEN-R", NVL, 10, 50_000, "2026-07-15")
	k.receipt("NEN-R", NVL, 10, 70_000, "2026-10-01")
	k.sale("NEN-R", NVL, 10, 70_000, "2026-10-03")
	k.receipt("NEN-R", NVL, 5, 0, "2026-10-05")
	k.sale("NEN-R", NVL, 5, 0, "2026-10-05")
	k.sale("NEN-R", CH2, 2, 0, "2026-10-06")
	# Dòng sổ ĐÃ HUỶ mới hơn với đơn giá 9.000 (không được dùng).
	k.receipt("NEN-R", NVL, 1, 9_000, "2026-10-08", name="NEN-PR-HUY")
	frappe.db.sql("UPDATE `tabStock Ledger Entry` SET is_cancelled = 1, valuation_rate = 9000 WHERE voucher_no = 'NEN-PR-HUY'")
	k.sale("NEN-Q", CH2, 0.5, 0, "2026-10-12")                        # Bin (−0,5 kg, 0, 0)
	k.receipt("NEN-Q2", NVL, 0.25, 0, "2026-10-12")                   # Bin (0,25 kg, 0, 0)
	k.receipt("NEN-Q3", NVL, 0.0000005, 0, "2026-10-12")              # Bin (0,0000005 kg, 0) — dưới ngưỡng 1e-6


def misc_checks(c):
	k = fresh()
	seed_misc(k)
	k.finalize()
	from bc.api import kho, kho_ton

	# ── XR-T7: carton_total trực tiếp ──
	ct = kho.carton_total({"A": 100, "B": -8, "C": -4}, {"A": 10, "B": 4})
	# thùng = 100/10 + (−8)/4 = 10 − 2 = 8,0; lẻ = −4 (C không hệ số, âm vẫn cộng); 1 mã không hệ số
	c("XR-T7 carton_total ròng có dấu: +100 (10/thùng), −8 (4/thùng), −4 (chưa khai) → 8,0 thùng, −4 hộp lẻ, 1 mã",
		ct == {"cartons": 8.0, "boxes_without_carton_factor": -4.0, "items_without_carton_factor": 1}, ct)
	ct2 = kho.carton_total({"B": -8, "C": -4, "D": 0.0000001}, {"B": 4})
	# −8/4 = −2,0 thùng; lẻ −4; D 1e-7 ≤ EPS không đếm
	c("XR-T7 toàn âm: −2,0 thùng, −4 hộp lẻ, 1 mã (mã ~0 không đếm)",
		ct2 == {"cartons": -2.0, "boxes_without_carton_factor": -4.0, "items_without_carton_factor": 1}, ct2)
	qs, fs = {"A": 100, "B": -8, "C": -4, "E": 37, "F": -3}, {"A": 10, "B": 4, "E": 6}
	per = [kho.carton_total({i: q}, fs) for i, q in qs.items()]
	inv = all(abs(q - (p["cartons"] * fs.get(i, 0) if fs.get(i) else p["boxes_without_carton_factor"])) < 0.5
		for (i, q), p in zip(qs.items(), per))
	tot = kho.carton_total(qs, fs)
	# Σ q = 100 − 8 − 4 + 37 − 3 = 122; có hệ số: 100/10 + (−8)/4 + 37/6 = 10 − 2 + 6,1667 = 14,1667 → 14,2; lẻ −4 − 3 = −7
	c("XR-T7 bất biến từng mã q = thùng × hệ số + lẻ; tổng: 14,2 thùng, −7 lẻ, 2 mã", inv and tot == {"cartons": 14.2,
		"boxes_without_carton_factor": -7.0, "items_without_carton_factor": 2}, (per, tot))

	# ── XR-T4 + XR-T7 trên K1 / K2 ──
	rows = kho.bin_rows("HGC")
	gk = {r.item_code: r.group_key for r in rows if r.item_code.startswith("NEN-T")}
	c("XR-T4 bin_rows: mã ở nhóm CON của truyền thống vẫn là truyền thống", gk == {"NEN-T1": "traditional",
		"NEN-T2": "traditional", "NEN-T3": "traditional"}, gk)
	tpg = kho._tp_by_group()
	c("XR-T4 _tp_by_group (site không sx): gồm mã nhóm con truyền thống, không gồm NVL",
		{"NEN-T1", "NEN-T2", "NEN-T3"} <= tpg and "NEN-R" not in tpg, sorted(tpg))
	ov = kho_ton.get_overview(refresh=1)["value"]
	g = {x["key"]: x for x in ov["by_group"]}
	tr = g["traditional"]
	# Truyền thống: T1 +100 (1.000.000) + T2 −8 (−40.000) + T3 −4 (−20.000) → 88 hộp, 940.000; thùng 100/10 − 8/4 = 8,0;
	# lẻ −4 (T3); 1 mã chưa khai; mã còn tồn (> 0) = 1. Tết không có gì.
	c("XR-T4/T7 K1 truyền thống (gồm nhóm con): 88 hộp, 8,0 thùng, −4 hộp chưa khai (1 mã), 940.000",
		(tr["value"], tr["qty"], tr["uom"], tr["cartons"], tr["boxes_without_carton_factor"], tr["items_without_carton_factor"],
		tr["items"]) == (940_000, 88, "Hộp", 8.0, -4, 1, 1), tr)
	c("XR-T7 K1 bất biến 88 = 10 × 10 + (−2) × 4 + (−4)", tr["qty"] == 10 * 10 + (-2) * 4 + tr["boxes_without_carton_factor"])
	c("XR-T4 K1 Tết = 0", g["tet"]["value"] == 0, g["tet"])
	pts = kho_ton.get_trend(refresh=1)["trend"]["points"]
	c("XR-T4 K2 điểm hôm nay: truyền thống 940.000 (gồm nhóm con)", pts[-1]["today"] and pts[-1]["traditional"] == 940_000,
		pts[-1])

	# ── XR-T8: ngưỡng dòng Bin ──
	br = {(r.item_code, r.warehouse): r.qty for r in rows if r.item_code.startswith("NEN-Q")}
	c("XR-T8 bin_rows: −0,5 kg (giá trị 0) ở CH Tuệ Tĩnh và 0,25 kg (giá trị 0) ở NVL được tính; 0,0000005 kg thì không",
		br == {("NEN-Q", CH2): -0.5, ("NEN-Q2", NVL): 0.25}, br)
	c("XR-T8 Bin thật của NEN-Q3 = 0,0000005 (dưới ngưỡng, không phải 0)", bin_of("NEN-Q3", NVL)[0] == 0.0000005,
		bin_of("NEN-Q3", NVL))

	# ── XR-T5: giá vốn dự phòng nấc sổ kho = dòng sống MỚI NHẤT ──
	rt = kho.rates([("NEN-R", CH2), ("NEN-R", NVL)], "HGC")
	c("XR-T5 rates: hai đơn giá dương 5.000 (01/07) và 7.000 (03/10) → lấy 7.000 (mới nhất, bỏ dòng huỷ 9.000), nguồn so_kho",
		rt == {("NEN-R", CH2): (7000.0, "so_kho"), ("NEN-R", NVL): (7000.0, "so_kho")}, rt)
	c("XR-T5 tiền đề: không Bin nào của NEN-R có đơn giá > 0", bin_of("NEN-R", NVL) == (0.0, 0.0, 0.0)
		and bin_of("NEN-R", CH2) == (-2.0, 0.0, 0.0), (bin_of("NEN-R", NVL), bin_of("NEN-R", CH2)))


# ═══════════════════════════════════════════════════════════════════════════
# D. Sổ giả: kiểm kê có lô = hai chân như ERPNext (XR-T1)
# ═══════════════════════════════════════════════════════════════════════════
def recon_checks(c):
	k = fresh()
	k.item("NEN-B", "Bánh lô NEN", G_TET, carton=10, batch=True, custom_sx_nhom="TP")
	k.item("NEN-NB", "Bánh không lô NEN", G_TET, carton=10, custom_sx_nhom="TP")
	for b in ("NEN-L1", "NEN-L2", "NEN-L3"):
		k.batch(b, "NEN-B", expiry="2027-06-30")
	k.receipt("NEN-B", TRA_VE, 10, 100_000, "2026-07-01", batch="NEN-L1")   # 10 × 10.000
	k.receipt("NEN-B", TRA_VE, 3, 30_000, "2026-08-01", batch="NEN-L3")
	k.receipt("NEN-NB", TRA_VE, 5, 50_000, "2026-07-01")
	k.recon("2026-10-20", [
		dict(item_code="NEN-B", warehouse=TRA_VE, qty=9, current_qty=10, value_diff=-10_000, batch="NEN-L1"),  # thiếu 1
		dict(item_code="NEN-NB", warehouse=TRA_VE, qty=6, current_qty=5, value_diff=10_000),                   # không lô
		dict(item_code="NEN-B", warehouse=TRA_VE, qty=2, current_qty=0, value_diff=20_000, batch="NEN-L2"),    # lô mới
		dict(item_code="NEN-B", warehouse=TRA_VE, qty=0, current_qty=3, value_diff=-30_000, batch="NEN-L3"),   # lô hết
	], name="NEN-SR-1")
	k.finalize()
	legs = frappe.db.sql("""SELECT sle.item_code, sle.actual_qty, sle.stock_value_difference AS svd, sle.voucher_detail_no,
			sle.qty_after_transaction, sbb.type_of_transaction AS loai, e.batch_no, e.qty AS lot_qty
		FROM `tabStock Ledger Entry` sle
		LEFT JOIN `tabSerial and Batch Bundle` sbb ON sbb.name = sle.serial_and_batch_bundle
		LEFT JOIN `tabSerial and Batch Entry` e ON e.parent = sbb.name
		WHERE sle.voucher_no = 'NEN-SR-1' ORDER BY sle.posting_datetime, sle.creation""", as_dict=True)
	got = [(r.item_code, r.batch_no, float(r.actual_qty), float(r.svd), r.loai, float(r.lot_qty) if r.lot_qty is not None
		else None) for r in legs]
	# L1: đơn giá suy ra = −10.000 / (9 − 10) = 10.000 → chân xuất −10 × 10.000 = −100.000, chân nhập −10.000 + 100.000
	# = +90.000 (= 9 × 10.000). Không lô: một dòng actual_qty 0, svd +10.000. L2 (current 0): chỉ chân nhập +2, +20.000.
	# L3 (đếm 0): chỉ chân xuất −3, −30.000.
	c("XR-T1 recon: lô thiếu → chân xuất −10 (Outward) rồi chân nhập +9 (Inward); không lô một dòng actual_qty 0; lô mới chỉ"
		" chân nhập; lô hết chỉ chân xuất", got == [
			("NEN-B", "NEN-L1", -10.0, -100_000.0, "Outward", -10.0), ("NEN-B", "NEN-L1", 9.0, 90_000.0, "Inward", 9.0),
			("NEN-NB", None, 0.0, 10_000.0, None, None),
			("NEN-B", "NEN-L2", 2.0, 20_000.0, "Inward", 2.0),
			("NEN-B", "NEN-L3", -3.0, -30_000.0, "Outward", -3.0)], got)
	c("XR-T1 hai chân cùng voucher_detail_no (cùng dòng phiếu)", legs[0].voucher_detail_no and
		legs[0].voucher_detail_no == legs[1].voucher_detail_no, [r.voucher_detail_no for r in legs])
	# Bin NEN-B @ trả về: 10 + 3 − 10 + 9 + 2 − 3 = 11; giá trị 100.000 + 30.000 − 100.000 + 90.000 + 20.000 − 30.000 = 110.000.
	# NEN-NB: tồn sau kiểm kê = 6; 50.000 + 10.000 = 60.000.
	c("XR-T1 Bin sau finalize: NEN-B 11 / 110.000; NEN-NB 6 / 60.000", (bin_of("NEN-B", TRA_VE)[:2], bin_of("NEN-NB", TRA_VE)[:2])
		== ((11.0, 110_000.0), (6.0, 60_000.0)), (bin_of("NEN-B", TRA_VE), bin_of("NEN-NB", TRA_VE)))
	from bc.api import kho
	lots = {r.batch_no: r.qty for r in kho.lot_rows(["NEN-B"], [TRA_VE])}
	c("XR-T1 kho.lot_rows khớp Bin: L1 9, L2 2 (L3 về 0 không hiện)", lots == {"NEN-L1": 9.0, "NEN-L2": 2.0}, lots)
	# rate / current_rate cho trước (thêm phiếu sau finalize — chỉ kiểm cách chia svd giữa hai chân, không kiểm Bin).
	k.recon("2026-10-21", [dict(item_code="NEN-B", warehouse=TRA_VE, qty=4, current_qty=2, value_diff=28_000, rate=12_000,
		batch="NEN-L2")], name="NEN-SR-2")
	k.recon("2026-10-22", [dict(item_code="NEN-B", warehouse=TRA_VE, qty=4, current_qty=4, value_diff=8_000,
		current_rate=12_000, batch="NEN-L2")], name="NEN-SR-3")
	sv = [(r[0], float(r[1]), float(r[2])) for r in frappe.db.sql("""SELECT voucher_no, actual_qty, stock_value_difference
		FROM `tabStock Ledger Entry` WHERE voucher_no IN ('NEN-SR-2', 'NEN-SR-3') ORDER BY creation""")]
	# SR-2 có rate 12.000: chân nhập 4 × 12.000 = 48.000, chân xuất 28.000 − 48.000 = −20.000 (= −2 × 10.000).
	# SR-3 chỉ đổi giá, current_rate 12.000: chân xuất −4 × 12.000 = −48.000, chân nhập 8.000 + 48.000 = 56.000 (4 × 14.000).
	c("XR-T1 recon chia svd theo rate / current_rate; tổng hai chân = value_diff", sv == [("NEN-SR-2", -2.0, -20_000.0),
		("NEN-SR-2", 4.0, 48_000.0), ("NEN-SR-3", -4.0, -48_000.0), ("NEN-SR-3", 4.0, 56_000.0)], sv)
	# Lô L4 có trên phiếu nhưng sổ 0 / đếm 0 (qty = current_qty = 0): ERPNext v16 get_sle_for_serialized_items không có chân
	# xuất (không bundle hiện tại) cũng không có chân nhập (qty = 0) → KHÔNG dòng sổ nào. Dòng L2 đếm 0 (sổ 4, current_rate
	# 12.000 nhưng value_diff −56.000 = −4 × 14.000 sau SR-3): chỉ chân xuất, nhận CẢ value_diff → (−4, −56.000).
	k.batch("NEN-L4", "NEN-B", expiry="2027-06-30")
	k.recon("2026-10-23", [
		dict(item_code="NEN-B", warehouse=TRA_VE, qty=0, current_qty=0, value_diff=0, batch="NEN-L4"),
		dict(item_code="NEN-B", warehouse=TRA_VE, qty=0, current_qty=4, value_diff=-56_000, current_rate=12_000, batch="NEN-L2"),
	], name="NEN-SR-4")
	s4 = [(r[0], float(r[1]), float(r[2])) for r in frappe.db.sql("""SELECT e.batch_no, sle.actual_qty,
			sle.stock_value_difference
		FROM `tabStock Ledger Entry` sle LEFT JOIN `tabSerial and Batch Entry` e ON e.parent = sle.serial_and_batch_bundle
		WHERE sle.voucher_no = 'NEN-SR-4' ORDER BY sle.creation""")]
	n4 = frappe.db.sql("SELECT COUNT(*) FROM `tabStock Reconciliation Item` WHERE parent = 'NEN-SR-4'")[0][0]
	c("XR-T1 dòng lô qty = current_qty = 0 không ghi dòng sổ (vẫn nằm trên phiếu); dòng lô đếm 0 chỉ chân xuất nhận cả"
		" value_diff", s4 == [("NEN-L2", -4.0, -56_000.0)] and n4 == 2, (s4, n4))


# ═══════════════════════════════════════════════════════════════════════════
# E. Thời gian thực: số mã có tồn từng kho, "+N mã" (XC-2)
# ═══════════════════════════════════════════════════════════════════════════
def live_checks(c):
	k = fresh()
	tp = {"custom_sx_nhom": "TP"}
	k.item("NEN-L1", "Bánh live NEN 1", G_TRAD, carton=10, **tp)
	k.item("NEN-L2", "Bánh live NEN 2", G_TRAD, carton=10, **tp)
	k.item("NEN-L3", "Bánh live NEN 3", G_TRAD, **tp)
	k.item("NEN-L4", "Bao bì live NEN", G_NL, uom="Cái")
	# Phiếu sản xuất HÔM NAY nhập 2 mã thành phẩm vào kho TP (_wh()) → dòng sự kiện "… +1 mã".
	k.se("Manufacture", TODAY.isoformat(), [dict(item_code="NEN-L1", t_warehouse=TP, qty=50, rate=10_000, is_finished_item=1),
		dict(item_code="NEN-L2", t_warehouse=TP, qty=30, rate=10_000, is_finished_item=1)], time="09:15:00", name="NEN-SE-SX")
	k.se("Material Transfer", "2026-10-26", [dict(item_code="NEN-L1", s_warehouse=TP, t_warehouse=CH1, qty=10,
		rate=10_000)], name="NEN-SE-CK")
	k.sale("NEN-L3", TP, 5, 25_000, "2026-10-26")                   # TP: dòng âm — không đếm là "có tồn"
	k.receipt("NEN-L4", XUONG, 12, 0, "2026-10-20")                 # Xưởng: 12 cái giá trị 0 — vẫn là kho có tồn
	k.finalize()
	from bc.api import live
	snap = live.get_snapshot(refresh=1)
	wh = {w["name"]: (w["items"], w["value"]) for w in snap["warehouses"]}
	# TP: L1 50 − 10 = 40 (400.000) + L2 30 (300.000) + L3 −5 (−25.000) → 2 mã có tồn, 675.000. CH Bạch Đằng: L1 10 →
	# 1 mã, 100.000. Xưởng: L4 12 cái, giá trị 0 → 1 mã, 0 (trước khi sửa: items = 0 và giá trị 0 → kho bị bỏ).
	c("XC-2 Thời gian thực: số mã có tồn từng kho (TP 2, CH Bạch Đằng 1, Xưởng 1 giá trị 0 vẫn hiện)",
		wh == {TP: (2, 675_000), CH1: (1, 100_000), XUONG: (1, 0)}, wh)
	ev = [e["title"] for e in snap["feed"] if e["kind"] == "production"]
	c("XC-2 dòng sự kiện phiếu sản xuất 2 mã: '… +1 mã'", len(ev) == 1 and ev[0].endswith(" +1 mã"), ev)
	c("XC-2 khoá payload giữ nguyên (warehouses[].items)", snap["warehouses"] and set(snap["warehouses"][0])
		== {"name", "warehouse_name", "items", "value", "top"}, snap["warehouses"][:1])


# ═══════════════════════════════════════════════════════════════════════════
# F. Tháng chọn (SEC-1)
# ═══════════════════════════════════════════════════════════════════════════
def month_checks(c):
	k = fresh()
	k.finalize()
	from bc.api import kho, kho_kk, kho_nhap
	cur = (datetime.date(2026, 10, 1), datetime.date(2026, 10, 27), "2026-10")
	cases = {None: cur, "": cur, "abc": cur, "2026-11": cur, "2099-01": cur, "0001-01": cur, "0001-02": cur, "0000-01": cur,
		"1999-12": cur, "2000-01": cur,                        # trước sàn: 10 năm trước tháng này = 10/2016
		"2016-09": cur,
		"2016-10": (datetime.date(2016, 10, 1), datetime.date(2016, 10, 31), "2016-10"),   # đúng sàn 10 năm
		"2026-09": (datetime.date(2026, 9, 1), datetime.date(2026, 9, 30), "2026-09"),
		"2026-10-15": cur, "2026-02": (datetime.date(2026, 2, 1), datetime.date(2026, 2, 28), "2026-02")}
	got = {}
	for t, exp in cases.items():
		try:
			got[t] = kho.month_period(t)
		except Exception as e:  # noqa: BLE001
			got[t] = repr(e)
	c("SEC-1 month_period: sai dạng / tương lai / trước 2000 / quá 10 năm → tháng này; tháng hợp lệ giữ nguyên",
		got == cases, {t: g for t, g in got.items() if g != cases[t]})
	# getdate v16 thật trả None cho '0001-01-01' (is_invalid_date_string) — month_period không được phụ thuộc getdate.
	orig = kho.getdate
	kho.getdate = lambda v=None: None if str(v or "").startswith("0001-01-01") else orig(v)
	try:
		r = kho.month_period("0001-01")
	except Exception as e:  # noqa: BLE001
		r = repr(e)
	finally:
		kho.getdate = orig
	c("SEC-1 month_period không ném lỗi khi getdate trả None (như v16)", r == cur, r)
	for mod, t in ((kho_kk, "0001-01"), (kho_nhap, "0001-02"), (kho_kk, "1900-01"), (kho_nhap, "0000-01")):
		try:
			m = mod.get_overview(thang=t, refresh=1)["meta"]
			ok, det = m["thang"] == "2026-10" and m["from"] == "2026-10-01", m
		except Exception as e:  # noqa: BLE001
			ok, det = False, repr(e)
		c(f"SEC-1 {mod.__name__.split('.')[-1]}.get_overview(thang='{t}') không 500, về tháng này", ok, det)


if __name__ == "__main__":
	c = Check()
	print("── A. Bộ chặn tĩnh")
	static_checks(c)
	print("── B. Vai trò kho")
	roles_checks(c)
	print("── C. Nhóm con, thùng, Bin lẻ, giá vốn")
	misc_checks(c)
	print("── D. Sổ giả: kiểm kê có lô")
	recon_checks(c)
	print("── E. Thời gian thực")
	live_checks(c)
	print("── F. Tháng chọn")
	month_checks(c)
	c.done()
