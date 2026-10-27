"""Đường dẫn bộ thử — đổi được bằng biến môi trường (mặc định: các app nằm cạnh repo bc)."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BC_ROOT = os.environ.get("BC_APP_ROOT") or os.path.abspath(os.path.join(HERE, "..", "..", ".."))
APPS = os.environ.get("APPS_ROOT") or os.path.dirname(os.path.abspath(os.path.join(HERE, "..", "..", "..")))
SRC = os.environ.get("ERPNEXT_SRC_ROOT") or os.path.join(HERE, ".src")  # bản sparse erpnext + frappe v16 (fetch_schema.sh)
DB = os.environ.get("BC_TEST_DB", "bc_test")
SOCK = os.environ.get("BC_TEST_SOCK", "/run/mysqld/mysqld.sock")


def app(name: str) -> str:
	return os.path.join(APPS, name)
