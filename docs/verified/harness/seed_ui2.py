"""Seed gộp cho kiểm giao diện: SX + Công nợ + ATTP + Vận chuyển + Nhân sự + bán hàng."""
import sys

from seed import reset
import seed_ui, test_attp, test_cn, test_ns, test_sx, test_vc
reset()
test_sx.seed()
test_cn.seed()
test_attp.seed()
test_vc.seed()
test_ns.seed()
from seed import insert
for n, par, l, r in [("Showroom", "All Customer Groups", 11, 14), ("Showroom HN", "Showroom", 12, 13), ("Co.op", "MT", 15, 16)]:
    insert("Customer Group", name=n, customer_group_name=n, parent_customer_group=par, lft=l, rgt=r)
seed_ui.sales()
print("seeded")
