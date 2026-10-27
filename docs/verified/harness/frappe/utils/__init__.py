"""frappe.utils giả — chỉ các hàm bc dùng, cùng ngữ nghĩa v16. FAKE_TODAY điều khiển 'hôm nay'."""
from __future__ import annotations

import calendar
import datetime
from decimal import Decimal

FAKE_TODAY = datetime.date(2026, 10, 27)
FAKE_NOW_TIME = datetime.time(10, 30, 0)


def getdate(v=None):
	if v is None or v == "":
		return FAKE_TODAY
	if isinstance(v, datetime.datetime):
		return v.date()
	if isinstance(v, datetime.date):
		return v
	return datetime.date.fromisoformat(str(v)[:10])


def get_datetime(v=None):
	if v is None:
		return now_datetime()
	if isinstance(v, datetime.datetime):
		return v
	if isinstance(v, datetime.date):
		return datetime.datetime.combine(v, datetime.time())
	return datetime.datetime.fromisoformat(str(v))


def nowdate():
	return FAKE_TODAY.isoformat()


def today():
	return nowdate()


def now_datetime():
	return datetime.datetime.combine(FAKE_TODAY, FAKE_NOW_TIME)


def now():
	return now_datetime().strftime("%Y-%m-%d %H:%M:%S.%f")


def nowtime():
	return FAKE_NOW_TIME.strftime("%H:%M:%S")


def flt(v, precision=None):
	try:
		if isinstance(v, str):
			v = v.replace(",", "")
		r = float(v or 0)
	except (TypeError, ValueError):
		r = 0.0
	return round(r, precision) if precision is not None else r


def cint(v, default=0):
	try:
		return int(float(v))
	except (TypeError, ValueError):
		return default


def cstr(v, encoding="utf-8"):
	return "" if v is None else str(v)


def add_days(d, n):
	return getdate(d) + datetime.timedelta(days=n)


def add_months(d, n):
	d = getdate(d)
	m = d.month - 1 + n
	y = d.year + m // 12
	m = m % 12 + 1
	return datetime.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def add_years(d, n):
	return add_months(d, 12 * n)


def get_first_day(d, d_years=0, d_months=0):
	d = add_months(getdate(d), d_months + 12 * d_years)
	return datetime.date(d.year, d.month, 1)


def get_last_day(d):
	d = getdate(d)
	return datetime.date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def date_diff(a, b):
	return (getdate(a) - getdate(b)).days


def formatdate(d, fmt=None):
	return getdate(d).strftime("%d-%m-%Y")


def fmt_money(v, *a, **k):
	return f"{flt(v):,.0f}"


def escape_html(s):
	import html
	return html.escape(str(s or ""))
