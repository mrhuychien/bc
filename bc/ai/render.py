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
  số, dính liền hay cách ("35%", "35 %", "2tỷ", "50k", "5 trăm triệu", "5 trăm khách"); ký hiệu tiền đứng trước ("$50");
- số viết bằng CHỮ / ước lượng quanh đơn vị lớn ("hai tỷ", "vài trăm triệu", "ba trăm", "mười phần trăm", "tỷ rưỡi",
  "tỷ hai", "tiền tỷ", "gần tỷ", "hơn trăm khách", "khoản đầu tư tỷ đồng"), "gấp đôi / gấp 3", "một nửa", "nửa số
  khách", "một phần ba", "hàng chục";
- phân số / tỷ số: "45/60", "chiếm 2/3", "đạt 3/5", "giảm 1/3", "1/3 số khách", "½";
- mã giả lạ (KH#… / NCC#… không có trong bảng của lượt chạy — mô hình bịa) và mã giả chép hỏng ("KH #0001", "KH0001");
- (render_insight, trên lời còn placeholder) số GHÉP quanh placeholder: "1{{a|so}}", "{{a|so}}.000", "1 {{a|so}}",
  "{{a|so}}{{b|so}}"; đơn vị nhân sau placeholder số "{{a|so}} triệu", "{{a|so}} trăm".
Giữ: năm 20xx; ngày d/m, d/m/yyyy, m/yyyy, năm/năm; mã có chữ đứng liền trước ("SR900") hoặc nối vào mã viết hoa
("KK-2026-002"); số ≤ 2 chữ số không kèm đơn vị ("trong 7 ngày", "quý 3", "top 5", "5:30", "12 khách"); "3 tỷ lệ …"
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


def fill(text: str, pack: dict, sections=None) -> Filled:
	"""Thay mọi `{{path|kiểu}}` trong `text` bằng giá trị đã định dạng lấy từ `pack` (bc.ai.registry.resolve).

	`sections`: tập khoá cấp 1 được phép (None = mọi mảng) — path ngoài tập → lỗi "ngoai-nhom:<p>".
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
		_them(out.paths, path)
		_them(out.sections_used, registry.section_of(path))
		return s

	out.text = registry.PLACEHOLDER.sub(thay, text)
	con = strip_placeholders(text)
	if "{" in con or "}" in con:
		_them(out.errors, "cu-phap")
	return out


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
# Đơn vị đứng SAU số (so từ ngay sau số; chữ phải hết từ: "5 khách", "7 trường hợp", "5 đơn" không dính).
_DON_VI = re.compile(
	r"\s*(?:[%‰٪₫$€]"
	rf"|(?:điểm\s+)?phần\s+trăm{_HET}"
	r"|điểm\s*%"
	rf"|(?:(?:trăm|chục)\s+)?(?:{_TY}|{_TRIEU}|nghìn|ngàn|vạn|tr|k)(?:\s*{_TIEN_TE})?{_HET}"
	rf"|trăm{_HET}"                             # "5 trăm khách" (chục thì như số < 100: giữ)
	rf"|{_TIEN_TE}{_HET})", re.I)
# Số: "1 250 000" (nhóm nghìn bằng dấu cách) hoặc dãy chữ số có thể kèm . , giữa các chữ số.
_SO = re.compile(r"\d{1,3}(?: \d{3})+(?!\d)(?:[.,]\d+)*|\d+(?:[.,]\d+)*")
_NAM = re.compile(r"20\d\d")
_NGAY_THANG = re.compile(r"(?<![\w/])(?<!\d[.,])(\d{1,2})/(\d{1,2})(?:/(\d{4}|\d{2}))?(?![\w/])(?![.,]\d)")
_THANG_NAM = re.compile(r"(?<![\w/])(?<!\d[.,])(\d{1,2})/(20\d\d)(?![\w/])(?![.,]\d)")
_PHAN_SO = re.compile(r"(?<![\w/])\d+(?:[.,]\d+)*\s*/\s*\d+(?:[.,]\d+)*")
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


def _chuan(text: str) -> str:
	"""NFKC (chữ số / % toàn chiều rộng, dấu cách đặc biệt, dấu tổ hợp → dạng thường) + bỏ ký tự vô hình (Cf) và dấu
	nhấn markdown * _ ` ~ (để "**2** tỷ", "__35__%" vẫn là "2 tỷ", "35%")."""
	s = unicodedata.normalize("NFKC", text)
	return "".join(ch for ch in s if unicodedata.category(ch) != "Cf" and ch not in "*_`~")


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


def _la_ma(s: str, a: int) -> bool:
	"""Chữ số tại s[a:] thuộc một MÃ: dính liền chữ cái đứng trước ("SR900"), hoặc nối bằng - / vào một mã viết HOA
	bắt đầu bằng chữ ("KK-2026-002", "ACC-SINV-2026-00012", "HGC/2026/001"). "giảm-150", "100-200" không phải mã.
	(Gạch dưới đã bị _chuan bỏ nên "KK_2026_002" thành dính liền chữ.)"""
	if a == 0:
		return False
	if s[a - 1].isalpha():
		return True
	if s[a - 1] not in "-/":
		return False
	j, dau = a, max(0, a - _CUA)
	while j > dau and (s[j - 1].isalnum() or s[j - 1] in "-/"):
		j -= 1
	if j > 0 and (s[j - 1].isalnum() or s[j - 1] in "-/"):       # dài quá _CUA ký tự: không phải mã
		return False
	return bool(_DAU_MA.fullmatch(s[j:a]))


def lint(text: str) -> list:
	"""Các mẩu "số trần" trong lời đã bỏ placeholder (rỗng = sạch). Bắt (đặc tả §5.3 bước 3):
	- dãy ≥ 3 chữ số không dính liền chữ cái đứng TRƯỚC (kể cả có dấu nhóm nghìn: "1.250.000", "1,250");
	- số (kể cả 1–2 chữ số, có thể có phần lẻ) đứng trước đơn vị: %, đ, ₫, k, tr, triệu, tỷ, nghìn ("35%", "2 tỷ",
	  "1,5 triệu", "50k").
	Ngoại lệ được giữ: năm 20xx; ngày d/m hoặc d/m/yyyy; mã có chữ đứng liền trước ("SR900"); số chỉ thời hạn ≤ 2 chữ
	số không kèm đơn vị trên ("trong 7 ngày", "30 ngày").
	Bắt thêm (xem docstring module): số có phần lẻ, số viết bằng chữ trước đơn vị lớn, "gấp đôi", phân số, mã giả lạ."""
	tho = "" if text is None else str(text)
	bat: list = [(-1, m.group(0)) for m in _PHAN_SO_KY_TU.finditer(tho)]
	s = _chuan(_PHAN_SO_KY_TU.sub(" ", tho))
	buf = list(s)

	def xoa(a: int, b: int, mau: str | None = None) -> None:
		"""Xoá s[a:b] (để lượt soát sau không bắt lại); có `mau` → ghi nhận là số trần. Chỗ đã xoá lấp bằng ký tự
		KHÔNG phải khoảng trắng để mẫu sau không bắc cầu qua ("khoảng 2/3 tỷ" không thành "khoảng tỷ")."""
		if mau is not None:
			bat.append((a, " ".join(mau.split())))
		buf[a:b] = _LAP * (b - a)

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
	for m in _PHAN_SO.finditer(s):
		xoa(m.start(), m.end(), None if _NAM_NAM.fullmatch(m.group(0)) else m.group(0))
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
	# 4. Số viết bằng chữ, bội số, phân số bằng chữ.
	for rx in _BANG_CHU:
		for m in rx.finditer(s):
			xoa(m.start(), m.end(), m.group(0))
		s = "".join(buf)
	out: list = []
	for _vt, mau in sorted(bat, key=lambda x: x[0]):
		_them(out, mau)
	return out


# Số do mô hình GHÉP quanh placeholder: chữ số dính liền ("1{{a|so}}", "{{a|so}}.000") hoặc đơn vị nhân đứng sau
# placeholder số ("{{a|so}} triệu") — lint trên lời đã bỏ placeholder không thấy được, phải soát trên lời gốc.
_PH = registry.PLACEHOLDER.pattern
_GHEP = (re.compile(r"\d[.,]?" + _PH), re.compile(_PH + r"[.,]?\d"))
# Cách một dấu cách, chỉ với placeholder kiểu so: "1 {{a|so}}" → "1 250"; "{{a|so}} 000" → "250 000". Số đứng trước
# phải là số RỜI 1–3 chữ số (đầu một nhóm nghìn): "5/11 {{a|so}}", "2026 {{a|so}}", "SR900 {{a|so}}" không phải ghép.
_GHEP_CACH = (re.compile(r"(?<![^\s(\[\"'“])\d{1,3} " + _PH), re.compile(_PH + r" \d{3}(?!\d)"))
# Hai placeholder SỐ dính nhau cũng thành một số không có thật: "{{a|so}}{{b|so}}" → "35", "{{a|so}},{{b|so}}" → "3,5";
# cách một dấu cách thì chỉ xét so + so ("3 250"). "{{a|so}}/{{b|so}}" (hai số thật) không bị bắt.
_GHEP_DOI = re.compile(_PH + r"([.,]?| )" + _PH)
# Đơn vị NHÂN sau placeholder số làm sai giá trị thật: "{{a|so}} triệu", "{{a|so}} trăm khách", "{{a|so}} chục".
_NHAN = re.compile(_PH + rf"\s*(?:(?:(?:trăm|chục)\s+)?(?:{_TY}|{_TRIEU}|nghìn|ngàn|vạn|tr|k)|trăm|chục){_HET}", re.I)


def _so_tran(text: str, mask=None) -> list:
	"""Số trần trong một đoạn lời của mô hình (còn placeholder, còn mã giả). Mã giả HỢP LỆ được bỏ trước (chữ số
	trong mã không phải số liệu; tên thật có thể chứa chữ số nên không bao giờ lint sau khi hoàn nguyên)."""
	goc = mask.strip(text) if mask is not None else text
	tho = unicodedata.normalize("NFKC", goc)
	out = [m.group(0) for rx in _GHEP for m in rx.finditer(tho)]
	out += [m.group(0) for rx in _GHEP_CACH for m in rx.finditer(tho) if m.group(2) == "so"]
	out += [m.group(0) for m in _GHEP_DOI.finditer(tho) if m.group(2) in SO_KIEU and m.group(5) in SO_KIEU
		and (m.group(3) != " " or m.group(2) == m.group(5) == "so")]
	out += [m.group(0) for m in _NHAN.finditer(tho) if m.group(2) in SO_KIEU]
	return out + lint(strip_placeholders(goc))


# ─── Dựng lời ────────────────────────────────────────────────────────────────
def _chuoi(v) -> str:
	return v if isinstance(v, str) else ""


def _mot_dong(s: str) -> str:
	return " ".join((s or "").split())


def _cat(s: str, n: int = TITLE_MAX) -> str:
	"""Cắt còn ≤ n ký tự (bị cắt thì kết bằng "…")."""
	return s if len(s) <= n else s[:n - 1].rstrip() + "…"


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


def render_insight(raw: dict, pack: dict, sections, mask=None) -> dict:
	"""Lời của MÔ HÌNH cho một nhận định → {"ok", "title", "body", "advice": [str], "paths", "sections_used", "errors"}.

	raw = {"title", "body", "advice": [str]} (đầu ra mô hình, còn placeholder và có thể còn mã giả KH#/NCC#).
	1. fill từng phần với `sections` = các mảng của NHÓM (path ngoài nhóm → lỗi);
	2. lint trên lời đã bỏ placeholder VÀ đã bỏ mã giả hợp lệ (mask.strip) — mã giả lạ (mô hình bịa) còn lại sẽ bị bắt;
	3. hoàn nguyên mã giả → tên thật (mask.unmask) trên lời đã thay số;
	4. title cắt 200 ký tự; advice bỏ dòng rỗng, tối đa 3.
	ok = False khi có bất kỳ lỗi nào (errors ghi lý do: lỗi của fill, "so-tran:<mẩu>", "rong" khi title / body rỗng)."""
	raw = raw if isinstance(raw, dict) else {}
	advice = raw.get("advice")
	advice = advice.splitlines() if isinstance(advice, str) else advice if isinstance(advice, (list, tuple)) else []
	advice = [a for a in (_DAU_DONG.sub("", _chuoi(x).strip()) for x in advice) if a][:ADVICE_MAX]
	errors, paths, secs, loi = [], [], [], []
	for text in (_chuoi(raw.get("title")), _chuoi(raw.get("body")), *advice):
		f = fill(text, pack, sections)
		_them(errors, *f.errors, *(f"so-tran:{mau}" for mau in _so_tran(text, mask)))
		_them(paths, *f.paths)
		_them(secs, *f.sections_used)
		loi.append(mask.unmask(f.text) if mask is not None else f.text)
	title, body, advice = _mot_dong(loi[0]), loi[1].strip(), [a for a in (_mot_dong(x) for x in loi[2:]) if a]
	if not title or not body:
		_them(errors, "rong")
	return {"ok": not errors, "title": _cat(title), "body": body, "advice": advice, "paths": paths,
		"sections_used": secs, "errors": errors}
