# -*- coding: utf-8 -*-
"""bc.ai.render — placeholder → số thật, định dạng kiểu VN, lint "số trần" (đặc tả §5.3). Hàm thuần, không DB.

Luật số: mô hình KHÔNG được viết số liệu — mọi số trong lời là `{{path|kiểu}}` trỏ vào gói số; ở đây thay bằng số
thật rồi mới lưu. Lời còn số trần → `ok = False` → nơi gọi bỏ lời AI, giữ lời quy tắc.

Kiểu và định dạng (fmt):
- tien : như fmtMoney của lib/format.js nhưng VIẾT ĐỦ đơn vị: |n| ≥ 1e9 → "1,6 tỷ" (1 số lẻ, bỏ ",0"); ≥ 1e8 →
         "250 triệu" (nguyên); ≥ 1e6 → "33 triệu" / "1,5 triệu" (1 số lẻ, bỏ ",0"); < 1e6 → "450.000 đ" (nhóm nghìn).
         Số âm giữ dấu "-". Làm tròn ĐÚNG như Math.round của JS (đúng giữa thì về +∞) để lời khớp màn gốc từng ký tự:
         1.050.000 → "1,1 triệu", 99.950.000 → "100 triệu", 999.999.999 → "1.000 triệu", −1.050.000.000 → "-1 tỷ".
- so   : nhóm nghìn kiểu VN ("12.345"); số không nguyên → 1 số lẻ, dấu phẩy ("12,5"; ",0" thì bỏ).
- pct  : giá trị ĐÃ nhân 100 → 1 số lẻ + "%" ("35,2%", "35,0%") — như fmtPct (làm tròn nửa ra xa 0).
- ngay : ngày ISO / date / datetime → "d/m/yyyy".
- chu  : chuỗi ≤ 120 ký tự (dài hơn → lỗi kiểu); khoảng trắng / xuống dòng gộp thành một dấu cách.
Giá trị không khớp kiểu (tien/so/pct cần int/float không phải bool — Decimal của MariaDB cũng nhận; ngay cần ngày;
chu cần str) → ValueError. NaN / vô cực / số quá lớn cũng là ValueError.

Lint (lời của MÔ HÌNH, sau khi đã bỏ placeholder và mã giả hợp lệ) — bắt:
- số có dấu nhóm nghìn / phần lẻ ("1.250.000", "1,5", "1 250 000") và dãy ≥ 3 chữ số ("1250");
- số đứng trước đơn vị: % ‰ đ ₫ đồng VND USD k tr triệu tỷ (tỉ) nghìn (ngàn) vạn trăm "phần trăm" — kể cả 1–2 chữ
  số, dính liền hay cách ("35%", "35 %", "2tỷ", "50k", "5 trăm triệu", "5 trăm khách"), viết không dấu ("2 ty dong",
  "35 phan tram", "4 trieu"), tiếng Anh ("35 percent", "per cent", "bps", "pct", "million", "bn", "35M", "2B"),
  "phần nghìn / phần mười", tiếng lóng "2 củ", cách bằng ngoặc (mở / đóng) / gạch / nháy / , : = · / "x" / thẻ hay thực
  thể HTML ("12 (tỷ)", "(12) tỷ", "12 x tỷ", "12: tỷ", "12-tỷ", "<b>12</b> tỷ", "12&nbsp;tỷ"); chữ số hệ khác trước đơn
  vị ("三十五%"); ký hiệu tiền đứng trước ("$50"); chữ trong NGOẶC NHỌN vẫn được soát ("<khoảng 350 triệu>" — E1);
- chữ số sau chữ thường / MỘT chữ cái ("đ350000000", "x1250", "A100"), "10^9", "4E3", dãy số rời ("1 2 5 0");
- số viết bằng CHỮ / ước lượng quanh đơn vị lớn ("hai tỷ", "vài trăm triệu", "ba trăm", "mười phần trăm", "tỷ rưỡi",
  "tỷ hai", "tiền tỷ", "gần tỷ", "hơn trăm khách", "khoản đầu tư tỷ đồng"), "gấp đôi / gấp 3", "một nửa", "nửa số
  khách", "một phần ba", "hàng chục", từ chỉ số trước % ("ba lăm %");
- phân số / tỷ số: "45/60", "chiếm 2/3", "đạt 3/5", "giảm 1/3", "1/3 số khách", "½";
- mã giả lạ (KH#… / NCC#… không có trong bảng của lượt chạy — mô hình bịa) và mã giả chép hỏng ("KH #0001", "KH0001");
- (render_insight, trên lời còn placeholder — xem _so_tran) số GHÉP quanh placeholder số (tien / so / pct, và chu mà
  giá trị trông như số): "1{{a|so}}", "{{a|so}}.000", "1 {{a|tien}}", "{{a|so}}{{b|so}}", "{{a|so}} {{b|tien}}"; mọi
  đơn vị / "lần" / chữ dính sau ("{{a|so}}%", "{{a|so}} đ", "{{a|so}} triệu", "{{a|so}}M"); dấu / phép toán trước
  ("-{{a|tien}}", "±{{a|so}}"; "-" dính chữ trước pct: "nợ-{{a|pct}}"); từ chỉ số sát bên ("mười {{a|so}}", "{{a|so}}
  rưỡi" — E3); nửa phân số viết tay ("1/{{a|so}}", "{{a|so}}/10", "3:{{a|so}}", "{{a|so}}-5") — sau khi bỏ ký tự vô
  hình. Placeholder chu ra chuỗi rỗng → "chu-rong:<p>"; chu chỉ là dấu ("–") được soát như chính dấu đó.
- (render_insight với kinds) kiểu số sai kiểu thật của giá trị ("{{số khách|pct}}", "{{tiền|so}}") → "kieu:<p>"; khoá
  không xếp được kiểu thì pct cũng bị loại (E2).
- (render_insight) tiêu đề dài quá 200 ký tự sau khi thay số → "dai" (lời quy tắc thì cắt, không cắt giữa số).
Giữ: năm 20xx; ngày d/m, d/m/yyyy, m/yyyy, năm/năm; mã có ≥ 2 chữ HOA đứng liền trước ("SR900") hoặc nối vào mã viết
hoa ("KK-2026-002", "PNTP-X120"); số ≤ 2 chữ số không kèm đơn vị ("trong 7 ngày", "quý 3", "top 5", "5:30", "12 khách"); "3 tỷ lệ …"
(tỷ lệ / tỷ trọng / tỷ giá / tỉ mỉ / triệu tập / triệu hồi không phải đơn vị); tên riêng viết hoa ("đến Triệu Sơn",
"hàng Vạn Phúc" — đơn vị không có chữ số đứng trước chỉ nhận khi viết thường). Chữ số toàn chiều rộng, dấu tổ hợp,
ký tự vô hình được chuẩn hoá (NFKC) trước khi soát; dấu nhấn markdown * _ ` ~ bị bỏ. Không phân biệt được thì nghiêng
về GIỮ đúng ngoại lệ của đặc tả ("24/7", "2/3" trơ trọi). Số ≤ 2 chữ số không kèm đơn vị luôn lọt (đặc tả cho phép)
— kể cả khi là số liệu ("DSO 62 ngày", "tăng 5 lần"): phần này do đề bài (bc.ai.prompt) răn, lint không phân biệt được.
Tên riêng có chữ số ("Bánh quy 300g", "ISO 22000") viết thẳng trong lời sẽ bị bắt — mô hình phải trích qua
`{{path|chu}}` (hoặc mã giả với khách / NCC).
"""

from __future__ import annotations

import datetime
import html
import math
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from bc.ai import registry

SO_KIEU = ("tien", "so", "pct")     # kiểu cần giá trị số
TITLE_MAX = 200                     # BC AI Insight.title là Data (200)
CHU_MAX = 120
ADVICE_MAX = 3


@dataclass
class Filled:
	text: str = ""                                   # lời đã thay số (placeholder lỗi để nguyên)
	paths: list = field(default_factory=list)        # path đã dùng, theo thứ tự, không trùng
	sections_used: list = field(default_factory=list)  # khoá cấp 1 của các path, theo thứ tự, không trùng
	errors: list = field(default_factory=list)       # "path:<p>" | "kieu:<p>" | "ngoai-nhom:<p>" | "cu-phap"


# ─── Định dạng ───────────────────────────────────────────────────────────────
def _tron_js(x: float) -> int:
	"""Math.round của JS: số nguyên gần nhất, đúng giữa thì về phía +∞ (10,5 → 11; −10,5 → −10)."""
	f = math.floor(x)
	return f + 1 if x - f >= 0.5 else f


def _nhom(n: int) -> str:
	"""Nhóm nghìn kiểu VN: 1234567 → "1.234.567"."""
	return f"{n:,}".replace(",", ".")


def _mot_le_js(v: float) -> str:
	"""`one()` của fmtMoney: 1 số lẻ, bỏ ",0", KHÔNG nhóm nghìn (như Number.toString)."""
	k = _tron_js(v * 10)
	q, r = divmod(abs(k), 10)
	return ("-" if k < 0 else "") + str(q) + (f",{r}" if r else "")


def _tien(n) -> str:
	a = abs(n)
	if a >= 1e9:
		return _mot_le_js(n / 1e9) + " tỷ"
	if a >= 1e8:
		return _nhom(_tron_js(n / 1e6)) + " triệu"
	if a >= 1e6:
		return _mot_le_js(n / 1e6) + " triệu"
	return _nhom(_tron_js(n)) + " đ"


def _mot_le(v, luon: bool) -> str:
	"""1 số lẻ + nhóm nghìn như Intl.NumberFormat('vi-VN'): làm tròn nửa ra xa 0 trên dạng thập phân ngắn nhất của số
	(0,15 → "0,2"). luon = False: bỏ ",0". Không bao giờ ra "-0"."""
	d = Decimal(repr(v)) if isinstance(v, float) else Decimal(v)
	k = int(d.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) * 10)     # quá 28 chữ số → InvalidOperation
	q, r = divmod(abs(k), 10)
	return ("-" if k < 0 else "") + _nhom(q) + (f",{r}" if (r or luon) else "")


_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[ T].*)?", re.S)


def _ngay(v) -> str:
	if isinstance(v, datetime.datetime):
		d = v.date()
	elif isinstance(v, datetime.date):
		d = v
	elif isinstance(v, str) and _ISO.fullmatch(v.strip()):
		d = datetime.date.fromisoformat(v.strip()[:10])     # ngày không có thật → ValueError
	else:
		raise ValueError("không phải ngày")
	return f"{d.day}/{d.month}/{d.year}"


def fmt(value, kind: str) -> str:
	"""Định dạng `value` theo `kind` (xem docstring module). Sai kiểu → ValueError."""
	if kind in SO_KIEU:
		if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
			raise ValueError(f"{kind}: cần số")
		huu_han = value.is_finite() if isinstance(value, Decimal) else isinstance(value, int) or math.isfinite(value)
		if not huu_han:
			raise ValueError(f"{kind}: số không hữu hạn")
		try:
			if kind == "tien":      # Decimal (SUM của MariaDB chưa qua flt) → float như Number của JS
				return _tien(float(value) if isinstance(value, Decimal) else value)
			return _mot_le(value, False) if kind == "so" else _mot_le(value, True) + "%"
		except (OverflowError, InvalidOperation) as e:
			raise ValueError(f"{kind}: số quá lớn") from e
	if kind == "ngay":
		return _ngay(value)
	if kind == "chu":
		if not isinstance(value, str) or len(value) > CHU_MAX:
			raise ValueError("chu: cần chuỗi ≤ 120 ký tự")
		return " ".join(value.split())
	raise ValueError(f"kiểu placeholder không hợp lệ: {kind}")


# ─── Thay placeholder ────────────────────────────────────────────────────────
def _them(ds: list, *items) -> None:
	for x in items:
		if x not in ds:
			ds.append(x)


def fill(text: str, pack: dict, sections=None, kinds=None) -> Filled:
	"""Thay mọi `{{path|kiểu}}` trong `text` bằng giá trị đã định dạng lấy từ `pack` (bc.ai.registry.resolve).

	`sections`: tập khoá cấp 1 được phép (None = mọi mảng) — path ngoài tập → lỗi "ngoai-nhom:<p>".
	`kinds`: {path đã bỏ chỉ số: kiểu} (registry.kind_map) — có thì kiểu số (tien / so / pct) phải đúng kiểu thật của
	giá trị (kieu_cua): path có trong kinds → đúng kiểu đó; không có → theo đơn vị của dòng ("don_vi") rồi theo tên khoá
	(kieu_theo_ten); không xếp được thì tien / so đều nhận, pct bị loại (tỷ lệ chỉ nhận trên khoá trông như tỷ lệ — E2).
	Sai → "kieu:<p>". None = không xét (lời quy tắc).
	Path không có → "path:<p>"; kiểu lạ / không khớp giá trị → "kieu:<p>"; còn "{{" hoặc "}}" sau khi thay (placeholder
	viết hỏng) → "cu-phap" (soát trên LỜI GỐC đã bỏ placeholder hợp lệ, nên giá trị có ngoặc nhọn không bị bắt nhầm;
	ngoặc nhọn đơn "{path|tien}" cũng là placeholder hỏng)."""
	text = "" if text is None else str(text)
	out = Filled()
	duoc = None if sections is None else {sections} if isinstance(sections, str) else set(sections)

	def thay(m):
		path, kind = m.group(1).strip(), m.group(2)
		if duoc is not None and registry.section_of(path) not in duoc:
			_them(out.errors, f"ngoai-nhom:{path}")
			return m.group(0)
		try:
			value = registry.resolve(pack, path)
		except registry.PathError:
			_them(out.errors, f"path:{path}")
			return m.group(0)
		try:
			s = fmt(value, kind)
		except ValueError:
			_them(out.errors, f"kieu:{path}")
			return m.group(0)
		if kinds is not None and kind in SO_KIEU:
			can = kieu_cua(pack, path, kinds)
			if can != kind and (can is not None or kind == "pct"):     # không xếp được: chỉ cấm pct (E2)
				_them(out.errors, f"kieu:{path}")
				return m.group(0)
		_them(out.paths, path)
		_them(out.sections_used, registry.section_of(path))
		return s

	out.text = registry.PLACEHOLDER.sub(thay, text)
	con = strip_placeholders(text)
	if "{" in con or "}" in con:
		_them(out.errors, "cu-phap")
	return out


# ─── Kiểu số theo tên khoá (D8, E2) ──────────────────────────────────────────
# Dựng từ MỌI lá số của gói số thật (seed gộp seed_ui2 VÀ seed sổ kho seed_ui_kho, collect.build + detector + _ai của
# quy tắc): xếp theo tên lá (lá cha khi lá là tên chung: "growth.sales" là %, "buckets.b1" là tiền; "cuoc.tong" là
# tiền; "dem.*", "by_status.*" là số đếm). Lá không xếp được → tien / so đều nhận, pct thì không (danh sách lá cố ý để
# trống trong test_ai_render). Thứ tự xét: riêng → tỷ lệ theo lá cha → tên lá (đếm / thời hạn / số lượng → tỷ lệ →
# tiền; đếm trước để "overdue_customers", "stranded_value_rows", "qty_no_rate" không bị coi là tiền / tỷ lệ) → lá cha.
_PCT_CHA = ("growth", "ty_le", "ty_trong", "tang_truong")             # "summary.meta.growth.sales" là %
_SO_DUNG = {"count", "n", "so", "over_limit", "qua_n", "dso", "produced", "stock", "plan", "outgoing",
	# vận chuyển, nhân sự: số đơn / chuyến / xe / người (E2)
	"cho", "da", "dang", "da_giao", "hoan", "khach_hen", "da_xep", "chua_xep", "mot_phan", "sua_tay", "tra_bat_thuong",
	"tra_chuyen_huy", "qua_tai", "thieu_cap", "trong_ky", "dang_mo", "dang_dung", "don_da_giao", "don_moi_chuyen",
	"hang_chua_ve", "con_km", "dong", "dang_lam", "tam_nghi", "da_nghi", "active_da_nghi", "vao", "nghi", "chua_muc",
	"loi_ky", "khoan_thieu_phieu",
	# số lượng hàng / lô / phiếu, số ngày, kỳ, năm, tháng (không phải tiền)
	"lech", "chenh", "ngoai_phieu", "nhap_lai", "carton_factor", "chua_dem", "lau", "cu", "im_lang", "uoc_tinh_qua_han",
	"kho_ban_duoc", "lo_ttl_giay", "pending_reposts", "unknown_term", "due_ahead", "limit", "k", "nam", "year", "month",
	"fy_month", "tet_year", "canh_bao", "nguy", "lan", "max_lan", "het_credit", "that_bai", "con_trong_gb",
	"failed_reposts", "pos_unconsolidated"}
_SO_DAU = {"so", "n", "count", "qty", "items", "rows", "lots", "slips", "entries", "warehouses", "days", "ngay",
	"boxes", "cartons"}
_SO_CUOI = {"count", "items", "rows", "lots", "customers", "days", "ngay", "qty", "slips", "entries", "orders",
	"warehouses", "cartons", "boxes", "tuoi"}
_SO_RX = re.compile(r"qua_\d+|mo_qua_\w+|\w+_tong")                 # "ds_tong", "lo_can_date_tong": số dòng
_PCT_CUOI = {"pct", "percent"}                                        # "*_rate" (return_rate) cũng là %, "rate" thì không
_TIEN_DUNG = {"value", "amount", "sales", "net", "returns", "overdue", "receivable", "total", "gia_tri", "tien",
	"debt", "revenue", "cash", "bank", "balance", "unallocated", "advances", "outstanding", "cogs", "opening",
	"closing", "gt", "thuc_nhan", "chua_tra", "da_tra", "moi_chuyen", "moi_diem", "mat_duong", "einv_pending",
	"pending_review", "unknown", "rate", "ledger_bin_diff"}                              # "rate" = đơn giá sổ (đồng), không phải tỷ lệ
_TIEN_DAU = {"value", "gt", "amount", "dt"}
_TIEN_CUOI = {"value", "amount", "total", "tien", "sales", "revenue", "debt"}
_BUCKET = {"current", "over", "unknown", "b1", "b2", "b3"}             # cột tuổi nợ (buckets.*) là tiền
_CHA_TIEN = {"flows", "points"}                                       # ton-kho.trend: dòng nhập xuất / điểm giá trị
# Lá cha (hoặc ông) là bảng đếm: "dem.xanh", "xe.dem.dang_kiem.ok", "by_status.Nháp", "nhan_su.loai.Khoán",
# "theo_dvt.am" (số lượng theo đơn vị tính), "entries_by_purpose.Repack" …
_CHA_SO = {"dem", "by_status", "by_type", "loai", "entries_by_purpose", "stages", "nguon_gia", "lo", "theo_dvt",
	"tp_set_mismatch", "lan_dau", "xep", "nhan_su", "by_dept", "bien_dong", "dang_kiem", "thay_dau", "thang", "giay_to"}
_CHA_LA = {("cuoc", "tong"): "tien", ("chi_phi_nam", "tong"): "tien"}  # "tong" trơ trọi: tiền hay số tuỳ khối
_RIENG = {"van-chuyen.overview.giao.total": "so",                     # tổng số đơn giao (không phải tiền)
	"van-chuyen.overview.chuyen.tai_tb": "pct"}                       # tải trung bình: m³ chở / sức chứa (%)


def _loai(k: str):
	k = str(k).lower()
	t = k.split("_")
	if k in _SO_DUNG or t[0] in _SO_DAU or t[-1] in _SO_CUOI or _SO_RX.fullmatch(k):
		return "so"
	if k.startswith(("ty_le", "ty_trong", "tang_truong", "growth", "percent")) or t[-1] in _PCT_CUOI \
			or (t[-1] == "rate" and len(t) > 1):
		return "pct"
	if k in _TIEN_DUNG or t[0] in _TIEN_DAU or t[-1] in _TIEN_CUOI or k.startswith(("gia_tri", "boi_thuong")):
		return "tien"
	return None


def kieu_theo_ten(path: str):
	"""Kiểu số ("tien" | "so" | "pct") mà path PHẢI dùng, đoán theo tên khoá; None = không đoán."""
	p = registry.strip_index(path)
	keys = p.split(".")
	rieng = _RIENG.get(p.replace(".overview_truoc.", ".overview.", 1))
	if rieng:
		return rieng
	la = keys[-1]
	cha = keys[-2].lower() if len(keys) > 2 else ""
	ong = keys[-3].lower() if len(keys) > 3 else ""
	if cha.startswith(_PCT_CHA):
		return "pct"
	if cha == "buckets" and la.lower() in _BUCKET:
		return "tien"
	if (cha, la.lower()) in _CHA_LA:
		return _CHA_LA[(cha, la.lower())]
	k = _loai(la)
	if k is None and cha in _CHA_TIEN:
		k = "tien"
	if k is None and (cha in _CHA_SO or ong in _CHA_SO):
		k = "so"
	if k is None and keys[0] == "he-thong":           # mảng hệ thống chỉ có số đếm / giờ / GB (và dia_day.pct)
		k = "so"
	return k


def _kieu_dong(pack, path: str):
	"""Dòng (phần tử danh sách gần nhất chứa path) có "don_vi" dạng chữ → "pct" khi "%", không thì "so" (bảng chỉ số
	ATTP: cùng khoá "thang.<tháng>" / "ky" / "nam" mà đơn vị theo dòng). Không có → None."""
	i = path.rfind("]")
	if i < 0 or i == len(path) - 1 or pack is None:
		return None
	dong = registry.resolve(pack, path[:i + 1], None)
	dv = dong.get("don_vi") if isinstance(dong, dict) else None
	if not isinstance(dv, str) or not dv.strip():
		return None
	return "pct" if dv.strip() == "%" else "so"


def kieu_cua(pack, path: str, kinds=None):
	"""Kiểu số path PHẢI dùng trong lời mô hình: kinds (registry.kind_map) → đơn vị của dòng → tên khoá; None = không
	xếp được (render nhận tien / so, loại pct)."""
	k = (kinds or {}).get(registry.strip_index(path))
	if k in SO_KIEU:
		return k
	return _kieu_dong(pack, path) or kieu_theo_ten(path)


def strip_placeholders(text: str) -> str:
	"""Lời đã BỎ mọi placeholder hợp lệ (thay bằng một dấu cách) — đầu vào của lint."""
	return registry.PLACEHOLDER.sub(" ", "" if text is None else str(text))


# ─── Lint "số trần" ──────────────────────────────────────────────────────────
_HET = r"(?![^\W\d_])"       # hết từ: không dính CHỮ CÁI phía sau (chữ số thì được: "2tr5")
# "3 tỷ lệ …", "tỷ trọng", "tỷ giá" (nhưng "2 tỷ giá trị" vẫn là tiền), "tỉ mỉ", "triệu chứng", "triệu hồi": không
# phải đơn vị
_TY = rf"(?:tỷ|tỉ)(?!\s+(?:lệ|trọng|suất|mỉ|giá(?!\s+trị)){_HET})"
_TRIEU = rf"triệu(?!\s+(?:chứng|tập|hồi){_HET})"
_TIEN_TE = r"(?:đồng|vnđ|vnd|usd|đ)"
# Viết không dấu / tiếng Anh — chỉ xét khi đứng SAU chữ số ("2 ty", "35 phan tram", "4M"; "công ty", "Ba Ti" không).
_TY_KD = rf"(?:ty|ti)(?!\s+(?:le|trong|suat|gia(?!\s+tri)){_HET})"
_TRIEU_KD = rf"trieu(?!\s+(?:chung|tap|hoi){_HET})"
# "đồng thời", "đồng bộ" … không phải tiền
_DONG = r"đồng(?!\s+(?:thời|bộ|ý|loạt|đều|nghĩa|hành|phục|nghiệp|tình|lòng|minh|tâm|thuận)(?!\w))"
_TIEN_TE_KD = rf"(?:{_DONG}|vnđ|vnd|usd|đ|dong)"
# Giữa số và đơn vị: khoảng trắng, ngoặc (mở / đóng), gạch, nháy, , : = · và "x" đứng riêng ("12 (tỷ)", "(12) tỷ",
# "12-tỷ", "12: tỷ", "12 x tỷ").
_GIUA = r"(?:[\s()\[\]\-–—\"'“”‘’«»,:=·]|x(?![^\W\d_]))*"
# Đơn vị đứng SAU số (so từ ngay sau số; chữ phải hết từ: "5 khách", "7 trường hợp", "5 đơn" không dính).
_DON_VI = re.compile(
	_GIUA + r"(?:[%‰٪₫$€]"
	rf"|(?:điểm\s+)?(?:phần|phan)\s+(?:trăm|tram){_HET}"
	r"|điểm\s*%"
	rf"|(?:(?:trăm|chục|tram|chuc)\s+)?(?:{_TY}|{_TRIEU}|{_TY_KD}|{_TRIEU_KD}|nghìn|ngàn|nghin|ngan|vạn|tr|k"
	rf"|mio|bn|million|billion)(?:\s*{_TIEN_TE_KD})?{_HET}"
	rf"|(?:trăm|tram){_HET}"                    # "5 trăm khách" (chục thì như số < 100: giữ)
	rf"|(?:percent|pct|per\s*cent|bps){_HET}"
	rf"|(?:phần|phan)\s+(?:nghìn|ngàn|nghin|ngan|mười|muoi){_HET}"     # "5 phần nghìn", "3 phần mười"
	rf"|củ{_HET}"                                # tiếng lóng: "2 củ" (= 2 triệu)
	r"|(?-i:[MBK])(?![^\W\d_])"                  # "4M", "2B", "50K" (viết hoa; "5 m" không)
	rf"|{_TIEN_TE_KD}{_HET})", re.I)
# Số: "1 250 000" (nhóm nghìn bằng dấu cách) hoặc dãy chữ số có thể kèm . , giữa các chữ số.
_SO = re.compile(r"\d{1,3}(?: \d{3})+(?!\d)(?:[.,]\d+)*|\d+(?:[.,]\d+)*")
_NAM = re.compile(r"20\d\d")
_NGAY_THANG = re.compile(r"(?<![\w/])(?<!\d[.,])(\d{1,2})/(\d{1,2})(?:/(\d{4}|\d{2}))?(?![\w/])(?![.,]\d)")
_THANG_NAM = re.compile(r"(?<![\w/])(?<!\d[.,])(\d{1,2})/(20\d\d)(?![\w/])(?![.,]\d)")
# Nhóm chữ số có trần (không thì "1.2.1.2…" dài chạy bậc hai — E4).
_PHAN_SO = re.compile(r"(?<![\w/])\d{1,15}(?:[.,]\d{1,15}){0,6}\s*/\s*\d{1,15}(?:[.,]\d{1,15}){0,6}")
# "chiếm 2/3", "đạt 3/5", "giảm 1/3", "còn 1/4", "1/3 số khách", "2/3 tổng nợ" là PHÂN SỐ dù trùng dạng ngày; có chữ
# chỉ ngày đứng trước ("ngày 2/3 số đơn tăng") thì vẫn là ngày.
_GOI_PHAN_SO = re.compile(r"(?:chiếm|đạt|được|bằng|giảm|tăng|mất|thêm|thiếu|vượt|còn)\s+"
	r"(?:(?:khoảng|gần|hơn)\s+)?$", re.I)
_SAU_PHAN_SO = re.compile(rf"\s+(?:số(?!\s+liệu)|tổng(?!\s+(?:hợp|kết))){_HET}", re.I)
_GOI_NGAY = re.compile(r"(?:ngày|hôm|hạn|đến|tới|từ|trước|sau|vào|mùng|mồng|sáng|chiều|tối|qua|lúc)\s+$", re.I)
_NAM_NAM = re.compile(r"20\d\d\s*/\s*(?:20)?\d\d")          # năm tài chính 2026/2027, 2026/27
_LAP = "\x00"                 # lấp chỗ đã soát xong: không là chữ, số hay khoảng trắng
_CUA = 40                     # số ký tự nhìn lại phía trước một con số (chữ gợi ý, ký hiệu tiền, phần đầu của mã)
_PHAN_SO_KY_TU = re.compile("[\u00bc-\u00be\u2150-\u215f\u2189]")                          # ½ ¼ ¾ ⅓ …
# Mã giả còn sót = mô hình bịa hoặc chép hỏng: "KH#0099", "KH #0001", "KH0001" (mất dấu #).
_MA_GIA = re.compile(r"(?:KH|NCC)\s?#\s?\d+|(?<![\w#])(?:KH|NCC)\d{3,}(?!\w)", re.I)
_DAU_MA = re.compile(r"[A-ZĐ][A-Z0-9Đ]*(?:[-/][A-Z0-9Đ]+)*[-/]")
_TIEN_TRUOC = re.compile(r"(?:[$€£¥₫]|(?<!\w)(?:vnd|vnđ|usd))\s?$", re.I)
_CHU_SO = (r"(?:một|hai|ba|bốn|(?<!đầu )tư|năm|lăm|sáu|bảy|bẩy|tám|chín|mười|mươi|mốt|chục|trăm|nghìn|ngàn|vài|mấy"
	r"|dăm|nửa|rưỡi|hàng|nhiều|cả)")        # "đầu tư tỷ …": "tư" không phải số
# Đơn vị lớn KHÔNG có chữ số đứng trước chỉ nhận khi viết THƯỜNG: "Triệu Sơn", "Bà Triệu", "Vạn Phúc" là tên riêng.
_LON = rf"(?-i:{_TY}|{_TRIEU}|nghìn|ngàn)"
# Số viết bằng chữ / ước lượng — cũng là "tự viết số liệu".
_BANG_CHU = (
	re.compile(r"(?<!\w)gấp\s+(?:(?:hơn|gần|khoảng|tới|đến)\s+)?"
		r"(?:\d+(?:[.,]\d+)?|đôi|rưỡi|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười)(?!\w)", re.I),
	re.compile(r"×\s?\d+(?:[.,]\d+)?"),
	# tối đa 8 từ số trước đơn vị ("hai trăm ba mươi lăm nghìn tỷ" là 6) — không chặn thì lời dài toàn chữ số chạy bậc hai
	re.compile(rf"(?<!\w)(?:{_CHU_SO}\s+){{1,8}}(?:{_LON}|(?-i:vạn|trăm)|phần\s+trăm)(?!\w)", re.I),
	re.compile(rf"(?<!\w)(?:{_CHU_SO}\s+){{0,7}}{_CHU_SO}\s*[%‰]", re.I),                  # "ba lăm %"
	re.compile(rf"(?<!\w){_LON}\s+(?:rưỡi|mốt|hai|ba|tư|bốn|lăm|sáu|bảy|tám|chín)(?!\w)", re.I),   # "tỷ rưỡi", "tỷ hai"
	re.compile(rf"(?<!\w)(?:tiền|bạc)\s+(?-i:{_TY}|{_TRIEU})(?!\w)", re.I),            # "tiền tỷ", "bạc triệu"
	re.compile(r"(?<!\w)hàng\s+(?-i:chục|vạn)(?!\w)", re.I),
	re.compile(r"(?<!\w)(?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín)\s+phần\s+(?:hai|ba|tư|bốn|mười)(?!\w)", re.I),
	# "một nửa", "nửa số khách" là tỷ phần; "nửa đầu tháng", "nửa năm" là thời gian (giữ)
	re.compile(r"(?<!\w)(?:(?:một|phân|quá|hơn|gần)\s+)?nửa"
		r"(?!\s+(?:đầu|cuối|sau|trước|năm|tháng|tuần|ngày|quý|kỳ|giờ|buổi|đêm|mùa|chừng|vời))(?!\w)", re.I),
	re.compile(r"(?<!\w)(?:hơn|gần|trên|dưới|ngót|khoảng|cỡ|tầm|chừng|tới|đến|quá|vượt)\s+"     # "gần tỷ", "hơn trăm"
		rf"(?:{_LON}|(?-i:vạn|trăm))(?!\w)", re.I),
	re.compile(rf"(?<!\w){_LON}\s+{_TIEN_TE}(?!\w)", re.I),                            # "khoản đầu tư tỷ đồng"
)


# Thẻ HTML TRƠN (chỉ tên thẻ, không thuộc tính): "<b>", "</b>", "<br/>". Nội dung trong ngoặc nhọn KHÔNG bao giờ bị
# bỏ (E1): "<khoảng 350 triệu>", "<b 1.250.000 đ>" vẫn được soát.
_THE_TRON = re.compile(r"<\s*/?\s*[A-Za-z][A-Za-z0-9]*\s*/?\s*>")


def _chuan(text: str, bo_the: bool = True) -> str:
	"""Giải thực thể HTML ("&nbsp;", "&#37;", "&lt;") + NFKC (chữ số / % toàn chiều rộng, dấu cách đặc biệt, dấu tổ
	hợp → dạng thường) + bỏ ký tự vô hình (Cf) và dấu nhấn markdown * _ ` ~ (để "**2** tỷ", "__35__%" vẫn là "2 tỷ",
	"35%") + bo_the: bỏ thẻ HTML trơn ("<b>12</b> tỷ" → "12 tỷ"); rồi mọi "<" ">" còn lại thành dấu cách (nội dung
	trong ngoặc vẫn được soát). Nơi gọi soát CẢ HAI dạng (bo_the True / False) khi lời có ngoặc nhọn: "Nợ 12 <tr>"."""
	s = unicodedata.normalize("NFKC", html.unescape(text))
	s = "".join(ch for ch in s if unicodedata.category(ch) != "Cf" and ch not in "*_`~")
	if bo_the:
		s = _THE_TRON.sub("", s)
	return s.replace("<", " ").replace(">", " ")


def _cac_dang(text: str) -> list:
	"""Các dạng chuẩn hoá để soát: một dạng; thêm dạng giữ tên thẻ khi lời có ngoặc nhọn (E1)."""
	a = _chuan(text)
	b = _chuan(text, bo_the=False)
	return [a] if a == b else [a, b]


def _la_ngay(s: str, m) -> bool:
	"""Khớp d/m[/y] này là NGÀY (được giữ) hay phân số / tỷ số (bị bắt)."""
	d, th, y = m.groups()
	if not (1 <= int(d) <= 31 and 1 <= int(th) <= 12 and (y is None or len(y) == 2 or y.startswith("20"))):
		return False
	if y is not None:
		return True
	truoc = s[max(0, m.start() - _CUA):m.start()]
	if _GOI_PHAN_SO.search(truoc) or _DON_VI.match(s, m.end()):      # "chiếm 2/3", "2/3 tỷ đồng"
		return False
	return not _SAU_PHAN_SO.match(s, m.end()) or bool(_GOI_NGAY.search(truoc))


_MA_HOA = re.compile(r"[A-ZĐ][A-Z0-9Đ]*(?:[-/][A-Z0-9Đ]+)*")


def _la_ma(s: str, a: int) -> bool:
	"""Chữ số tại s[a:] thuộc một MÃ:
	- dính liền ≥ 2 chữ HOA đứng trước ("SR900", "KK2026002"), hoặc chữ HOA là đuôi của mã nối - / viết hoa
	  ("PNTP-X120", "SE-NL-X8");
	- nối bằng - / vào một mã viết HOA bắt đầu bằng chữ ("KK-2026-002", "ACC-SINV-2026-00012", "HGC/2026/001").
	Chữ thường / một chữ cái đứng trước ("đ350000000", "x1250", "A100") KHÔNG phải mã; "giảm-150", "100-200" cũng
	không. (Gạch dưới đã bị _chuan bỏ nên "KK_2026_002" thành dính liền chữ.)"""
	if a == 0:
		return False
	dau = max(0, a - _CUA)
	if s[a - 1].isalpha():
		j = a
		while j > dau and s[j - 1].isalpha():
			j -= 1
		chu = s[j:a]
		if not _MA_HOA.fullmatch(chu):
			return False
		if len(chu) >= 2:
			return True
		if j == 0 or s[j - 1] not in "-/":
			return False
		a = j          # một chữ HOA sau - / : xét phần mã phía trước như dưới
	if s[a - 1] not in "-/":
		return False
	j = a
	while j > dau and (s[j - 1].isalnum() or s[j - 1] in "-/"):
		j -= 1
	if j > 0 and (s[j - 1].isalnum() or s[j - 1] in "-/"):       # dài quá _CUA ký tự: không phải mã
		return False
	return bool(_DAU_MA.fullmatch(s[j:a]))


# Dãy số rời cách nhau bằng dấu cách / tab ("1 2 5 0", "3 5 khách") — đọc như một số.
_SO_ROI = re.compile(r"(?<![\w.,])\d{1,3}(?:[ \t]+\d{1,3})+(?![\w.,])")
# Chỉ bắt đầu ở ĐẦU một dãy chữ số (không thì dãy dài chạy bậc hai — E4).
_LUY_THUA = re.compile(r"(?<!\d)\d+\s*\^\s*\d+|(?<![\w])\d+[eE][+-]?\d+(?![^\W\d_])")        # "10^9", "4E3"


def _chu_so_khac(ch: str) -> bool:
	"""Ký tự là chữ số của hệ chữ khác (三, 五, Ⅻ đã NFKC thì thành chữ La-tinh): có giá trị số, không phải 0-9."""
	return not ch.isascii() and not ch.isdigit() and unicodedata.numeric(ch, None) is not None


def lint(text: str) -> list:
	"""Các mẩu "số trần" trong lời đã bỏ placeholder (rỗng = sạch). Bắt (đặc tả §5.3 bước 3):
	- dãy ≥ 3 chữ số không thuộc một mã (kể cả có dấu nhóm nghìn: "1.250.000", "1,250"; chữ thường / một chữ cái đứng
	  trước không làm thành mã: "đ350000000", "x1250"); dãy số rời cách dấu cách ("1 2 5 0"); "10^9", "4E3";
	- số (kể cả 1–2 chữ số, có thể có phần lẻ) đứng trước đơn vị: %, đ, ₫, k, tr, triệu, tỷ, nghìn, viết không dấu
	  ("ty", "trieu", "phan tram", "dong"), tiếng Anh ("percent", "pct", "million", "bn", "4M", "2B"), kể cả cách bằng
	  ngoặc / gạch / thẻ HTML ("12 (tỷ)", "12-tỷ", "<b>12</b> tỷ"); chữ số hệ khác trước đơn vị ("三十五%").
	Ngoại lệ được giữ: năm 20xx; ngày d/m hoặc d/m/yyyy; mã viết HOA ("SR900", "KK-2026-002"); số chỉ thời hạn ≤ 2 chữ
	số không kèm đơn vị trên ("trong 7 ngày", "30 ngày", "quý 4").
	Bắt thêm (xem docstring module): số có phần lẻ, số viết bằng chữ trước đơn vị lớn, "gấp đôi", phân số, mã giả lạ."""
	tho = "" if text is None else str(text)
	out: list = []
	for mau in [m.group(0) for m in _PHAN_SO_KY_TU.finditer(tho)]:
		_them(out, mau)
	for s in _cac_dang(_PHAN_SO_KY_TU.sub(" ", tho)):       # có ngoặc nhọn: soát cả hai dạng (E1)
		_them(out, *_lint_mot(s))
	return out


def _lint_mot(s: str) -> list:
	"""lint trên MỘT dạng đã chuẩn hoá (_chuan)."""
	bat: list = []
	buf = list(s)

	def xoa(a: int, b: int, mau: str | None = None) -> None:
		"""Xoá s[a:b] (để lượt soát sau không bắt lại); có `mau` → ghi nhận là số trần. Chỗ đã xoá lấp bằng ký tự
		KHÔNG phải khoảng trắng để mẫu sau không bắc cầu qua ("khoảng 2/3 tỷ" không thành "khoảng tỷ")."""
		if mau is not None:
			bat.append((a, " ".join(mau.split())))
		buf[a:b] = _LAP * (b - a)

	# 0. Chữ số hệ chữ khác đứng trước đơn vị ("三十五%").
	i = 0
	while i < len(s):
		if _chu_so_khac(s[i]):
			j = i
			while j < len(s) and _chu_so_khac(s[j]):
				j += 1
			dv = _DON_VI.match(s, j)
			if dv:
				xoa(i, dv.end(), s[i:dv.end()])
			i = j
		else:
			i += 1
	s = "".join(buf)
	# 1. Mã giả còn sót (mã hợp lệ đã được Mask.strip bỏ trước khi vào đây) → mô hình bịa.
	for m in _MA_GIA.finditer(s):
		xoa(m.start(), m.end(), m.group(0))
	s = "".join(buf)
	# 2. Ngày d/m, d/m/yyyy, m/yyyy được giữ; "chiếm 2/3" và mọi a/b không phải ngày → phân số.
	for m in _NGAY_THANG.finditer(s):
		xoa(m.start(), m.end(), None if _la_ngay(s, m) else m.group(0))
	s = "".join(buf)
	for m in _THANG_NAM.finditer(s):
		xoa(m.start(), m.end(), None if 1 <= int(m.group(1)) <= 12 else m.group(0))
	s = "".join(buf)
	for m in (_PHAN_SO.finditer(s) if "/" in s else ()):
		xoa(m.start(), m.end(), None if _NAM_NAM.fullmatch(m.group(0)) else m.group(0))
	s = "".join(buf)
	# 2b. Luỹ thừa ("10^9", "4E3").
	for m in _LUY_THUA.finditer(s):
		if not _la_ma(s, m.start()):
			xoa(m.start(), m.end(), m.group(0))
	s = "".join(buf)
	# 3. Từng con số còn lại.
	for m in _SO.finditer(s):
		a, b, tok = m.start(), m.end(), m.group(0)
		dv = _DON_VI.match(s, b)
		dau = max(0, a - _CUA)
		truoc = _TIEN_TRUOC.search(s[dau:a])
		if dv:                                  # số + đơn vị: "35%", "2 tỷ", "50k"
			xoa(a, dv.end(), s[a:dv.end()])
		elif truoc:                             # "$50", "VND 50"
			xoa(dau + truoc.start(), b, s[dau + truoc.start():b])
		elif not tok.isdigit():                 # có dấu nhóm nghìn / phần lẻ: "1.250.000", "12,5", "1 250"
			xoa(a, b, tok)
		elif _la_ma(s, a):                      # "SR900", "KK-2026-002"
			continue
		elif len(tok) >= 3 and not _NAM.fullmatch(tok):
			xoa(a, b, tok)
	s = "".join(buf)
	# 3b. Dãy số rời còn lại sau bước 3 (từng số ≤ 2 chữ số đã lọt): "1 2 5 0" đọc như 1250.
	for m in _SO_ROI.finditer(s):
		if not _la_ma(s, m.start()):
			xoa(m.start(), m.end(), m.group(0))
	s = "".join(buf)
	# 4. Số viết bằng chữ, bội số, phân số bằng chữ.
	for rx in _BANG_CHU:
		for m in rx.finditer(s):
			xoa(m.start(), m.end(), m.group(0))
		s = "".join(buf)
	out: list = []
	for _vt, mau in sorted(bat, key=lambda x: x[0]):
		_them(out, mau)
	return out


# ─── Số do mô hình GHÉP quanh placeholder (soát trên lời CÒN placeholder) ─────
# Mỗi placeholder được thay bằng MỘT ký tự riêng (vùng dùng riêng, không phải chữ / số / khoảng trắng) rồi mới chuẩn
# hoá như lint (thực thể / thẻ HTML, NFKC, bỏ ký tự vô hình) — nên "1\u200b{{a|so}}" vẫn là dính. Với placeholder
# SỐ (tien / so / pct, và chu mà giá trị trông như số — "1234", "55,6%"):
# - sau nó: chữ số dính ("{{a|so}}.000", "{{a|so}}5"), chữ cái dính ("{{a|so}}k", "{{a|so}}E3"), dãy số cách dấu cách
#   ("{{a|so}} 000"), đơn vị (như lint: "%", "đ", "đồng", "USD", "triệu", "phần trăm", "(tỷ)") hoặc "lần" / "chục",
#   placeholder số khác dính / cách khoảng trắng ("{{a|so}}{{b|so}}", "{{a|so}},{{b|so}}", "{{a|so}} {{b|tien}}");
# - trước nó: chữ số dính ("1{{a|so}}"), số rời 1–3 chữ số cách khoảng trắng ("1 {{a|tien}}"; "5/11", "2026", "SR900",
#   "5:30" đứng trước thì không), dấu / phép toán ("-", "−", "+", "±", "×", "^"; "-" / "+" / "–" dính sau chữ, ")" hay
#   một placeholder khác — "KK-{{a|so}}", "{{a|so}}-{{b|so}}" — là nối, không phải dấu).
# "{{a|so}}/{{b|so}}" (hai số thật) và placeholder chu / ngay thường không bị xét.
_MOC = 0xF0000
_LA_MOC = re.compile("[\U000F0000-\U000FFFFD]")
_GIONG_SO = re.compile(r"[\d\s.,/%‰+\-−]*\d[\d\s.,/%‰+\-−]*")
_SAU_KHAC = re.compile(rf"{_GIUA}(?:lần|lan|chục|chuc){_HET}", re.I)
_TRUOC_SO = re.compile(r"(?<![^\s(\[\"'“])\d{1,3}[ \t]+$")
_TRUOC_DAU = re.compile(r"([-+–−±×^])[ \t]?$")
_SAU_DINH = re.compile(r"[.,]?\d|[^\W\d_]+|[ \t]+\d+")      # sau: chữ số / chữ cái dính, dãy số cách dấu cách
_KE = re.compile(r"\s+|[.,]?")                                 # giữa hai placeholder liền nhau
# Từ chỉ số sát placeholder số ("mười {{so}}", "{{so}} mươi", "{{so}} rưỡi", "{{so}} tá") — E3.
_TU_SO = r"(?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|mươi|chục|trăm|rưỡi|tá|lẻ|linh)"
_TRUOC_TU_SO = re.compile(rf"(?<!\w){_TU_SO}\s*$", re.I)
_SAU_TU_SO = re.compile(rf"\s*{_TU_SO}(?!\w)", re.I)
# Nửa phân số viết tay: "1/{{so}}", "{{so}}/10", "3:{{so}}".
# Cũng vậy với gạch DÍNH một chữ số viết tay: "{{so}}-5", "5–{{so}}" ("{{a}}-{{b}}" hai số thật thì giữ).
_TRUOC_PHAN = re.compile(r"\d\s*[/:]\s*$|\d[-–−]$")
_SAU_PHAN = re.compile(r"\s*[/:]\s*\d|[-–−]\d")


def _so_tran(text: str, mask=None, pack=None) -> list:
	"""Số trần trong một đoạn lời của mô hình (còn placeholder, còn mã giả). Mã giả ĐÃ GỬI được bỏ trước (chữ số
	trong mã không phải số liệu; tên thật có thể chứa chữ số nên không bao giờ lint sau khi hoàn nguyên). `pack` (gốc)
	để biết placeholder chu nào trông như số (→ xét như số) hay chỉ là dấu / ký hiệu ("–", "-": thay bằng đúng ký tự
	đó để soát trước / sau — E3)."""
	goc = mask.strip(text) if mask is not None else text
	goc = "" if goc is None else str(goc)
	ph, kieu = [], []

	def moc(m):
		k = m.group(2)
		if k == "chu" and pack is not None:
			v = registry.resolve(pack, m.group(1).strip(), None)
			if isinstance(v, str):
				vc = " ".join(_chuan(v).split())
				if vc and not any(ch.isalnum() for ch in vc):
					return vc                       # "–", "-", "+": chính ký tự đó
				if _GIONG_SO.fullmatch(vc):
					k = "pct" if "%" in vc or "‰" in vc else "so"
		ph.append(m.group(0))
		kieu.append(k)
		return chr(_MOC + len(ph) - 1)

	tho = registry.PLACEHOLDER.sub(moc, goc)
	if not ph:
		return lint(strip_placeholders(goc))
	out: list = []
	for s in _cac_dang(tho):                       # có ngoặc nhọn: soát cả hai dạng (E1)
		_them(out, *_quanh(s, ph, kieu))
	_them(out, *lint(strip_placeholders(goc)))
	return out


def _quanh(s: str, ph: list, kieu: list) -> list:
	"""Số / đơn vị / dấu GHÉP quanh từng placeholder số trong s (placeholder đã thành ký tự mốc)."""
	def tra(a: int, b: int) -> str:
		"""Mẩu s[a:b] với ký tự mốc trả lại thành placeholder gốc."""
		return _LA_MOC.sub(lambda m: ph[ord(m.group(0)) - _MOC], s[a:b])

	def la_so(ch: str) -> bool:
		return bool(_LA_MOC.fullmatch(ch)) and kieu[ord(ch) - _MOC] in SO_KIEU

	out: list = []
	for m in _LA_MOC.finditer(s):
		j = m.start()
		k = kieu[ord(s[j]) - _MOC]
		if k not in SO_KIEU:
			continue
		# sau
		sau = [x for x in (_SAU_DINH.match(s, j + 1), _DON_VI.match(s, j + 1), _SAU_KHAC.match(s, j + 1),
			_SAU_TU_SO.match(s, j + 1), _SAU_PHAN.match(s, j + 1)) if x]
		if sau:
			out.append(tra(j, max(x.end() for x in sau)))
		ke = _KE.match(s, j + 1)
		if ke and ke.end() < len(s) and la_so(s[ke.end()]):
			out.append(tra(j, ke.end() + 1))
		# trước
		truoc = s[max(0, j - _CUA):j]
		g = re.search(r"\d[.,]?$", truoc) or _TRUOC_SO.search(truoc) or _TRUOC_TU_SO.search(truoc) \
			or _TRUOC_PHAN.search(truoc)
		if g:
			out.append(tra(j - len(truoc) + g.start(), j + 1))
		d = _TRUOC_DAU.search(truoc)
		if d:
			a = j - len(truoc) + d.start()
			truoc_dau = s[a - 1] if a > 0 else ""
			if d.group(1) in "−±×^" or not (truoc_dau.isalnum() or truoc_dau == ")" or _LA_MOC.fullmatch(truoc_dau)) \
					or (k == "pct" and d.group(1) in "-–" and truoc_dau.isalpha()):     # "thu nợ-{{pct}}"
				out.append(tra(a, j + 1))
	return out


# ─── Dựng lời ────────────────────────────────────────────────────────────────
def _chuoi(v) -> str:
	return v if isinstance(v, str) else ""


def _mot_dong(s: str) -> str:
	return " ".join((s or "").split())


_DUOI_SO = re.compile(r"\s*\S*\d\S*$")


def _cat(s: str, n: int = TITLE_MAX) -> str:
	"""Cắt còn ≤ n ký tự (bị cắt thì kết bằng "…") — KHÔNG BAO GIỜ giữa một con số: cắt ở khoảng trắng cuối cùng trước
	mốc, rồi bỏ luôn từ cuối nếu nó có chữ số (đơn vị đi sau nó đã bị cắt: "1,6 tỷ" không thành "1,6…"). Không có
	khoảng trắng nào → lùi qua chữ số / . , ở cuối."""
	if len(s) <= n:
		return s
	cat = s[:n - 1]
	if not s[n - 1].isspace():
		k = max(cat.rfind(" "), cat.rfind("\t"))
		cat = cat[:k] if k > 0 else re.sub(r"[\d.,]+$", "", cat)
	cat = cat.rstrip()
	if len(s) > len(cat) and _DUOI_SO.search(cat):
		cat = _DUOI_SO.sub("", cat).rstrip()
	return cat + "…"


def render_rule(title: str, detail: str, pack: dict) -> dict:
	"""Lời QUY TẮC → {"ok", "title" (≤ 200 ký tự), "body", "paths", "sections_used", "errors"} (không lint — lời do
	code viết). ok = False khi có lỗi placeholder (quy tắc viết sai path) hoặc tiêu đề rỗng ("rong")."""
	t, b = fill(title, pack), fill(detail, pack)
	errors, paths, secs = [], [], []
	_them(errors, *t.errors, *b.errors)
	_them(paths, *t.paths, *b.paths)
	_them(secs, *t.sections_used, *b.sections_used)
	tieu_de = _mot_dong(t.text)
	if not tieu_de:
		_them(errors, "rong")
	return {"ok": not errors, "title": _cat(tieu_de), "body": b.text.strip(), "paths": paths, "sections_used": secs,
		"errors": errors}


_DAU_DONG = re.compile(r"^(?:[-–—•*·]+|\d{1,2}[.)])\s+")     # "- …", "1. …" đầu dòng khuyến nghị


def render_insight(raw: dict, pack: dict, sections, mask=None, kinds=None) -> dict:
	"""Lời của MÔ HÌNH cho một nhận định → {"ok", "title", "body", "advice": [str], "paths", "sections_used", "errors"}.

	raw = {"title", "body", "advice": [str]} (đầu ra mô hình, còn placeholder và có thể còn mã giả KH#/NCC#).
	1. fill từng phần với `sections` = các mảng của NHÓM (path ngoài nhóm → lỗi) và `kinds` (registry.kind_map — kiểu
	   số sai kiểu thật của giá trị → "kieu:<p>"; None = không xét kiểu);
	2. lint trên lời đã bỏ placeholder VÀ đã bỏ mã giả ĐÃ GỬI (mask.strip) — mã giả khác (mô hình bịa / chưa gửi) còn
	   lại sẽ bị bắt; số ghép quanh placeholder xét trên lời còn placeholder (_so_tran);
	3. hoàn nguyên mã giả đã gửi → tên thật (mask.unmask) trên lời đã thay số;
	4. title sau bước 3 dài quá TITLE_MAX → lỗi "dai" (không cắt lời mô hình); advice bỏ dòng rỗng, tối đa 3.
	ok = False khi có bất kỳ lỗi nào (errors ghi lý do: lỗi của fill, "so-tran:<mẩu>", "rong" khi title / body rỗng,
	"dai")."""
	raw = raw if isinstance(raw, dict) else {}
	advice = raw.get("advice")
	advice = advice.splitlines() if isinstance(advice, str) else advice if isinstance(advice, (list, tuple)) else []
	advice = [a for a in (_DAU_DONG.sub("", _chuoi(x).strip()) for x in advice) if a][:ADVICE_MAX]
	errors, paths, secs, loi = [], [], [], []
	for text in (_chuoi(raw.get("title")), _chuoi(raw.get("body")), *advice):
		f = fill(text, pack, sections, kinds)
		_them(errors, *f.errors, *(f"so-tran:{mau}" for mau in _so_tran(text, mask, pack)))
		_them(errors, *(f"chu-rong:{p}" for p, k in registry.placeholders(text) if k == "chu"
			and isinstance(registry.resolve(pack, p, None), str) and not registry.resolve(pack, p, "").strip()))
		_them(paths, *f.paths)
		_them(secs, *f.sections_used)
		loi.append(mask.unmask(f.text) if mask is not None else f.text)
	title, body, advice = _mot_dong(loi[0]), loi[1].strip(), [a for a in (_mot_dong(x) for x in loi[2:]) if a]
	if not title or not body:
		_them(errors, "rong")
	if len(title) > TITLE_MAX:
		_them(errors, "dai")
	return {"ok": not errors, "title": _cat(title), "body": body, "advice": advice, "paths": paths,
		"sections_used": secs, "errors": errors}
