"""Ngày Tết một nguồn: BC Settings. pkd đọc mềm (đè từng năm), bc đưa tetDates ra frontend."""
import sys

from seed import Check, bc_settings, drop_doctype, insert, reset
import frappe

c = Check()
reset(); bc_settings()
# Sửa 2027 trong BC Settings thành ngày khác hằng số của pkd → pkd phải theo BC.
frappe.db.sql("UPDATE `tabBC Tet Date` SET tet_date='2027-02-07' WHERE year=2027")
from pkd.api import utils as U
c("pkd: năm có trong BC Settings → lấy BC (2027-02-07)", str(U.tet_date(2027)) == "2027-02-07", U.tet_date(2027))
c("pkd: năm BC chưa khai → hằng số dự phòng (2016-02-08)", str(U.tet_date(2016)) == "2016-02-08", U.tet_date(2016))
b = U.tet_banner_info("2026-10-27")
c("pkd: thẻ Mùa Tết dùng ngày BC", b["tet_date"] == "2027-02-07" and b["days_to_tet"] == 103, b)
from pkd.api import tet as T
c("pkd: chọn mùa theo ngày BC (09/12/2026 → 2027 vì cửa sổ 60 ngày)", T._pick_current_year(frappe.utils.getdate("2026-12-09"), 60, U.tet_dates_map()) == 2027)
from bc.api.common import build_context_meta
ctx = build_context_meta()
c("bc: BC_CONTEXT.tetDates có 2027-02-07", ctx["tetDates"].get("2027") == "2027-02-07", ctx["tetDates"])
drop_doctype("BC Tet Date")
c("pkd: site không có bc → hằng số (2027-02-06)", str(U.tet_date(2027)) == "2027-02-06", U.tet_date(2027))
c.done()
