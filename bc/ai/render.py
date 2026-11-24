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

Lint (lời của MÔ HÌNH) — hai danh sách CHO PHÉP (vòng sửa 3, G1 / G2) cộng các lớp chặn cũ (D7, E1, E3):

G1 — chữ số viết tay (trên lời đã bỏ placeholder và mã giả đã gửi; sau giải thực thể HTML, NFKC, bỏ ký tự vô hình;
nội dung trong ngoặc nhọn vẫn được soát — E1). MỌI dãy chữ số phải thuộc MỘT trong bốn dạng, còn lại là số trần:
  1. năm 20xx đứng riêng (không dính chữ / số / phần lẻ), cặp năm "2026/27", "2026-2027";
  2. ngày d/m/yyyy, m/yyyy (năm 20xx, ngày có thật — H4: d/m trơ trọi là số trần), ngày đủ viết bằng "." hoặc "-"
     ("5.11.2026", "5-11-2026", "2026-11-05"), "24/7";
  3. thuộc một mã: mẩu không dấu cách (chữ, số, - / . _) mở đầu bằng chữ cái, ≤ 40 ký tự, có ≥ 2 chữ HOA hoặc một chữ
     HOA đứng liền trước ≤ 2 chữ số ("SR900", "KK-2026-002", "T10", "Q3/2026"; "A100", "x1250", "Top5" thì không); số
     hiệu tiêu chuẩn / văn bản sau đúng ISO | HACCP | TCVN | QCVN | TK | QĐ | NĐ | TT + một dấu cách ("ISO 22000:2018");
  4. thời hạn / thứ tự ≤ 2 chữ số: ngay sau quý | tháng | tuần | ngày | mùng | mồng | thứ | ca | đợt | bước | kỳ | Tết |
     T (một dấu cách hoặc liền: "quý 4", "T10", "lần thứ 2"), hoặc ngay trước (một dấu cách) ngày | tuần | tháng | giờ |
     phút | hôm | năm | quý ("trong 7 ngày").
  Chữ số hệ khác không bao giờ được phép. Vì vậy "99 khách", "tăng 5 lần", "top 10", "18 x 10", "1 2 5 0", "10^9",
  "đ350000000", "lúc 5:30" đều bị loại. Lớp hai (giữ từ trước): dạng 1–4 mà kèm đơn vị vẫn bị loại ("2026 tỷ", "quý 4
  %"); giữa số và đơn vị cho phép tối đa 6 dấu / ký hiệu bất kỳ ("12 ; tỷ", "3 • tỷ", "12<!-- -->tỷ" — W1); đơn vị:
  % ‰ đ ₫ đồng VND USD k tr triệu tỷ (tỉ) nghìn (ngàn) vạn trăm "phần trăm", viết không dấu, tiếng Anh, "4M", "2B",
  "2 củ"; "$50", "VND 50"; mã giả lạ / chép hỏng ("KH#0099", "KH0001"); phân số "45/60", "½".
  Số viết bằng CHỮ chỉ bị loại khi kèm đơn vị / bội số (cách tối đa 6 dấu: "hai tỷ", "hai ; tỷ", "năm tỏi", "ba lăm %",
  "tỷ rưỡi", "gần tỷ", "non tỷ", "tỷ bạc", "gấp đôi", "một nửa", "một phần ba") hoặc khi đứng cạnh placeholder (G2);
  số La Mã viết HOA + đơn vị ("XII tỷ", "XXXV phần trăm"; "quý IV" thì giữ — W2).

G2 — láng giềng của placeholder (MỌI kiểu: tien, so, pct, ngay, chu; xét trên lời còn placeholder, mỗi placeholder là một
ký tự mốc; mã giả đã gửi là một mốc khác — không phải chữ; chu chỉ gồm dấu ("–") thay bằng chính dấu đó — E3):
- TRƯỚC (bỏ khoảng trắng): đầu lời / đầu dòng; một CHỮ mà từ nó kết thúc không phải từ chỉ số (một … mười, mươi, lăm,
  mốt, tư, chục, trăm, nghìn, vạn, triệu, tỷ, rưỡi, tá, lẻ, linh, nửa, vài, dăm, mấy, đôi, cặp, dạng không dấu), số La
  Mã, trên | phần | nhân | chia | cộng | trừ | gấp | x | âm (từ ghép đã biết thì được: "đầu tư", "tổng cộng", "khấu
  trừ", "thứ hai"); hoặc dấu ( [ " “ ' ‘ , : ; . ! ? … — với , . : ; phải có khoảng trắng tới placeholder, và thứ đứng
  trước dấu không được là chữ số, từ chỉ số (trừ "năm": "đầu năm: {{…}}"), dấu / phép tính, mã giả.
- SAU (bỏ khoảng trắng): hết lời / hết dòng; một CHỮ mà từ nó mở đầu không phải đơn vị / bội số / từ chỉ số (kể cả
  "năm", "lẻ"; "linh", "tư", "đồng", "triệu", "tỷ" trong từ ghép đã biết thì được: "linh kiện", "đồng hồ", "tỷ lệ"),
  "lần", trên | phần | nhân | chia | cộng | trừ | x (và "điểm" sau pct); hoặc dấu ) ] " ” ' ’ , ; : . ! ? … — sau , .
  phải là khoảng trắng / hết lời; qua các dấu và khoảng trắng, thứ kế tiếp không được là chữ số (trừ khi có ngắt câu
  thật . ! ? … ; + khoảng trắng ở giữa), đơn vị, từ chỉ số (trừ "năm"), mã giả (trừ sau ngắt câu thật).
- GIỮA hai placeholder liền nhau: ít nhất một từ thường (không phải từ chỉ số / đơn vị); dấu và khoảng trắng không đủ
  ("{{a}} ({{b}})", "{{a}}: {{b}}", "{{a}}–{{b}}", "{{a}}/{{b}}" bị loại) — trừ khi khoảng giữa không có chữ số và
  giá trị chu kề bên mở / kết bằng một từ như thế ("{{số lượng|so}} {{đơn vị tính|chu}}" → "120 Thùng").
Còn lại (chữ số, - – — − + ± × * / \\ ^ = < > ~ ≈ % # sát placeholder, ngoặc đóng trước / ngoặc mở sau …) → số trần.
Các lớp cũ quanh placeholder số (đơn vị / "lần" / chữ số dính sau, dấu trước, từ chỉ số sát bên, nửa phân số — D7, E3)
vẫn chạy cùng.
- (render_insight với kinds) kiểu số sai kiểu thật của giá trị ("{{số khách|pct}}", "{{tiền|so}}") → "kieu:<p>"; khoá
  không xếp được kiểu thì pct cũng bị loại (E2). Placeholder chu ra chuỗi rỗng → "chu-rong:<p>".
- (render_insight) tiêu đề dài quá 200 ký tự sau khi thay số → "dai" (lời quy tắc thì cắt, không cắt giữa số).
Vòng sửa 4 (H1–H8) — luật theo cấu trúc, một bộ cho mỗi khái niệm (_TU_SO_*, _DV_*, _TIEN_NGOAI*), lượt tuyến tính:
- H1 (lượt theo TỪ, không phân biệt hoa thường; dạng bỏ VÀ dạng giữ dấu markdown * _ ` ~): từ chỉ số (có dấu, hoặc dạng
  không dấu khi cả từ là ASCII) + khoảng (≤ 6 dấu) + đơn vị (tỷ, triệu, trăm, nghìn, vạn, đồng, đ, k, tr, % chữ / dấu,
  tiếng lóng tỏi củ chai lít xị vé lố, tiền tệ đô yên euro …) → số trần ("HAI TỶ", "hai_tỷ", "ba tram trieu", "tám
  mươi ٪"); phân số "<số> phần <số>"; "nhân đôi", "gấp ba"; (tăng | giảm | gấp | hơn | kém | lên | xuống | bằng) + ≤ 2
  từ + số + "lần"; million billion thousand hundred percent half double triple twice.
- H2: mọi chữ của lời phải là chữ La-tinh, không còn dấu tổ hợp rời → "chu-la:<mẩu>"; mẩu chữ số trộn O o l I |
  ("I2O", "l00") là số; từ chỉ gồm O o l I có O hoa ("lOO") + đơn vị là số.
- H3: sau MỌI dạng chữ số được phép (năm, ngày, tháng/năm, cặp năm, mã, số hiệu, thời hạn) không được có đơn vị (bộ
  của H1, thêm "lần", "chục" khi chỉ cách khoảng trắng): "5/11/2026 tỷ", "Tết 26 tỏi".
- H4: ngày viết tay phải đủ năm 20xx (hoặc tháng/20xx); "24/7" giữ; d/m trơ trọi, d/m/yy là số trần.
- H5 (render_insight(nguon=đề bài cuối đã gửi)): mẩu mã G1.3 phải có NGUYÊN VĂN trong đề bài (trừ tiền tố tiêu chuẩn
  / văn bản và T10, Q3, T10/2026) — "KH-0099", "SL-350", mã của dòng bị cắt bị loại. nguon=None: không xét.
- H6: tiêu đề và từng khuyến nghị gộp một dòng TRƯỚC mọi bước; ở thân, hết dòng sau placeholder không phải ngắt câu:
  dòng sau (qua dấu đầu dòng "- • * 1.") không được mở bằng chữ số / đơn vị / từ chỉ số (kể cả "năm").
- H7: ngay sau placeholder số không được là đơn vị của bộ chung, tên tiền tệ, "bảng Anh", và "đồng" (trừ đồng hồ, thời,
  nghiệp, ý, bộ, hành, phục, tình, thuận).
- H8: số La Mã chỉ I V X (≥ 2 chữ HOA, hợp lệ, đứng riêng) chỉ được ngay sau từ chỉ thứ tự (quý, tháng, kỳ, đợt, giai
  đoạn, chương, phần, mục, cấp, loại, hạng, khoá, thứ, thế kỷ, vùng, khu, QĐ, NĐ, TT).
GIỚI HẠN đã biết (G4): dạng được phép của G1 lọt dù dùng sai ("DSO 62 ngày" là số liệu thật viết tay) và số bằng chữ
không kèm đơn vị, không sát placeholder lọt ("chín mươi chín hoá đơn"), số La Mã có L C D M không kèm
đơn vị ("XL khách") — lint không biết thật / giả; đề bài
(bc.ai.prompt) răn. Loại nhầm thì chấp nhận (thẻ giữ lời quy tắc); lời quy tắc (render_rule) không lint.
"""

from __future__ import annotations

import datetime
import functools
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
_DONG_GHEP = ("thời|bộ|ý|loạt|đều|nghĩa|hành|phục|nghiệp|tình|lòng|minh|tâm|thuận|hồ|nhất|dạng|bằng|ruộng|cỏ|chí|cấp"
	"|bào|hương|khởi|phạm|hoá|hóa|ca|loại")
_DONG = rf"đồng(?!\s+(?:{_DONG_GHEP})(?!\w))"        # "đồng hồ", "đồng thời" … không phải tiền
_TIEN_TE_KD = rf"(?:{_DONG}|vnđ|vnd|usd|đ|dong)"
# Mốc riêng (vùng dùng riêng của BMP): mã giả ĐÃ GỬI đứng sát placeholder (G2) — không phải chữ, số, khoảng trắng.
_MA_MOC = ""
# Giữa số và đơn vị (W1): khoảng trắng và tối đa 6 ký tự KHÔNG phải chữ / chữ số (dấu câu, ký hiệu: ; . × ⋅ • / | !
# … + & @ # → \ ‐ ngoặc, nháy …), trừ chính các đơn vị ký hiệu (% ‰ ₫ $ €), chỗ đã soát (\x00) và mốc placeholder / mã;
# cùng "x" đứng riêng ("12 (tỷ)", "(12) tỷ", "12-tỷ", "12 ; tỷ", "12 • tỷ", "12 x tỷ"). Mỗi khoảng trắng chỉ khớp một
# cách (\s* xen giữa các ký tự dấu) nên không chạy bậc cao.
_DAU_GIUA = "[^\\w\\s%‰٪₫$€\\x00-\\x1f\U000F0000-\U000FFFFD]"
_GIUA = rf"\s*(?:(?:{_DAU_GIUA}|x(?![^\W\d_]))\s*){{0,6}}"
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
	# G1: từ chỉ số + dấu chen giữa + đơn vị / tiếng lóng ("hai ; tỷ", "năm tỏi", "ba • triệu", "hai chai") (W1, W2)
	re.compile(rf"(?<!\w)(?:{_CHU_SO}\s+){{0,7}}{_CHU_SO}(?![^\W\d_])\s*(?:{_DAU_GIUA}\s*){{0,6}}"
		rf"(?:{_LON}|(?-i:vạn|trăm)|phần\s+trăm|tỏi|củ|chai|lít|[%‰])(?!\w)", re.I),
	# G1: số La Mã (chữ HOA đứng riêng) trước đơn vị / bội số / % ("XII tỷ", "XXXV phần trăm"; "quý IV" thì giữ) (W2)
	re.compile(rf"(?<![^\W\d_])(?-i:[IVXLCDM]+)(?![^\W\d_])(?={_GIUA}(?:[%‰]|(?:phần|phan)\s+(?:trăm|tram)"
		rf"|(?:{_TY}|{_TRIEU}|nghìn|ngàn|vạn|trăm|chục|tr|k|triệu|tỷ|tỏi|củ|{_TIEN_TE_KD}|percent|pct|million|billion|bn)"
		rf"(?![^\W\d_])))", re.I),
	re.compile(rf"(?<!\w)(?:{_CHU_SO}\s+){{0,7}}{_CHU_SO}\s*[%‰]", re.I),                  # "ba lăm %"
	re.compile(rf"(?<!\w){_LON}\s+(?:rưỡi|mốt|hai|ba|tư|bốn|lăm|sáu|bảy|tám|chín)(?!\w)", re.I),   # "tỷ rưỡi", "tỷ hai"
	re.compile(rf"(?<!\w)(?:tiền|bạc)\s+(?-i:{_TY}|{_TRIEU})(?!\w)", re.I),            # "tiền tỷ", "bạc triệu"
	re.compile(r"(?<!\w)hàng\s+(?-i:chục|vạn)(?!\w)", re.I),
	re.compile(r"(?<!\w)(?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín)\s+phần\s+(?:hai|ba|tư|bốn|mười)(?!\w)", re.I),
	# "một nửa", "nửa số khách" là tỷ phần; "nửa đầu tháng", "nửa năm" là thời gian (giữ)
	re.compile(r"(?<!\w)(?:(?:một|phân|quá|hơn|gần)\s+)?nửa"
		r"(?!\s+(?:đầu|cuối|sau|trước|năm|tháng|tuần|ngày|quý|kỳ|giờ|buổi|đêm|mùa|chừng|vời))(?!\w)", re.I),
	re.compile(r"(?<!\w)(?:hơn|gần|trên|dưới|ngót|nghét|non|khoảng|cỡ|tầm|chừng|tới|đến|quá|vượt)\s+"   # "gần tỷ", "non tỷ"
		rf"(?:{_LON}|(?-i:vạn|trăm))(?!\w)", re.I),
	re.compile(rf"(?<!\w){_LON}\s+(?:{_TIEN_TE}|bạc)(?!\w)", re.I),                    # "… tỷ đồng", "tỷ bạc"
)


# ─── Vòng sửa 4 (H1, H2, H3, H7, H8): MỘT bộ cho mỗi khái niệm, xét theo TỪ (không phân biệt hoa thường) ─────
# Từ = dãy chữ cái liền nhau; khoảng giữa hai từ = khoảng trắng + tối đa 6 dấu (không chữ, không chữ số) như _GIUA.
# Từ chỉ số: dạng có dấu (so đúng dấu) hoặc dạng KHÔNG dấu (chỉ khi cả từ là ASCII: "muoi", "tram"; "tự", "bà" thì không).
_TU_SO_DAU = frozenset("một hai ba bốn tư năm lăm nhăm sáu bảy bẩy tám chín mười mươi mốt chục trăm nghìn ngàn vạn vài "
	"mấy rưỡi rưởi nửa đôi tá".split())
_TU_SO_KD = frozenset("mot hai ba bon tu nam lam sau bay tam chin muoi chuc tram nghin ngan vai may ruoi nua".split())
# Tên tiền tệ (H7; cũng là đơn vị sau từ chỉ số / dạng chữ số được phép — H1, H3).
_TIEN_NGOAI = frozenset("đô đôla dollar usd yên euro eur tệ won baht bath rúp xu hào cắc bạc".split())
_TIEN_NGOAI_KD = frozenset("dollar usd yen euro eur won baht bath rup".split())
# Đơn vị: có dấu (+ % chữ, tiếng lóng, tiền tệ) / không dấu.
_DV_DAU = frozenset("tỷ tỉ triệu trăm nghìn ngàn vạn đồng đ vnđ percent pct tỏi củ chai lít xị vé lố".split()) | _TIEN_NGOAI
_DV_KD = frozenset("ty ti trieu tram nghin ngan dong d vnd usd tr trd k percent pct".split()) | _TIEN_NGOAI_KD
# Đơn vị hai từ: "phần trăm", "phan tram", "per cent", "phần nghìn", "phần mười", "bảng Anh", "nhân dân (tệ)".
_DV_HAI = {"phần": {"trăm", "nghìn", "ngàn", "mười"}, "phan": {"tram", "nghin", "ngan", "muoi"}, "per": {"cent"},
	"bảng": {"anh"}, "nhân": {"dân"}, "nhan": {"dan"}}
# Từ ghép làm "đơn vị" thành chữ thường ("tỷ lệ", "triệu tập", "đồng thời", "củ cải", "đô thị", "xu hướng" …).
_TY_GHEP = {"lệ", "trọng", "suất", "mỉ", "giá", "phú", "le", "trong", "suat", "gia"}
_DV_GHEP = {"tỷ": _TY_GHEP, "tỉ": _TY_GHEP, "ty": _TY_GHEP, "ti": _TY_GHEP, "triệu": {"chứng", "tập", "hồi"},
	"trieu": {"chung", "tap", "hoi"}, "đồng": set(_DONG_GHEP.split("|")),
	"dong": {"thoi", "bo", "y", "deu", "loat", "nghiep", "ho", "hanh", "phuc", "tinh", "thuan", "nhat", "dang", "bang"},
	"củ": {"cải", "hành", "tỏi", "khoai", "kiệu", "gừng", "sắn", "từ", "ấu", "quả"}, "đô": {"thị", "đốc", "vật"},
	"yên": {"tâm", "ổn", "bái", "lặng", "bình", "ả"}, "xu": {"hướng", "thế", "nịnh"}, "hào": {"hứng", "phóng", "quang",
	"hoa"}, "bạc": {"hà", "màu", "nhược", "đãi"}, "tệ": {"hại", "nạn"}, "chai": {"lì", "sạn"}}
# Sau placeholder SỐ chỉ các "đồng …" này mới không đọc thành tiền (H7); lời viết tay vẫn dùng _DV_GHEP["đồng"].
_DONG_SAU_SO = {"hồ", "thời", "nghiệp", "ý", "bộ", "hành", "phục", "tình", "thuận"}
_BOI_DONG_TU = {"tăng", "giảm", "gấp", "hơn", "kém", "lên", "xuống", "bằng", "tang", "giam", "gap", "hon", "kem", "len",
	"xuong", "bang"}                       # (tăng | giảm | …) + ≤ 2 từ + từ chỉ số + "lần"
_BOI_DOI = {"rưỡi", "rưởi", "ruoi", "doi"}            # "gấp rưỡi", "gap doi" (đôi có dấu đã là từ chỉ số)
_ANH_SO = frozenset("million billion thousand hundred percent half double triple twice".split())
_NHAN_GHEP = {"công", "cá", "nhà", "bệnh", "thương", "chủ", "quân", "doanh", "nạn", "tư", "bị", "nguyên"}
# Số La Mã I V X (H8) chỉ được ngay sau một từ chỉ thứ tự.
_LA_MA_IVX = re.compile(r"X{0,3}(?:IX|IV|V?I{0,3})")
_THU_TU = {"quý", "tháng", "kỳ", "đợt", "chương", "phần", "mục", "cấp", "loại", "hạng", "khoá", "khóa", "thứ", "vùng",
	"khu", "qđ", "nđ", "tt"}
_THU_TU_HAI = {"đoạn": "giai", "kỷ": "thế"}           # "giai đoạn II", "thế kỷ XX"
_CHU_GIONG_SO = re.compile(r"[OolI]+")                 # chữ trông như chữ số (H2)
_TU = re.compile(r"[^\W\d_]+")
_DAU_PT = "%‰٪"


def _giua_ok(s: str, a: int, b: int) -> tuple:
	"""Khoảng s[a:b] giữa hai từ có phải "khoảng trắng + ≤ 6 dấu" (không chữ số, không ký tự điều khiển / mốc / chỗ đã
	soát) → (hợp lệ, có dấu % ‰ ٪ ở giữa, chỉ có khoảng trắng)."""
	dau = 0
	pt = False
	for k in range(a, b):
		ch = s[k]
		if ch.isspace():
			continue
		o = ord(ch)
		if ch.isdigit() or o < 0x20 or 0xF0000 <= o <= 0xFFFFD:
			return False, False, False
		if ch in _DAU_PT:
			pt = True
		dau += 1
		if dau > 6:
			return False, False, False
	return True, pt, dau == 0


def _la_tu_so(w: str, truoc: str = "") -> bool:
	"""Từ chỉ số (H1) — hoặc từ chỉ gồm chữ trông như chữ số có chữ O hoa, ≥ 2 ký tự ("lOO", "OO") (H2)."""
	t = w.lower()
	if t in _TU_SO_DAU or (w.isascii() and t in _TU_SO_KD):
		return not (t == "tư" and truoc in ("đầu", "riêng"))         # "đầu tư" không phải số
	return len(w) >= 2 and "O" in w and bool(_CHU_GIONG_SO.fullmatch(w))


def _don_vi_tu(w: str, ke: str, ke2: str = "", them=()) -> int:
	"""Từ w (ke, ke2: hai từ kế tiếp, chữ thường, chỉ cách khoảng trắng) là đơn vị: 0 = không; 1 = một từ; 2 = hai từ."""
	t = w.lower()
	if ke in _DV_HAI.get(t, ()):
		return 2
	if not (t in _DV_DAU or (w.isascii() and t in _DV_KD) or t in them):
		return 0
	if ke in _DV_GHEP.get(t, ()) and not (ke in ("giá", "gia") and ke2 in ("trị", "tri")):
		return 0
	return 1


def _tu_so_bat(s: str) -> list:
	"""H1 / H2 / H8 trên MỘT dạng lời (theo từ, tuyến tính) → [(vị trí, mẩu)]:
	- từ chỉ số (+ từ chỉ số …) + khoảng (≤ 6 dấu) + đơn vị (H1 / slang / tiền tệ / % chữ / dấu %): "HAI TỶ", "hai_tỷ",
	  "ba tram trieu", "tám mươi ٪", "lOO triệu";
	- phân số bằng chữ "<từ chỉ số> phần <từ chỉ số>" ("ba phần năm"); "nhân đôi / nhân ba", "gấp ba";
	  (tăng | giảm | gấp | hơn | kém | lên | xuống | bằng) + ≤ 2 từ + từ chỉ số + "lần";
	- million, billion, thousand, hundred, percent, half, double, triple, twice;
	- số La Mã I V X (≥ 2 chữ HOA, hợp lệ, đứng riêng) không ngay sau từ chỉ thứ tự ("XII khách"; "quý IV" thì giữ)."""
	ws = [(m.start(), m.end(), m.group(0)) for m in _TU.finditer(s)]
	n = len(ws)
	lo = [w.lower() for _a, _b, w in ws]
	gap = [_giua_ok(s, ws[i][1], ws[i + 1][0]) for i in range(n - 1)] + [(False, False, False)]
	so = [_la_tu_so(ws[i][2], lo[i - 1] if i else "") for i in range(n)]
	out: list = []
	dau = 0                                  # vị trí từ đầu của dãy từ chỉ số đang xét
	for i in range(n):
		a, b, w = ws[i]
		t = lo[i]
		if not (i and so[i - 1] and gap[i - 1][0]):
			dau = i
		if t in _ANH_SO:
			out.append((a, w))
		e = _dv_sau(s, b, ()) if so[i] else 0
		if e:
			out.append((ws[dau][0], s[ws[dau][0]:e]))
		elif so[i] and i + 1 < n and gap[i][0]:
			if t != "phần" and lo[i + 1] in ("phần", "phan") and i + 2 < n and gap[i + 1][0] and so[i + 2]:
				out.append((ws[dau][0], s[ws[dau][0]:ws[i + 2][1]]))           # "ba phần năm"
			elif lo[i + 1] in ("lần", "lan") and any(lo[k] in _BOI_DONG_TU for k in range(max(0, dau - 3), dau)):
				out.append((ws[dau][0], s[ws[dau][0]:ws[i + 1][1]]))           # "tăng ba lần"
		if t in ("nhân", "nhan", "gấp", "gap") and i + 1 < n and gap[i][0] and (so[i + 1] or lo[i + 1] in _BOI_DOI) \
				and not (t in ("nhân", "nhan") and i and lo[i - 1] in _NHAN_GHEP):
			out.append((a, s[a:ws[i + 1][1]]))                                 # "nhân đôi", "gấp ba"
		if len(w) >= 2 and w.isupper() and set(w) <= set("IVX") and _LA_MA_IVX.fullmatch(w) \
				and not (a and (s[a - 1].isdigit() or s[a - 1] == "-")) and not (b < len(s) and (s[b].isdigit()
				or s[b] == "-")):
			truoc = lo[i - 1] if i and gap[i - 1][2] else ""
			if not (truoc in _THU_TU or (truoc in _THU_TU_HAI and i > 1 and lo[i - 2] == _THU_TU_HAI[truoc])):
				out.append((a, w))                                             # "XII khách" (H8)
	return out


def _dv_sau(s: str, k: int, them=("lần", "lan", "chục", "chuc")) -> int:
	"""H3: đơn vị (bộ của H1 + "lần", "chục") sau vị trí k, cách khoảng trắng + ≤ 6 dấu → vị trí hết đơn vị; 0 = không."""
	n = len(s)
	dau = 0
	j = k
	while j < n:
		ch = s[j]
		if ch.isspace():
			j += 1
			continue
		if ch in _DAU_PT or ch in "₫$€":
			return j + 1
		if ch.isalpha() or ch.isdigit() or ord(ch) < 0x20 or 0xF0000 <= ord(ch) <= 0xFFFFD:
			break
		dau += 1
		if dau > 6:
			return 0
		j += 1
	if j >= n or not ch.isalpha():
		return 0
	m = _TU.match(s, j)
	w = m.group(0)

	def tu_ke(e: int) -> tuple:
		x = e
		while x < n and s[x] in " \t":
			x += 1
		mm = _TU.match(s, x) if x > e else None
		return (mm.group(0).lower(), mm.end()) if mm else ("", e)

	ke, e2 = tu_ke(m.end())
	ke2, _e3 = tu_ke(e2) if ke else ("", e2)
	hai = _don_vi_tu(w, ke, ke2, them if dau == 0 else ())      # "lần", "chục": chỉ khi cách bằng khoảng trắng
	return 0 if not hai else (m.end() if hai == 1 else e2)


# Thẻ HTML TRƠN (chỉ tên thẻ, không thuộc tính): "<b>", "</b>", "<br/>". Nội dung trong ngoặc nhọn KHÔNG bao giờ bị
# bỏ (E1): "<khoảng 350 triệu>", "<b 1.250.000 đ>" vẫn được soát.
_THE_TRON = re.compile(r"<\s*/?\s*[A-Za-z][A-Za-z0-9]*\s*/?\s*>")


def _chuan(text: str, bo_the: bool = True, giu_dau: bool = False) -> str:
	"""Giải thực thể HTML ("&nbsp;", "&#37;", "&lt;") + NFKC (chữ số / % toàn chiều rộng, dấu cách đặc biệt, dấu tổ
	hợp → dạng thường) + bỏ ký tự vô hình (Cf) và dấu nhấn markdown * _ ` ~ (để "**2** tỷ", "__35__%" vẫn là "2 tỷ",
	"35%") + bo_the: bỏ thẻ HTML trơn ("<b>12</b> tỷ" → "12 tỷ"); rồi mọi "<" ">" còn lại thành dấu cách (nội dung
	trong ngoặc vẫn được soát). Nơi gọi soát CẢ HAI dạng (bo_the True / False) khi lời có ngoặc nhọn: "Nợ 12 <tr>"."""
	s = unicodedata.normalize("NFKC", html.unescape(text))
	s = s.replace("<!--", " ").replace("-->", " ")     # "12<!-- -->tỷ" → "12 tỷ" (W1); nội dung vẫn được soát
	bo = "" if giu_dau else "*_`~"           # giu_dau (G2): dấu nhấn markdown cũng là "dấu" sát placeholder
	s = "".join(ch for ch in s if unicodedata.category(ch) != "Cf" and ch not in bo)
	if bo_the:
		s = _THE_TRON.sub("", s)
	return s.replace("<", " ").replace(">", " ")


def _cac_dang(text: str, giu_dau: bool = False) -> list:
	"""Các dạng chuẩn hoá để soát: một dạng; thêm dạng giữ tên thẻ khi lời có ngoặc nhọn (E1)."""
	a = _chuan(text, giu_dau=giu_dau)
	b = _chuan(text, bo_the=False, giu_dau=giu_dau)
	return [a] if a == b else [a, b]


def _la_ngay(s: str, m) -> bool:
	"""Khớp d/m[/y] này là NGÀY được giữ (H4): chỉ khi có năm bốn chữ số 20xx và ngày có thật ("5/11/2026"), hoặc đúng
	"24/7". d/m trơ trọi ("5/11", "1/2", "9/10") và d/m/yy là số trần, dù chữ nào đứng trước."""
	d, th, y = m.groups()
	if y is None:
		return d == "24" and th == "7"
	if len(y) != 4 or not y.startswith("20"):
		return False
	try:
		datetime.date(int(y), int(th), int(d))
	except ValueError:
		return False
	return True


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


# ─── G1: chữ số viết tay — danh sách CHO PHÉP ────────────────────────────────
# Ngày đủ viết bằng "-" / "." (d-m-yyyy, d.m.yyyy, yyyy-mm-dd; năm 20xx): chỉ dạng đủ — "12.5" không phải ngày.
_NGAY_DU = re.compile(r"(?<![\w.,/\-])(?:(\d{1,2})([.\-])(\d{1,2})\2(20\d\d)|(20\d\d)-(\d{2})-(\d{2}))"
	r"(?![\w/])(?![.,\-]\d)")
# Số hiệu tiêu chuẩn / văn bản: đúng các chữ viết HOA này + MỘT dấu cách + phần số (có thể nối - / . : và chữ).
_MA_CHUAN = re.compile(r"(?<![^\W\d_])(?:ISO|HACCP|TCVN|QCVN|TK|QĐ|NĐ|TT) \d(?:[^\W_]|[\-/:](?=[^\W_])|\.(?=[^\W_]))*")
_TU_TRUOC_SO = {"quý", "tháng", "tuần", "ngày", "mùng", "mồng", "thứ", "ca", "đợt", "bước", "kỳ", "tết"}
_TU_SAU_SO = {"ngày", "tuần", "tháng", "giờ", "phút", "hôm", "năm", "quý"}
_NOI_MA = "-/._"
# H2: mẩu chỉ gồm chữ số và chữ trông như chữ số (O o l I |), có ít nhất một chữ số.
_SO_GIA = re.compile(r"(?<![^\W_])(?<!\|)[0-9OolI|]*\d[0-9OolI|]*(?![^\W_])(?!\|)")
# H5: mã không cần có trong đề bài — tiền tố tiêu chuẩn / văn bản + số, viết tắt thời gian "T10", "Q3", "T10/2026".
_MA_MIEN = re.compile(r"(?:T\d{1,2}|Q\d)(?:/20\d\d)?|(?:ISO|HACCP|TCVN|QCVN|TK|QĐ|NĐ|TT)[-/.:]?\d[^\s]*")


def _ngay_that(m) -> bool:
	try:
		if m.group(1):
			datetime.date(int(m.group(4)), int(m.group(3)), int(m.group(1)))
		else:
			datetime.date(int(m.group(5)), int(m.group(6)), int(m.group(7)))
	except ValueError:
		return False
	return True


def _tu_ket_thuc(s: str, k: int) -> str:
	"""Từ (chỉ chữ cái, ≤ 20) kết thúc ngay trước s[k]; dài hơn / không có → ""."""
	j = k
	while j > 0 and k - j <= 20 and s[j - 1].isalpha():
		j -= 1
	return "" if k - j > 20 or (j > 0 and s[j - 1].isalpha()) else s[j:k]


def _tu_bat_dau(s: str, k: int) -> str:
	"""Từ (chỉ chữ cái, ≤ 20) bắt đầu tại s[k]."""
	j = k
	while j < len(s) and j - k <= 20 and s[j].isalpha():
		j += 1
	return "" if j - k > 20 or (j < len(s) and s[j].isalpha()) else s[k:j]


def _la_ma_g1(s: str, a: int, b: int) -> bool:
	"""G1.3: dãy chữ số s[a:b] thuộc một MÃ — mẩu không dấu cách (chữ, số, - / . _) bắt đầu bằng chữ cái, ≤ 40 ký tự,
	có ≥ 2 chữ HOA, hoặc đúng một chữ HOA đứng liền trước ≤ 2 chữ số ("T10", "Q3/2026"; "A100" thì không — giữ luật D7)."""
	return bool(_ma_g1(s, a, b)[0])


_DOAN = re.compile(r"[\w\-/.]+")          # mẩu liền (chữ, số, - / . _) — chứa mọi mã có thể


def _ma_g1(s: str, a: int, b: int, doan=None) -> tuple:
	"""(mẩu mã chứa s[a:b], vị trí hết mẩu) theo G1.3 (_la_ma_g1); không phải mã → ("", b). doan = (đầu, cuối) của mẩu
	liền chứa s[a:b] khi nơi gọi đã tính sẵn (_DOAN) — khỏi dò lại từng ký tự."""
	if doan is not None:
		if a - doan[0] > 42 or doan[1] - b > 42:          # quá dài: không phải mã
			return "", b
		i, j = doan
	else:
		i = a
		while i > 0 and a - i <= 41 and (s[i - 1].isalnum() or s[i - 1] in _NOI_MA):
			i -= 1
		j = b
		while j < len(s) and j - b <= 41 and (s[j].isalnum() or s[j] in _NOI_MA):
			j += 1
	while i < a and s[i] in _NOI_MA:
		i += 1
	while j > b and s[j - 1] in _NOI_MA:
		j -= 1
	tok = s[i:j]
	if not tok or not tok[0].isalpha() or len(tok) > 40 or (i > 0 and (s[i - 1].isalnum() or s[i - 1] in _NOI_MA)):
		return "", b
	hoa = sum(1 for ch in tok if ch.isupper())
	return (tok, j) if hoa >= 2 or (hoa == 1 and bool(re.search(r"[A-ZĐ]\d{1,2}(?!\d)", tok))) else ("", b)


def _g1_duoc(s: str, a: int, b: int, xet_ma: bool = True) -> bool:
	"""G1: dãy chữ số s[a:b] (đã qua các lượt trên: ngày, phân số, đơn vị đã bị xoá) là một dạng ĐƯỢC PHÉP:
	1. năm 20xx đứng riêng (không dính chữ / số / phần lẻ), cả cặp 2026/27, 2026-2027;
	3. thuộc một mã viết HOA (_la_ma_g1);
	4. ≤ 2 chữ số chỉ thời hạn / thứ tự: ngay sau quý | tháng | tuần | ngày | mùng | mồng | thứ | ca | đợt | bước | kỳ |
	   Tết | T (một dấu cách hoặc liền), hoặc ngay trước (một dấu cách) ngày | tuần | tháng | giờ | phút | hôm | năm | quý.
	(2. ngày d/m, d/m/yyyy, m/yyyy, 24/7 đã được lượt ngày giữ lại; chữ số hệ khác không bao giờ được phép.)"""
	run = s[a:b]
	if not run.isascii():
		return False
	n = len(s)
	truoc = s[a - 1] if a else ""
	sau = s[b] if b < n else ""
	dinh_trai = truoc.isalnum() or (truoc in ".," and a >= 2 and s[a - 2].isdigit())
	dinh_phai = sau.isalnum() or (sau in ".," and b + 1 < n and s[b + 1].isdigit())
	if xet_ma and _ma_g1(s, a, b)[0]:
		return True
	nam = len(run) == 4 and run.startswith("20")
	if nam and not dinh_trai and not dinh_phai:
		return True
	if (len(run) == 2 or nam) and truoc in "/-–" and a >= 5 and re.fullmatch(r"20\d\d", s[a - 5:a - 1]) \
			and not (a >= 6 and s[a - 6].isalnum()) and not dinh_phai:          # "2025-26", "2026/27"
		return True
	if len(run) > 2:
		return False
	if not dinh_phai:                                   # sau một từ chỉ thời gian / thứ tự
		k = a - 1 if truoc in " \t" else a
		tu = _tu_ket_thuc(s, k)
		if tu and (tu.lower() in _TU_TRUOC_SO or tu == "T"):
			return True
	if sau in " \t" and not dinh_trai:                 # trước một từ chỉ thời gian
		tu = _tu_bat_dau(s, b + 1)
		if tu and tu.lower() in _TU_SAU_SO:
			return True
	return False


def _chu_so_khac(ch: str) -> bool:
	"""Ký tự là chữ số của hệ chữ khác (三, 五, Ⅻ đã NFKC thì thành chữ La-tinh): có giá trị số, không phải 0-9."""
	return not ch.isascii() and not ch.isdigit() and unicodedata.numeric(ch, None) is not None


def lint(text: str, ma=None) -> list:
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
	tho = _PHAN_SO_KY_TU.sub(" ", tho)
	bo = _cac_dang(tho)
	for s in bo:                   # có ngoặc nhọn: soát cả hai dạng (E1)
		_them(out, *_lint_mot(s, ma))
	# H1: lượt theo từ chạy thêm trên dạng GIỮ dấu nhấn markdown (dấu là "khoảng": "hai_tỷ", "hai~tỷ")
	for s in _cac_dang(tho, giu_dau=True):
		if s not in bo:
			_them(out, *_lint_mot(s, ma, chi_tu=True))
	return out


def _lint_mot(s: str, ma=None, chi_tu: bool = False) -> list:
	"""lint trên MỘT dạng đã chuẩn hoá (_chuan). ma: tập mẩu mã có trong đề bài (H5; None = không xét). chi_tu: chỉ trả
	mẩu của lượt theo từ (H1 / H2 / H8)."""
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
	def giu(a: int, b: int, duoc: bool) -> None:
		"""Dạng được phép s[a:b] (duoc) → giữ, trừ khi có đơn vị theo sau (H3: "5/11/2026 tỷ", "2026/27 tỷ"); không
		được phép → số trần."""
		if not duoc:
			xoa(a, b, s[a:b])
			return
		dv = _DON_VI.match(s, b)
		e = dv.end() if dv else _dv_sau(s, b)
		xoa(a, e or b, s[a:e] if e else None)

	# 1. Mã giả còn sót (mã hợp lệ đã được Mask.strip bỏ trước khi vào đây) → mô hình bịa.
	for m in _MA_GIA.finditer(s):
		xoa(m.start(), m.end(), m.group(0))
	s = "".join(buf)
	# 1b. H2: chữ trông như chữ số trộn với chữ số ("I2O", "1O0", "l00") là một con số, không bao giờ là mã.
	for m in _SO_GIA.finditer(s):
		if any(ch in "OolI|" for ch in m.group(0)):
			xoa(m.start(), m.end(), m.group(0))
	s = "".join(buf)
	# 2. Ngày đủ năm 20xx (d/m/yyyy, m/yyyy) và "24/7" được giữ; d/m trơ trọi và mọi a/b khác → phân số (H4).
	for m in _NGAY_THANG.finditer(s):
		giu(m.start(), m.end(), _la_ngay(s, m))
	s = "".join(buf)
	for m in _THANG_NAM.finditer(s):
		giu(m.start(), m.end(), 1 <= int(m.group(1)) <= 12)
	s = "".join(buf)
	for m in _NGAY_DU.finditer(s):          # G1: ngày đủ viết bằng - hoặc . ("5.11.2026", "2026-11-05")
		if _ngay_that(m):
			giu(m.start(), m.end(), True)
	s = "".join(buf)
	for m in _MA_CHUAN.finditer(s):         # G1: số hiệu tiêu chuẩn / văn bản ("ISO 22000", "TT 200/2014/TT-BTC")
		giu(m.start(), m.end(), True)
	s = "".join(buf)
	for m in (_PHAN_SO.finditer(s) if "/" in s else ()):
		giu(m.start(), m.end(), bool(_NAM_NAM.fullmatch(m.group(0))))
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
	n0 = len(bat)               # chi_tu: chỉ trả mẩu từ đây (lớp chữ: 4 + 4b)
	for rx in _BANG_CHU:
		for m in rx.finditer(s):
			xoa(m.start(), m.end(), m.group(0))
		s = "".join(buf)
	# 4b. Lượt theo từ (H1 / H2 / H8) trên phần CHƯA bị bắt: từ chỉ số + đơn vị (mọi cách viết), phân số / bội số bằng
	# chữ, tiếng Anh, số La Mã I V X ngoài chỗ chỉ thứ tự.
	for vt, mau in _tu_so_bat(s):
		bat.append((vt, " ".join(mau.split())))
	if chi_tu:
		return [mau for _vt, mau in bat[n0:]]
	# 5. G1 — danh sách CHO PHÉP: mọi dãy chữ số còn lại phải là năm, mã, hoặc thời hạn / thứ tự ≤ 2 chữ số.
	i, n = 0, len(s)
	doan = _DOAN.search(s)
	while i < n:
		if not s[i].isdigit():
			i += 1
			continue
		j = i
		while j < n and s[j].isdigit():
			j += 1
		while doan is not None and doan.end() < j:
			doan = _DOAN.search(s, doan.end())
		tok, het = _ma_g1(s, i, j, doan.span() if doan is not None and doan.start() <= i else None)
		if tok and ma is not None and tok not in ma and not _MA_MIEN.fullmatch(tok):
			xoa(i, j, tok)                      # H5: mã không có trong đề bài → bịa ("KH-0099", "SL-350")
		elif tok or _g1_duoc(s, i, j, xet_ma=False):
			e = _dv_sau(s, het if tok else j) or (tok and het != j and _dv_sau(s, j))
			if e:                               # H3: dạng được phép + đơn vị ("Tết 26 tỏi", "tháng 10 lần")
				xoa(i, e, s[i:e])
		else:
			xoa(i, j, s[i:j])
		i = j
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
# "linh kiện", "linh hoạt" sau placeholder không phải từ chỉ số (W6)
_SAU_TU_SO = re.compile(r"\s*" + _TU_SO.replace("|linh)", r"|linh(?!\s+(?:kiện|hoạt|động|tinh)(?!\w)))") + r"(?!\w)", re.I)
# "{{a|pct}} điểm" ("55,6% điểm" — điểm phần trăm tự đặt); "{{a|so}} điểm bán" thì giữ.
_SAU_PCT = re.compile(r"\s*điểm(?!\w)", re.I)
# Nửa phân số viết tay: "1/{{so}}", "{{so}}/10", "3:{{so}}".
# Cũng vậy với gạch DÍNH một chữ số viết tay: "{{so}}-5", "5–{{so}}" ("{{a}}-{{b}}" hai số thật thì giữ).
_TRUOC_PHAN = re.compile(r"\d\s*[/:]\s*$|\d[-–−]$")
_SAU_PHAN = re.compile(r"\s*[/:]\s*\d|[-–−]\d")


def _so_tran(text: str, mask=None, pack=None, ma=None) -> list:
	"""Số trần trong một đoạn lời của mô hình (còn placeholder, còn mã giả). Mã giả ĐÃ GỬI được bỏ trước (chữ số
	trong mã không phải số liệu; tên thật có thể chứa chữ số nên không bao giờ lint sau khi hoàn nguyên) — với luật
	láng giềng (G2) mã đó thành một mốc riêng (không phải chữ: đứng sát placeholder là bị loại). `pack` (gốc) để biết
	placeholder chu nào trông như số (→ xét như số), chỉ là dấu / ký hiệu ("–", "-": thay bằng đúng ký tự đó để soát
	trước / sau — E3), hay mở / kết bằng một từ (G2: từ đó được tính là chữ ngăn giữa hai placeholder)."""
	text = "" if text is None else str(text)
	goc = mask.strip(text) if mask is not None else text
	thay_ma = getattr(mask, "_thay", None)
	co_ma = thay_ma(text, lambda _ma: _MA_MOC) if callable(thay_ma) else text
	ph, kieu, gia = [], [], []

	def moc(m):
		k = m.group(2)
		vc = None
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
		gia.append(vc)
		return chr(_MOC + len(ph) - 1)

	tho = registry.PLACEHOLDER.sub(moc, co_ma)
	if not ph:
		return lint(strip_placeholders(goc), ma)
	out: list = []
	for s in _cac_dang(tho):                       # có ngoặc nhọn: soát cả hai dạng (E1)
		_them(out, *_quanh(s, ph, kieu))
	for s in _cac_dang(tho, giu_dau=True):         # G2: "~", "*", "_", "`" sát placeholder cũng là dấu
		_them(out, *_lang_gieng(s, ph, gia, kieu))
	_them(out, *lint(strip_placeholders(goc), ma))
	return out


class _Nguon:
	"""H5: đề bài cuối cùng đã gửi (chuẩn hoá như lời mô hình) — `ma in nguon` = mẩu mã có mặt NGUYÊN VĂN (không dính
	chữ / số hai bên; "\\n" của JSON không tính là chữ dính). Quá 200 mẩu khác nhau trong một lượt → coi như không có."""

	def __init__(self, text: str):
		self.s = _chuan(text, bo_the=False)
		self.da = {}

	def __contains__(self, tok: str) -> bool:
		if tok in self.da:
			return self.da[tok]
		if len(self.da) >= 200:
			return False
		s, n, k, co = self.s, len(self.s), self.s.find(tok), False
		while k >= 0 and not co:
			e = k + len(tok)
			truoc = k == 0 or not s[k - 1].isalnum() or (k >= 2 and s[k - 2] == "\\")
			co = truoc and (e >= n or not s[e].isalnum())
			k = s.find(tok, k + 1)
		self.da[tok] = co
		return co


@functools.lru_cache(maxsize=2)
def _nguon(text: str) -> _Nguon:
	return _Nguon(text)


def forget_source() -> None:
	"""Xoá bản đề bài còn giữ tạm để soát mã (H5). Pipeline gọi sau MỖI lượt gọi mô hình, kể cả khi lượt đó lỗi:
	đề bài không ở lại trong bộ nhớ của tiến trình sau khi dùng xong."""
	_nguon.cache_clear()


def _chu_la(text: str) -> list:
	"""H2: mẩu (không dấu cách, ≤ 40 ký tự) chứa chữ KHÔNG phải chữ La-tinh (Kirin, Hy Lạp …) hoặc dấu tổ hợp còn rời
	sau NFKC — trên lời CỦA MÔ HÌNH (đã bỏ placeholder, mã giả đã gửi). Tối đa 10 mẩu."""
	s = unicodedata.normalize("NFKC", html.unescape(text))
	out: dict = {}
	n = len(s)
	i = 0
	while i < n and len(out) < 10:
		ch = s[i]
		if not ch.isascii() and ((ch.isalpha() and not unicodedata.name(ch, "").startswith("LATIN"))
				or unicodedata.category(ch) in ("Mn", "Mc", "Me")):
			a, b = i, i + 1
			while a > 0 and i - a < 20 and not s[a - 1].isspace():
				a -= 1
			while b < n and b - i < 20 and not s[b].isspace():
				b += 1
			out.setdefault(s[a:b], None)
			i = b
		else:
			i += 1
	return list(out)


# ─── G2: láng giềng của placeholder — danh sách CHO PHÉP (mọi kiểu) ──────────
# Từ chỉ số (cả dạng không dấu không trùng chữ thường gặp), số La Mã xét riêng.
_G2_TU_SO = {"một", "mốt", "hai", "ba", "bốn", "tư", "năm", "lăm", "nhăm", "sáu", "bảy", "bẩy", "tám", "chín", "mười",
	"mươi", "chục", "trăm", "nghìn", "ngàn", "vạn", "muôn", "ức", "triệu", "tỷ", "tỉ", "rưỡi", "rưởi", "tá", "lẻ", "linh",
	"nửa", "vài", "dăm", "mấy", "đôi", "cặp", "mot", "bon", "chin", "muoi", "tram", "nghin", "trieu"}
# Đơn vị / bội số / phép tính (đứng SAU placeholder).
_G2_DON_VI = {"đ", "đồng", "vnđ", "vnd", "usd", "k", "m", "b", "t", "x", "tr", "trđ", "ty", "ti", "dong", "chuc", "ngan",
	"percent", "pct", "pc", "pt", "per", "bps", "million", "billion", "bn", "mio", "củ", "tỏi", "lần", "lan", "phần", "phan",
	"trên", "nhân", "chia", "cộng", "trừ", "mũ"}
# Đứng TRƯỚC placeholder.
_G2_TRUOC = _G2_TU_SO | {"trên", "phần", "phan", "nhân", "chia", "cộng", "trừ", "gấp", "x", "âm", "lần", "mũ", "k", "m",
	"b", "đ", "tr"}
_G2_SAU = _G2_TU_SO | _G2_DON_VI
# Sau dấu đóng / ngắt (rồi khoảng trắng): đơn vị / từ chỉ số; "năm" ở đây là năm tháng ("{{…}}, năm ngoái …").
_G2_SAU_DAU = (_G2_TU_SO - {"năm"}) | (_G2_DON_VI - {"trên", "phần", "phan", "nhân", "chia", "cộng", "trừ"})
# Đầu dòng sau một placeholder (H6): như sau dấu, thêm "năm", mọi từ chỉ số không dấu, "gấp".
_G2_DONG_MOI = _G2_SAU_DAU | _TU_SO_DAU | _TU_SO_KD | {"gấp", "gap"}
# Từ ghép: chữ đầu trùng đơn vị / từ chỉ số nhưng không phải số ("đồng hồ", "linh kiện", "triệu tập", "tỷ lệ", "tư nhân").
_G2_GHEP = {"đồng": set(_DONG_GHEP.split("|")), "triệu": {"tập", "chứng", "hồi"},
	"tỷ": {"lệ", "trọng", "suất", "mỉ", "giá", "phú"}, "tỉ": {"lệ", "trọng", "suất", "mỉ", "giá", "phú"},
	"linh": {"kiện", "hoạt", "động", "tinh"}, "tư": {"nhân", "vấn", "liệu", "cách", "duy", "thế", "pháp"},
	"cộng": {"đồng", "tác"}, "nhân": {"viên", "sự", "lực", "công", "dịp", "tố"}, "phần": {"mềm", "lớn", "nào", "việc"},
	"chia": {"sẻ"}, "trừ": {"khi"}}
# Từ ghép theo từ ĐỨNG TRƯỚC (xét khi từ cấm đứng ngay trước placeholder): "đầu tư", "tổng cộng", "khấu trừ", "thứ hai".
_G2_GHEP_TRUOC = {"tư": {"đầu", "riêng", "thứ"}, "cộng": {"tổng"}, "nhân": {"công", "cá", "nhà", "bệnh"},
	"trừ": {"khấu", "loại", "ngoại"}, "phần": {"thành", "cổ", "bộ"}, "chia": {"phân"}, "hai": {"thứ"}, "ba": {"thứ"},
	"năm": {"thứ"}, "sáu": {"thứ"}, "bảy": {"thứ"}}
_G2_ROMAN = re.compile(r"[IVXLCDM]+")
_CHU_CAI = re.compile(r"[^\W\d_]+")
_G2_MO = "([\"“'‘«"                       # được đứng ngay trước placeholder
_G2_NGHI = ",:;.!?…"                        # dấu ngắt: , . : ; phải cách placeholder ít nhất một khoảng trắng
_G2_DONG = ")]\"”'’»"                       # được đứng ngay sau placeholder
_G2_DAU = "-–—−‐‑‒―+±×*/\\^=<>~≈%‰#÷⁄∕"     # dấu / phép tính: không bao giờ đứng sát dấu mở trước placeholder


def _cam(tu: str, ds: set, sau: str = "", truoc: str = "") -> bool:
	"""Từ `tu` (chỉ chữ) thuộc danh sách cấm `ds` (so chữ thường; số La Mã viết HOA luôn cấm), trừ khi là một từ ghép
	đã biết: từ kế SAU nó (`sau`: "đồng hồ", "linh kiện") hoặc từ ĐỨNG TRƯỚC nó (`truoc`: "đầu tư", "tổng cộng")."""
	if not tu:
		return False
	if _G2_ROMAN.fullmatch(tu):
		return True
	t = tu.lower()
	if t not in ds:
		return False
	return not ((sau and sau in _G2_GHEP.get(t, ())) or (truoc and truoc in _G2_GHEP_TRUOC.get(t, ())))


def _cam_sau(tu: str, ke: str, so: bool, ds: set, sat: bool = True) -> bool:
	"""Từ `tu` (kế tiếp: `ke`) đứng sau placeholder bị cấm: danh sách `ds` (_cam); sau placeholder SỐ (so) thêm mọi
	đơn vị của bộ chung (H1), tên tiền tệ, "bảng Anh"; "đồng" đứng SÁT (sat) chỉ được trong vài từ ghép không thể đọc
	thành tiền (H7: "{{…}} đô", "{{…}} đồng bằng" bị loại; "{{…}}, đồng nghĩa" thì xét như lời thường)."""
	if so:
		t = tu.lower()
		if t in ("đồng", "dong", "đ") and (sat or t != "đồng"):
			return t != "đồng" or ke not in _DONG_SAU_SO
		if t in _TIEN_NGOAI or (tu.isascii() and t in _TIEN_NGOAI_KD) or _don_vi_tu(tu, ke):   # một bộ đơn vị (H1)
			return ke not in _DV_GHEP.get(t, ())
			return ke not in _DV_GHEP.get(t, ())
		if t == "bảng" and ke == "anh":
			return True
	return _cam(tu, ds, ke)


def _lang_gieng(s: str, ph: list, gia: list, kieu=None) -> list:
	"""G2 trên s (placeholder đã thành ký tự mốc, mã giả đã gửi thành _MA_MOC). Mỗi placeholder (MỌI kiểu):
	- trước (bỏ khoảng trắng): đầu lời / đầu dòng; một CHỮ mà từ nó kết thúc không phải từ chỉ số / bội số / số La Mã /
	  trên | phần | nhân | chia | cộng | trừ | gấp | x; hoặc dấu mở / ngắt ( [ " “ ' ‘ , : ; . ! ? … — với , . : ; phải
	  có khoảng trắng giữa dấu và placeholder, và thứ đứng trước dấu không được là chữ số / từ chỉ số / dấu phép tính;
	- sau (bỏ khoảng trắng): hết lời / hết dòng; một CHỮ mà từ nó mở đầu không phải đơn vị / bội số / từ chỉ số / "lần"
	  / trên | phần | nhân | chia | cộng | trừ | x (từ ghép đã biết thì được: "đồng hồ", "linh kiện"); hoặc dấu đóng /
	  ngắt ) ] " ” ' ’ , ; : . ! ? … — sau , . phải là khoảng trắng / hết lời; qua các dấu và khoảng trắng, thứ kế tiếp
	  không được là chữ số (trừ khi có ngắt câu thật . ! ? … ; + khoảng trắng ở giữa), đơn vị, từ chỉ số;
	- giữa hai placeholder liền nhau phải có ít nhất một từ thường (không phải từ chỉ số / đơn vị) — hoặc giá trị chu
	  kề bên mở / kết bằng một từ như thế ("{{số lượng|so}} {{đơn vị tính|chu}}" → "120 Thùng").
	Còn lại (chữ số, dấu - – + × / % …, ngoặc đóng trước / ngoặc mở sau, mã giả, placeholder khác) → số trần."""
	def tra(a: int, b: int) -> str:
		return _LA_MOC.sub(lambda m: ph[ord(m.group(0)) - _MOC], s[a:b]).replace(_MA_MOC, "KH#…")

	def la_moc(ch: str) -> bool:
		return bool(ch) and _MOC <= ord(ch) <= _MOC + len(ph) - 1

	n = len(s)
	out: list = []

	def khong_trang(k: int, buoc: int) -> int:
		"""Vị trí ký tự đầu tiên không phải khoảng trắng (trừ xuống dòng) từ k theo hướng buoc."""
		while 0 <= k < n and s[k].isspace() and s[k] != "\n":
			k += buoc
		return k

	def tu_truoc(k: int) -> tuple:
		"""(từ kết thúc tại s[k] (chữ), từ liền trước nó (chữ thường))."""
		tu = _tu_ket_thuc(s, k + 1)
		j = khong_trang(k - len(tu), -1)
		return tu, _tu_ket_thuc(s, j + 1).lower() if j >= 0 and s[j].isalpha() else ""

	def tu_sau(k: int) -> tuple:
		tu = _tu_bat_dau(s, k)
		j = khong_trang(k + len(tu), 1)
		return tu, _tu_bat_dau(s, j).lower() if j < n and s[j].isalpha() else ""

	def tu_truoc_cam(k: int) -> bool:
		tu, truoc = tu_truoc(k)
		return _cam(tu, _G2_TRUOC, truoc=truoc)

	def truoc_dau_mo(k: int) -> bool:
		"""Thứ đứng trước dấu mở / ngắt tại s[k] (bỏ khoảng trắng, xuống dòng và các dấu mở / ngắt khác) có hợp lệ."""
		while k >= 0 and (s[k].isspace() or s[k] in _G2_MO or s[k] in _G2_NGHI):
			k -= 1
		if k < 0:
			return True
		ch = s[k]
		if ch.isdigit() or ch in _G2_DAU or ch == _MA_MOC:
			return False
		if ch.isalpha():                    # từ chỉ số trước dấu ("mười, {{…}}"); "năm" ở đây là năm tháng ("đầu năm: {{…}}")
			tu, truoc = tu_truoc(k)
			return not _cam(tu, _G2_TU_SO - {"năm"}, truoc=truoc)
		return True

	def bad_sau(k: int, ngat: bool, so: bool) -> bool:
		"""Thứ kế tiếp tại s[k] (sau dấu đóng / ngắt và khoảng trắng) là chữ số (không có ngắt câu thật) / đơn vị / từ
		chỉ số."""
		if k >= n:
			return False
		ch = s[k]
		if ch.isdigit():
			return not ngat
		if ch == _MA_MOC:                 # mã giả: chỉ được mở câu mới
			return not ngat
		if ch in "%‰٪₫$€":
			return True
		if ch.isalpha():
			tu, ke = tu_sau(k)
			if ngat and tu[:1].isupper() and not _G2_ROMAN.fullmatch(tu):
				return False
			return _cam_sau(tu, ke, so, _G2_SAU_DAU, sat=False)
		return False

	def bad_dong_moi(k: int, so: bool) -> int:
		"""H6: hết dòng sau placeholder KHÔNG phải ngắt câu — dòng sau (bỏ khoảng trắng, dấu đóng, dấu đầu dòng "- • *
		1.") không được mở bằng chữ số, dấu %, từ chỉ số / đơn vị / bội số (không phân biệt hoa thường, kể cả "năm")."""
		while k < n and (s[k].isspace() or s[k] in _G2_DONG):
			k += 1
		m = _DAU_DONG_GIUA.match(s, k)
		if m:
			k = m.end()
		if k >= n:
			return 0
		ch = s[k]
		if ch.isdigit() or ch in "%‰٪₫$€":
			return k
		if ch.isalpha():
			tu, ke = tu_sau(k)
			if _cam_sau(tu, ke, so, _G2_DONG_MOI) or _don_vi_tu(tu, ke):
				return k
		return 0

	vi_tri = [m.start() for m in _LA_MOC.finditer(s)]
	for so_thu, j in enumerate(vi_tri):
		la_so = kieu is not None and kieu[ord(s[j]) - _MOC] in SO_KIEU
		# ── trước
		i = khong_trang(j - 1, -1)
		loi = False
		if i >= 0 and not la_moc(s[i]):
			ch = s[i]
			if ch == "\n":
				loi = not truoc_dau_mo(i - 1)
			elif ch.isalpha():
				loi = tu_truoc_cam(i)
			elif ch in _G2_MO or ch in _G2_NGHI:
				loi = (ch in ",.:;" and i == j - 1) or not truoc_dau_mo(i - 1)
			else:
				loi = True
		if loi:
			a = max(0, i)
			while a > 0 and i - a < 20 and (s[a - 1].isalnum() or (s[a - 1] in "/.,:-" and s[a].isalnum())):
				a -= 1                      # cả mẩu đứng trước: "5/11", "SR900", "nợ"
			out.append(tra(a, j + 1).strip())
		# ── sau
		i = khong_trang(j + 1, 1)
		loi = False
		if i < n and not la_moc(s[i]):
			ch = s[i]
			if ch == "\n":
				k = bad_dong_moi(i, la_so)
				if k:
					loi, i = True, k
			elif ch.isalpha():
				tu, ke = tu_sau(i)
				loi = _cam_sau(tu, ke, la_so, _G2_SAU)
			elif ch in _G2_DONG or ch in _G2_NGHI:
				k, ngat = i, False
				while k < n and (s[k].isspace() or s[k] in _G2_DONG or s[k] in _G2_NGHI):
					if s[k] in ",." and k + 1 < n and not (s[k + 1].isspace() or s[k + 1] in _G2_DONG
							or s[k + 1] in _G2_NGHI):
						loi = True
					if s[k] in ".!?…;" and (k + 1 >= n or s[k + 1].isspace()):
						ngat = True     # chỉ . ! ? … ; + khoảng trắng là ngắt câu thật; xuống dòng thì không (H6)
					k += 1
				if not loi and (bad_sau(k, ngat, la_so) or (not ngat and "\n" in s[i:k] and bad_dong_moi(i, la_so))):
					loi, i = True, min(k, n - 1)
			else:
				loi = True
		if loi:
			b = i + max(1, len(_tu_bat_dau(s, i))) if i < n else n
			out.append(tra(j, b).strip())
		# ── giữa placeholder này và placeholder kế tiếp
		if so_thu + 1 < len(vi_tri):
			k2 = vi_tri[so_thu + 1]
			giua = s[j + 1:k2]
			co_tu = any(not _cam(t, _G2_SAU) for t in _CHU_CAI.findall(giua))
			if not co_tu and giua and not any(ch.isdigit() or ch == _MA_MOC for ch in giua):   # nhờ từ của giá trị chu
				co_tu = _bien_chu(gia[ord(s[j]) - _MOC], cuoi=True) or _bien_chu(gia[ord(s[k2]) - _MOC], cuoi=False)
			if not co_tu:
				out.append(tra(j, k2 + 1))
	return out


def _bien_chu(v, cuoi: bool) -> bool:
	"""Giá trị chu `v` (đã chuẩn hoá) kết thúc (cuoi) / mở đầu bằng một từ thường (không phải từ chỉ số / đơn vị / số
	La Mã) — từ đó ngăn giữa hai placeholder đặt cạnh nhau ("120 Thùng")."""
	if not isinstance(v, str) or not v:
		return False
	tu = _tu_ket_thuc(v, len(v)) if cuoi else _tu_bat_dau(v, 0)
	return bool(tu) and not _cam(tu, _G2_SAU)


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
			_SAU_TU_SO.match(s, j + 1), _SAU_PHAN.match(s, j + 1), k == "pct" and _SAU_PCT.match(s, j + 1)) if x]
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
_DAU_DONG_GIUA = re.compile(r"(?:[-–—•*·]+|\d{1,2}[.)])\s+")   # như trên, xét tại một vị trí bất kỳ (H6)


def render_insight(raw: dict, pack: dict, sections, mask=None, kinds=None, nguon: str | None = None) -> dict:
	"""Lời của MÔ HÌNH cho một nhận định → {"ok", "title", "body", "advice": [str], "paths", "sections_used", "errors"}.

	raw = {"title", "body", "advice": [str]} (đầu ra mô hình, còn placeholder và có thể còn mã giả KH#/NCC#).
	0. title và từng advice gộp thành MỘT dòng TRƯỚC mọi bước (H6: thứ được soát là thứ được hiện);
	1. fill từng phần với `sections` = các mảng của NHÓM (path ngoài nhóm → lỗi) và `kinds` (registry.kind_map — kiểu
	   số sai kiểu thật của giá trị → "kieu:<p>"; None = không xét kiểu);
	2. lint trên lời đã bỏ placeholder VÀ đã bỏ mã giả ĐÃ GỬI (mask.strip) — mã giả khác (mô hình bịa / chưa gửi) còn
	   lại sẽ bị bắt; số ghép quanh placeholder xét trên lời còn placeholder (_so_tran); chữ không phải La-tinh / dấu tổ
	   hợp rời → "chu-la:<mẩu>" (H2); `nguon` (đề bài cuối cùng đã gửi, H5) → mọi mẩu mã G1.3 phải có NGUYÊN VĂN trong
	   đó (trừ tiền tố tiêu chuẩn / văn bản và "T10", "Q3"), không thì "so-tran:<mã>"; None = không xét;
	3. hoàn nguyên mã giả đã gửi → tên thật (mask.unmask) trên lời đã thay số;
	4. title sau bước 3 dài quá TITLE_MAX → lỗi "dai" (không cắt lời mô hình); advice bỏ dòng rỗng, tối đa 3.
	ok = False khi có bất kỳ lỗi nào (errors ghi lý do: lỗi của fill, "so-tran:<mẩu>", "chu-la:<mẩu>", "rong" khi title /
	body rỗng, "dai")."""
	raw = raw if isinstance(raw, dict) else {}
	advice = raw.get("advice")
	advice = advice.splitlines() if isinstance(advice, str) else advice if isinstance(advice, (list, tuple)) else []
	advice = [a for a in (_mot_dong(_DAU_DONG.sub("", _chuoi(x).strip())) for x in advice) if a][:ADVICE_MAX]
	ma = _nguon(nguon) if isinstance(nguon, str) else None
	errors, paths, secs, loi = [], [], [], []
	for text in (_mot_dong(_chuoi(raw.get("title"))), _chuoi(raw.get("body")), *advice):
		f = fill(text, pack, sections, kinds)
		_them(errors, *f.errors, *(f"so-tran:{mau}" for mau in _so_tran(text, mask, pack, ma)))
		goc = mask.strip(text) if mask is not None else text
		_them(errors, *(f"chu-la:{mau}" for mau in _chu_la(strip_placeholders(goc))))
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
