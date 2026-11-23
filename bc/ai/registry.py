# -*- coding: utf-8 -*-
"""bc.ai.registry — hợp đồng lõi của Trợ lý AI: tín hiệu (Signal), quy tắc (@rule), detector (@detector), đường dẫn
(path) vào gói số, placeholder, nhóm gọi mô hình, KPI.

Gói số (pack) = {mảng: {tên: payload của đúng một method bc.api.*}} (bc.ai.collect) + pack["he-thong"][tên] do detector
đổ vào. Path là ĐỊA CHỈ DUY NHẤT của mọi con số: "cong-no.receivables.kpis.overdue_pct",
"cong-no.receivables.top_overdue[0].overdue". Khoá cấp 1 = mảng → suy ra nhận định dùng số của mảng nào (ẩn mảng thì
ẩn nhận định).

Quy tắc = hàm THUẦN trên pack (không SQL, không frappe.db), trả list[Signal]. Lời quy tắc viết bằng placeholder
`{{path|kiểu}}` (kiểu: tien | so | pct | ngay | chu) — máy chủ thay bằng số thật (bc.ai.render). Số do quy tắc tự tính
(đếm, tổng) khai trong `tinh` của tín hiệu và viết `{{@tên|kiểu}}`; bộ chạy ghi chúng vào pack ở
`<mảng>._ai.<khoá tín hiệu>.<tên>` nên vẫn là một path như mọi số khác (mô hình cũng trích được).

Khối nguồn của quy tắc (`sources`) thiếu / `_error` / `available: False` → quy tắc "không chạy được": KHÔNG sinh và
KHÔNG đóng tín hiệu cũ (khác với "chạy, không còn tín hiệu" → đóng).
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass, field

import frappe

from bc.api._common import SECTIONS

HE_THONG = "he-thong"            # "mảng" của detector hệ thống — không nằm trong SECTIONS, chỉ quản trị thấy
AUDIENCES = ("lanh-dao", "quan-tri")
SEVERITIES = ("do", "vang")       # đỏ nặng hơn vàng
KINDS = ("tien", "so", "pct", "ngay", "chu")

# Nhóm gọi mô hình (mỗi nhóm một lượt) — cũng là nhóm lọc trên màn #/tro-ly. Thứ tự = thứ tự hiện.
GROUPS = {
	"kinh-doanh": {"label": "Kinh doanh", "sections": ("tong-quan", "ngay", "thang", "tet", "tinh-thanh", "san-pham"),
		"audience": "lanh-dao"},
	"kho-sx": {"label": "Kho & SX", "sections": ("sx-tet", "ton-kho", "han-dung", "kiem-ke", "nhap-tp"),
		"audience": "lanh-dao"},
	"van-chuyen": {"label": "Vận chuyển", "sections": ("van-chuyen",), "audience": "lanh-dao"},
	"tai-chinh": {"label": "Công nợ", "sections": ("cong-no", "phai-tra"), "audience": "lanh-dao"},
	"nhan-su": {"label": "Nhân sự", "sections": ("nhan-su",), "audience": "lanh-dao"},
	"attp": {"label": "ATTP", "sections": ("attp",), "audience": "lanh-dao"},
	HE_THONG: {"label": "Hệ thống", "sections": (HE_THONG,), "audience": "quan-tri"},
}

# Nhãn mảng — PHẢI khớp lib/nav.js (bộ thử so); dùng cho "Xem ở màn {nhãn}".
SECTION_LABELS = {
	"thoi-gian-thuc": "Thời gian thực", "tro-ly": "Trợ lý AI", "tong-quan": "Tổng quan", "ngay": "Theo ngày",
	"thang": "Theo tháng", "tet": "Hàng Tết", "tinh-thanh": "Tỉnh thành", "san-pham": "Sản phẩm",
	"sx-tet": "SX Hàng Tết", "ton-kho": "Tồn kho", "han-dung": "Hạn dùng & tồn âm",
	"kiem-ke": "Kiểm kê & điều chỉnh", "nhap-tp": "Nhập TP & giá vốn", "van-chuyen": "Giao hàng & xe",
	"cong-no": "Phải thu", "phai-tra": "Phải trả & quỹ", "nhan-su": "Nhân sự & lương",
	"attp": "An toàn thực phẩm", HE_THONG: "Hệ thống",
}

# Module chứa @rule / @detector — load() import để đăng ký.
_MODULES = ("bc.ai.rules.kd", "bc.ai.rules.kho", "bc.ai.rules.cn", "bc.ai.rules.vc", "bc.ai.rules.ns",
	"bc.ai.rules.attp", "bc.ai.detectors.he_thong")


def group_of(section: str) -> str | None:
	"""Nhóm chứa mảng (None nếu mảng không thuộc nhóm nào, vd thoi-gian-thuc)."""
	return next((g for g, d in GROUPS.items() if section in d["sections"]), None)


# ─── Path ────────────────────────────────────────────────────────────────────
class PathError(KeyError):
	"""Path không phân giải được trên pack."""


_SEG = re.compile(r"^([^\[\]]+)((?:\[\d+\])*)$")
_IDX = re.compile(r"\[(\d+)\]")
_MISSING = object()


def split_path(path: str) -> list:
	"""'a.b[0].c' → ['a', 'b', 0, 'c']. Sai cú pháp → PathError. Khoá không được chứa . [ ] { } |"""
	out: list = []
	for seg in str(path).strip().split("."):
		m = _SEG.match(seg)
		if not m:
			raise PathError(path)
		out.append(m.group(1))
		out += [int(i) for i in _IDX.findall(m.group(2))]
	return out


def resolve(pack, path: str, default=_MISSING):
	"""Giá trị tại path. Thiếu → default nếu có, không thì PathError."""
	try:
		cur = pack
		for p in split_path(path):
			if isinstance(p, int):
				if not isinstance(cur, (list, tuple)) or p >= len(cur):
					raise PathError(path)
				cur = cur[p]
			else:
				if not isinstance(cur, dict) or p not in cur:
					raise PathError(path)
				cur = cur[p]
		return cur
	except PathError:
		if default is _MISSING:
			raise
		return default


def has(pack, path: str) -> bool:
	"""Path có trên pack (giá trị None vẫn tính là có)."""
	try:
		resolve(pack, path)
		return True
	except PathError:
		return False


def section_of(path: str) -> str:
	"""Mảng (khoá cấp 1) của path."""
	return str(path).split(".", 1)[0].strip()


def strip_index(path: str) -> str:
	"""Bỏ chỉ số mảng: 'a.b[0].c' → 'a.b.c' (khoá của nhận định tự do của AI)."""
	return _IDX.sub("", str(path))


# ─── Placeholder ─────────────────────────────────────────────────────────────
PLACEHOLDER = re.compile(r"\{\{\s*([^{}|]+?)\s*\|\s*([a-z]+)\s*\}\}")


def ph(path: str, kind: str) -> str:
	"""Placeholder '{{path|kiểu}}'."""
	if kind not in KINDS:
		raise ValueError(f"kiểu placeholder không hợp lệ: {kind}")
	return "{{" + f"{path}|{kind}" + "}}"


def placeholders(text: str) -> list:
	"""[(path, kiểu)] theo thứ tự xuất hiện (kiểu chưa được kiểm ở đây)."""
	return [(m.group(1).strip(), m.group(2)) for m in PLACEHOLDER.finditer(text or "")]


# ─── Tín hiệu, quy tắc ───────────────────────────────────────────────────────
@dataclass
class Signal:
	key: str            # ổn định: "<rule>" hoặc "<rule>:<đối tượng>"
	rule: str
	section: str        # mảng chính (một mã trong SECTIONS, hoặc "he-thong")
	audience: str       # "lanh-dao" | "quan-tri"
	severity: str       # "do" | "vang"
	title: str          # lời quy tắc, có placeholder
	detail: str = ""    # (tuỳ chọn) một câu nói rõ thêm — thân thẻ khi không có lời AI
	paths: list = field(default_factory=list)       # mọi path quy tắc đã dùng (bộ chạy tự thêm path trong lời)
	documents: list = field(default_factory=list)   # [{"doctype", "name"}] ≤ 20 — chỉ trả cho quản trị
	route: str = ""
	tinh: dict = field(default_factory=dict)        # số quy tắc tự tính: {tên: giá trị} → {{@tên|kiểu}}


@dataclass
class RuleDef:
	key: str
	fn: object
	section: str
	sources: tuple
	audience: str = "lanh-dao"
	vang: float | None = None
	do: float | None = None
	unit: str = ""
	label: str = ""
	lower: bool = False     # True: càng THẤP càng xấu (vd tỷ lệ giao lần đầu)
	route: str = ""


RULES: dict = {}        # key → RuleDef (thứ tự đăng ký)
DETECTORS: dict = {}    # tên → hàm(ctx) → dict


class NotRunnable(Exception):
	"""Quy tắc tự báo không chạy được (thiếu số ngoài `sources`) — tín hiệu cũ giữ nguyên."""


def rule(key: str, *, section: str, sources, vang=None, do=None, unit: str = "", label: str = "",
		audience: str = "lanh-dao", lower: bool = False, route: str | None = None):
	"""Đăng ký quy tắc. `sources`: path các khối nguồn trong pack (vd "cong-no.receivables", "van-chuyen.overview.giao")
	— một khối thiếu / `_error` / `available: False` thì quy tắc không chạy. `vang` / `do`: ngưỡng mặc định (BC Settings
	.ai_rules ghi đè). `route` mặc định "#/<mảng>" (he-thong: không có)."""
	if section not in SECTIONS and section != HE_THONG:
		raise ValueError(f"bc.ai: mảng không tồn tại: {section}")
	if audience not in AUDIENCES:
		raise ValueError(f"bc.ai: audience không hợp lệ: {audience}")
	if isinstance(sources, str):
		sources = (sources,)

	def deco(fn):
		if key in RULES and RULES[key].fn.__module__ != fn.__module__:
			raise ValueError(f"bc.ai: trùng mã quy tắc {key}")
		RULES[key] = RuleDef(key=key, fn=fn, section=section, sources=tuple(sources), audience=audience, vang=vang,
			do=do, unit=unit, label=label or key, lower=lower,
			route=("" if section == HE_THONG else f"#/{section}") if route is None else route)
		return fn
	return deco


def detector(name: str):
	"""Đăng ký detector: hàm(ctx) → dict, ctx = {"now": datetime, "today": date}. Kết quả vào pack["he-thong"][name].
	SQL chỉ SELECT; mốc thời gian lấy từ ctx (không NOW() / CURDATE())."""
	def deco(fn):
		DETECTORS[name] = fn
		return fn
	return deco


class Cfg:
	"""Cấu hình đã phân giải của một quy tắc (mặc định + ghi đè từ BC Settings.ai_rules) + tiện ích dựng tín hiệu."""

	def __init__(self, rd: RuleDef, override: dict | None = None):
		o = override or {}
		self.rd = rd
		self.key, self.section, self.audience, self.route = rd.key, rd.section, rd.audience, rd.route
		self.unit, self.label, self.lower = rd.unit, rd.label, rd.lower
		self.disabled = bool(o.get("disabled"))
		self.vang = o.get("vang") if o.get("vang") else rd.vang     # 0 / trống = dùng mặc định
		self.do = o.get("do") if o.get("do") else rd.do

	def _vuot(self, value, nguong, bang: bool) -> bool:
		if nguong is None or value is None:
			return False
		if self.lower:
			return value <= nguong if bang else value < nguong
		return value >= nguong if bang else value > nguong

	def muc(self, value, bang: bool = False) -> str | None:
		"""Mức của `value` theo ngưỡng: 'do' | 'vang' | None. Mặc định so NGẶT (> ; lower: <); bang=True: ≥ (≤)."""
		if self._vuot(value, self.do, bang):
			return "do"
		if self._vuot(value, self.vang, bang):
			return "vang"
		return None

	def signal(self, severity: str, title: str, *, detail: str = "", paths=(), tinh: dict | None = None,
			obj: str | None = None, documents=(), route: str | None = None) -> Signal:
		"""Tín hiệu của quy tắc này. `obj`: đối tượng (→ key '<rule>:<obj>') khi một quy tắc sinh nhiều tín hiệu."""
		return Signal(key=self.key if obj in (None, "") else f"{self.key}:{obj}", rule=self.key, section=self.section,
			audience=self.audience, severity=severity, title=title, detail=detail, paths=list(paths),
			documents=list(documents)[:20], route=self.route if route is None else route, tinh=dict(tinh or {}))


def load() -> None:
	"""Import mọi module quy tắc / detector (đăng ký vào RULES / DETECTORS). Gọi lại nhiều lần được."""
	for m in _MODULES:
		importlib.import_module(m)


def overrides_from_settings() -> dict:
	"""{rule_key: {"disabled": bool, "vang": float|None, "do": float|None}} từ BC Settings.ai_rules (dòng sau thắng)."""
	from bc.api._common import get_settings
	out: dict = {}
	for r in (get_settings().get("ai_rules") or []):
		k = (r.get("rule_key") or "").strip()
		if k:
			out[k] = {"disabled": bool(frappe.utils.cint(r.get("disabled"))),
				"vang": frappe.utils.flt(r.get("threshold")) or None, "do": frappe.utils.flt(r.get("threshold_red")) or None}
	return out


def source_ok(pack, source: str) -> bool:
	"""Khối nguồn dùng được: có trong pack, không `_error`, không `available: False` — kể cả ở MỌI khối cha."""
	cur = pack
	try:
		for p in split_path(source):
			cur = cur[p]
			if isinstance(cur, dict) and (cur.get("_error") or cur.get("available") is False):
				return False
	except (KeyError, IndexError, TypeError):
		return False
	return cur is not None


def slug(key: str) -> str:
	return re.sub(r"[^A-Za-z0-9_]", "_", key)


def tinh_path(sig: Signal, name: str) -> str:
	"""Path của số quy tắc tự tính."""
	return f"{sig.section}._ai.{slug(sig.key)}.{name}"


_AT = re.compile(r"\{\{\s*@([A-Za-z0-9_]+)\s*\|")


def _expand(sig: Signal, text: str) -> str:
	return _AT.sub(lambda m: "{{" + tinh_path(sig, m.group(1)) + "|", text or "")


@dataclass
class RuleRun:
	signals: list = field(default_factory=list)
	ran: set = field(default_factory=set)            # quy tắc đã chạy (kể cả đang tắt) → tín hiệu không còn thì đóng
	not_run: dict = field(default_factory=dict)      # {rule: lý do} → tín hiệu cũ giữ nguyên
	disabled: set = field(default_factory=set)


def run_rules(pack: dict, overrides: dict | None = None, only=None) -> RuleRun:
	"""Chạy mọi quy tắc trên pack (pack được GHI THÊM các khối `_ai` chứa số quy tắc tự tính).

	Trả RuleRun. Tín hiệu trả về đã: đúng key / rule / mảng / audience, placeholder `@tên` đã mở thành path đầy đủ,
	`paths` gồm mọi path trong lời, mọi path phân giải được trên pack. Quy tắc ném lỗi / sinh tín hiệu sai (key lạ,
	path không có) → coi là không chạy được (ghi Error Log), không làm hỏng quy tắc khác."""
	load()
	overrides = overrides or {}
	out = RuleRun()
	for key, rd in RULES.items():
		if only is not None and key not in only:
			continue
		cfg = Cfg(rd, overrides.get(key))
		if cfg.disabled:
			out.disabled.add(key)
			out.ran.add(key)
			continue
		bad = next((s for s in rd.sources if not source_ok(pack, s)), None)
		if bad:
			out.not_run[key] = f"nguon:{bad}"
			continue
		try:
			sigs = list(rd.fn(pack, cfg) or [])
			done = [_finish(pack, rd, s) for s in sigs]
			if len({s.key for s in done}) != len(done):
				raise ValueError(f"trùng khoá tín hiệu trong {key}")
		except NotRunnable as e:
			out.not_run[key] = f"khong-chay:{e}"
			continue
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"bc.ai quy tắc {key}")
			out.not_run[key] = "loi"
			continue
		out.signals += done
		out.ran.add(key)
	return out


def _finish(pack: dict, rd: RuleDef, s: Signal) -> Signal:
	if not isinstance(s, Signal):
		raise TypeError(f"{rd.key}: quy tắc phải trả Signal")
	if s.key != rd.key and not s.key.startswith(rd.key + ":"):
		raise ValueError(f"{rd.key}: khoá tín hiệu lạ {s.key}")
	if s.severity not in SEVERITIES:
		raise ValueError(f"{rd.key}: mức không hợp lệ {s.severity}")
	s.rule, s.section, s.audience = rd.key, rd.section, rd.audience
	if s.tinh:
		if not isinstance(pack.get(s.section), dict):
			pack[s.section] = {}
		pack[s.section].setdefault("_ai", {})[slug(s.key)] = dict(s.tinh)
	s.title, s.detail = _expand(s, s.title), _expand(s, s.detail)
	paths = list(dict.fromkeys([*s.paths, *(p for p, _ in placeholders(s.title + " " + s.detail))]))
	for p, k in placeholders(s.title + " " + s.detail):
		if k not in KINDS:
			raise ValueError(f"{rd.key}: kiểu placeholder lạ {k}")
	for p in paths:
		resolve(pack, p)  # PathError → quy tắc không chạy được (lời sẽ không dựng được)
	s.paths = paths
	return s


def run_detectors(now) -> dict:
	"""{tên: kết quả} của mọi detector (lỗi → {"_error": True}, ghi Error Log) — đặt vào pack["he-thong"]."""
	load()
	ctx = {"now": now, "today": frappe.utils.getdate(now)}
	out = {}
	for name, fn in DETECTORS.items():
		try:
			res = fn(ctx)
			out[name] = res if isinstance(res, dict) else {"_error": True}
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"bc.ai detector {name}")
			frappe.clear_last_message()
			out[name] = {"_error": True}
	return out


# ─── KPI (ảnh chụp mỗi ngày vào BC AI Run.kpis — nền cho phát hiện lệch chuẩn / bản tin tuần ở P2) ─────────────
# Mỗi mục: (path, kiểu, nhãn). Chỉ path có thật trên payload (docs/ai-rules-audit.md); thiếu thì bỏ qua lúc chụp.
KPIS: list = []


def snapshot_kpis(pack: dict) -> dict:
	"""{path: giá trị số} của các KPI phân giải được (None / không phải số → bỏ)."""
	out = {}
	for path, _kind, _label in KPIS:
		v = resolve(pack, path, None)
		if isinstance(v, bool) or not isinstance(v, (int, float)):
			continue
		out[path] = v
	return out
