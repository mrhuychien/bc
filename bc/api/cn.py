# -*- coding: utf-8 -*-
"""bc.api.cn — Công nợ cho Ban lãnh đạo (đã chốt: tính như app ketoan, MT theo bảng kê chuỗi).

Phải thu (get_receivables):
- Ngoài MT: số dư GL từng khách trên TK phải thu (Ketoan Portal Settings.receivable_account, trống
  thì mọi TK loại Receivable) — y như ketoan.api.receivables. Quá hạn phân bổ FIFO như danh sách công
  nợ của Kế toán (_allocate_open): số dư còn lại thuộc các hoá đơn MỚI nhất, hoá đơn cũ coi như đã trả;
  hạn = due_date, trống thì ngày HĐ + invoice_due_days. Phần dư không gắn được hoá đơn (vd nợ đầu kỳ
  ghi bằng bút toán) → cột "Chưa rõ hạn".
- MT: số còn nợ theo bảng kê thanh toán của chuỗi — GỌI THẲNG helper của ketoan (mt_debt._fetch/
  _enrich/_rollup/_orphan_returns: không guard, không phụ thuộc phiên) để khớp màn của Kế toán; khách
  MT (Customer.customer_group = Ketoan Portal Settings.mt_customer_group) bị loại khỏi phần GL để không
  đếm 2 lần. Site chưa có bảng kê → MT tính theo GL như kênh khác (meta.mt.source = "gl").
- Kênh: theo nhóm khách HIỆN TẠI (công nợ không có snapshot trên hoá đơn) qua channel_of() của bc.
- DSO: công thức ketoan.get_dso — nợ GL toàn công ty / doanh thu gồm VAT (base_grand_total) cửa sổ
  dso_window_days ngày × số ngày.
Phải trả + quỹ (get_payables): GL TK loại Payable (credit − debit), tuổi nợ theo chứng từ như
ketoan.api.payables; số dư TK Cash/Bank như ketoan.api.cash.get_balances.

Mọi số tiền ở đây GỒM VAT (khác doanh số trước VAT ở nhóm Kinh doanh). Công ty do server chọn
(Ketoan Portal Settings.default_company → Global Defaults), KHÔNG nhận từ client — bc không lặp lại
User Permission Company của ketoan. Không dùng frappe.defaults.get_user_default (phụ thuộc phiên,
còn cache dùng chung mọi người xem).
"""

from __future__ import annotations

import re

import frappe
from frappe.utils import cint, flt, getdate, nowdate

from bc.api._common import CHANNEL_LABELS, _guard, channel_of, iso, pct, run_cached

KT = "Ketoan Portal Settings"
CHUNK = 300  # số khách mỗi lượt quét hoá đơn FIFO
BUCKET_KEYS = ("current", "b1", "b2", "b3", "over", "unknown")
MT_BASIS = ("Số còn nợ MT tính từ dòng thanh toán trên bảng kê chuỗi đã nạp (như màn Công nợ MT của Kế toán), "
	"không phải số dư TK 131 trên sổ cái.")


# ─── Cấu hình ketoan (đọc mềm) ───────────────────────────────────────────────
def kt(field: str, default=None):
	"""Giá trị Ketoan Portal Settings như ketoan (`x or default`); site không có ketoan → default."""
	if not frappe.db.exists("DocType", KT):
		return default
	try:
		v = frappe.db.get_single_value(KT, field)
	except Exception:  # field chưa có trên site (ketoan cũ) → frappe.throw đã ghi message_log
		frappe.clear_last_message()
		return default
	return v or default


def company() -> str:
	c = kt("default_company")
	if not c:
		try:
			c = frappe.db.get_single_value("Global Defaults", "default_company")
		except Exception:
			frappe.clear_last_message()
			c = None
	if not c:
		frappe.throw("Chưa xác định được công ty: khai Default Company trong Ketoan Portal Settings hoặc Global Defaults")
	return c


def buckets() -> tuple[int, int, int]:
	return cint(kt("aging_bucket_1")) or 30, cint(kt("aging_bucket_2")) or 60, cint(kt("aging_bucket_3")) or 90


def bucket_labels(b1, b2, b3) -> list[dict]:
	return [{"key": "current", "label": "Trong hạn"}, {"key": "b1", "label": f"1–{b1} ngày"},
		{"key": "b2", "label": f"{b1 + 1}–{b2} ngày"}, {"key": "b3", "label": f"{b2 + 1}–{b3} ngày"},
		{"key": "over", "label": f">{b3} ngày"}, {"key": "unknown", "label": "Chưa rõ hạn"}]


def bucket_of(days, b1, b2, b3) -> str:
	if days is None:
		return "unknown"
	if days <= 0:
		return "current"
	if days <= b1:
		return "b1"
	if days <= b2:
		return "b2"
	return "b3" if days <= b3 else "over"


def _racc(p: dict) -> str:
	"""Như ketoan.receivables._racc_clause — alias gle/acc."""
	acc = kt("receivable_account")
	if acc:
		p["racc"] = acc
		return "gle.account = %(racc)s"
	return "acc.account_type = 'Receivable'"


def mt_group() -> str:
	return kt("mt_customer_group") or "MT"


def _mt_debt():
	"""Module ketoan.api.mt_debt nếu dùng được trên site này, không thì None (đọc mềm)."""
	if "ketoan" not in frappe.get_installed_apps():
		return None
	try:
		from ketoan.api import mt_debt
	except ImportError:
		return None
	if not all(frappe.db.table_exists(t) for t in ("MT Payment Advice", "MT Payment Advice Line")):
		return None
	if not frappe.db.has_column("Customer", "custom_mt_chain"):
		return None
	if not all(hasattr(mt_debt, f) for f in ("_fetch", "_enrich", "_rollup", "_orphan_returns", "einv_available")):
		return None  # API riêng của ketoan đổi — báo "chưa có" thay vì số sai
	return mt_debt


def _empty_buckets() -> dict:
	return {k: 0.0 for k in BUCKET_KEYS}


def _round(d: dict) -> dict:
	return {k: round(flt(v), 2) for k, v in d.items()}


# ─── FIFO như ketoan.receivables (_fifo_invoice_rows + _allocate_open) ──────────
def _fifo_rows(comp: str, customers: list, due_days: int) -> dict:
	"""{customer: [hoá đơn mới → cũ]} — cùng SQL ketoan, chia lượt thay cho LIMIT 20000 toàn cục
	(ketoan cắt theo tên khách: khách cuối bảng chữ cái mất hoá đơn → phần dư thành "quá hạn")."""
	out: dict = {}
	due = "COALESCE(si.due_date, DATE_ADD(si.posting_date, INTERVAL %(due_days)s DAY))"
	for i in range(0, len(customers), CHUNK):
		for r in frappe.db.sql(
			f"""
			SELECT si.customer, si.posting_date, si.base_grand_total AS grand_total, {due} AS due
			FROM `tabSales Invoice` si
			WHERE si.docstatus = 1 AND si.company = %(company)s
			  AND si.customer IN %(customers)s
			  AND IFNULL(si.is_return, 0) = 0
			  AND si.base_grand_total > 0
			ORDER BY si.customer ASC, {due} DESC, si.posting_date DESC, si.creation DESC
			""",
			{"company": comp, "customers": tuple(customers[i:i + CHUNK]), "due_days": due_days},
			as_dict=True,
		):
			out.setdefault(r.customer, []).append(r)
	return out


def allocate(rows: list, balance: float, today) -> tuple[list, float]:
	"""Phân số dư vào hoá đơn mới nhất trước (ketoan _allocate_open). Trả ([(số tiền, số ngày quá hạn)], phần dư)."""
	remaining = flt(balance)
	out = []
	if remaining <= 0.5:
		return out, 0.0
	for r in rows:
		if remaining <= 0.5:
			break
		amt = min(remaining, flt(r.grand_total))
		remaining -= amt
		due = getdate(r.due) if r.due else getdate(r.posting_date)
		out.append((amt, (today - due).days))
	return out, (remaining if remaining > 0.5 else 0.0)


# ─── Phải thu ────────────────────────────────────────────────────────────────
def _gl_balances(comp: str, exclude_mt: bool) -> list:
	p = {"company": comp, "mt_group": mt_group()}
	racc = _racc(p)
	nomt = "AND COALESCE(c.customer_group, '') != %(mt_group)s" if exclude_mt else ""
	return frappe.db.sql(
		f"""
		SELECT gle.party AS customer, MAX(COALESCE(c.customer_name, gle.party)) AS customer_name,
			MAX(c.customer_group) AS customer_group, SUM(gle.debit - gle.credit) AS bal
		FROM `tabGL Entry` gle
		JOIN `tabAccount` acc ON acc.name = gle.account
		JOIN `tabCustomer` c ON c.name = gle.party
		WHERE gle.is_cancelled = 0 AND gle.company = %(company)s
		  AND gle.party_type = 'Customer' AND {racc} {nomt}
		GROUP BY gle.party
		HAVING ROUND(SUM(gle.debit - gle.credit), 2) != 0
		""",
		p,
		as_dict=True,
	)


def _mt_gl_total(comp: str) -> float:
	"""Số dư TK phải thu của khách MT trên sổ cái — để đối chiếu với số theo bảng kê."""
	p = {"company": comp, "mt_group": mt_group()}
	racc = _racc(p)
	return flt(frappe.db.sql(
		f"""SELECT SUM(gle.debit - gle.credit) FROM `tabGL Entry` gle
		    JOIN `tabAccount` acc ON acc.name = gle.account
		    JOIN `tabCustomer` c ON c.name = gle.party
		    WHERE gle.is_cancelled = 0 AND gle.company = %(company)s AND gle.party_type = 'Customer'
		      AND {racc} AND c.customer_group = %(mt_group)s""", p)[0][0])


def _dso(comp: str, today) -> dict:
	"""ketoan.receivables.get_dso: nợ GL toàn công ty (gồm MT) / doanh thu gồm VAT trong cửa sổ."""
	window = cint(kt("dso_window_days")) or 365
	p = {"company": comp, "today": today, "window": window}
	racc = _racc(p)
	debt = flt(frappe.db.sql(
		f"""SELECT SUM(gle.debit - gle.credit) FROM `tabGL Entry` gle JOIN `tabAccount` acc ON acc.name = gle.account
		    WHERE gle.is_cancelled = 0 AND gle.company = %(company)s AND gle.party_type = 'Customer' AND {racc}""",
		p)[0][0])
	rev = flt(frappe.db.sql(
		"""SELECT SUM(base_grand_total) FROM `tabSales Invoice`
		   WHERE docstatus = 1 AND company = %(company)s AND IFNULL(is_opening, 'No') != 'Yes'
		     AND IFNULL(is_return, 0) = 0 AND posting_date >= DATE_SUB(%(today)s, INTERVAL %(window)s DAY)""",
		p)[0][0])
	return {"debt": debt, "revenue": rev, "window_days": window, "dso": round(debt / rev * window, 1) if rev else None}


def _unallocated(comp: str) -> float:
	return flt(frappe.db.sql(
		"""SELECT SUM(unallocated_amount) FROM `tabPayment Entry`
		   WHERE docstatus = 1 AND party_type = 'Customer' AND company = %s AND unallocated_amount > 0""",
		(comp,))[0][0])


def _over_limit(comp: str) -> int:
	"""Số khách nợ vượt hạn mức tín dụng (ketoan alert A1; tắt khi enable_credit_limit_alert = 0)."""
	if frappe.db.exists("DocType", KT):
		try:
			if not cint(frappe.db.get_single_value(KT, "enable_credit_limit_alert")):
				return 0
		except Exception:
			frappe.clear_last_message()
	p = {"company": comp}
	racc = _racc(p)
	return len(frappe.db.sql(
		f"""
		SELECT gle.party
		FROM `tabGL Entry` gle
		JOIN `tabAccount` acc ON acc.name = gle.account
		JOIN `tabCustomer Credit Limit` ccl ON ccl.parent = gle.party AND ccl.parenttype = 'Customer'
			AND ccl.company = %(company)s
		WHERE gle.is_cancelled = 0 AND gle.company = %(company)s AND gle.party_type = 'Customer' AND {racc}
		  AND ccl.credit_limit > 0
		GROUP BY gle.party, ccl.credit_limit
		HAVING SUM(gle.debit - gle.credit) > ccl.credit_limit
		""", p))


def _mt_block(md, comp: str, today, b1, b2, b3) -> dict:
	"""MT theo bảng kê chuỗi — gọi helper ketoan, gom về cùng bộ cột tuổi nợ với các kênh khác."""
	rows = md._enrich(md._fetch(comp, today), today)
	roll = md._rollup(rows)
	roll.update(md._orphan_returns(comp, today))
	bk = _empty_buckets()
	n_overdue = 0
	for r in rows:
		amt = flt(r.get("remaining"))
		days = r.get("days_overdue")
		bk[bucket_of(days, b1, b2, b3)] += amt
	customers_overdue = {r.get("customer") for r in rows if (r.get("days_overdue") or 0) > 0}
	n_overdue = len(customers_overdue)
	einv_known = bool(md.einv_available())
	chains = [{
		"chain": c.get("chain") or "Chưa gán chuỗi",
		"amount": round(flt(c.get("amount")), 2),
		"overdue": round(flt(c.get("overdue")), 2),
		"count": cint(c.get("count")),
		"unknown_term": cint(c.get("unknown_term")),
		"einv_pending": round(flt(c.get("einv_pending")), 2) if einv_known else None,
	} for c in roll.get("chains") or []]
	return {
		"buckets": bk,
		"total": flt(roll.get("total")),
		"overdue": flt(roll.get("overdue")),
		"customers": len({r.get("customer") for r in rows}),
		"overdue_customers": n_overdue,
		"chains": chains,
		"invoice_count": cint(roll.get("total_count")),
		"unknown_term_amount": flt(roll.get("unknown_term_amount")),
		"pending_review": flt(roll.get("pending_review")),
		"orphan_return_count": cint(roll.get("orphan_return_count")),
		"orphan_return_amount": flt(roll.get("orphan_return_amount")),
		"einv_known": einv_known,
	}


@frappe.whitelist()
def get_receivables(refresh=0):
	"""Phải thu khách hàng: KPI, tuổi nợ theo kênh, top khách quá hạn, MT theo chuỗi.

	{meta: {company, as_of, buckets[{key,label}], mt: {source: statement|gl, basis, gl_total}},
	 kpis: {receivable, advances, net, overdue, overdue_pct, unknown, overdue_customers, dso{...},
	        unallocated, over_limit},
	 channels: [{key, label, receivable, overdue, customers, overdue_customers, buckets{...}}],
	 top_overdue: [{customer, channel, receivable, overdue, unknown, max_days}] (10, ngoài MT),
	 mt: {chains[...], total, overdue, invoice_count, pending_review, orphan_return_*, einv_known} | null}
	"""
	_guard("cong-no")
	comp = company()
	today = getdate(nowdate())

	def build():
		b1, b2, b3 = buckets()
		due_days = cint(kt("invoice_due_days")) or 30
		md = _mt_debt()
		mt = None
		mt_error = None
		if md:
			try:
				mt = _mt_block(md, comp, today, b1, b2, b3)
			except Exception:
				# Fail closed: báo "chưa có số" thay vì nửa số; MT quay về GL để tổng không hụt.
				frappe.log_error(frappe.get_traceback(), "bc.cn MT theo bảng kê")
				mt, mt_error = None, "error"
		balances = _gl_balances(comp, exclude_mt=mt is not None)
		positive = [r for r in balances if flt(r.bal) > 0.5]
		fifo = _fifo_rows(comp, [r.customer for r in positive], due_days)

		ch = {k: {"key": k, "label": CHANNEL_LABELS[k], "receivable": 0.0, "overdue": 0.0, "customers": 0,
			"overdue_customers": 0, "buckets": _empty_buckets()} for k in CHANNEL_LABELS}
		advances = 0.0
		people = []
		for r in balances:
			bal = flt(r.bal)
			if bal <= 0.5:
				advances += -bal if bal < 0 else 0.0
				continue
			key = channel_of(r.customer_group)
			parts, rest = allocate(fifo.get(r.customer, []), bal, today)
			bk = _empty_buckets()
			for amt, days in parts:
				bk[bucket_of(days, b1, b2, b3)] += amt
			bk["unknown"] += rest
			overdue = sum(v for k, v in bk.items() if k not in ("current", "unknown"))
			c = ch[key]
			c["receivable"] += bal
			c["overdue"] += overdue
			c["customers"] += 1
			c["overdue_customers"] += 1 if overdue > 0.5 else 0
			for k, v in bk.items():
				c["buckets"][k] += v
			people.append({"customer": r.customer_name, "channel": CHANNEL_LABELS[key], "receivable": round(bal, 2),
				"overdue": round(overdue, 2), "unknown": round(rest, 2),
				"max_days": max((d for a, d in parts if d > 0), default=0)})
		if mt:
			c = ch["mt"]
			c["receivable"] += mt["total"]
			c["overdue"] += mt["overdue"]
			c["customers"] += mt["customers"]
			c["overdue_customers"] += mt["overdue_customers"]
			for k, v in mt["buckets"].items():
				c["buckets"][k] += v

		channels = []
		for c in ch.values():
			if c["receivable"] <= 0.5 and c["key"] in ("showroom", "khac"):
				continue  # kênh phụ không nợ thì ẩn
			c["buckets"] = _round(c["buckets"])
			c["receivable"], c["overdue"] = round(c["receivable"], 2), round(c["overdue"], 2)
			channels.append(c)
		receivable = sum(c["receivable"] for c in channels)
		overdue = sum(c["overdue"] for c in channels)
		unknown = sum(c["buckets"]["unknown"] for c in channels)
		people.sort(key=lambda x: (x["overdue"], x["receivable"]), reverse=True)
		mt_meta = {"source": "statement" if mt else "gl", "basis": MT_BASIS if mt else None, "error": mt_error,
			"group": mt_group(), "gl_total": round(_mt_gl_total(comp), 2) if mt else None}
		return {
			"meta": {"company": comp, "as_of": iso(today), "buckets": bucket_labels(b1, b2, b3), "mt": mt_meta,
				"due_days": due_days},
			"kpis": {
				"receivable": round(receivable, 2),
				"advances": round(advances, 2),
				"net": round(receivable - advances, 2),
				"overdue": round(overdue, 2),
				"overdue_pct": pct(overdue, receivable),
				"unknown": round(unknown, 2),
				"overdue_customers": sum(c["overdue_customers"] for c in channels),
				"dso": _dso(comp, today),
				"unallocated": round(_unallocated(comp), 2),
				"over_limit": _over_limit(comp),
			},
			"channels": channels,
			"top_overdue": [x for x in people if x["overdue"] > 0.5][:10],
			"mt": mt,
		}

	return run_cached("cn.get_receivables", {"c": comp, "d": iso(today)}, build, refresh)


# ─── Phải trả + quỹ ──────────────────────────────────────────────────────────
# ≥ 6 chữ số, cho phép 1 dấu cách / chấm / gạch giữa các chữ số (số TK hay viết theo nhóm: "1903 5678 9012").
_LONG_DIGITS = re.compile(r"\d(?:[ .\-]?\d){5,}")


def mask_account(name: str | None) -> str:
	"""Che số tài khoản ngân hàng trong tên TK, giữ 4 số cuối: 'TGNH VCB 0011 0045 67890' → 'TGNH VCB •••7890'."""
	return _LONG_DIGITS.sub(lambda m: "•••" + re.sub(r"\D", "", m.group(0))[-4:], name or "")


def cash_types() -> tuple:
	f = kt("cash_bank_account_filter") or "Cash and Bank"
	return {"Cash": ("Cash",), "Bank": ("Bank",)}.get(f, ("Cash", "Bank"))


@frappe.whitelist()
def get_payables(refresh=0):
	"""Phải trả nhà cung cấp + số dư quỹ tiền mặt / ngân hàng.

	{meta: {company, as_of, buckets[...], due_ahead},
	 ap: {total, overdue, buckets{...}, top[{supplier, outstanding, days_overdue}],
	      due: {overdue_total, overdue_count, upcoming_total, upcoming_count, rows[{supplier, due_date, days_to_due, amount}]}},
	 cash: {rows[{account, type, balance}], total, cash, bank}}
	"""
	_guard("phai-tra")
	comp = company()
	today = getdate(nowdate())
	ahead = 14

	def build():
		b1, b2, b3 = buckets()
		p = {"company": comp, "today": today, "ahead": ahead}
		total = flt(frappe.db.sql(
			"""SELECT SUM(gle.credit - gle.debit) FROM `tabGL Entry` gle JOIN `tabAccount` acc ON acc.name = gle.account
			   WHERE gle.is_cancelled = 0 AND gle.company = %(company)s AND gle.party_type = 'Supplier'
			     AND acc.account_type = 'Payable'""", p)[0][0])
		# Tuổi nợ phải trả: như ketoan.payables.get_aging — theo chứng từ, hạn của Purchase Invoice.
		bk = _empty_buckets()
		for r in frappe.db.sql(
			"""
			SELECT y.o, DATEDIFF(%(today)s, COALESCE(pi.due_date, pi.posting_date, y.first_date)) AS age
			FROM (
				SELECT COALESCE(gle.against_voucher, gle.voucher_no) AS ref, SUM(gle.credit - gle.debit) AS o,
					MIN(gle.posting_date) AS first_date
				FROM `tabGL Entry` gle
				JOIN `tabAccount` acc ON acc.name = gle.account
				WHERE gle.is_cancelled = 0 AND gle.company = %(company)s
				  AND gle.party_type = 'Supplier' AND acc.account_type = 'Payable'
				GROUP BY COALESCE(gle.against_voucher, gle.voucher_no)
				HAVING ROUND(SUM(gle.credit - gle.debit), 2) != 0
			) y
			LEFT JOIN `tabPurchase Invoice` pi ON pi.name = y.ref
			""", p, as_dict=True):
			age = cint(r.age) if r.age is not None else None
			bk[bucket_of(age, b1, b2, b3) if age is not None else "current"] += flt(r.o)
		top = frappe.db.sql(
			"""
			SELECT MAX(COALESCE(s.supplier_name, gle.party)) AS supplier, SUM(gle.credit - gle.debit) AS outstanding,
				MAX(pi.earliest_due) AS earliest_due
			FROM `tabGL Entry` gle
			JOIN `tabAccount` acc ON acc.name = gle.account
			LEFT JOIN `tabSupplier` s ON s.name = gle.party
			LEFT JOIN (SELECT supplier, MIN(COALESCE(due_date, posting_date)) AS earliest_due FROM `tabPurchase Invoice`
				WHERE docstatus = 1 AND company = %(company)s AND outstanding_amount > 0 GROUP BY supplier) pi
				ON pi.supplier = gle.party
			WHERE gle.is_cancelled = 0 AND gle.company = %(company)s
			  AND gle.party_type = 'Supplier' AND acc.account_type = 'Payable'
			GROUP BY gle.party
			HAVING ROUND(SUM(gle.credit - gle.debit), 2) > 0
			ORDER BY SUM(gle.credit - gle.debit) DESC
			LIMIT 10
			""", p, as_dict=True)
		due_tot = frappe.db.sql(
			"""
			SELECT SUM(CASE WHEN COALESCE(due_date, posting_date) < %(today)s THEN outstanding_amount ELSE 0 END) AS od,
				SUM(CASE WHEN COALESCE(due_date, posting_date) < %(today)s THEN 1 ELSE 0 END) AS od_n,
				SUM(CASE WHEN COALESCE(due_date, posting_date) >= %(today)s THEN outstanding_amount ELSE 0 END) AS up,
				SUM(CASE WHEN COALESCE(due_date, posting_date) >= %(today)s THEN 1 ELSE 0 END) AS up_n
			FROM `tabPurchase Invoice`
			WHERE docstatus = 1 AND company = %(company)s AND outstanding_amount > 0
			  AND COALESCE(due_date, posting_date) <= DATE_ADD(%(today)s, INTERVAL %(ahead)s DAY)
			""", p, as_dict=True)[0]
		upcoming = frappe.db.sql(
			"""
			SELECT supplier_name AS supplier, COALESCE(due_date, posting_date) AS due_date,
				DATEDIFF(COALESCE(due_date, posting_date), %(today)s) AS days_to_due, outstanding_amount AS amount
			FROM `tabPurchase Invoice`
			WHERE docstatus = 1 AND company = %(company)s AND outstanding_amount > 0
			  AND COALESCE(due_date, posting_date) BETWEEN %(today)s AND DATE_ADD(%(today)s, INTERVAL %(ahead)s DAY)
			ORDER BY COALESCE(due_date, posting_date) ASC, outstanding_amount DESC
			LIMIT 10
			""", p, as_dict=True)
		cash_rows = frappe.db.sql(
			"""
			SELECT gle.account, acc.account_name, acc.account_type, SUM(gle.debit - gle.credit) AS balance
			FROM `tabGL Entry` gle
			JOIN `tabAccount` acc ON acc.name = gle.account
			WHERE gle.is_cancelled = 0 AND gle.company = %(company)s AND gle.posting_date <= %(today)s
			  AND acc.account_type IN %(types)s AND acc.is_group = 0
			GROUP BY gle.account, acc.account_name, acc.account_type
			HAVING ROUND(SUM(gle.debit - gle.credit), 2) != 0
			ORDER BY acc.account_type, SUM(gle.debit - gle.credit) DESC
			""", {**p, "types": cash_types()}, as_dict=True)
		ap_overdue = sum(v for k, v in bk.items() if k not in ("current", "unknown"))
		return {
			"meta": {"company": comp, "as_of": iso(today), "buckets": bucket_labels(b1, b2, b3)[:5], "due_ahead": ahead},
			"ap": {
				"total": round(total, 2),
				"overdue": round(ap_overdue, 2),
				"buckets": _round(bk),
				"top": [{"supplier": r.supplier, "outstanding": round(flt(r.outstanding), 2),
					"days_overdue": max((today - getdate(r.earliest_due)).days, 0) if r.earliest_due else 0} for r in top],
				"due": {
					"overdue_total": round(flt(due_tot.od), 2), "overdue_count": cint(due_tot.od_n),
					"upcoming_total": round(flt(due_tot.up), 2), "upcoming_count": cint(due_tot.up_n),
					"rows": [{"supplier": r.supplier, "due_date": iso(r.due_date), "days_to_due": cint(r.days_to_due),
						"amount": round(flt(r.amount), 2)} for r in upcoming],
				},
			},
			"cash": {
				"rows": [{"account": mask_account(r.account_name or r.account), "type": r.account_type,
					"balance": round(flt(r.balance), 2)} for r in cash_rows],
				"total": round(sum(flt(r.balance) for r in cash_rows), 2),
				"cash": round(sum(flt(r.balance) for r in cash_rows if r.account_type == "Cash"), 2),
				"bank": round(sum(flt(r.balance) for r in cash_rows if r.account_type == "Bank"), 2),
			},
		}

	return run_cached("cn.get_payables", {"c": comp, "d": iso(today)}, build, refresh)
