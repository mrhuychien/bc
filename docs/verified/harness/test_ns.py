"""Nhân sự của bc (bc.api.ns) trên MariaDB thật: Employee (ERPNext v16 + field app ns + field site), SalaryDay
(DocType site — site_doctypes.json), SX Phieu Luong (app sx), NS Giay To (app ns).

Số kỳ vọng TÍNH TAY (hôm nay 27/10/2026; cửa sổ 11/2025–10/2026; tháng trước = 09/2026 tạm tính). So vi sai
với hàm cảnh báo THẬT của ns (canh_bao.tinh) cho BHXH rủi ro và giấy tờ HĐ / khám SK. Có ca cho từng bẫy
trong đặc tả: phiếu trùng / nháp mới hơn phiếu duyệt, phiếu lỗi kỳ, snapshot bộ phận trên phiếu, bộ phận NFD,
nghỉ việc thiếu ngày, ngày vào làm tương lai, option ATTP lưu sai chữ, nhóm < 5 người.
"""
import json
import sys
import unicodedata

from seed import Check, bc_settings, drop_column, drop_doctype, insert, reset
from paths import app

sys.path.insert(1, app("ns"))

import frappe  # noqa: E402

CN, CK, VP, SR = "Công nhật - HGC", "Công khoán - HGC", "Văn phòng - HGC", "Showroom - HGC"
BH, LCB, LTK = "custom_bảo_hiểm", "custom_lương_cơ_bản", "custom_lương_tài_khoản"
TEN = "Nguyễn Thị Bí Mật"
LUONG_HUU = "Đang hưởng lương hưu"


def emp(i, status, dept, doj, dong=0, bh=0, ly_do=None, **kw):
	base = {"employee_name": TEN, "status": status, "department": dept, "date_of_joining": doj, "ns_dong_bhxh": dong,
		BH: bh, "ns_ly_do_khong_bhxh": ly_do, "custom_cccd": "079123456789", "attendance_device_id": f"M{i:02d}",
		LCB: 5_000_000, LTK: 0, "bank_ac_no": "0123456789", "company": "HGC"}
	base.update(kw)
	return insert("Employee", name=f"HR-EMP-{i:05d}", **base)


def sd(e, y, m, ds, tong, thuc, dept=None, mod="2026-10-01 08:00:00"):
	insert("SalaryDay", employee=f"HR-EMP-{e:05d}", employee_name=TEN, year=y, month=m, docstatus=ds, tongtien=tong,
		luongthucnhan=thuc, department=dept, modified=mod, taikhoan="0123456789", chutaikhoan=TEN)


def pl(e, y, m, ds, tong, thuc):
	insert("SX Phieu Luong", name=f"PL-{y}-{m}-HR-EMP-{e:05d}", employee=f"HR-EMP-{e:05d}", nam=y, thang=m, docstatus=ds,
		tong_tien=tong, luong_thuc_nhan=thuc, modified="2026-10-01 08:00:00")


def gt(e, loai, het=None, cap=None, idx=1):
	insert("NS Giay To", parent=f"HR-EMP-{e:05d}", parenttype="Employee", parentfield="ns_giay_to", idx=idx, loai=loai,
		ngay_het_han=het, ngay_cap=cap, so="SO-BI-MAT")


def seed():
	bc_settings()
	old = "2024-03-01"
	# ── Đang làm (21) ──
	emp(1, "Active", CN, old, 1, 500_000, date_of_birth="1990-10-05")
	emp(2, "Active", CN, old, 1, 500_000)
	emp(3, "Active", CN, old, 1, 0)                                        # đóng nhưng chưa có mức trừ
	emp(4, "Active", CN, old, 0, 300_000)                                  # lệch: có mức trừ mà cờ tắt
	emp(5, "Active", CN, old, custom_cccd=None)
	emp(6, "Active", CN, old, attendance_device_id=None, relieving_date="2026-10-01")  # nghỉ mà chưa đổi trạng thái
	emp(7, "Active", VP, old, 1, 500_000, **{LCB: 0})
	emp(8, "Active", VP, old, 1, 500_000, **{LTK: 3_000_000, "bank_ac_no": None})
	emp(9, "Active", VP, old, 1, 500_000, **{LTK: 3_000_000})
	emp(10, "Active", VP, old, ly_do=LUONG_HUU)
	emp(11, "Active", VP, old, ly_do=LUONG_HUU)
	emp(12, "Active", SR, "2025-11-03", ly_do="Khác")
	emp(13, "Active", SR, "2026-09-05")
	emp(14, "Active", None, "2026-10-20")
	emp(15, "Active", CK, old, 1, 500_000, custom_cccd=None)
	emp(16, "Active", CK, old, 1, 0)
	for i in (17, 18, 19):
		emp(i, "Active", CK, old, ly_do="Thời vụ dưới 1 tháng", **({"attendance_device_id": None} if i == 17 else {LCB: 0} if i == 18 else {}))
	emp(20, "Active", CK, "2026-10-30", ly_do="Thời vụ dưới 1 tháng")    # ngày vào làm sau hôm nay (Desk không chặn)
	emp(21, "Active", unicodedata.normalize("NFD", CK), "2026-05-10", ly_do="Thời vụ dưới 1 tháng")  # bộ phận lưu NFD
	# ── Tạm nghỉ (3) / Đã nghỉ (3) ──
	emp(22, "Inactive", CK, old, **{LTK: 1_000_000, "bank_ac_no": None})
	emp(23, "Inactive", CK, old)
	emp(24, "Suspended", VP, old)
	emp(25, "Left", CN, "2026-01-10", relieving_date="2026-08-15")
	emp(26, "Left", CN, old)                                               # nghỉ không có ngày
	emp(27, "Left", VP, old, relieving_date="2025-10-30")                  # nghỉ trước cửa sổ 12 tháng
	# ── Phiếu công nhật (SalaryDay) ──
	sd(1, 0, 0, 0, 1, 1)                                                   # phiếu lỗi kỳ (tháng/năm = 0)
	sd(1, 0, 0, 2, 1, 1)                                                   # lỗi kỳ nhưng đã huỷ → không đếm
	for e in (1, 2, 3, 4, 5):
		sd(e, 2026, 5, 1, 6_000_000, 5_500_000)
		sd(e, 2026, 6, 1, 6_000_000, 5_500_000)
	sd(1, 2026, 6, 0, 9_999_000, 9_999_000, mod="2026-10-20 08:00:00")    # nháp SỬA SAU phiếu duyệt — vẫn chọn phiếu duyệt
	sd(6, 2026, 6, 0, 6_000_000, 5_500_000)                                # tháng đã chốt: nháp không tính, chỉ đếm
	sd(1, 2026, 7, 1, 6_000_000, 5_000_000, mod="2026-08-01 08:00:00")
	sd(1, 2026, 7, 1, 6_000_000, 5_812_345, mod="2026-08-05 08:00:00")    # 2 phiếu duyệt: lấy phiếu sửa sau
	for e in (2, 3, 4, 5):
		sd(e, 2026, 7, 1, 6_000_000, 5_500_000)
	sd(6, 2026, 7, 2, 6_000_000, 5_500_000)                                # đã huỷ
	for e, ds, dept in [(1, 1, CN), (2, 1, CN), (3, 1, CN), (4, 0, CN), (5, 0, CN), (7, 1, VP), (8, 1, VP), (9, 1, VP),
			(10, 1, VP), (11, 1, VP), (12, 1, SR), (13, 0, VP), (14, 0, "")]:  # E13 nay ở Showroom, phiếu T9 ghi Văn phòng
		sd(e, 2026, 9, ds, 7_000_000, 6_543_210, dept)
	sd(2, 2026, 9, 0, 7_000_000, 1, CN)                                   # E02 trùng nháp cả T9 (bên cạnh phiếu duyệt)…
	sd(2, 2026, 9, 0, 7_000_000, 1, CN)
	for e in (1, 2, 3):
		sd(e, 2026, 10, 0, 7_000_000, 6_000_000, CN)
	sd(2, 2026, 10, 0, 7_000_000, 6_000_000, CN, mod="2026-10-02 08:00:00")  # …và T10: ns báo 2 lượt, bc đếm 1 người
	# ── Phiếu khoán (SX Phieu Luong) ──
	for e in (15, 16, 17, 18, 19):
		pl(e, 2026, 9, 1, 8_000_000, 7_000_000)
	for e in range(15, 22):
		pl(e, 2026, 10, 0, 8_000_000, 7_500_000)
	# ── Giấy tờ ──
	gt(1, "Hợp đồng lao động", None, "2026-10-02", 2)                     # HĐ không thời hạn mới hơn: thua dòng có ngày (như ns)
	gt(1, "Hợp đồng lao động", "2026-10-01", "2025-10-01", 1)
	gt(2, "Phụ lục HĐLĐ", "2026-11-10")
	frappe.db.sql("UPDATE `tabEmployee` SET contract_end_date = '2026-10-20' WHERE name = 'HR-EMP-00002'")
	frappe.db.sql("UPDATE `tabEmployee` SET contract_end_date = '2026-11-20' WHERE name = 'HR-EMP-00003'")
	gt(4, "Giấy khám sức khỏe", "2025-01-01", "2024-01-01", 1)          # dòng cũ nằm trước
	gt(4, "Giấy khám sức khỏe", "2026-11-01", "2025-11-01", 2)
	gt(5, "Giấy khám sức khỏe", "2026-12-31")
	gt(7, "Xác nhậ3n kiến thức ATTP", "2026-10-15")                       # option lưu sai chữ trên site
	gt(8, "Xác nhận kiến thức ATTP", "2026-11-05")
	gt(9, "CCCD", "2020-01-01")
	gt(22, "Giấy khám sức khỏe", "2026-01-01")                             # tạm nghỉ vẫn tính
	gt(25, "Hợp đồng lao động", "2026-01-01")                              # đã nghỉ: bỏ


def run():
	from bc.api import ns
	return ns.get_overview(refresh=1)


def ns_dem():
	"""Đếm theo hàm cảnh báo THẬT của ns (mỗi người một lần mỗi mã)."""
	from ns.api import canh_bao, common
	emps = common.lay_nhan_vien({"status": ("!=", "Left")})
	g = common.lay_giay_to([e.name for e in emps])
	ctx = canh_bao.ngu_canh()
	out: dict = {}
	for e in emps:
		for c in {(c["ma"], c["muc"]) for c in canh_bao.tinh(e, g.get(e.name, []), ctx)}:
			out.setdefault(c[0], {"do": 0, "vang": 0, "xanh": 0})[c[1]] += 1
	return out


if __name__ == "__main__":
	c = Check()
	from bc.api import ns
	from bc.api.ns import an_danh

	# ── an_danh (thuần) ──
	def tong_n(cells):
		return sum(x["n"] for x in cells)
	A = [{"nhom": "A", "n": 9, "t": 90}, {"nhom": "B", "n": 6, "t": 60}]
	c("ẩn danh: mọi nhóm ≥ 5 giữ nguyên", an_danh(A, keys=("t",)) == A)
	r = an_danh(A + [{"nhom": "C", "n": 3, "t": 30}, {"nhom": "D", "n": 2, "t": 20}], keys=("t",))
	c("ẩn danh: nhóm nhỏ gộp đủ 5 → một ô gộp", [x["nhom"] for x in r] == ["A", "B", "Nhóm nhỏ (gộp)"] and r[2]["t"] == 50, r)
	r = an_danh(A + [{"nhom": "C", "n": 1, "t": 10}], keys=("t",))
	c("ẩn danh: gộp vẫn < 5 → nhập vào nhóm lớn nhỏ nhất", [(x["nhom"], x["n"], x["t"]) for x in r] == [("A", 9, 90), ("B + nhóm nhỏ", 7, 70)], r)
	r = an_danh([{"nhom": "C", "n": 3, "t": 30}], keys=("t",))
	c("ẩn danh: chỉ có nhóm nhỏ → không tiền", r == [{"nhom": "Tất cả", "n": 3, "t": None}], r)
	c("ẩn danh: không làm mất người", tong_n(an_danh(A + [{"nhom": "C", "n": 1, "t": 1}], keys=("t",))) == 16)
	c("ẩn danh: không sửa list gốc", A[1] == {"nhom": "B", "n": 6, "t": 60})

	reset(); seed()
	d = run()
	c("có dữ liệu", d["available"] is True)
	c("meta", {k: d["meta"][k] for k in ("as_of", "thang", "ky", "k")} == {"as_of": "2026-10-27", "thang": "2026-10", "ky": "2026-09", "k": 5}, d["meta"])

	# ── Quân số ──
	q = d["nhan_su"]
	c("đang làm / tạm nghỉ / đã nghỉ", (q["dang_lam"], q["tam_nghi"], q["da_nghi"], q["khac"]) == (21, 3, 3, 0),
		(q["dang_lam"], q["tam_nghi"], q["da_nghi"], q["khac"]))
	c("nhật / khoán (bộ phận NFD vẫn là khoán)", q["loai"] == {"Nhật": 14, "Khoán": 7}, q["loai"])
	c("theo bộ phận (bỏ đuôi công ty, trống = Chưa có bộ phận)",
		[(x["bo_phan"], x["loai"], x["dang_lam"], x["tam_nghi"]) for x in q["by_dept"]] == [
			("Công khoán", "Khoán", 7, 2), ("Công nhật", "Nhật", 6, 0), ("Văn phòng", "Nhật", 5, 1), ("Showroom", "Nhật", 2, 0),
			("Chưa có bộ phận", "Nhật", 1, 0)], q["by_dept"])
	c("đang làm mà đã có ngày nghỉ", q["active_da_nghi"] == 1, q["active_da_nghi"])

	# ── Biến động ──
	b = d["bien_dong"]
	c("12 tháng 11/2025 → 10/2026", [x["thang"] for x in b["rows"]][0] == "2025-11" and b["rows"][-1]["thang"] == "2026-10"
		and len(b["rows"]) == 12)
	vao = {x["thang"]: x["vao"] for x in b["rows"] if x["vao"]}
	c("vào làm theo tháng (mọi trạng thái, bỏ ngày tương lai)", vao == {"2025-11": 1, "2026-01": 1, "2026-05": 1, "2026-09": 1, "2026-10": 1}, vao)
	nghi = {x["thang"]: x["nghi"] for x in b["rows"] if x["nghi"]}
	c("nghỉ theo ngày nghỉ (chỉ Left, trong cửa sổ)", nghi == {"2026-08": 1} and b["nghi"] == 1, nghi)
	c("nghỉ không có ngày nghỉ", b["nghi_khong_ngay"] == 1)

	# ── BHXH ──
	h = d["bhxh"]
	c("đóng BHXH / đang làm", (h["dong"], h["dang_lam"], h["ty_le"], h["uoc_tinh"]) == (8, 21, 38.1, False),
		(h["dong"], h["dang_lam"], h["ty_le"]))
	c("chưa có mức trừ / lệch cờ / rủi ro", (h["chua_muc"], h["lech"], h["rui_ro"]) == (2, 1, 4), (h["chua_muc"], h["lech"], h["rui_ro"]))
	c("lý do không đóng: nhóm < 5 gộp, không lộ 'lương hưu'",
		h["ly_do"] == [{"ly_do": "Chưa ghi lý do", "n": 5}, {"ly_do": "Thời vụ dưới 1 tháng + nhóm nhỏ", "n": 8}], h["ly_do"])

	# ── Lương ──
	L = d["luong"]
	c("có công nhật + khoán; hook P1 tắt; 1 phiếu lỗi kỳ", L["co"] == {"nhat": True, "khoan": True} and L["hook_tat"] is True
		and L["loi_ky"] == 1, (L["co"], L["hook_tat"], L["loi_ky"]))
	c("tháng đầu có dữ liệu", L["dau_ky"] == {"nhat": "2026-05", "khoan": "2026-09"}, L["dau_ky"])
	S = {s["thang"]: s for s in L["series"]}
	c("trước tháng đầu: chưa có dữ liệu (None, không phải 0)", S["2026-04"]["nhat"] is None and S["2026-08"]["khoan"] is None
		and S["2025-11"]["nhat"] is None)
	n5 = S["2026-05"]["nhat"]
	c("T5 đã chốt", (n5["so_nguoi"], n5["thuc_nhan"], n5["tong_tien"], S["2026-05"]["tam_tinh"]) == (5, 27_500_000, 30_000_000, False), n5)
	n6 = S["2026-06"]["nhat"]
	c("T6: nháp mới hơn không thay phiếu duyệt; nháp tháng đã chốt chỉ đếm", (n6["so_nguoi"], n6["thuc_nhan"], n6["so_nhap"]) == (5, 27_500_000, 1), n6)
	n7 = S["2026-07"]["nhat"]
	c("T7: 2 phiếu duyệt → lấy phiếu sửa sau; phiếu huỷ bỏ", (n7["so_nguoi"], n7["thuc_nhan"]) == (5, 27_800_000), n7)
	c("T8: đã có dữ liệu mà không phiếu → 0", S["2026-08"]["nhat"]["so_nguoi"] == 0 and S["2026-08"]["nhat"]["thuc_nhan"] == 0)
	n9 = S["2026-09"]["nhat"]
	c("T9 tạm tính gồm nháp, làm tròn 100.000", (S["2026-09"]["tam_tinh"], n9["so_nguoi"], n9["so_nhap"], n9["thuc_nhan"], n9["tong_tien"])
		== (True, 13, 4, 85_100_000, 91_000_000), n9)
	n10 = S["2026-10"]["nhat"]
	c("T10 < 5 người → ẩn tiền (trùng nháp chỉ tính 1)", (n10["so_nguoi"], n10["so_nhap"], n10["an"], n10["thuc_nhan"]) == (3, 3, True, None), n10)
	k9, k10 = S["2026-09"]["khoan"], S["2026-10"]["khoan"]
	c("khoán T9 / T10", (k9["so_nguoi"], k9["thuc_nhan"], k10["so_nguoi"], k10["so_nhap"], k10["thuc_nhan"]) == (5, 35_000_000, 7, 7, 52_500_000),
		(k9, k10))
	bp = [(x["nhom"], x["loai"], x["n"], x["thuc_nhan"], x["tong_tien"]) for x in L["bo_phan"]]
	c("T9 theo bộ phận: snapshot bộ phận trên phiếu, nhóm < 5 nhập nhóm lớn nhỏ nhất, khoán một nhóm",
		sorted(bp) == sorted([("Công nhật + nhóm nhỏ", "Công nhật", 7, 45_800_000, 49_000_000), ("Văn phòng", "Công nhật", 6, 39_300_000, 42_000_000),
			("Công khoán", "Khoán", 5, 35_000_000, 40_000_000)]), bp)
	c("T9 theo bộ phận cộng lại = tổng tháng (không mất ai)", sum(x["n"] for x in L["bo_phan"] if x["loai"] == "Công nhật") == n9["so_nguoi"])

	# ── Giấy tờ ──
	g = d["giay_to"]
	c("HĐ: dòng có ngày thắng HĐ không thời hạn (như ns); gộp hạn HĐ trên Employee",
		g["hd"] == {"do": 2, "vang": 1}, g["hd"])
	c("khám SK: dòng mới nhất; tạm nghỉ vẫn tính", g["ksk"] == {"do": 1, "vang": 1}, g["ksk"])
	c("ATTP khớp cả option lưu sai chữ", g["attp"] == {"do": 1, "vang": 1}, g["attp"])

	# ── Cảnh báo ──
	cb = d["canh_bao"]
	dem = {x["ma"]: x["so_nguoi"] for x in cb["rows"]}
	c("cảnh báo theo số người", dem == {"thieu_cccd": 2, "thieu_bo_phan": 1, "thieu_ma_may": 1, "thieu_luong_cb": 1, "thieu_tk": 2,
		"bhxh_rui_ro": 4, "bhxh_chua_muc": 2, "luong_thieu_phieu": 2, "luong_con_nhap": 4, "luong_trung": 1}, dem)
	c("đỏ trước, rồi theo thứ tự của ns", [x["ma"] for x in cb["rows"]][:2] == ["bhxh_rui_ro", "luong_trung"], [x["ma"] for x in cb["rows"]])
	c("không có sinh nhật / mã giấy tờ trong cảnh báo", not ({"sinh_nhat", "hd_het_han", "kham_sk_het_han", "attp_het_han"} & set(dem)))
	c("khoán thiếu phiếu tháng trước", (cb["khoan_thieu_phieu"], cb["thang_truoc"]) == (1, "2026-09"), (cb["khoan_thieu_phieu"], cb["thang_truoc"]))

	# ── So vi sai với ns thật ──
	goc = ns_dem()
	c("vi sai: BHXH rủi ro = ns", goc.get("bhxh_rui_ro", {}).get("do") == h["rui_ro"], goc.get("bhxh_rui_ro"))
	c("vi sai: HĐ = ns", {k: goc.get("hd_het_han", {}).get(k, 0) for k in ("do", "vang")} == g["hd"], goc.get("hd_het_han"))
	c("vi sai: khám SK = ns", {k: goc.get("kham_sk_het_han", {}).get(k, 0) for k in ("do", "vang")} == g["ksk"], goc.get("kham_sk_het_han"))
	c("vi sai: ATTP — ns bỏ sót dòng option sai chữ (bc khớp lỏng)", goc.get("attp_het_han") == {"do": 0, "vang": 1, "xanh": 0},
		goc.get("attp_het_han"))

	# ── Riêng tư ──
	dump = json.dumps(d, ensure_ascii=False, default=str)
	lo = [x for x in (TEN, "HR-EMP", "079123456789", "0123456789", LUONG_HUU, "SO-BI-MAT", "6543210", "5812345") if x in dump]
	c("không lộ tên, mã NV, CCCD, số TK, lý do từng người, số giấy tờ, lương từng phiếu", not lo, lo)

	# ── Quyền ──
	frappe.session.user = "nobody@example.com"
	try:
		ns.get_overview(refresh=1)
		c("người không có quyền bị chặn", False)
	except frappe.PermissionError:
		c("người không có quyền bị chặn", True)
	finally:
		frappe.session.user = "viewer@example.com"

	# ── Cấu hình / thiếu từng phần ──
	frappe.conf["ns_tinh_lai_salaryday"] = 1
	try:
		c("bật hook P1 → không cảnh báo", run()["luong"]["hook_tat"] is False)
	finally:
		frappe.conf.pop("ns_tinh_lai_salaryday", None)
	frappe.INSTALLED_APPS.remove("ns")
	try:
		d2 = run()
		c("không có app ns: khối cảnh báo tắt, còn lại vẫn chạy", d2["canh_bao"] == {"available": False}
			and d2["giay_to"]["available"] and d2["bhxh"]["dong"] == 8)
	finally:
		frappe.INSTALLED_APPS.append("ns")
	frappe.INSTALLED_APPS.remove("sx")
	try:
		L2 = run()["luong"]
		c("không có app sx: khoán None, công nhật vẫn có", L2["co"] == {"nhat": True, "khoan": False}
			and all(s["khoan"] is None for s in L2["series"]) and not [x for x in L2["bo_phan"] if x["loai"] == "Khoán"], L2["co"])
	finally:
		frappe.INSTALLED_APPS.append("sx")
	drop_doctype("SalaryDay")
	L3 = run()["luong"]
	c("không có SalaryDay: chỉ khoán, không cảnh báo hook", L3["co"] == {"nhat": False, "khoan": True} and L3["hook_tat"] is False
		and L3["loi_ky"] == 0, (L3["co"], L3["hook_tat"]))
	drop_doctype("SX Phieu Luong")
	c("không có phiếu lương nào: khối lương tắt", run()["luong"] == {"available": False})
	drop_doctype("NS Giay To")
	d4 = run()
	c("không có NS Giay To: giấy tờ + cảnh báo tắt", d4["giay_to"] == {"available": False} and d4["canh_bao"] == {"available": False})
	drop_column("Employee", "ns_dong_bhxh")
	h5 = run()["bhxh"]
	c("chưa cài field ns: BHXH ước tính theo mức trừ", (h5["uoc_tinh"], h5["dong"], h5["ty_le"], h5["rui_ro"]) == (True, 7, 33.3, None), h5)
	drop_column("Employee", BH)
	c("không có cả hai cột: BHXH tắt", run()["bhxh"] == {"available": False})
	c.done()
