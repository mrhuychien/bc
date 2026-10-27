"""Vận chuyển của bc (bc.api.vc) trên MariaDB thật, bảng sinh từ DocType JSON của vanchuyen + ketoan.

Số kỳ vọng TÍNH TAY từ dữ liệu dưới (hôm nay 27/10/2026, kỳ 01–27/10). Mỗi bẫy trong đặc tả có một ca:
chuyến nháp (custom_trang_thai_xep chưa reconcile), dòng chưa giao trên chuyến Hoàn thành được nhả, đơn tách
2 chuyến chia doanh thu theo kiện, cước sửa tay, trả cước mà bút toán đã huỷ, sự cố trạng thái trống, phiếu
kiểm ketoan thắng trạng thái lô, xe ngừng sử dụng. Lịch xe gọi helper THẬT của vanchuyen.
"""
import json
import sys
import unicodedata

from seed import Check, bc_settings, drop_column, drop_doctype, insert, reset
from paths import app

sys.path.insert(1, app("vanchuyen"))

import frappe  # noqa: E402

HT, ST, KIEN = "custom_hình_thức_vận_chuyển", "custom_trạng_thái_vận_chuyển", "custom_tổng_kiện"
TVC, NT, VP = "Tự vận chuyển", "Nhất Tín", "Viettel Post"
DA1, DA2 = "Đã giao hàng, chụp chứng từ", "Đã nộp chứng từ"
BI_MAT = ["Nguyễn Văn Lái", "0901234567", "Khách Bí Mật", "MÔ TẢ RIÊNG", "Người Liên Hệ X", "0987654321",
	"Phụ Trách Y", "Số 1 Ngõ Kín"]


def si(name, date, ht, st, net, kien=0, **kw):
	base = {"docstatus": 1, "is_return": 0, "customer_group": "NPP", "posting_date": date, "net_total": net,
		"grand_total": net * 1.08, "customer": "C1", "customer_name": "Khách Bí Mật", HT: ht, ST: st, KIEN: kien}
	base.update(kw)
	return insert("Sales Invoice", name=name, **base)


def trip(name, ngay, docstatus, tt, rows, **kw):
	insert("Chuyen Xe", name=name, ngay_giao=ngay, docstatus=docstatus, trang_thai=tt, ten_lai_xe="Nguyễn Văn Lái",
		sdt_lai_xe="0901234567", lai_xe="DRV-1", creation=f"{ngay} 08:00:00", **kw)
	for i, (s, k, g) in enumerate(rows, 1):
		insert("Chuyen Xe Don Hang", parent=name, parenttype="Chuyen Xe", parentfield="don_hang", idx=i,
			sales_invoice=s, so_kien=k, trang_thai_giao=g, khach_hang="Khách Bí Mật", dia_chi="Số 1 Ngõ Kín")


def seed():
	bc_settings()
	# ── Đơn trong kỳ ──
	si("S1", "2026-10-05", TVC, DA1, 1_000_000, 10)
	si("S2", "2026-10-10", TVC, "Đang giao hàng", 2_000_000, 12)
	si("S3", "2026-10-20", TVC, "Chờ xử lý", 500_000, 5)
	si("S4", "2026-10-22", TVC, None, 300_000, 0)            # lô nguyên, chỉ nằm trên chuyến NHÁP
	si("S5", "2026-10-15", NT, DA2, 800_000)
	si("S6", "2026-10-26", VP, "Đang xử lý", 400_000)
	si("S7", "2026-10-23", None, "Chờ xử lý", 100_000)       # chưa phân công
	si("S8", "2026-10-25", TVC, "Đang xử lý", 600_000, 10)   # 4/10 kiện trên chuyến nháp → một phần
	si("S9", "2026-10-26", TVC, "Chờ xử lý", 200_000, 0)     # lô nguyên chưa lên chuyến nào → chưa xếp
	# ── Loại khỏi kỳ ──
	si("X1", "2026-10-12", TVC, "Chờ xử lý", 9_999_999, 3, customer_group="Showroom")
	si("X2", "2026-10-12", TVC, "Chờ xử lý", -9_999_999, 3, is_return=1)
	si("X3", "2026-10-12", TVC, "Chờ xử lý", 9_999_999, 3, docstatus=0)
	si("X4", "2026-10-12", TVC, "Chờ xử lý", 9_999_999, 3, is_opening="Yes")
	si("X5", "2026-09-20", TVC, "Đang xử lý", 700_000, 7)    # tháng trước: chỉ vào ảnh chụp chờ giao
	si("X6", "2026-03-01", NT, "Chờ xử lý", 9_999_999)       # cũ hơn 180 ngày: bỏ khỏi ảnh chụp
	# ── Chuyến ──
	trip("CX1", "2026-10-21", 1, "Hoàn thành", [("S1", 10, "Đã giao"), ("S2", 8, "Đã giao"), ("S3", 5, "Hoàn")],
		tong_don=3, tong_kien=23, tong_the_tich=2.0, the_tich_xe=4.0, ti_le_tai=50,
		cuoc_goc=500_000, phu_phi_gui_xe=100_000, tong_cuoc=600_000, da_tra_cuoc=1, cuoc_je="JE-1")
	trip("CX2", "2026-10-24", 1, "Đang giao", [("S2", 4, "Chờ giao")],
		tong_don=1, tong_kien=4, tong_the_tich=1.5, the_tich_xe=1.0, ti_le_tai=150,
		cuoc_goc=300_000, phu_phi_chuyen_2=100_000, tong_cuoc=450_000, cuoc_thu_cong=1, da_tra_cuoc=1, cuoc_je="JE-2")
	trip("CX3", "2026-10-26", 0, "", [("S8", 4, "Chờ giao"), ("S4", 0, "Chờ giao")],
		tong_don=2, tong_kien=4, tong_the_tich=0.5, the_tich_xe=0, ti_le_tai=0, tong_cuoc=999)
	trip("CX4", "2026-10-21", 2, "Đang giao", [("S3", 5, "Chờ giao")],
		tong_don=1, tong_kien=5, tong_the_tich=0.4, the_tich_xe=2.0, ti_le_tai=20, tong_cuoc=777, da_tra_cuoc=1)
	trip("CX5", "2026-09-28", 1, "Hoàn thành", [("X5", 7, "Khách hẹn")], tong_don=1, tong_kien=7, tong_cuoc=888)
	trip("CX6", "2026-10-03", 1, "Hoàn thành", [("X5", 7, "Đã giao")],
		tong_don=1, tong_kien=7, tong_the_tich=1.0, the_tich_xe=5.0, ti_le_tai=20,
		cuoc_goc=200_000, phu_phi_xe=50_000, tong_cuoc=250_000)
	insert("Journal Entry", name="JE-1", docstatus=1)
	insert("Journal Entry", name="JE-2", docstatus=2)
	# ── Sự cố ──
	sc = dict(customer="Khách Bí Mật", mo_ta="MÔ TẢ RIÊNG", nguoi_phu_trach="Phụ Trách Y")
	insert("Su Co Van Chuyen", ngay_phat_sinh="2026-10-05", loai_su_co="Hư hỏng, móp méo", trang_thai="Đã xử lý",
		gia_tri_anh_huong=200_000, tong_mat_duong=150_000, boi_thuong_trang_thai="Đã thu", boi_thuong_so_tien=150_000,
		ngay_dong="2026-10-09", hang_ve_trang_thai="Đã lọc xong", **sc)
	insert("Su Co Van Chuyen", ngay_phat_sinh="2026-10-15", loai_su_co="Hoàn hàng", trang_thai="Mới",
		gia_tri_anh_huong=300_000, boi_thuong_trang_thai="Đã đòi", boi_thuong_so_tien=100_000,
		hang_ve_trang_thai="Chưa về", **sc)
	insert("Su Co Van Chuyen", ngay_phat_sinh="2026-10-25", loai_su_co="Hư hỏng, móp méo", trang_thai=None,
		gia_tri_anh_huong=50_000, boi_thuong_trang_thai="Không đòi", boi_thuong_so_tien=999,
		hang_ve_trang_thai="Đang về", **sc)
	insert("Su Co Van Chuyen", ngay_phat_sinh="2026-09-10", loai_su_co="Giao nhầm", trang_thai="Đang xử lý",
		gia_tri_anh_huong=1_000_000, hang_ve_trang_thai="Đã về sân", **sc)
	insert("Su Co Van Chuyen", ngay_phat_sinh="2026-09-01", loai_su_co="Khác", trang_thai="Đóng",
		ngay_dong="2026-10-11", **sc)
	# ── Thu hồi ──
	lo = dict(nguoi_lien_he="Người Liên Hệ X", sdt_lien_he="0987654321", customer_name="Khách Bí Mật")
	for name, ngay, tt, kiem in [("L1", "2026-10-20", "Tạo yêu cầu", None), ("L2", "2026-10-01", "Đã nhận hàng", "Đang kiểm"),
			("L3", "2026-09-01", "Đã nhận hàng", ""), ("L4", "2026-10-10", "Hủy tại chỗ", None),
			("L5", "2026-10-05", "Đã nhận hàng", "Xong"), ("L6", "2026-10-12", "Đã hủy", None),
			("L7", "2026-08-01", "Đã nhận hàng", "Xong")]:
		insert("Lo Thu Hoi", name=name, ngay_yeu_cau=ngay, trang_thai=tt, **lo)
		if kiem is not None:
			insert("Kiem Hang Thu Hoi", name=name, lo_thu_hoi=name, trang_thai=kiem)
	for name, lot, net, ds in [("R1", "L5", -400_000, 1), ("R2", "L5", -100_000, 1), ("R3", "L2", -50_000, 0),
			("R4", "L7", -999, 1)]:
		si(name, "2026-10-20", None, None, net, is_return=1, docstatus=ds, custom_kiem_hang_thu_hoi=lot)
	# ── Xe ──
	insert("Vehicle", name="29C-111.11", custom_loai_xe="Xe tải", custom_chu_ky_dang_kiem="1 năm",
		custom_ngay_dang_kiem="2025-10-20", custom_thay_dau_moi_km=5000, custom_km_thay_dau=10000, last_odometer=14700)
	insert("Vehicle", name="29C-222.22", custom_chu_ky_dang_kiem="Ngày cụ thể", custom_han_dang_kiem="2027-06-01",
		custom_thay_dau_moi_thang=6, custom_ngay_thay_dau="2026-06-01", last_odometer=1000)
	insert("Vehicle", name="29C-333.33", custom_ngung_su_dung=1, custom_chu_ky_dang_kiem="Ngày cụ thể",
		custom_han_dang_kiem="2026-01-01")
	insert("Vehicle", name="30A-444.44", custom_loai_xe="Xe con")
	for xe, loai, ngay, tien, han in [("29C-222.22", "Bảo dưỡng", "2026-09-01", 1_500_000, "2026-11-05"),
			("29C-111.11", "Đăng kiểm", "2025-10-20", 340_000, None), ("29C-111.11", "Sửa chữa", "2026-03-03", 2_000_000, None),
			("29C-333.33", "Thay dầu", "2026-02-02", 500_000, None)]:
		insert("Nhat Ky Xe", xe=xe, loai=loai, ngay=ngay, chi_phi=tien, han_tiep=han, creation=f"{ngay} 09:00:00")


def run(thang=None):
	from bc.api import vc
	return vc.get_overview(thang=thang, refresh=1)


def by(rows, key, val):
	return next((r for r in rows if r[key] == val), None)


if __name__ == "__main__":
	c = Check()
	reset(); seed()
	from bc.api import vc

	d = run()
	c("có dữ liệu", d["available"] is True)
	c("kỳ mặc định = tháng này cắt ở hôm nay", {k: d["meta"][k] for k in ("thang", "from", "to", "as_of", "prev")} == {"thang": "2026-10", "from": "2026-10-01", "to": "2026-10-27",
		"as_of": "2026-10-27", "prev": "2026-09"}, d["meta"])

	# ── Giao hàng ──
	g = d["giao"]
	c("tổng đơn: bỏ Showroom / trả hàng / nháp / đầu kỳ / ngoài kỳ", g["total"] == 9, g["total"])
	c("giá trị = net_total các đơn trong kỳ", g["value"] == 5_900_000, g["value"])
	c("chờ / đang / đã giao", (g["cho"], g["dang"], g["da"]) == (6, 1, 2), (g["cho"], g["dang"], g["da"]))
	c("tỷ lệ giao", g["ty_le_giao"] == 22.2, g["ty_le_giao"])
	c("tỷ lệ đã phân công hình thức", g["ty_le_phan_cong"] == 88.9, g["ty_le_phan_cong"])
	t = by(g["by_type"], "hinh_thuc", TVC)
	c("Tự vận chuyển: 6 đơn / 4,6tr; trạng thái trống tính là chờ",
		t and (t["n"], t["gt"], t["cho"], t["dang"], t["da"]) == (6, 4_600_000, 4, 1, 1), t)
	c("Tự vận chuyển đứng đầu, Chưa phân công cuối", g["by_type"][0]["hinh_thuc"] == TVC
		and g["by_type"][-1]["hinh_thuc"] == "Chưa phân công", [x["hinh_thuc"] for x in g["by_type"]])
	ch = g["cho_qua_han"]
	c("chờ giao quá 3 ngày (ảnh chụp, gồm đơn tháng trước, bỏ đơn > 180 ngày)", ch["qua_n"] == 5, ch)
	c("chờ giao theo hình thức", by(ch["rows"], "hinh_thuc", TVC) == {"hinh_thuc": TVC, "cho": 6, "qua_n": 4}
		and by(ch["rows"], "hinh_thuc", VP) == {"hinh_thuc": VP, "cho": 1, "qua_n": 0}
		and by(ch["rows"], "hinh_thuc", NT) is None, ch["rows"])
	c("xếp chuyến tính theo dòng chuyến (chuyến nháp có tính, dòng Hoàn trên chuyến Hoàn thành được nhả)",
		g["xep"] == {"chua_xep": 2, "mot_phan": 1, "da_xep": 2}, g["xep"])
	c("giao được ngay lần đầu: dòng kết thúc ĐẦU TIÊN của mỗi đơn, theo ngày giao trong kỳ",
		g["lan_dau"] == {"so_don": 3, "da_giao": 2, "khach_hen": 0, "hoan": 1, "ty_le": 66.7}, g["lan_dau"])

	# ── Chuyến ──
	x = d["chuyen"]
	c("số chuyến (bỏ chuyến huỷ, ngoài kỳ)", x["so_chuyen"] == 4, x["so_chuyen"])
	c("chuyến theo trạng thái (trống = Nháp)", x["by_status"] == {"Nháp": 1, "Đang giao": 1, "Hoàn thành": 2}, x["by_status"])
	c("đơn / chuyến", x["don_moi_chuyen"] == 1.8, x["don_moi_chuyen"])
	c("chuyến / ngày có chuyến", x["chuyen_moi_ngay"] == 1.0, x["chuyen_moi_ngay"])
	c("tải TB có trọng số, bỏ xe chưa khai sức chứa", x["tai_tb"] == 45.0, x["tai_tb"])
	c("quá tải / thiếu sức chứa", (x["qua_tai"], x["thieu_cap"]) == (1, 1), (x["qua_tai"], x["thieu_cap"]))
	c("chuyến theo ngày", [r["date"] for r in x["by_day"]] == ["2026-10-03", "2026-10-21", "2026-10-24", "2026-10-26"],
		x["by_day"])

	# ── Cước ──
	k = d["cuoc"]
	c("tổng cước chỉ chuyến đã duyệt", (k["tong"], k["so_chuyen"]) == (1_300_000, 3), (k["tong"], k["so_chuyen"]))
	c("cước / chuyến, / điểm", (k["moi_chuyen"], k["moi_diem"]) == (433_333, 260_000), (k["moi_chuyen"], k["moi_diem"]))
	tp = {r["key"]: r["tien"] for r in k["thanh_phan"]}
	c("thành phần + điều chỉnh tay", tp == {"goc": 1_000_000, "gui": 100_000, "nhieu_diem": 0, "chuyen_2": 100_000,
		"pp_xe": 50_000, "tay": 50_000}, tp)
	c("sửa tay", k["sua_tay"] == 1, k["sua_tay"])
	c("đã trả / chưa trả", (k["da_tra"], k["chua_tra"], k["so_chua_tra"]) == (1_050_000, 250_000, 1),
		(k["da_tra"], k["chua_tra"], k["so_chua_tra"]))
	c("đánh dấu đã trả mà bút toán đã huỷ", k["tra_bat_thuong"] == 1, k["tra_bat_thuong"])
	c("doanh thu đã giao chia theo kiện (đơn tách 2 chuyến không đếm đôi)",
		(k["don_da_giao"], k["dt_da_giao"]) == (3, 3_033_333.33), (k["don_da_giao"], k["dt_da_giao"]))
	c("% cước / doanh thu đã giao", k["ty_le_doanh_thu"] == 42.86, k["ty_le_doanh_thu"])

	# ── Sự cố ──
	s = d["su_co"]
	c("sự cố trong kỳ", (s["trong_ky"], s["gia_tri_anh_huong"], s["mat_duong"]) == (3, 550_000, 150_000),
		(s["trong_ky"], s["gia_tri_anh_huong"], s["mat_duong"]))
	c("bồi thường đã thu / còn đòi", (s["boi_thuong_da_thu"], s["boi_thuong_con_doi"]) == (150_000, 100_000),
		(s["boi_thuong_da_thu"], s["boi_thuong_con_doi"]))
	c("theo loại", s["by_type"] == [{"loai": "Hư hỏng, móp méo", "n": 2, "gt": 250_000}, {"loai": "Hoàn hàng", "n": 1, "gt": 300_000}],
		s["by_type"])
	c("đang mở gồm trạng thái trống; quá 7 ngày; hàng chưa về",
		(s["dang_mo"], s["mo_qua_n"], s["hang_chua_ve"]) == (3, 2, 2), (s["dang_mo"], s["mo_qua_n"], s["hang_chua_ve"]))
	c("ngày xử lý TB theo ngày đóng trong kỳ", s["ngay_xu_ly_tb"] == 22.0, s["ngay_xu_ly_tb"])

	# ── Thu hồi ──
	h = d["thu_hoi"]
	c("có phiếu kiểm của Kế toán", h["ke_toan"] is True)
	c("chặng tổng: phiếu thắng lô; Hủy tại chỗ = Đã kiểm hàng",
		[(r["chang"], r["n"]) for r in h["stages"]] == [("Tạo yêu cầu", 1), ("Đang kiểm", 2), ("Đã kiểm hàng", 1), ("Xong", 2), ("Đã hủy", 1)],
		[(r["chang"], r["n"]) for r in h["stages"]])
	dk = by(h["stages"], "chang", "Đang kiểm")
	c("tuổi lô", dk and (dk["a7"], dk["a30"], dk["a30p"], dk["max_tuoi"]) == (0, 1, 1, 56), dk)
	c("đang mở / mở quá 30 ngày / tạo trong kỳ", (h["dang_mo"], h["mo_qua_30"], h["trong_ky"]) == (4, 1, 4),
		(h["dang_mo"], h["mo_qua_30"], h["trong_ky"]))
	c("giá trị hàng về = HĐ trả đã duyệt của lô tạo trong kỳ", h["gia_tri"] == {"so_lo": 1, "so_hd": 2, "net": 500_000}, h["gia_tri"])

	# ── Xe ──
	v = d["xe"]
	c("xe đang dùng (bỏ xe ngừng)", v.get("dang_dung") == 3, v)
	c("đăng kiểm", v["dem"]["dang_kiem"] == {"qua_han": 1, "sap_den": 0, "ok": 1, "chua_co": 1}, v["dem"]["dang_kiem"])
	c("thay dầu", v["dem"]["thay_dau"] == {"qua_han": 0, "sap_den": 1, "ok": 1, "chua_co": 1}, v["dem"]["thay_dau"])
	c("xe cần xử lý: quá hạn trước", [(r["xe"], r["qua_han"], [w["viec"] for w in r["viec"]]) for r in v["can_xu_ly"]] == [
		("29C-111.11", True, ["Đăng kiểm", "Thay dầu"]), ("29C-222.22", False, ["Bảo dưỡng"])], v["can_xu_ly"])
	c("chi phí xe năm nay (gồm xe ngừng), lớn trước",
		[(r["loai"], r["tien"]) for r in v["chi_phi_nam"]["rows"]] == [("Sửa chữa", 2_000_000), ("Bảo dưỡng", 1_500_000), ("Thay dầu", 500_000)]
		and v["chi_phi_nam"]["tong"] == 4_000_000, v["chi_phi_nam"])

	# ── Riêng tư ──
	dump = json.dumps(d, ensure_ascii=False, default=str)
	c("không lộ tên / SĐT lái xe, khách, người liên hệ, mô tả, địa chỉ", not [b for b in BI_MAT if b in dump],
		[b for b in BI_MAT if b in dump])

	# ── Kỳ ──
	d9 = run("2026-09")
	c("tháng 9 trọn tháng", (d9["meta"]["from"], d9["meta"]["to"], d9["meta"]["prev"]) == ("2026-09-01", "2026-09-30", "2026-08"),
		d9["meta"])
	c("tháng 9: 1 đơn X5, ngày giao lần đầu X5 = Khách hẹn 28/09", (d9["giao"]["total"], d9["giao"]["lan_dau"]["khach_hen"]) == (1, 1),
		(d9["giao"]["total"], d9["giao"]["lan_dau"]))
	for bad in ("2026-11", "2026-13", "abc", "", None, "2026-1"):
		c(f"tháng không hợp lệ / tương lai ({bad!r}) → tháng này", run(bad)["meta"]["thang"] == "2026-10")

	# ── Quyền ──
	frappe.session.user = "nobody@example.com"
	try:
		vc.get_overview(refresh=1)
		c("người không có quyền bị chặn", False)
	except frappe.PermissionError:
		c("người không có quyền bị chặn", True)
	finally:
		frappe.session.user = "viewer@example.com"

	# ── Cột có dấu dạng NFD (tạo từ Customize Form) ──
	nfd = unicodedata.normalize("NFD", HT)
	frappe.db.sql(f"ALTER TABLE `tabSales Invoice` CHANGE `{HT}` `{nfd}` varchar(140)")
	if frappe.db.has_column("Sales Invoice", HT):
		c("(MariaDB coi NFC = NFD — bỏ qua ca NFD)", True)
	else:
		g2 = run()["giao"]
		c("cột hình thức dạng NFD vẫn đọc được", g2.get("available") and g2["total"] == 9 and g2["xep"]["mot_phan"] == 1, g2)
	frappe.db.sql(f"ALTER TABLE `tabSales Invoice` CHANGE `{nfd}` `{HT}` varchar(140)")

	# ── Thiếu từng phần ──
	frappe.INSTALLED_APPS.remove("ketoan")
	try:
		h2 = run()["thu_hoi"]
		c("không có ketoan: chặng = trạng thái lô (Hủy tại chỗ giữ nguyên), không có giá trị",
			h2["ke_toan"] is False and h2["gia_tri"] is None and by(h2["stages"], "chang", "Hủy tại chỗ")["n"] == 1
			and by(h2["stages"], "chang", "Đã nhận hàng")["n"] == 4, h2)
	finally:
		frappe.INSTALLED_APPS.append("ketoan")
	drop_column("Sales Invoice", ST)
	d2 = run()
	c("thiếu cột trạng thái vận chuyển: chỉ khối giao tắt", d2["giao"] == {"available": False}
		and d2["chuyen"]["available"] and d2["cuoc"]["available"])
	drop_doctype("Su Co Van Chuyen")
	drop_doctype("Nhat Ky Xe")
	d3 = run()
	c("thiếu bảng Sự cố: khối sự cố tắt", d3["su_co"] == {"available": False})
	c("thiếu bảng Nhật ký xe: lịch vẫn có (không có bảo dưỡng), chi phí rỗng",
		d3["xe"]["available"] and d3["xe"]["chi_phi_nam"]["rows"] == []
		and [r["xe"] for r in d3["xe"]["can_xu_ly"]] == ["29C-111.11"], d3["xe"])
	frappe.INSTALLED_APPS.remove("vanchuyen")
	try:
		c("chưa cài vanchuyen → không có dữ liệu", run() == {"available": False, "meta": {}})
	finally:
		frappe.INSTALLED_APPS.append("vanchuyen")
	c.done()
