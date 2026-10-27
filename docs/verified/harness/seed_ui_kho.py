"""Seed gộp sổ kho cho kiểm giao diện nhóm Kho (ui_kho_*.mjs): danh mục chung + kịch bản của 4 bộ thử Kho.

BC_TEST_DB=bc_test_kho_ui python3 -B seed_ui_kho.py   (run_all.sh tự chạy)
"""
from seed import bc_settings, reset
from seed_kho import K, base
import test_kho_han, test_kho_kk, test_kho_nhap, test_kho_ton

reset()
bc_settings()
k = K()
base(k)
for t in (test_kho_ton, test_kho_han, test_kho_kk, test_kho_nhap):
	t.seed(k)
k.finalize()
print("seeded kho")
