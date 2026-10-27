"""Công nợ bc (bc.api.cn) trên MariaDB + code ketoan THẬT cho MT. Số kỳ vọng tính tay (triệu đồng).

Hôm nay 27/10/2026. Hạn mặc định = ngày HĐ + 30 (invoice_due_days); tuổi nợ 30/60/90.
"""
import sys



from seed import Check, bc_settings, drop_doctype, insert, reset, single

import frappe

M = 1_000_000
C = "HGC"


def gl(posting, account, party_type=None, party=None, debit=0, credit=0, voucher_type="Journal Entry", voucher_no=None,
		against=None, against_type=None):
	insert("GL Entry", posting_date=posting, account=account, party_type=party_type, party=party, debit=debit * M,
		credit=credit * M, voucher_type=voucher_type, voucher_no=voucher_no or f"JV-{posting}", against_voucher=against,
		against_voucher_type=against_type, is_cancelled=0, company=C)


def si(name, customer, group, posting, amount, due=None, is_return=0, return_against=None):
	insert("Sales Invoice", name=name, docstatus=1, company=C, customer=customer, customer_name=customer, customer_group=group,
		posting_date=posting, due_date=due, grand_total=amount * M, base_grand_total=amount * M, net_total=amount * M / 1.08,
		is_return=is_return, return_against=return_against, is_opening="No")
	if amount > 0:
		gl(posting, "131 - HGC", "Customer", customer, debit=amount, voucher_type="Sales Invoice", voucher_no=name,
			against=name, against_type="Sales Invoice")
	else:
		gl(posting, "131 - HGC", "Customer", customer, credit=-amount, voucher_type="Sales Invoice", voucher_no=name,
			against=return_against or name, against_type="Sales Invoice")


def seed():
	bc_settings()
	single("Global Defaults", default_company=C)
	single("Ketoan Portal Settings", default_company=C, mt_customer_group="MT", npp_customer_group="NPP", invoice_due_days=30,
		aging_bucket_1=30, aging_bucket_2=60, aging_bucket_3=90, dso_window_days=365, enable_credit_limit_alert=1,
		cash_bank_account_filter="Cash and Bank")
	for name, typ, an in [("131 - HGC", "Receivable", "Phải thu KH"), ("331 - HGC", "Payable", "Phải trả NCC"),
			("1111 - HGC", "Cash", "Tiền mặt"), ("1121 - HGC", "Bank", "TGNH VCB 0011004567890"), ("511 - HGC", "Income Account", "DT")]:
		insert("Account", name=name, account_name=an, account_type=typ, company=C, is_group=0)
	for i, (g, p) in enumerate([("All Customer Groups", None), ("NPP", "All Customer Groups"), ("MT", "All Customer Groups"),
			("Du lịch", "All Customer Groups"), ("Khách lẻ", "All Customer Groups")]):
		insert("Customer Group", name=g, customer_group_name=g, parent_customer_group=p, lft=2 * i + 1, rgt=2 * i + 2)
	for c, g, chain, days in [("NPP-A", "NPP", None, 0), ("NPP-B", "NPP", None, 0), ("DL-1", "Du lịch", None, 0),
			("KH-ADV", "Khách lẻ", None, 0), ("COOP-1", "MT", "Saigon Co.op", 30)]:
		insert("Customer", name=c, customer_name=c, customer_group=g, custom_mt_chain=chain, custom_mt_credit_days=days)
	# NPP-A: 3 HĐ 200tr, đã trả 120 → còn 80: INV3 40 (chưa hạn) + INV2 40/60 (quá 26 ngày)
	si("INV1", "NPP-A", "NPP", "2026-06-01", 100, due="2026-07-01")
	si("INV2", "NPP-A", "NPP", "2026-09-01", 60, due="2026-10-01")
	si("INV3", "NPP-A", "NPP", "2026-10-20", 40, due="2026-11-19")
	gl("2026-10-05", "131 - HGC", "Customer", "NPP-A", credit=120, voucher_type="Payment Entry", voucher_no="PE-1")
	insert("Customer Credit Limit", parent="NPP-A", parenttype="Customer", parentfield="credit_limits", company=C, credit_limit=50 * M)
	# NPP-B: nợ đầu kỳ bút toán 50 (không HĐ) + INV4 30 không có due_date → hạn 31/08 → quá 57 ngày
	gl("2026-05-01", "131 - HGC", "Customer", "NPP-B", debit=50, voucher_no="JV-OPEN")
	si("INV4", "NPP-B", "NPP", "2026-08-01", 30)
	# DL-1: INV5 20 hạn 15/07 → quá 104 ngày (>90)
	si("INV5", "DL-1", "Du lịch", "2026-07-01", 20, due="2026-07-15")
	# KH-ADV: trả trước 10 (chưa gắn HĐ)
	gl("2026-10-01", "131 - HGC", "Customer", "KH-ADV", credit=10, voucher_type="Payment Entry", voucher_no="PE-2")
	insert("Payment Entry", name="PE-2", docstatus=1, party_type="Customer", party="KH-ADV", company=C, unallocated_amount=10 * M)
	# MT COOP-1: INV6 50 (15/08, hạn khai 30 ngày → 14/09 → quá 43 ngày), INV7 10 (10/10 → hạn 09/11)
	si("INV6", "COOP-1", "MT", "2026-08-15", 50)
	si("INV7", "COOP-1", "MT", "2026-10-10", 10)
	gl("2026-09-20", "131 - HGC", "Customer", "COOP-1", credit=20, voucher_no="JV-MT-1")  # JE MT: 1 dòng tổng, không reference
	si("RET1", "COOP-1", "MT", "2026-10-12", -2, is_return=1)  # trả hàng MT không gắn HĐ gốc
	adv = insert("MT Payment Advice", company=C, chain="Saigon Co.op", customer="COOP-1", payment_date="2026-09-20", status="Nháp")
	insert("MT Payment Advice Line", parent=adv, parenttype="MT Payment Advice", parentfield="lines", sales_invoice="INV6",
		row_kind="Thanh toán", match_confidence="Chắc chắn", total_amount=20 * M)
	insert("MT Payment Advice Line", parent=adv, parenttype="MT Payment Advice", parentfield="lines", sales_invoice="INV7",
		row_kind="Thanh toán", match_confidence="Cần review", total_amount=5 * M)
	# Phải trả: PI1 30 hạn 01/10 (quá 26), PI2 15 hạn 05/11 (còn 9 ngày)
	for name, sup, post, due, amt in [("PI1", "NCC Đường", "2026-09-01", "2026-10-01", 30), ("PI2", "NCC Bao bì", "2026-10-25", "2026-11-05", 15)]:
		insert("Supplier", name=sup, supplier_name=sup)
		insert("Purchase Invoice", name=name, docstatus=1, company=C, supplier=sup, supplier_name=sup, posting_date=post, due_date=due,
			grand_total=amt * M, outstanding_amount=amt * M)
		gl(post, "331 - HGC", "Supplier", sup, credit=amt, voucher_type="Purchase Invoice", voucher_no=name, against=name,
			against_type="Purchase Invoice")
	# Quỹ: tiền mặt 100 − 20; ngân hàng 500
	gl("2026-10-01", "1111 - HGC", debit=100)
	gl("2026-10-02", "1111 - HGC", credit=20)
	gl("2026-10-03", "1121 - HGC", debit=500)


def approx(a, b):
	return abs(a - b) < 1


if __name__ == "__main__":
	c = Check()
	from bc.api import cn

	print("A. Có ketoan + bảng kê MT")
	reset(); seed()
	d = cn.get_receivables(refresh=1)
	ch = {x["key"]: x for x in d["channels"]}
	k = d["kpis"]
	c("MT tính theo bảng kê", d["meta"]["mt"]["source"] == "statement", d["meta"]["mt"])
	c("NPP: phải thu 160, quá hạn 70", approx(ch["npp"]["receivable"], 160 * M) and approx(ch["npp"]["overdue"], 70 * M), ch["npp"])
	b = ch["npp"]["buckets"]
	c("NPP: trong hạn 40 · 1–30: 40 · 31–60: 30 · chưa rõ hạn 50",
		approx(b["current"], 40 * M) and approx(b["b1"], 40 * M) and approx(b["b2"], 30 * M) and approx(b["unknown"], 50 * M), b)
	c("Du lịch: 20 ở cột >90", approx(ch["dulich"]["buckets"]["over"], 20 * M), ch["dulich"])
	c("MT: còn nợ 40 (50−20 + 10), quá hạn 30 ở 31–60",
		approx(ch["mt"]["receivable"], 40 * M) and approx(ch["mt"]["buckets"]["b2"], 30 * M) and approx(ch["mt"]["overdue"], 30 * M), ch["mt"])
	c("Kênh không nợ (Khác, Showroom) ẩn", "khac" not in ch and "showroom" not in ch, list(ch))
	c("KPI: phải thu 220, trả trước 10, ròng 210, quá hạn 120, chưa rõ hạn 50",
		approx(k["receivable"], 220 * M) and approx(k["advances"], 10 * M) and approx(k["net"], 210 * M)
		and approx(k["overdue"], 120 * M) and approx(k["unknown"], 50 * M), k)
	c("DSO = nợ GL 208 / doanh thu 310 × 365 = 244,9", k["dso"]["dso"] == 244.9 and approx(k["dso"]["debt"], 208 * M), k["dso"])
	c("Vượt hạn mức: 1 khách (NPP-A 80 > 50)", k["over_limit"] == 1, k["over_limit"])
	c("Tiền khách trả chưa gắn HĐ: 10", approx(k["unallocated"], 10 * M), k["unallocated"])
	top = [x["customer"] for x in d["top_overdue"]]
	c("Top quá hạn: NPP-A, NPP-B, DL-1 (không có khách MT)", top == ["NPP-A", "NPP-B", "DL-1"], top)
	c("NPP-A quá hạn xa nhất 26 ngày", d["top_overdue"][0]["max_days"] == 26, d["top_overdue"][0])
	m = d["mt"]
	c("MT theo chuỗi: Saigon Co.op 40 / quá hạn 30", m["chains"][0]["chain"] == "Saigon Co.op"
		and approx(m["chains"][0]["amount"], 40 * M) and approx(m["chains"][0]["overdue"], 30 * M), m["chains"])
	c("MT: trả hàng mồ côi 1 phiếu 2tr; chờ xác nhận 5tr", m["orphan_return_count"] == 1
		and approx(m["orphan_return_amount"], 2 * M) and approx(m["pending_review"], 5 * M), m)
	c("Sổ cái MT 38 (chênh −2 = phiếu trả mồ côi)", approx(d["meta"]["mt"]["gl_total"], 38 * M), d["meta"]["mt"])

	p = cn.get_payables(refresh=1)
	ap = p["ap"]
	c("Phải trả 45, quá hạn 30 (1–30 ngày)", approx(ap["total"], 45 * M) and approx(ap["overdue"], 30 * M)
		and approx(ap["buckets"]["b1"], 30 * M), ap)
	c("Đến hạn 14 ngày: 15 (1 HĐ, còn 9 ngày); quá hạn chưa trả 30", approx(ap["due"]["upcoming_total"], 15 * M)
		and ap["due"]["rows"][0]["days_to_due"] == 9 and approx(ap["due"]["overdue_total"], 30 * M), ap["due"])
	cash = p["cash"]
	c("Quỹ: tiền mặt 80, ngân hàng 500", approx(cash["cash"], 80 * M) and approx(cash["bank"], 500 * M), cash)
	c("Che số tài khoản ngân hàng", any(r["account"] == "TGNH VCB •••7890" for r in cash["rows"]), cash["rows"])
	c("Không trả số TK đầy đủ ra ngoài", "0011004567890" not in str(p), "")

	for raw, want in [("TGNH Techcombank 1903 5678 9012 34", "TGNH Techcombank •••1234"), ("BIDV 1234.5678.9012", "BIDV •••9012"),
			("VCB 0071-000-123456", "VCB •••3456"), ("TK 112 - 2024", "TK 112 - 2024"), ("Tiền mặt", "Tiền mặt")]:
		c(f"Che số TK viết theo nhóm: {raw!r}", cn.mask_account(raw) == want, cn.mask_account(raw))

	print("\nA2. DSO như ketoan.get_dso: hoá đơn ghi ngày tương lai vẫn vào doanh thu (chỉ có cận dưới)")
	si("INV-FUT", "NPP-A", "NPP", "2026-10-30", 10, due="2026-11-29")
	k = cn.get_receivables(refresh=1)["kpis"]
	c("DSO = 218 / 320 × 365 = 248,7", k["dso"]["dso"] == 248.7 and approx(k["dso"]["revenue"], 320 * M), k["dso"])

	print("\nB. Site chưa có bảng kê MT → MT tính theo sổ cái")
	reset(); seed(); drop_doctype("MT Payment Advice Line"); drop_doctype("MT Payment Advice")
	d = cn.get_receivables(refresh=1)
	ch = {x["key"]: x for x in d["channels"]}
	c("source = gl, không có khối mt", d["meta"]["mt"]["source"] == "gl" and d["mt"] is None, d["meta"]["mt"])
	c("MT theo GL: 38, quá hạn 28 (INV6 phần còn lại)", approx(ch["mt"]["receivable"], 38 * M)
		and approx(ch["mt"]["overdue"], 28 * M), ch["mt"])

	print("\nC. Helper ketoan lỗi → không trả nửa số, MT quay về GL")
	reset(); seed()
	from ketoan.api import mt_debt
	orig = mt_debt._fetch
	mt_debt._fetch = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
	try:
		d = cn.get_receivables(refresh=1)
	finally:
		mt_debt._fetch = orig
	ch = {x["key"]: x for x in d["channels"]}
	c("error được báo, MT theo GL 38", d["meta"]["mt"]["error"] == "error" and approx(ch["mt"]["receivable"], 38 * M), d["meta"]["mt"])

	print("\nD. Site không có ketoan (không Ketoan Portal Settings) → công ty từ Global Defaults, MT theo GL")
	reset(); seed(); frappe.db.sql("DELETE FROM tabDocType WHERE name='Ketoan Portal Settings'")
	frappe.INSTALLED_APPS.remove("ketoan")
	try:
		d = cn.get_receivables(refresh=1)
	finally:
		frappe.INSTALLED_APPS.append("ketoan")
	c("Công ty = HGC từ Global Defaults; MT theo GL", d["meta"]["company"] == C and d["meta"]["mt"]["source"] == "gl", d["meta"])
	c.done()
