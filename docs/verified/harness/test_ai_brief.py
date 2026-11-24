"""Trợ lý AI P2 — bản tin tuần / tháng (bc.ai.brief, hợp đồng P2 §4, đặc tả §11).

Chạy bc.ai.brief.run_brief THẬT trên bảng thật (BC AI Run / Insight / Brief, BC Settings, Customer), chỉ thay
bc.ai.llm.call (mô hình giả ghi lại đề bài). Mạng bị chặn ở tầng socket. Số kỳ vọng TÍNH TAY từ các dòng Run chèn
trong file (ghi ở comment).

Phần:
A. kỳ (period) trên nhiều "hôm nay": thứ Hai, giữa tuần, Chủ nhật, mùng 1, mùng 2, tháng Giêng, năm nhuận
B. số KPI tuần trên dòng Run chèn thật: ảnh chụp muộn nhất mỗi ngày, ngày thiếu, tuần thiếu, gốc 0, gốc âm, ít lịch sử,
   chỉ dòng tổng ok ngay / tay, JSON hỏng, KPI cộng dồn (vá registry.KPI_TICH_LUY)
C. số KPI tháng (12 tháng, cùng kỳ, gốc 0)
D. gói bản tin + kinds
E. nhận định của kỳ (mở / đóng / tồn, ngưỡng 7 / 30 ngày, bo-qua, quan-tri, mảng ẩn)
F. bản tin theo quy tắc (hàm thuần)
G. bản tin AI qua mô hình giả: đề bài sạch, mục có số viết tay / sai kiểu / mảng ẩn / mã bịa bị bỏ, sections mỗi mục
H. mọi lý do bỏ bước AI + lỗi lượt gọi
I. chạy lại cùng tuần / tháng ghi đè cùng bản tin
J. khoá riêng, không bao giờ ném, user, không lưu đề bài

Chạy: BC_TEST_DB=bc_test_ai_p2c python3 -B test_ai_brief.py
"""
import datetime
import json
import socket

from seed import Check, bc_settings, child, insert, reset, single
from paths import DB

import frappe  # noqa: E402  (giả)
import frappe.utils as fu  # noqa: E402

c = Check()
D, d = datetime.datetime, datetime.date
INSIGHT, RUN, BRIEF = "BC AI Insight", "BC AI Run", "BC AI Brief"
KEY = "sk-ant-api03-KHOAGIA-brief-4Tq8NvR2xL"
TEN = "Đại lý Minh Phát"          # tên thật của khách NPP-A — không được rời máy chủ
DEEP, DAILY = "claude-opus-5-5", "claude-sonnet-5-5"


def eq(label, got, want):
	c(label, got == want, f"\n      được: {got!r}\n      cần : {want!r}")


def nem(fn, loi=Exception):
	try:
		fn()
	except loi:
		return True
	except BaseException:  # noqa: BLE001
		return False
	return False


class MangBiChan(RuntimeError):
	pass


def _chan(fn):
	def g(self, addr, *a, **k):
		if self.family in (socket.AF_INET, socket.AF_INET6):
			raise MangBiChan(f"bộ thử chặn mạng: {addr}")
		return fn(self, addr, *a, **k)
	return g


def _dns(*a, **k):
	raise MangBiChan("bộ thử chặn DNS")


socket.socket.connect, socket.socket.connect_ex = _chan(socket.socket.connect), _chan(socket.socket.connect_ex)
socket.getaddrinfo = socket.create_connection = _dns

reset(only={INSIGHT, RUN, BRIEF, "Customer", "Supplier", "BC AI Rule", "BC AI Model Price", "BC Tet Date",
	"BC Hidden Item", "BC Share Link"})
c("chặn mạng: MariaDB vẫn chạy, socket AF_INET nổ", frappe.db.sql("SELECT 1")[0][0] == 1
	and nem(lambda: socket.socket(socket.AF_INET).connect(("127.0.0.1", 9)), MangBiChan))
bc_settings()
insert("Customer", name="NPP-A", customer_name=TEN)

from bc.ai import brief, jobs, llm, prompt, registry, render, store  # noqa: E402

P1 = "cong-no.receivables.kpis.overdue"          # tien — "Nợ phải thu quá hạn"
P2 = "cong-no.receivables.kpis.overdue_pct"      # pct
P3 = "tong-quan.summary.rows[0].sales"           # cộng dồn (luỹ kế năm tài chính)
P4 = "nhan-su.overview.nhan_su.dang_lam"         # so
P5 = "phai-tra.payables.ap.total"                # chỉ có ở tuần trước
P6 = "cong-no.receivables.kpis.net"              # tien, gốc âm
P7 = "ton-kho.overview.value.totals.value"       # chỉ có tuần này (ít lịch sử)
P8 = "cong-no.receivables.kpis.receivable"       # đổi 5 % — không đáng chú ý
NHAN = {p: n for p, _k, n in registry.KPIS}
c("các path thử nằm trong KPIS; P3 cộng dồn, P1 / P2 / P6 / P8 thì không (hằng số thật)",
	all(p in NHAN for p in (P1, P2, P3, P4, P5, P6, P7, P8)) and P3 in registry.KPI_TICH_LUY
	and not {P1, P2, P6, P8} & set(registry.KPI_TICH_LUY))


def run_row(started, kpis, status="ok", run_type="ngay", step="tong"):
	insert(RUN, step=step, status=status, run_type=run_type, started=started, provider=None,
		kpis=kpis if isinstance(kpis, str) else json.dumps(kpis))


def xoa(*doctypes):
	for dt in doctypes:
		frappe.db.sql(f"DELETE FROM `tab{dt}`")


def hom_nay(day, h=6, m=0):
	fu.FAKE_TODAY = day
	fu.FAKE_NOW_TIME = datetime.time(h, m)


# ═══════════════════════════════════════════════════════════════════════════
print("A. Kỳ")
for today, want in [
	(d(2026, 11, 23), (d(2026, 11, 16), d(2026, 11, 22), d(2026, 11, 23))),    # thứ Hai: tuần vừa xong hôm qua
	(d(2026, 11, 25), (d(2026, 11, 16), d(2026, 11, 22), d(2026, 11, 23))),    # thứ Tư
	(d(2026, 11, 29), (d(2026, 11, 16), d(2026, 11, 22), d(2026, 11, 23))),    # Chủ nhật: tuần này CHƯA trọn
	(d(2026, 11, 30), (d(2026, 11, 23), d(2026, 11, 29), d(2026, 11, 30))),
	(d(2027, 1, 5), (d(2026, 12, 28), d(2027, 1, 3), d(2027, 1, 4))),         # qua năm
]:
	eq(f"tuần, hôm nay {today}", brief.period("tuan", today), want)
for today, want in [
	(d(2026, 11, 1), (d(2026, 10, 1), d(2026, 10, 31), d(2026, 11, 1))),      # mùng 1
	(d(2026, 11, 2), (d(2026, 10, 1), d(2026, 10, 31), d(2026, 11, 1))),      # mùng 2 (scheduler)
	(d(2026, 11, 30), (d(2026, 10, 1), d(2026, 10, 31), d(2026, 11, 1))),
	(d(2027, 1, 2), (d(2026, 12, 1), d(2026, 12, 31), d(2027, 1, 1))),        # tháng Giêng
	(d(2028, 3, 1), (d(2028, 2, 1), d(2028, 2, 29), d(2028, 3, 1))),          # năm nhuận
]:
	eq(f"tháng, hôm nay {today}", brief.period("thang", today), want)
c("loại lạ → ValueError", nem(lambda: brief.period("nam", d(2026, 1, 1)), ValueError))
eq("kỳ lùi: tuần cách 7 tuần", brief._ky_lui("tuan", d(2026, 11, 16), 7), (d(2026, 9, 28), d(2026, 10, 4)))
eq("kỳ lùi: tháng Giêng lùi 1 / 12 tháng", (brief._ky_lui("thang", d(2027, 1, 1), 1), brief._ky_lui("thang",
	d(2027, 1, 1), 12)), ((d(2026, 12, 1), d(2026, 12, 31)), (d(2026, 1, 1), d(2026, 1, 31))))

# ═══════════════════════════════════════════════════════════════════════════
print("B. KPI tuần (hôm nay thứ Hai 23/11/2026 → kỳ 16–22/11)")
# Tuần: W0 16–22/11, W1 9–15/11, W2 2–8/11, W3 26/10–1/11 (trống), W4 19–25/10, W5 12–18/10, W6 5–11/10 (trống),
# W7 28/9–4/10; 27/9 thuộc tuần thứ 9 → ngoài 8 tuần.


def nap_tuan():
	xoa(RUN)
	run_row(D(2026, 9, 27, 5, 30), {P1: 1000000})
	run_row(D(2026, 10, 4, 5, 30), {P1: 200000000})
	run_row(D(2026, 10, 18, 5, 30), {P1: 60000000})
	run_row(D(2026, 10, 25, 5, 30), {P1: 150000000})
	run_row(D(2026, 11, 8, 5, 30), {P1: 80000000})
	run_row(D(2026, 11, 13, 5, 30), {P1: 90000000})
	run_row(D(2026, 11, 14, 5, 30), {P1: 100000000, P2: 20.0, P3: 400, P4: 0, P5: 7000000, P6: -100000000,
		P8: 100000000})                                      # thứ Bảy W1 (Chủ nhật 15/11 thiếu)
	run_row(D(2026, 11, 20, 5, 30), "{}")                  # ảnh chụp rỗng → bỏ
	run_row(D(2026, 11, 21, 5, 30), "[1, 2]")               # JSON không phải dict → bỏ (cột JSON chặn JSON hỏng)
	run_row(D(2026, 11, 22, 5, 30), {P1: 1, P2: 99.0, P5: 1})   # lượt sớm trong ngày: thua lượt muộn (cả ảnh chụp)
	run_row(D(2026, 11, 22, 14, 0), {P1: 120000000, P2: 25.0, P3: 500, P4: 5, P6: -50000000, P7: 3000000000,
		P8: 105000000, "khong.phai.kpi": 1, P5: "chuoi"}, run_type="tay")
	run_row(D(2026, 11, 22, 23, 0), {P1: 2}, status="loi")            # lượt hỏng → bỏ
	run_row(D(2026, 11, 22, 23, 10), {P1: 3}, run_type="tuan")        # không phải lượt ngày → bỏ
	run_row(D(2026, 11, 22, 23, 20), {P1: 4}, step="kinh-doanh")      # không phải dòng tổng → bỏ
	run_row(D(2026, 11, 23, 5, 30), {P1: 999000000})                  # hôm nay: ngoài kỳ


nap_tuan()
TU, DEN, _BD = brief.period("tuan", d(2026, 11, 23))
SN = brief.snapshots(brief._ky_lui("tuan", TU, 7)[0], DEN)
eq("ảnh chụp: đúng các ngày (bỏ rỗng, không phải dict, ngoài khoảng, lượt không phải ngày / tay ok)", sorted(SN),
	[d(2026, 10, 4), d(2026, 10, 18), d(2026, 10, 25), d(2026, 11, 8), d(2026, 11, 13), d(2026, 11, 14),
	d(2026, 11, 22)])
eq("ảnh chụp 22/11 = của lượt MUỘN nhất trong ngày", SN[d(2026, 11, 22)][P1], 120000000)
ROWS = brief.kpi_rows("tuan", TU, SN, tich_luy=frozenset({P3}))
eq("P1 (tien): đủ phép so", ROWS[P1], {"nhan": NHAN[P1], "gia_tri": 120000000,
	"tuan_truoc": 100000000, "d_tuan": 20000000, "d_tuan_pct": 20.0,                # W1: thứ Bảy 14/11 (CN thiếu)
	"bon_tuan_truoc": 150000000, "d_4tuan": -30000000, "d_4tuan_pct": -20.0,         # W4: 25/10
	"min_8t": 60000000, "max_8t": 200000000})                                         # 120,100,80,150,60,200 (27/9 ngoài)
eq("P2 (pct): không có tuần thứ 4 → không bon_tuan_truoc / d_4tuan", ROWS[P2], {"nhan": NHAN[P2], "gia_tri": 25.0,
	"tuan_truoc": 20.0, "d_tuan": 5.0, "d_tuan_pct": 25.0, "min_8t": 20.0, "max_8t": 25.0})
eq("P3 cộng dồn: chỉ nhan + gia_tri", ROWS[P3], {"nhan": NHAN[P3], "gia_tri": 500})
eq("P4 gốc 0: có d_tuan, KHÔNG có d_tuan_pct (không phải 0)", ROWS[P4], {"nhan": NHAN[P4], "gia_tri": 5,
	"tuan_truoc": 0, "d_tuan": 5, "min_8t": 0, "max_8t": 5})
c("P5: không có giá trị tuần này (lượt muộn không có số, chuỗi không phải số) → không có mục", P5 not in ROWS)
eq("P6 gốc âm: -100 tr → -50 tr = tăng 50 %", (ROWS[P6]["d_tuan"], ROWS[P6]["d_tuan_pct"]), (50000000, 50.0))
eq("P7 một tuần lịch sử: chỉ nhan + gia_tri (min / max cần ≥ 2 điểm)", ROWS[P7], {"nhan": NHAN[P7],
	"gia_tri": 3000000000})
c("path lạ trong ảnh chụp không thành KPI", set(ROWS) <= set(NHAN))
_cu = registry.KPI_TICH_LUY
registry.KPI_TICH_LUY = frozenset({P1})
try:
	R2 = brief.kpi_rows("tuan", TU, SN)          # mặc định đọc registry.KPI_TICH_LUY
finally:
	registry.KPI_TICH_LUY = _cu
eq("vá KPI_TICH_LUY = {P1}: P1 chỉ còn nhan + gia_tri, P3 (không còn cộng dồn) có phép so",
	(R2[P1], R2[P3].get("d_tuan")), ({"nhan": NHAN[P1], "gia_tri": 120000000}, 100))
c("mặc định = hằng số thật: P3 chỉ gia_tri", brief.kpi_rows("tuan", TU, SN)[P3] == {"nhan": NHAN[P3], "gia_tri": 500})
eq("không ảnh chụp nào → không KPI nào", brief.kpi_rows("tuan", TU, {}), {})
xoa(RUN)
run_row(D(2026, 11, 22, 5, 30), {P1: 100})
SN1 = brief.snapshots(d(2026, 9, 28), DEN)
eq("tuần đầu tiên có số (chưa có lịch sử): chỉ gia_tri", brief.kpi_rows("tuan", TU, SN1)[P1],
	{"nhan": NHAN[P1], "gia_tri": 100})
run_row(D(2026, 11, 10, 5, 30), {P1: 80})
eq("tuần thứ hai: so tuần trước, min / max 2 điểm, chưa có 4 tuần", brief.kpi_rows("tuan", TU,
	brief.snapshots(d(2026, 9, 28), DEN))[P1], {"nhan": NHAN[P1], "gia_tri": 100, "tuan_truoc": 80, "d_tuan": 20,
	"d_tuan_pct": 25.0, "min_8t": 80, "max_8t": 100})

# ═══════════════════════════════════════════════════════════════════════════
print("C. KPI tháng (hôm nay 2/11/2026 → kỳ tháng 10)")
xoa(RUN)
run_row(D(2025, 9, 30, 5, 30), {P1: 1})              # tháng thứ 14 → ngoài
run_row(D(2025, 10, 31, 5, 30), {P1: 50, P4: 0})     # cùng kỳ (M12) — KHÔNG thuộc min / max 12 tháng
run_row(D(2025, 11, 30, 5, 30), {P1: 100})           # M11
run_row(D(2026, 7, 31, 5, 30), {P1: 400})            # M3
run_row(D(2026, 8, 31, 5, 30), {P1: 500})            # M2
run_row(D(2026, 9, 29, 5, 30), {P1: 200})            # M1 (30/9 thiếu → ngày 29)
run_row(D(2026, 10, 31, 5, 30), {P1: 300, P4: 5})    # M0
run_row(D(2026, 11, 1, 5, 30), {P1: 999})            # sau kỳ
TU_T, DEN_T, BD_T = brief.period("thang", d(2026, 11, 2))
SNT = brief.snapshots(brief._ky_lui("thang", TU_T, 12)[0], DEN_T)
c("ảnh chụp tháng: từ mùng 1 của tháng cùng kỳ năm trước tới hết kỳ", min(SNT) == d(2025, 10, 31)
	and max(SNT) == d(2026, 10, 31))
RT = brief.kpi_rows("thang", TU_T, SNT, tich_luy=frozenset())
eq("P1 tháng: đủ phép so", RT[P1], {"nhan": NHAN[P1], "gia_tri": 300, "thang_truoc": 200, "d_thang": 100,
	"d_thang_pct": 50.0, "ba_thang_truoc": 400, "d_3thang": -100, "d_3thang_pct": -25.0, "cung_ky": 50,
	"d_nam_pct": 500.0, "min_12t": 100, "max_12t": 500})
eq("P4 tháng: cùng kỳ 0 → có cung_ky, không d_nam_pct; tháng trước thiếu; một điểm → không min / max", RT[P4],
	{"nhan": NHAN[P4], "gia_tri": 5, "cung_ky": 0})
c("tháng: không có khoá d_nam (chỉ d_nam_pct)", "d_nam" not in RT[P1])

# ═══════════════════════════════════════════════════════════════════════════
print("D. Gói bản tin + kinds")
PK, KN, GOC = brief.build_pack("tuan", ROWS)
B1 = "cong-no._tuan.cong_no_receivables_kpis_overdue"
eq("đường dẫn: <mảng>._tuan.<slug>", GOC[P1], B1)
eq("phân giải trên gói", (registry.resolve(PK, B1 + ".gia_tri"), registry.resolve(PK, B1 + ".nhan")),
	(120000000, NHAN[P1]))
eq("mảng của gói = đoạn đầu path KPI", sorted(PK), ["cong-no", "nhan-su", "ton-kho", "tong-quan"])
eq("kinds P1: tien, *_pct → pct", {k.rsplit(".", 1)[1]: v for k, v in KN.items() if k.startswith(B1 + ".")},
	{"gia_tri": "tien", "tuan_truoc": "tien", "d_tuan": "tien", "d_tuan_pct": "pct", "bon_tuan_truoc": "tien",
	"d_4tuan": "tien", "d_4tuan_pct": "pct", "min_8t": "tien", "max_8t": "tien"})
eq("kinds P2 (KPI pct): d_tuan cũng pct", KN["cong-no._tuan.cong_no_receivables_kpis_overdue_pct.d_tuan"], "pct")
eq("kinds P4 (so)", KN["nhan-su._tuan.nhan_su_overview_nhan_su_dang_lam.d_tuan"], "so")
c("kinds: không có nhan, không path thừa", not any(k.endswith(".nhan") for k in KN)
	and all(registry.has(PK, k) for k in KN))
eq("tháng: khối _thang", sorted(brief.build_pack("thang", RT)[0]["cong-no"]), ["_thang"])

# ═══════════════════════════════════════════════════════════════════════════
print("E. Nhận định của kỳ")


def ins(key, *, status="mo", sev="vang", aud="lanh-dao", section="cong-no", secs=None, title=None, rule_title="",
		first=None, closed=None, rank=0, body="", admin_note="", mute=None):
	return insert(INSIGHT, name=key, signal_key=key, rule=key.split(":")[0], section=section,
		sections_used="\n".join(secs or [section]), audience=aud, severity=sev, status=status, source="quy-tac",
		title=title or key, rule_title=rule_title, body=body, advice="", first_seen=first, last_seen=first,
		closed_on=closed, rank=rank, admin_note=admin_note, mute_until=mute, seen_count=1)


xoa(INSIGHT)
ins("i.ton22", sev="do", first=D(2026, 11, 1, 5, 30), rank=2)                     # mở 22 ngày → ton
ins("i.ton7", first=D(2026, 11, 16, 23, 59), section="ton-kho")                     # 7 ngày (biên) → ton
ins("i.moi6", first=D(2026, 11, 17, 0, 1))                                          # 6 ngày, mở trong kỳ → moi
ins("i.dong", status="dong", first=D(2026, 11, 10, 5, 30), closed=D(2026, 11, 20, 5, 30), section="van-chuyen")
ins("i.dong_som", status="dong", first=D(2026, 11, 1), closed=D(2026, 11, 15, 23, 59))  # đóng trước kỳ → bỏ
ins("i.dong_sau", status="dong", first=D(2026, 11, 18), closed=D(2026, 11, 23, 5, 30))  # mở trong kỳ, đóng sau
ins("i.homnay", first=D(2026, 11, 23, 5, 30))                                       # sau kỳ, mới 0 ngày → bỏ
ins("i.boqua", status="bo-qua", first=D(2026, 11, 1))
ins("i.boqua2", status="bo-qua", first=D(2026, 11, 18))                            # bỏ qua, mở trong kỳ → bỏ
ins("i.qt", aud="quan-tri", section="he-thong", first=D(2026, 11, 1))
ins("i.an", first=D(2026, 11, 1), secs=["cong-no", "nhan-su"])                      # dùng số mảng ẩn → bỏ
ins("i.an2", first=D(2026, 11, 1), section="nhan-su")
ins("i.dxl", status="dang-xu-ly", first=D(2026, 10, 1), sev="do", rank=1)          # 53 ngày
NI = brief.period_insights("tuan", TU, DEN, d(2026, 11, 23), {"nhan-su"})
eq("chọn + phân loại (đỏ trước, kéo dài lâu trước)", [(x["name"], x["tinh_trang"], x["so_ngay"]) for x in NI],
	[("i.dxl", "ton", 53), ("i.ton22", "ton", 22), ("i.dong", "da-dong", 10), ("i.ton7", "ton", 7),
	("i.moi6", "moi", 6), ("i.dong_sau", "moi", 5)])
eq("không mảng ẩn: i.an / i.an2 có mặt", sorted(x["name"] for x in brief.period_insights("tuan", TU, DEN,
	d(2026, 11, 23), set()) if x["name"].startswith("i.an")), ["i.an", "i.an2"])
eq("sections = sections_used ∪ section", next(x for x in NI if x["name"] == "i.ton7")["sections"], ["ton-kho"])
NT = brief.period_insights("thang", d(2026, 10, 1), d(2026, 10, 31), d(2026, 11, 2), set())
eq("tháng (2/11, kỳ 10): ngưỡng 30 ngày — dang-xu-ly từ 1/10 (32 ngày) là ton; mở 1/11 (1 ngày) không vào",
	[(x["name"], x["tinh_trang"]) for x in NT], [("i.dxl", "ton")])
xoa(INSIGHT)
ins("t.30", first=D(2026, 10, 3, 9, 0))     # 2/11 − 3/10 = 30 ngày → ton (≥ 30)
ins("t.29", first=D(2026, 10, 4, 9, 0))     # 29 ngày, ngoài kỳ tháng 10? 4/10 thuộc kỳ → moi
ins("t.29b", first=D(2026, 11, 1, 0, 0))    # 1 ngày, sau kỳ → bỏ
eq("biên 30 ngày (tháng)", [(x["name"], x["tinh_trang"]) for x in brief.period_insights("thang", d(2026, 10, 1),
	d(2026, 10, 31), d(2026, 11, 2), set())], [("t.30", "ton"), ("t.29", "moi")])

# ═══════════════════════════════════════════════════════════════════════════
print("F. Bản tin theo quy tắc (hàm thuần)")
F_ROWS = {P1: ROWS[P1], P2: ROWS[P2], P3: ROWS[P3], P4: ROWS[P4], P6: ROWS[P6], P8: ROWS[P8]}
RP = brief.rule_parts("tuan", F_ROWS, [])
eq("ba phần, đúng tiêu đề tuần", [(p["key"], p["title"]) for p in RP], [("dang_chu_y", "Điều đáng chú ý"),
	("viec_ton", "Việc tồn chưa xử lý"), ("uu_tien", "Ưu tiên tuần tới")])
eq("đáng chú ý: |%| lớn nhất trước, ≥ 10 % (P8 5 % bỏ; P3 cộng dồn, P4 gốc 0 không có %)", RP[0]["items"], [
	{"text": "Phải thu ròng: -50 triệu, tăng 50,0% so với tuần trước (-100 triệu).", "sections": ["cong-no"]},
	{"text": "Tỷ lệ nợ quá hạn: 25,0%, tăng 5 điểm phần trăm so với tuần trước (20,0%).", "sections": ["cong-no"]},
	{"text": "Nợ phải thu quá hạn: 120 triệu, tăng 20,0% so với tuần trước (100 triệu).", "sections": ["cong-no"]}])
eq("tháng: tiêu đề phần ưu tiên", brief.rule_parts("thang", {}, [])[2]["title"], "Ưu tiên tháng tới")
many = {f"x{i}": {"nhan": f"Chỉ số {i}", "gia_tri": 100 + i, "tuan_truoc": 100, "d_tuan": i, "d_tuan_pct": float(i)}
	for i in (9, 10, 11, 12, 13, 14, 15)}
many["x20"] = {"nhan": "Hai mươi", "gia_tri": 80, "tuan_truoc": 100, "d_tuan": -20, "d_tuan_pct": -20.0,
	"bon_tuan_truoc": 160, "d_4tuan": -80, "d_4tuan_pct": -50.0}
many["nhan-su.x"] = {"nhan": "Mảng ẩn", "gia_tri": 1, "tuan_truoc": 2, "d_tuan": -1, "d_tuan_pct": -50.0}
RPm = brief.rule_parts("tuan", many, [])[0]["items"]
eq("tối đa 5, |%| lớn nhất trước (bằng nhau → theo path), mỗi KPI lấy phép so có |%| lớn nhất (x20: bốn tuần)",
	[t["text"].split(":")[0] for t in RPm], ["Mảng ẩn", "Hai mươi", "Chỉ số 15", "Chỉ số 14", "Chỉ số 13"])
eq("lời x20: giảm, so với bốn tuần trước (KPI ngoài KPIS → kiểu so)", RPm[1]["text"],
	"Hai mươi: 80, giảm 50,0% so với bốn tuần trước (160).")
eq("KPI mảng ẩn vẫn vào bản quy tắc, chỉ mang mảng của nó (API lọc theo người xem)", RPm[0]["sections"], ["nhan-su"])
few = {"a": {"nhan": "Mười", "gia_tri": 110, "tuan_truoc": 100, "d_tuan": 10, "d_tuan_pct": 10.0},
	"b": {"nhan": "Chín", "gia_tri": 109.99, "tuan_truoc": 100, "d_tuan": 9.99, "d_tuan_pct": 9.99}}
eq("biên: 10 % vào, 9,99 % không", [t["text"].split(":")[0] for t in brief.rule_parts("tuan", few, [])[0]["items"]],
	["Mười"])


def nd(name, tt, so_ngay, sev="vang", status="mo", rank=0, secs=("cong-no",)):
	return {"name": name, "severity": sev, "status": status, "tinh_trang": tt, "so_ngay": so_ngay,
		"section": secs[0], "sections": list(secs), "title": f"Tiêu đề {name}", "rule_title": "", "rank": rank}


NDS = [nd(f"t{i}", "ton", 10 + i) for i in range(7)] + [nd("m1", "moi", 3, sev="do", rank=4),
	nd("r1", "ton", 8, sev="do", rank=2, secs=("ton-kho", "han-dung")), nd("r0", "moi", 2, sev="do", rank=0),
	nd("r3", "ton", 9, sev="do", rank=1), nd("rd", "da-dong", 30, sev="do", status="dong", rank=1)]
RPi = brief.rule_parts("tuan", {}, NDS)
eq("việc tồn: tối đa 5 nhận định ton kéo dài lâu nhất, chữ = tiêu đề đã lưu", [t["text"] for t in RPi[1]["items"]],
	[f"Tiêu đề t{i}" for i in (6, 5, 4, 3, 2)])
eq("ưu tiên: tối đa 3 nhận định ĐỎ đang mở theo rank (rank 0 cuối; đã đóng không vào)",
	[t["text"] for t in RPi[2]["items"]], ["Tiêu đề r3", "Tiêu đề r1", "Tiêu đề m1"])
eq("mục nhận định mang đúng mảng của nó", RPi[2]["items"][1]["sections"], ["ton-kho", "han-dung"])
eq("không gì cả → ba phần rỗng", [len(p["items"]) for p in brief.rule_parts("tuan", {}, [])], [0, 0, 0])
eq("tiêu đề mặc định", (brief.default_title("tuan", d(2026, 11, 16), d(2026, 11, 22)),
	brief.default_title("thang", d(2026, 10, 1), d(2026, 10, 31))),
	("Bản tin tuần 16/11 – 22/11/2026", "Bản tin tháng 10/2026"))

# ═══════════════════════════════════════════════════════════════════════════
print("G. Bản tin AI qua mô hình giả")
frappe.conf["bc_ai_anthropic_key"] = KEY
single("BC Settings", ai_enabled=1, ai_mask_parties=1, ai_cap_claude_usd=90, ai_claude_model=DAILY,
	ai_claude_model_deep=DEEP, ai_context="BOI-CANH-CONG-TY-RVHG", hidden_sections="nhan-su")
child("BC Settings", "BC Settings", "BC AI Model Price", "ai_prices",
	[{"model": DEEP, "price_in": 15, "price_out": 75}, {"model": DAILY, "price_in": 3, "price_out": 15}])

GOI, KB = [], {}


def fake_call(provider, model, system, user, schema_name, schema, max_tokens=16000, timeout=300):
	obj = json.loads(user)
	GOI.append({"provider": provider, "model": model, "system": system, "user": user, "obj": obj,
		"schema_name": schema_name, "schema": schema, "timeout": timeout, "user_phien": frappe.session.user})
	f = KB.get("f")
	if f is None:
		return {"data": {"title": "", "dang_chu_y": [], "viec_ton": [], "uu_tien": []}, "tokens_in": 10,
			"tokens_out": 1, "model": model}
	return f(obj)


llm.call = fake_call


def nap_insight():
	xoa(INSIGHT)
	ins("cn.qua_han_lon", sev="do", first=D(2026, 11, 1, 5, 30), rank=1, title="Lời AI cho IA",
		rule_title=f"Khách {TEN} quá hạn 50 triệu", body="THAN-BI-MAT", admin_note="GHI-CHU-BI-MAT")
	ins("kho.ton_chet", first=D(2026, 11, 18, 5, 30), section="ton-kho", secs=["ton-kho", "han-dung"],
		title="Tồn chết tăng ở phiếu KK-2026-002", body="THAN-BI-MAT-2")
	ins("vc.cho_qua_han", status="dong", first=D(2026, 11, 10, 5, 30), closed=D(2026, 11, 20, 5, 30),
		section="van-chuyen", title="Đơn chờ giao quá hạn")
	ins("ns.viec_ton", first=D(2026, 11, 1), section="nhan-su", title="NHAN-SU-AN")
	ins("kho.am", status="bo-qua", first=D(2026, 11, 18), section="han-dung", title="BO-QUA-AN")
	ins("ht.loi", aud="quan-tri", section="he-thong", first=D(2026, 11, 1), title="HE-THONG-AN")


S = "cong-no._tuan.cong_no_receivables_kpis_overdue"
TK = "ton-kho._tuan.ton_kho_overview_value_totals_value"
NS = "nhan-su._tuan.nhan_su_overview_nhan_su_dang_lam"
SAU = "MUC-THU-SAU không được xét"


def tra_loi(obj):
	ma = next((m for x in obj["nhan_dinh"] for m in __import__("re").findall(r"KH#\d+", x["tieu_de"])), "KH#0000")
	return {"data": {"title": "Nợ quá hạn tăng, tồn kho cần theo dõi",
		"dang_chu_y": [
			f"Nợ quá hạn {{{{{S}.gia_tri|tien}}}}, tăng {{{{{S}.d_tuan_pct|pct}}}} so với tuần trước.",   # giữ
			"Nợ quá hạn tăng 20% so với tuần trước.",                                                    # số tay → bỏ
			f"Nhân sự đang làm {{{{{NS}.gia_tri|so}}}} người.",                                             # mảng ẩn → bỏ
			f"Tỷ lệ quá hạn đổi {{{{cong-no._tuan.cong_no_receivables_kpis_overdue_pct.d_tuan|tien}}}} trong kỳ.",  # sai kiểu
			f"Tồn kho {{{{{TK}.gia_tri|tien}}}}, cần kiểm tra: hàng chậm bán.",                            # giữ
			SAU],                                                                                         # mục thứ 6
		"viec_ton": [f"{ma} còn nợ quá hạn đã lâu, cần kiểm tra: kế hoạch thu tiền.",                     # giữ, ra tên
			"KH#9999 nợ lâu chưa trả."],                                                                  # mã bịa → bỏ
		"uu_tien": ["Kế toán: rà soát công nợ quá hạn trong tuần tới.",
			"Kho: đối chiếu lại phiếu KK-2026-002 trong tuần tới.",                                     # mã có trong đề bài
			"Kho: đối chiếu phiếu KK-2026-999."]},                                                        # mã bịa → bỏ
		"tokens_in": 2000, "tokens_out": 300, "model": DEEP}


nap_tuan()
nap_insight()
hom_nay(d(2026, 11, 23))
frappe.session.user = "viewer@example.com"
KB["f"] = tra_loi
GOI.clear()
n_tong = frappe.db.sql(f"SELECT COUNT(*) FROM `tab{RUN}` WHERE step = 'tong'")[0][0]
OUT = brief.run_brief("tuan")
c("render.forget_source() đã chạy (đề bài không ở lại bộ nhớ)", render._nguon.cache_info().currsize == 0)
eq("kết quả run_brief", {k: OUT.get(k) for k in ("status", "source", "ai", "items", "rejected")},
	{"status": "ok", "source": "ai", "ai": "ok", "items": 5, "rejected": 5})
c("một lượt gọi, provider claude, model deep, schema ban_tin", len(GOI) == 1 and GOI[0]["provider"] == "claude"
	and GOI[0]["model"] == DEEP and GOI[0]["schema_name"] == "ban_tin" and GOI[0]["schema"] is brief.SCHEMA)
c("schema ban_tin chặt: additionalProperties False + required đủ", brief.SCHEMA["additionalProperties"] is False
	and set(brief.SCHEMA["required"]) == set(brief.SCHEMA["properties"]) == {"title", "dang_chu_y", "viec_ton",
	"uu_tien"})
G0 = GOI[0]
U, SYS, OBJ = G0["user"], G0["system"], G0["obj"]
c("chạy dưới Administrator, trả lại user cũ", G0["user_phien"] == "Administrator"
	and frappe.session.user == "viewer@example.com")
for bi_mat in (TEN, "THAN-BI-MAT", "GHI-CHU-BI-MAT", "NHAN-SU-AN", "BO-QUA-AN", "HE-THONG-AN", "nhan_su_overview",
		"Lời AI cho IA", KEY):
	c(f"đề bài (user + system) không chứa {bi_mat!r}", bi_mat not in U and bi_mat not in SYS)
eq("user: đúng các khoá", sorted(OBJ), ["kieu", "ky", "loai", "nhan_dinh", "pack"])
eq("ky / loai", (OBJ["loai"], OBJ["ky"]), ("tuan", {"tu": "2026-11-16", "den": "2026-11-22"}))
eq("pack: chỉ mảng không ẩn", sorted(OBJ["pack"]), ["cong-no", "ton-kho", "tong-quan"])
eq("pack: số đã tính sẵn (P1)", OBJ["pack"]["cong-no"]["_tuan"]["cong_no_receivables_kpis_overdue"]["d_tuan_pct"], 20.0)
c("kieu: đúng path của gói đã gửi, *_pct → pct, không mảng ẩn", OBJ["kieu"] and all(registry.has(OBJ["pack"], p)
	for p in OBJ["kieu"]) and all(v == "pct" for p, v in OBJ["kieu"].items() if p.endswith("_pct"))
	and not any(p.startswith("nhan-su") for p in OBJ["kieu"]))
eq("nhan_dinh: chỉ khoá đã chốt, đỏ trước rồi lâu trước", [(x["id"], x["muc"], x["tinh_trang"], x["so_ngay"], x["mang"])
	for x in OBJ["nhan_dinh"]], [("N1", "do", "ton", 22, "cong-no"), ("N2", "vang", "da-dong", 10, "van-chuyen"),
	("N3", "vang", "moi", 5, "ton-kho")])
c("nhan_dinh: mỗi dòng đúng 6 khoá", all(set(x) == {"id", "muc", "tinh_trang", "so_ngay", "mang", "tieu_de"}
	for x in OBJ["nhan_dinh"]))
c("tieu_de: rule_title khi có (tên khách thành mã giả), không thì title", OBJ["nhan_dinh"][0]["tieu_de"].startswith(
	"Khách KH#") and "quá hạn 50 triệu" in OBJ["nhan_dinh"][0]["tieu_de"] and OBJ["nhan_dinh"][2]["tieu_de"] == "Tồn chết tăng ở phiếu KK-2026-002")
c("system: luật placeholder DÙNG CHUNG với lượt ngày + bối cảnh công ty + mốc thời gian", prompt._PLACEHOLDER in SYS
	and "BOI-CANH-CONG-TY-RVHG" in SYS and "Hôm nay: 23/11/2026" in SYS and "LUẬT VIẾT BẢN TIN" in SYS)
c("system không chứa số liệu của gói", "120000000" not in SYS and "cong_no_receivables" not in SYS)

BR = store.latest_briefs(("tuan",))[0]
eq("bản tin: loại, ngày, kỳ, nguồn, model thực", (BR["brief_type"], BR["brief_date"], BR["period_from"],
	BR["period_to"], BR["source"], BR["model"]), ("tuan", d(2026, 11, 23), d(2026, 11, 16), d(2026, 11, 22), "ai", DEEP))
eq("tiêu đề AI", BR["title"], "Nợ quá hạn tăng, tồn kho cần theo dõi")
eq("mục giữ lại, số đã thay, mã giả về tên thật", [[it["text"] for it in p["items"]] for p in BR["parts"]], [
	["Nợ quá hạn 120 triệu, tăng 20,0% so với tuần trước.", "Tồn kho 3 tỷ, cần kiểm tra: hàng chậm bán."],
	[f"{TEN} còn nợ quá hạn đã lâu, cần kiểm tra: kế hoạch thu tiền."],
	["Kế toán: rà soát công nợ quá hạn trong tuần tới.", "Kho: đối chiếu lại phiếu KK-2026-002 trong tuần tới."]])
THAY = {"cong-no", "ton-kho", "tong-quan", "van-chuyen", "han-dung"}
c("MỌI mục AI mang MỌI mảng mô hình đã thấy (gói + nhận định), không mảng ẩn",
	all(set(it["sections"]) == THAY for p in BR["parts"] for it in p["items"]),
	[it["sections"] for p in BR["parts"] for it in p["items"]])
eq("sections_used của bản tin", set(BR["sections_used"]), THAY)
c("mục thứ 6 không được xét", SAU not in json.dumps(BR, default=str, ensure_ascii=False))
RR = frappe.db.sql(f"SELECT * FROM `tab{RUN}` WHERE step = 'ban-tin:tuan'", as_dict=True)
eq("một dòng Run ban-tin:tuan", len(RR), 1)
R0 = RR[0]
eq("dòng Run: loại, provider, model, trạng thái, token, đếm", (R0.run_type, R0.provider, R0.model, R0.status,
	R0.tokens_in, R0.tokens_out, R0.insights_ai, R0.rejected, R0.signals, R0.run_id, R0.error),
	("tuan", "claude", DEEP, "ok", 2000, 300, 5, 5, 3, None, None))
c("chi phí = 2000 × 15 + 300 × 75 trên 1 triệu = 0,0525 USD", abs(float(R0.cost_usd) - 0.0525) < 1e-9
	and int(R0.cost_known) == 1, R0.cost_usd)
eq("không thêm dòng tổng", frappe.db.sql(f"SELECT COUNT(*) FROM `tab{RUN}` WHERE step = 'tong'")[0][0], n_tong)
eq("đúng mục bị loại (render_text tự kiểm): số tay / mảng ẩn / sai kiểu / mã bịa", [
	any(e.startswith(p) for e in render.render_text(t, brief.build_pack("tuan", brief.kpi_rows("tuan", TU, SN))[0],
		{"cong-no", "ton-kho", "tong-quan"}, kinds=brief.build_pack("tuan", brief.kpi_rows("tuan", TU, SN))[1],
		nguon=U)["errors"]) for t, p in [
		("Nợ quá hạn tăng 20% so với tuần trước.", "so-tran"), (f"Nhân sự đang làm {{{{{NS}.gia_tri|so}}}} người.",
		"ngoai-nhom"), ("Tỷ lệ quá hạn đổi {{cong-no._tuan.cong_no_receivables_kpis_overdue_pct.d_tuan|tien}} trong kỳ.",
		"kieu"), ("KH#9999 nợ lâu chưa trả.", "so-tran"), ("Kho: đối chiếu phiếu KK-2026-999.", "so-tran")]],
	[True, True, True, True, True])
c("… mã KK-2026-999 chỉ bị bắt khi xét đề bài (nguon)", render.render_text("Kho: đối chiếu phiếu KK-2026-999.", {},
	set())["ok"])

# Đề bài quá dài → bớt nhận định ở cuối; mã giả của nhận định bị bớt KHÔNG còn là "đã gửi" (mô hình chép → bị loại,
# không thành tên thật).
TEN2 = "Công ty Bình An Phát"
insert("Customer", name="NPP-B", customer_name=TEN2)
ins("cn.binh_an", first=D(2026, 11, 22, 5, 30), rule_title=f"Khách {TEN2} chậm trả")
KB["f"] = None
GOI.clear()
brief.run_brief("tuan")
NDF = GOI[0]["obj"]["nhan_dinh"]
MA2 = __import__("re").search(r"KH#\d+", NDF[-1]["tieu_de"]).group(0)
c("nhận định Bình An đứng cuối, tên đã che", NDF[-1]["mang"] == "cong-no" and TEN2 not in GOI[0]["user"]
	and len(NDF) == 4, NDF)
_mc = prompt.MAX_CHARS
prompt.MAX_CHARS = len(GOI[0]["user"]) - 1
KB["f"] = lambda obj: {"data": {"title": "T", "dang_chu_y": [], "viec_ton": [f"{MA2} chậm trả, cần kiểm tra.",
	"Kế toán: theo dõi công nợ."], "uu_tien": []}, "tokens_in": 5, "tokens_out": 5, "model": DEEP}
GOI.clear()
try:
	o = brief.run_brief("tuan")
finally:
	prompt.MAX_CHARS = _mc
BR = store.latest_briefs(("tuan",))[0]
c("đề bài vượt trần → còn 2 nhận định, mã của nhận định bị bớt không có trong đề bài",
	len(GOI[0]["obj"]["nhan_dinh"]) == 2 and MA2 not in GOI[0]["user"], GOI[0]["obj"]["nhan_dinh"])
c("mục chép mã đã bị bớt → bị loại, không thành tên thật", o["rejected"] == 1 and o["items"] == 1
	and TEN2 not in json.dumps(BR, ensure_ascii=False, default=str), (o, BR["parts"]))
c("mục AI: sections = mảng đã THỰC gửi (nhận định bị bớt không tính)", set(BR["parts"][1]["items"][0]["sections"])
	== {"cong-no", "ton-kho", "tong-quan", "van-chuyen"}, BR["parts"][1]["items"][0]["sections"])
frappe.db.sql(f"DELETE FROM `tab{INSIGHT}` WHERE name = 'cn.binh_an'")
KB["f"] = tra_loi

# deep trống → model ngày
single("BC Settings", ai_claude_model_deep="")
GOI.clear()
brief.run_brief("tuan")
eq("ai_claude_model_deep trống → model ngày", GOI[0]["model"], DAILY)
single("BC Settings", ai_claude_model_deep=DEEP)

# tiêu đề hỏng → tiêu đề mặc định; vẫn source ai
KB["f"] = lambda obj: {"data": {"title": "Nợ tăng 20%", "dang_chu_y": ["Kế toán: rà soát nợ quá hạn."],
	"viec_ton": [], "uu_tien": []}, "tokens_in": 5, "tokens_out": 5, "model": DEEP}
o = brief.run_brief("tuan")
BR = store.latest_briefs(("tuan",))[0]
eq("tiêu đề có số tay → tiêu đề mặc định, bản tin vẫn AI", (o["source"], BR["title"], o["items"], o["rejected"]),
	("ai", "Bản tin tuần 16/11 – 22/11/2026", 1, 0))
KB["f"] = lambda obj: {"data": {"title": "Tuần ổn", "dang_chu_y": ["Kế toán: " + "rà soát nợ quá hạn, " * 30 + "xong."],
	"viec_ton": ["Kho: kiểm lại tồn chậm bán."], "uu_tien": []}, "tokens_in": 5, "tokens_out": 5, "model": DEEP}
o = brief.run_brief("tuan")
eq("mục dài quá ITEM_MAX → bỏ, đếm rejected", (o["items"], o["rejected"]), (1, 1))

# không mục nào sống → bản quy tắc, Run loi (vẫn ghi token)
KB["f"] = lambda obj: {"data": {"title": "x", "dang_chu_y": ["Tăng 20%."], "viec_ton": ["", "  "], "uu_tien": []},
	"tokens_in": 700, "tokens_out": 70, "model": DEEP}
o = brief.run_brief("tuan")
BR = store.latest_briefs(("tuan",))[0]
eq("mọi mục bị loại → bản tin quy tắc", (o["status"], o["source"], o["ai"], o["rejected"], BR["source"], BR["model"],
	BR["title"]), ("ok", "quy-tac", "loi", 3, "quy-tac", "", "Bản tin tuần 16/11 – 22/11/2026"))
R0 = frappe.db.sql(f"SELECT * FROM `tab{RUN}` WHERE name = %s", (o["run"],), as_dict=True)[0]
eq("… dòng Run loi + token + lý do", (R0.status, R0.error, R0.tokens_in, R0.tokens_out, R0.rejected),
	("loi", brief.KHONG_SONG, 700, 70, 3))
eq("bản quy tắc trên số thật (hằng số KPI_TICH_LUY thật; nhan-su ẩn vẫn tính nhưng không có %)",
	[it["text"] for it in BR["parts"][0]["items"]], [
	"Phải thu ròng: -50 triệu, tăng 50,0% so với tuần trước (-100 triệu).",
	"Tỷ lệ nợ quá hạn: 25,0%, tăng 5 điểm phần trăm so với tuần trước (20,0%).",
	"Nợ phải thu quá hạn: 120 triệu, tăng 20,0% so với tuần trước (100 triệu)."])
eq("bản quy tắc: việc tồn = tiêu đề ĐÃ LƯU của nhận định ton; ưu tiên = đỏ đang mở",
	([(it["text"], it["sections"]) for it in BR["parts"][1]["items"]], [it["text"] for it in BR["parts"][2]["items"]]),
	([("Lời AI cho IA", ["cong-no"])], ["Lời AI cho IA"]))
eq("bản quy tắc: sections_used = hợp mảng của các mục", BR["sections_used"], ["cong-no"])

# ═══════════════════════════════════════════════════════════════════════════
print("H. Lý do bỏ bước AI + lỗi lượt gọi")


def thu(label, want_ai, want_err=None, goi=0, **kw):
	GOI.clear()
	o = brief.run_brief("tuan")
	r = frappe.db.sql(f"SELECT status, error, step, run_type, provider, tokens_in FROM `tab{RUN}` WHERE name = %s",
		(o.get("run"),), as_dict=True)
	br = store.latest_briefs(("tuan",))[0]
	c(f"{label}: ai={want_ai}, Run ban-tin:tuan cùng trạng thái, bản tin quy tắc, {goi} lượt gọi",
		o["status"] == "ok" and o["ai"] == want_ai and o["source"] == "quy-tac" and br["source"] == "quy-tac"
		and r and r[0].status == want_ai and r[0].step == "ban-tin:tuan" and r[0].run_type == "tuan"
		and r[0].provider == "claude" and len(GOI) == goi and (want_err is None or r[0].error == want_err)
		and all(KEY not in str(v) for v in r[0].values()), (o, r, len(GOI)))
	return o, r[0] if r else None


KB["f"] = tra_loi
single("BC Settings", ai_enabled=0)
thu("ai_enabled = 0", "tat")
single("BC Settings", ai_enabled=1)
del frappe.conf["bc_ai_anthropic_key"]
thu("không khoá", "khong-khoa")
frappe.conf["bc_ai_anthropic_key"] = "sk-ant khoá có dấu cách"
thu("khoá sai dạng", "khong-khoa")
frappe.conf["bc_ai_anthropic_key"] = KEY
single("BC Settings", ai_cap_claude_usd=0)
thu("trần 0", "vuot-tran")
single("BC Settings", ai_cap_claude_usd=90)
for i in range(30):
	insert(RUN, step="kinh-doanh", status="ok", run_type="ngay", provider="claude", started=D(2026, 11, 23, 5, 30),
		cost_usd=0)
thu("30 lượt / ngày", "vuot-tran", "quá số lượt gọi trong ngày")
frappe.db.sql(f"DELETE FROM `tab{RUN}` WHERE step = 'kinh-doanh'")


def nem_llm(kind, ti=0):
	def f(obj):
		e = llm.LLMError(kind, f"lỗi {kind} kèm {KEY}")
		e.tokens_in, e.tokens_out, e.model = ti, ti // 10, DEEP
		raise e
	return f


KB["f"] = nem_llm("credit")
thu("hết credit", "het-credit", goi=1)
KB["f"] = nem_llm("http", 500)
o, r = thu("lỗi HTTP (máy chủ đã trả lời: ghi token)", "loi", goi=1)
eq("… token của lượt hỏng", r.tokens_in, 500)
n_log = len(frappe.LOGGED)


def hong(obj):
	raise RuntimeError(f"lỗi lạ chứa {KEY} và {TEN}")


KB["f"] = hong
thu("lỗi không lường trong lượt gọi", "loi", "lỗi không lường: RuntimeError", goi=1)
LG = frappe.LOGGED[n_log:]
c("… Error Log chỉ tên loại lỗi (không khoá, không tên khách)", LG and all(KEY not in str(x) and TEN not in str(x)
	for x in LG) and "RuntimeError" in str(LG), LG)
KB["f"] = tra_loi
_to = brief.BRIEF_TIMEOUT
brief.BRIEF_TIMEOUT = 200          # 200 − 240 < 60 giây còn lại
try:
	thu("hết thời gian", "loi", brief.HET_GIO)
finally:
	brief.BRIEF_TIMEOUT = _to
xoa(RUN, INSIGHT)
GOI.clear()
o = brief.run_brief("tuan")
eq("không ảnh chụp, không nhận định → không gọi, không dòng Run, vẫn lưu bản quy tắc rỗng", (o["status"], o["ai"],
	o["run"], o["source"], o["items"], len(GOI), frappe.db.sql(f"SELECT COUNT(*) FROM `tab{RUN}`")[0][0]),
	("ok", None, None, "quy-tac", 0, 0, 0))
nap_insight()
GOI.clear()
o = brief.run_brief("tuan")
c("chỉ có nhận định (không KPI) → vẫn gọi, gói rỗng", len(GOI) == 1 and GOI[0]["obj"]["pack"] == {}
	and len(GOI[0]["obj"]["nhan_dinh"]) == 3)
single("BC Settings", hidden_sections="")
nap_tuan()
GOI.clear()
brief.run_brief("tuan")
c("bỏ ẩn nhan-su → nhan-su vào đề bài + nhận định nhan-su", "nhan-su" in GOI[0]["obj"]["pack"]
	and any(x["mang"] == "nhan-su" for x in GOI[0]["obj"]["nhan_dinh"]))
single("BC Settings", hidden_sections="nhan-su")

# ═══════════════════════════════════════════════════════════════════════════
print("I. Chạy lại cùng tuần / tháng ghi đè cùng bản tin")
xoa(BRIEF)
KB["f"] = tra_loi
hom_nay(d(2026, 11, 23))
o1 = brief.run_brief("tuan")
hom_nay(d(2026, 11, 25), 15, 0)
KB["f"] = None                     # mô hình trả rỗng → bản quy tắc
o2 = brief.run_brief("tuan")
eq("thứ Hai rồi thứ Tư cùng tuần → cùng một bản tin (bị ghi đè)", (o1["brief"] == o2["brief"],
	frappe.db.sql(f"SELECT COUNT(*) FROM `tab{BRIEF}`")[0][0], store.latest_briefs(("tuan",))[0]["source"]),
	(True, 1, "quy-tac"))
eq("khoá bản tin", frappe.db.sql(f"SELECT brief_key FROM `tab{BRIEF}`")[0][0], "tuan:2026-11-23")
hom_nay(d(2026, 11, 30))
o3 = brief.run_brief("tuan")
c("tuần sau → bản tin mới", o3["brief"] != o1["brief"] and frappe.db.sql(f"SELECT COUNT(*) FROM `tab{BRIEF}`")[0][0] == 2)
xoa(RUN)
run_row(D(2026, 9, 30, 5, 30), {P1: 200})
run_row(D(2026, 10, 31, 5, 30), {P1: 300})
hom_nay(d(2026, 11, 1))
KB["f"] = tra_loi
GOI.clear()
m1 = brief.run_brief("thang")
hom_nay(d(2026, 11, 2), 7, 0)
m2 = brief.run_brief("thang")
BT = store.latest_briefs(("thang",))[0]
eq("tháng: mùng 1 và mùng 2 → cùng bản tin, kỳ tháng 10, brief_date 1/11", (m1["brief"] == m2["brief"],
	BT["brief_date"], BT["period_from"], BT["period_to"]), (True, d(2026, 11, 1), d(2026, 10, 1), d(2026, 10, 31)))
eq("tháng: Run run_type thang, step ban-tin:thang", [tuple(r) for r in frappe.db.sql(
	f"SELECT DISTINCT run_type, step FROM `tab{RUN}` WHERE step LIKE 'ban-tin%%'")], [("thang", "ban-tin:thang")])
c("tháng: đề bài dùng khối _thang, mô tả phép so tháng", "_thang" in json.dumps(GOI[0]["obj"]["pack"])
	and "cung_ky" in GOI[0]["system"] and GOI[0]["obj"]["loai"] == "thang")
eq("tháng: ưu tiên tháng tới", BT["parts"][2]["title"], "Ưu tiên tháng tới")

# ═══════════════════════════════════════════════════════════════════════════
print("J. Khoá, không bao giờ ném, không lưu đề bài")
cache = frappe.cache()
hom_nay(d(2026, 11, 23))
cache.set_value(jobs.BRIEF_LOCK_KEY, 1)
nb = frappe.db.sql(f"SELECT COUNT(*) FROM `tab{RUN}`")[0][0]
eq("khoá bản tin đang giữ → dang-chay, không ghi gì", (brief.run_brief("tuan"), brief.run_brief("thang"),
	frappe.db.sql(f"SELECT COUNT(*) FROM `tab{RUN}`")[0][0]), ({"status": "dang-chay"}, {"status": "dang-chay"}, nb))
c("… khoá của người khác không bị xoá", cache.get_value(jobs.BRIEF_LOCK_KEY))
cache.delete_value(jobs.BRIEF_LOCK_KEY)
cache.set_value(jobs.LOCK_KEY, 1)            # lượt ngày đang chạy
o = brief.run_brief("tuan")
c("lượt ngày giữ khoá → bản tin vẫn chạy; khoá lượt ngày giữ nguyên", o["status"] == "ok"
	and cache.get_value(jobs.LOCK_KEY) and not cache.get_value(jobs.BRIEF_LOCK_KEY))
cache.delete_value(jobs.LOCK_KEY)
KHOA = []
_goc_call = llm.call


def thay_khoa(*a, **k):
	KHOA.append((cache.get_value(jobs.BRIEF_LOCK_KEY), cache.get_value(jobs.LOCK_KEY)))
	return fake_call(*a, **k)


llm.call = thay_khoa
brief.run_brief("tuan")
llm.call = _goc_call
eq("trong lúc chạy: giữ khoá bản tin, không đặt khoá lượt ngày", KHOA, [(1, None)])
eq("loại lạ → loi, không ghi gì, không khoá", (brief.run_brief("nam")["status"], brief.run_brief(None)["status"],
	frappe.db.sql(f"SELECT COUNT(*) FROM `tab{RUN}`")[0][0] - nb, cache.get_value(jobs.BRIEF_LOCK_KEY)),
	("loi", "loi", 2, None))
_up = store.upsert_brief


def up_hong(*a, **k):
	raise RuntimeError(f"ghi hỏng {KEY}")


store.upsert_brief = up_hong
n_log = len(frappe.LOGGED)
frappe.session.user = "viewer@example.com"
try:
	ok_khong_nem = not nem(lambda: brief.run_brief("tuan"))
	o = brief.run_brief("tuan")
finally:
	store.upsert_brief = _up
c("lỗi ngoài dự kiến → không ném, status loi, nhả khoá, trả user cũ", ok_khong_nem and o["status"] == "loi"
	and not cache.get_value(jobs.BRIEF_LOCK_KEY) and frappe.session.user == "viewer@example.com", o)
LG = frappe.LOGGED[n_log:]
c("… Error Log 'bc.ai bản tin tuan', chỉ tên loại lỗi, không khoá", LG and all(KEY not in str(x) for x in LG)
	and any("bc.ai bản tin tuan" in str(x) for x in LG), LG)
c("… render.forget_source() vẫn chạy", render._nguon.cache_info().currsize == 0)
_snap = brief.snapshots
brief.snapshots = lambda *a, **k: (_ for _ in ()).throw(ValueError("hỏng"))
try:
	o = brief.run_brief("thang")
finally:
	brief.snapshots = _snap
eq("lỗi trước bước AI → loi, không ném", o["status"], "loi")
_cache = frappe.cache
frappe.cache = lambda: (_ for _ in ()).throw(RuntimeError("redis chết"))
try:
	o = brief.run_brief("tuan")
finally:
	frappe.cache = _cache
eq("cache hỏng → loi, không ném", o["status"], "loi")

# Không lưu đề bài / gói số ở đâu cả.
KB["f"] = tra_loi
GOI.clear()
brief.run_brief("tuan")
U = GOI[0]["user"]
MAU = ["LUẬT VIẾT BẢN TIN", '"nhan_dinh"', '"kieu"', "._tuan.", "{{", "BOI-CANH-CONG-TY-RVHG", KEY]
for dt in (BRIEF, RUN, INSIGHT):
	cols = [r[0] for r in frappe.db.sql(f"SHOW COLUMNS FROM `tab{dt}`")]
	rows = frappe.db.sql(f"SELECT * FROM `tab{dt}`")
	blob = json.dumps([list(r) for r in rows], default=str, ensure_ascii=False)
	c(f"{dt}: không mẩu nào của đề bài / gói số / khoá", not [m for m in MAU if m in blob]
		and U not in blob, [m for m in MAU if m in blob])
c("Error Log: không mẩu đề bài / khoá / tên khách", not [m for m in MAU + [TEN] if m in str(frappe.LOGGED)])
c("singles: không mẩu đề bài", "LUẬT VIẾT BẢN TIN" not in str(frappe.db.sql("SELECT value FROM `tabSingles`")))
c("cache: không mẩu đề bài", not any("nhan_dinh" in str(v) for v in frappe.cache().store.values()))
c("kết quả run_brief không mang khoá / đề bài", KEY not in str(brief.run_brief("tuan")))

frappe.db.sql(f"DROP DATABASE IF EXISTS `{DB}`")
c.done()
