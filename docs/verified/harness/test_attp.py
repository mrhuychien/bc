"""ATTP của bc = màn Tổng quan ATTP / Báo cáo tháng của sx (so vi sai với code sx THẬT trên MariaDB).

bc gọi dưới quyền BC Viewer (sx sẽ chặn), sx gọi dưới quyền System Manager. Khác nhau duy nhất được phép:
route bị bỏ, chi tiết dòng sổ (#/so/) bị xoá.
"""
import copy
import sys



from seed import Check, bc_settings, insert, reset, single

import frappe


def seed():
	bc_settings()
	single("SX QC Setting", su_co_qua_han_ngay=7)
	for ngay, luot, ds, muon in [("2026-10-20", "Đầu sáng", 1, 1), ("2026-10-20", "Trưa", 1, 0), ("2026-10-20", "Cuối chiều", 1, 0),
			("2026-10-21", "Đầu sáng", 1, 0), ("2026-10-21", "Trưa", 1, 0), ("2026-10-21", "Bổ sung", 1, 0),
			("2026-10-22", "Đầu sáng", 0, 0), ("2026-10-27", "Đầu sáng", 1, 0)]:
		insert("SX QC Round", ngay=ngay, luot=luot, docstatus=ds, ghi_muon=muon,
			reviewed_on="2026-10-23 08:00:00" if ngay == "2026-10-20" else None)
	insert("SX Su Co", ngay="2026-10-15", trang_thai="Mở", muc_do="Cao", dien_tap=0, cong_doan="Rang", loai="Dị vật")
	insert("SX Su Co", ngay="2026-10-24", trang_thai="Đóng", muc_do="Thường", dien_tap=0, dong_ngay="2026-10-25")
	insert("Issue", subject="Bánh mốc", status="Open", custom_khieu_nai=1, opening_date="2026-10-10")
	insert("Batch", name="LO-TET-01", item="TET1", custom_thu_hoi=1)
	insert("SX Kiem Tra Xuat Xuong", trang_thai="Chờ duyệt", kiem_luc="2026-10-25 10:00:00")
	insert("SX Kiem Tra Xuat Xuong", trang_thai="Đã duyệt", kiem_luc="2026-10-20 10:00:00", duyet_luc="2026-10-20 11:00:00")
	insert("SX Khac Phuc", trang_thai="Mở", han="2026-10-20", ngay="2026-10-16")


def strip(out):
	out = copy.deepcopy(out)
	for t in out["linh_vuc"]:
		t.pop("route", None)
		for x in t["nhac"]:
			if str(x.get("route") or "").startswith("#/so/"):
				x["chi_tiet"] = ""
			x.pop("route", None)
			x.pop("nhom", None)
	return out


if __name__ == "__main__":
	c = Check()
	reset(); seed()
	from bc.api import attp
	from sx.api import qc_attp, qc_baocao

	frappe.session.user = "viewer@example.com"
	mine = attp.get_overview(refresh=1)
	c("BC Viewer xem được (sx sẽ chặn)", mine["available"] is True)
	frappe.session.user = "Administrator"
	try:
		goc = qc_attp.tong_quan()
		rep_goc = qc_baocao.so_lieu("2026-10")
	finally:
		frappe.session.user = "viewer@example.com"
	ref = strip(goc)
	th_b = {t["ma"]: t for t in mine["linh_vuc"]}
	th_s = {t["ma"]: t for t in ref["linh_vuc"]}
	c("Cùng 19 mảng, cùng thứ tự", [t["ma"] for t in mine["linh_vuc"]] == [t["ma"] for t in ref["linh_vuc"]],
		([t["ma"] for t in mine["linh_vuc"]], [t["ma"] for t in ref["linh_vuc"]]))
	c("Đếm đỏ/vàng/xanh khớp sx", mine["dem"] == ref["dem"], (mine["dem"], ref["dem"]))
	lech = [m for m in th_s if th_s[m] != th_b.get(m)]
	c("Từng thẻ (số, nhãn, dòng, đèn, việc treo) khớp sx", not lech,
		[(m, th_b.get(m), th_s[m]) for m in lech][:2])
	vk = th_b["vong_kiem"]
	# 3 ngày SX (20, 21 + 22/10 có lượt dở) × 3 = 9; lượt đủ 5 (Bổ sung không tính) → 55,6%
	c("Vòng kiểm: 5/9 lượt = 55,6% (Bổ sung không tính, ngày có lượt dở vẫn là ngày SX)",
		vk["so"] == "55,6%" and "5/9" in vk["nhan_so"], vk)
	c("Sự cố mở 8 ngày, mức Cao → thẻ đỏ", th_b["su_co"]["den"] == "do" and th_b["su_co"]["so"] == "1", th_b["su_co"])
	c("Lô đang thu hồi → thẻ Truy xuất đỏ", th_b["truy_xuat"]["den"] == "do", th_b["truy_xuat"])
	c("Khiếu nại mở 17 ngày (>7) → đỏ", th_b["khieu_nai"]["den"] == "do", th_b["khieu_nai"])
	c("Không lộ route sx ra bc", "route" not in str(mine["linh_vuc"]), "")

	r = attp.get_report("2026-10", refresh=1)
	c("Báo cáo tháng: 16 chỉ số khớp sx", r["bang"] == rep_goc["bang"], [(a["ma"], a["ky"], b["ky"]) for a, b in zip(r["bang"], rep_goc["bang"]) if a != b][:3])
	c("Tháng chưa bắt đầu (2026-11) → về tháng trước, không lỗi", attp.get_report("2026-11", refresh=1)["thang"] == "2026-09")
	c("Chuỗi rác → tháng trước", attp.get_report("x' OR 1", refresh=1)["thang"] == "2026-09")

	from sx.qc import bien_ban
	goi = []
	orig = bien_ban.nhac
	bien_ban.nhac = lambda *a, **k: (goi.append((a, k)), orig(*a, **k))[1]
	try:
		frappe.session.user = "Administrator"
		attp.get_overview(refresh=1)
	finally:
		bien_ban.nhac = orig
		frappe.session.user = "viewer@example.com"
	c("Biên bản: bc gọi bien_ban.nhac(d) KHÔNG kèm người xem (cache dùng chung không mang 'chờ BẠN ký')",
		goi and all(len(a) == 1 and not k for a, k in goi[-1:]), goi)

	print("\nSite không có sx → available False, không lỗi")
	frappe.INSTALLED_APPS.remove("sx")
	try:
		c("overview", attp.get_overview(refresh=1)["available"] is False)
		c("report", attp.get_report(refresh=1)["available"] is False)
	finally:
		frappe.INSTALLED_APPS.append("sx")
	c.done()
