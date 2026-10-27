"""Helper nạp sổ kho NHẤT QUÁN cho các bộ thử nhóm Kho (test_kho_*.py).

Nguyên tắc: chỉ ghi sổ (SLE + chứng từ); Bin tính lại từ sổ bằng finalize() theo đúng ngữ nghĩa ERPNext:
- chạy theo (posting_datetime, creation) từng (mã, kho), dòng is_cancelled = 1 bỏ qua;
- dòng Stock Reconciliation KHÔNG lô có actual_qty = 0 và đặt thẳng qty_after_transaction (ERPNext v16
  stock_reconciliation.py: `actual_qty: 0`); mọi dòng khác cộng actual_qty;
- giá trị chạy = Σ stock_value_difference; valuation_rate = giá trị / số lượng khi số lượng > 0, không thì giữ đơn giá trước;
- Bin.actual_qty / stock_value / valuation_rate = trạng thái sau dòng CUỐI (kể cả phiếu ghi ngày tương lai).
Lô: bundle=True ghi Serial and Batch Bundle + Serial and Batch Entry (v15+), bundle=False ghi SLE.batch_no (dữ liệu cũ).

Dùng:
    from seed_kho import K
    k = K(company="HGC")
    k.wh("Tất cả kho - HGC", group=True); k.wh("Thành phẩm - HGC", parent="Tất cả kho - HGC")
    k.item("TP1", "Bánh A", "Hàng truyền thống", uom="Hộp", carton=20, batch=True)
    k.se("Material Receipt", "2026-10-01", [dict(item_code="TP1", t_warehouse=TP, qty=100, rate=10_000, batch="L1")])
    k.finalize()
"""
from __future__ import annotations

import datetime
import itertools

from seed import insert, single

import frappe

_seq = itertools.count(1)


def _dt(date, time="09:00:00"):
	return f"{date} {time}"


class K:
	def __init__(self, company="HGC"):
		self.company = company
		self.whs: list = []          # [(name, parent, is_group, extra)]
		self.groups: list = []       # [(name, parent, is_group)]
		self.sle_n = 0
		single("Global Defaults", default_company=company)

	# ── Danh mục ───────────────────────────────────────────────────────────
	def wh(self, name, parent=None, group=False, company=None, **extra):
		"""Kho (lft/rgt dựng ở finalize — thêm theo thứ tự cha trước con)."""
		self.whs.append((name, parent, 1 if group else 0, {"company": company or self.company, **extra}))
		return name

	def group(self, name, parent=None, is_group=None):
		self.groups.append((name, parent, is_group))
		return name

	def item(self, code, name, group, uom="Hộp", carton=None, batch=False, disabled=0, rate=None, **kw):
		insert("Item", name=code, item_code=code, item_name=name, item_group=group, stock_uom=uom,
			has_batch_no=1 if batch else 0, disabled=disabled, is_stock_item=1, valuation_rate=rate or 0, **kw)
		if carton:
			insert("UOM Conversion Detail", parent=code, parenttype="Item", parentfield="uoms", idx=1, uom="Thùng",
				conversion_factor=carton)
		return code

	def batch(self, name, item, expiry=None, mfg=None, **kw):
		insert("Batch", name=name, batch_id=name, item=item, expiry_date=expiry, manufacturing_date=mfg, **kw)
		return name

	# ── Sổ ─────────────────────────────────────────────────────────────────
	def sle(self, item, wh, qty, value, date, voucher_type, voucher_no, time="09:00:00", batch=None, bundle=True,
			cancelled=0, sr_qty=None, voucher_detail_no=None, lots=None):
		"""Một dòng sổ. `value` = stock_value_difference (có dấu). `sr_qty`: dòng kiểm kê không lô → actual_qty 0, tồn sau
		= sr_qty. `lots`: [(batch, qty)] cho một bundle nhiều lô (qty có dấu); `batch`: một lô với đúng `qty`."""
		self.sle_n += 1
		name = f"SLE-{self.sle_n:06d}"
		sbb = None
		if lots is None and batch:
			lots = [(batch, qty)]
		if lots and bundle:
			sbb = insert("Serial and Batch Bundle", name=f"SBB-{self.sle_n:06d}", item_code=item, warehouse=wh,
				voucher_type=voucher_type, voucher_no=voucher_no, docstatus=2 if cancelled else 1,
				is_cancelled=cancelled, type_of_transaction="Inward" if qty > 0 else "Outward", has_batch_no=1)
			for i, (b, q) in enumerate(lots, 1):
				insert("Serial and Batch Entry", parent=sbb, parenttype="Serial and Batch Bundle", parentfield="entries",
					idx=i, batch_no=b, qty=q, warehouse=wh, item_code=item, is_outward=1 if q < 0 else 0)
		insert("Stock Ledger Entry", name=name, item_code=item, warehouse=wh, posting_date=date, posting_time=time,
			posting_datetime=_dt(date, time), creation=f"{_dt(date, time)}.{self.sle_n:06d}", voucher_type=voucher_type,
			voucher_no=voucher_no, voucher_detail_no=voucher_detail_no, actual_qty=0 if sr_qty is not None else qty,
			stock_value_difference=value, company=self.company, is_cancelled=cancelled, serial_and_batch_bundle=sbb,
			batch_no=(lots[0][0] if lots and not bundle else None), has_batch_no=1 if lots else 0,
			qty_after_transaction=sr_qty or 0)  # cột Float NOT NULL như Frappe; finalize() tính lại dòng thường
		return name

	def se(self, purpose, date, rows, docstatus=1, remarks=None, kiem_ke=None, is_opening="No", entry_type=None,
			time="09:00:00", name=None, **kw):
		"""Stock Entry + Detail + SLE (docstatus 1 → dòng sổ sống; 2 → dòng sổ huỷ như ERPNext; 0 → không sổ).
		row: item_code, s_warehouse / t_warehouse, qty, rate (đơn giá; giá trị dòng = qty × rate), batch, is_finished_item,
		secondary_item_type, value_out / value_in (ghi đè giá trị từng phía nếu cần)."""
		extra = {"custom_kiem_ke": kiem_ke} if frappe.db.has_column("Stock Entry", "custom_kiem_ke") else {}
		name = insert("Stock Entry", name=name, docstatus=docstatus, purpose=purpose, stock_entry_type=entry_type or purpose,
			posting_date=date, posting_time=time, remarks=remarks, company=self.company, is_opening=is_opening,
			**extra, **kw)
		for i, r in enumerate(rows, 1):
			r = dict(r)
			q, rate = r.pop("qty"), r.pop("rate", 0)
			b = r.pop("batch", None)
			v_out, v_in = r.pop("value_out", None), r.pop("value_in", None)
			det = insert("Stock Entry Detail", parent=name, parenttype="Stock Entry", parentfield="items", idx=i,
				docstatus=docstatus, item_name=r["item_code"], qty=q, transfer_qty=q, basic_rate=rate,
				valuation_rate=rate, amount=abs(q * rate), **r)
			if docstatus == 0:
				continue
			c = 1 if docstatus == 2 else 0
			if r.get("s_warehouse"):
				self.sle(r["item_code"], r["s_warehouse"], -q, -(v_out if v_out is not None else q * rate), date,
					"Stock Entry", name, time, batch=b, cancelled=c, voucher_detail_no=det)
			if r.get("t_warehouse"):
				self.sle(r["item_code"], r["t_warehouse"], q, v_in if v_in is not None else q * rate, date,
					"Stock Entry", name, time, batch=b, cancelled=c, voucher_detail_no=det)
		return name

	def sale(self, item, wh, qty, cost, date, voucher_type="Sales Invoice", name=None, cancelled=0, time="10:00:00",
			batch=None, is_return=0):
		"""Xuất bán (qty > 0 = số xuất; trả lại: qty âm + is_return) — dòng sổ actual_qty = −qty, giá trị = −cost."""
		name = name or f"{'SINV' if voucher_type == 'Sales Invoice' else 'DN'}-{next(_seq):05d}"
		if not frappe.db.exists(voucher_type, name):
			extra = {"update_stock": 1} if voucher_type == "Sales Invoice" else {}
			insert(voucher_type, name=name, docstatus=2 if cancelled else 1, posting_date=date, company=self.company,
				is_return=is_return, **extra)
		self.sle(item, wh, -qty, -cost, date, voucher_type, name, time, batch=batch, cancelled=cancelled)
		return name

	def receipt(self, item, wh, qty, value, date, voucher_type="Purchase Receipt", name=None, time="08:00:00",
			batch=None):
		name = name or f"PR-{next(_seq):05d}"
		if not frappe.db.exists(voucher_type, name):
			insert(voucher_type, name=name, docstatus=1, posting_date=date, company=self.company)
		self.sle(item, wh, qty, value, date, voucher_type, name, time, batch=batch)
		return name

	def recon(self, date, rows, purpose="Stock Reconciliation", docstatus=1, name=None, time="18:00:00"):
		"""Stock Reconciliation. row: item_code, warehouse, qty (đếm), current_qty (sổ), value_diff (svd), batch (lô →
		dòng sổ có actual_qty = qty − current_qty như ERPNext; không lô → actual_qty 0, tồn sau = qty)."""
		name = name or f"MAT-RECO-{next(_seq):05d}"
		insert("Stock Reconciliation", name=name, docstatus=docstatus, purpose=purpose, posting_date=date,
			posting_time=time, company=self.company)
		for i, r in enumerate(rows, 1):
			insert("Stock Reconciliation Item", parent=name, parenttype="Stock Reconciliation", parentfield="items", idx=i,
				docstatus=docstatus, item_code=r["item_code"], warehouse=r["warehouse"], qty=r["qty"],
				current_qty=r.get("current_qty", 0), valuation_rate=r.get("rate", 0), batch_no=r.get("batch"))
			if docstatus != 1:
				continue
			if r.get("batch"):
				self.sle(r["item_code"], r["warehouse"], r["qty"] - r.get("current_qty", 0), r["value_diff"], date,
					"Stock Reconciliation", name, time, batch=r["batch"])
			else:
				self.sle(r["item_code"], r["warehouse"], 0, r["value_diff"], date, "Stock Reconciliation", name, time,
					sr_qty=r["qty"])
		return name

	# ── Dựng cây + Bin ─────────────────────────────────────────────────────
	def _tree(self, nodes, table, parent_field, name_field, extra_of):
		kids: dict = {}
		for n in nodes:
			kids.setdefault(n[1], []).append(n)
		c = itertools.count(1)

		def walk(node):
			lft = next(c)
			for k in kids.get(node[0], []):
				walk(k)
			rgt = next(c)
			insert(table, name=node[0], **{name_field: node[0].split(" - ")[0], parent_field: node[1],
				"lft": lft, "rgt": rgt, "is_group": node[2] if node[2] is not None else (1 if kids.get(node[0]) else 0),
				**extra_of(node)})

		for root in kids.get(None, []):
			walk(root)

	def finalize(self):
		self._tree(self.whs, "Warehouse", "parent_warehouse", "warehouse_name", lambda n: n[3])
		if self.groups:
			self._tree(self.groups, "Item Group", "parent_item_group", "item_group_name", lambda n: {})
		rows = frappe.db.sql("""SELECT name, item_code, warehouse, actual_qty, stock_value_difference, voucher_type,
				IFNULL(batch_no, '') AS batch_no, serial_and_batch_bundle, qty_after_transaction
			FROM `tabStock Ledger Entry` WHERE is_cancelled = 0 ORDER BY posting_datetime, creation""", as_dict=True)
		state: dict = {}
		for r in rows:
			q, v, rate = state.get((r.item_code, r.warehouse), (0.0, 0.0, 0.0))
			sr_plain = r.voucher_type == "Stock Reconciliation" and not r.batch_no and not r.serial_and_batch_bundle
			q = float(r.qty_after_transaction) if sr_plain else q + float(r.actual_qty or 0)
			v += float(r.stock_value_difference or 0)
			rate = v / q if q > 0 else rate
			state[(r.item_code, r.warehouse)] = (q, v, rate)
			frappe.db.sql("""UPDATE `tabStock Ledger Entry` SET qty_after_transaction = %s, stock_value = %s,
				valuation_rate = %s WHERE name = %s""", (q, v, rate, r.name))
		for (item, wh), (q, v, rate) in state.items():
			insert("Bin", name=f"BIN-{item}-{wh}", item_code=item, warehouse=wh, actual_qty=q, stock_value=v,
				valuation_rate=rate, company=self.company)
		return state


def bin_of(item, wh):
	r = frappe.db.sql("SELECT actual_qty, stock_value, valuation_rate FROM `tabBin` WHERE item_code = %s AND warehouse = %s",
		(item, wh))
	return tuple(float(x) for x in r[0]) if r else (0.0, 0.0, 0.0)


TODAY = datetime.date(2026, 10, 27)


# ─── Danh mục chung cho mọi bộ thử Kho (gộp được cho kiểm giao diện) ─────────────
# Mỗi bộ thử thêm mã / lô / chứng từ với TIỀN TỐ riêng (TON-, HAN-, KKE-, NTP-) để seed gộp không trùng tên.
ROOT = "Tất cả kho - HGC"
TP = "Thành phẩm - HGC"
CH_GROUP = "Cửa hàng - HGC"
CH1 = "CH Bạch Đằng - HGC"
CH2 = "CH Tuệ Tĩnh - HGC"
TRA_VE = "Hàng trả về - HGC"
CACH_LY = "Kho cách ly - HGC"
DI_DUONG = "Hàng đi đường - HGC"
XUONG = "Kho Xưởng - HGC"
BTP = "Bán thành phẩm - HGC"
NVL = "Kho NVL - HGC"
KHO_CU = "Kho cũ - HGC"          # ngừng dùng nhưng còn hàng
RV = "Kho TP - RV"              # công ty khác — không bao giờ được tính
G_TET, G_QUA_TET, G_TRAD, G_NL, G_BB = "Hàng Tết", "Hộp quà Tết", "Hàng truyền thống", "Nguyên liệu", "Bao bì"


def base(k: K, sx=True):
	"""Cây kho + nhóm hàng + SX Settings + POS Profile chuẩn. sx=False: site không cài sx (không SX Settings)."""
	k.wh(ROOT, group=True)
	for w in (TP, TRA_VE, CACH_LY, XUONG, BTP, NVL):
		k.wh(w, ROOT)
	k.wh(DI_DUONG, ROOT, warehouse_type="Transit")
	k.wh(KHO_CU, ROOT, disabled=1)
	k.wh(CH_GROUP, ROOT, group=True)
	k.wh(CH1, CH_GROUP)
	k.wh(CH2, CH_GROUP)
	k.wh("Tất cả kho - RV", group=True, company="RV")
	k.wh(RV, "Tất cả kho - RV", company="RV")
	k.group("Tất cả nhóm hàng")
	k.group(G_TET, "Tất cả nhóm hàng", is_group=1)
	k.group(G_QUA_TET, G_TET)
	k.group(G_TRAD, "Tất cả nhóm hàng")
	k.group(G_NL, "Tất cả nhóm hàng")
	k.group(G_BB, "Tất cả nhóm hàng")
	for n, w in (("POS Bạch Đằng", CH1), ("POS Tuệ Tĩnh", CH2)):
		insert("POS Profile", name=n, company=k.company, warehouse=w, disabled=0)
	insert("POS Profile", name="POS RV", company="RV", warehouse=RV, disabled=0)
	if sx:
		single("SX Settings", cong_ty=k.company, kho_tp=TP, kho_xuong=XUONG, kho_btp=BTP, kho_nvl=NVL,
			kho_hang_tra_ve=TRA_VE, kho_cach_ly=CACH_LY)
	else:
		frappe.db.sql("DELETE FROM `tabDocType` WHERE name = 'SX Settings'")
