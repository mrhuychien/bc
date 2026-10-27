"""Server thử SPA /bc: trang dựng từ CHÍNH www/bc.html (import map thật), /assets/bc/bc/* → public/,
POST /api/method/<dotted> → gọi hàm Python thật của bc trên Frappe giả + MariaDB.

python3 server.py <port>   (BC_APP_ROOT đổi được gốc app để thử phá)
"""
from __future__ import annotations

import importlib
import json
import os
import re
import sys
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paths import BC_ROOT as ROOT, app  # noqa: E402

sys.path.insert(0, ROOT)
sys.path.insert(1, app("sx"))      # bc.api.attp gọi helper sx thật
sys.path.insert(1, app("ketoan"))  # bc.api.cn gọi mt_debt của ketoan thật
PUBLIC = os.path.join(ROOT, "bc", "public", "bc")

import frappe  # noqa: E402  (fake)

V = "test-v1"


def page_html() -> str:
	src = open(os.path.join(ROOT, "bc", "www", "bc.html"), encoding="utf-8").read()
	head = re.search(r"{% block head_include %}(.*?){% endblock %}", src, re.S).group(1)
	body = re.search(r"{% block page_content %}(.*?){% endblock %}", src, re.S).group(1)

	def jinja(s):
		s = re.sub(r"{%\s*set bc_v[^%]*%}", "", s)
		s = re.sub(r"{%\s*if not no_access\s*%}(.*?){%\s*endif\s*%}", r"\1", s, flags=re.S)
		s = re.sub(r"{%\s*if no_access\s*%}.*?{%\s*else\s*%}(.*?){%\s*endif\s*%}", r"\1", s, flags=re.S)
		s = s.replace("{{ bc_v }}", V)
		s = re.sub(r"{{\s*frappe\.utils\.now\(\)[^}]*}}", V, s)
		ctx = json.dumps(context())
		s = s.replace("{{ bc_context | tojson }}", ctx)
		s = s.replace("{{ shell_build | tojson }}", json.dumps(shell_build()))
		return s

	return f"<!doctype html><html><head><meta charset='utf-8'>{jinja(head)}</head><body>{jinja(body)}</body></html>"


def shell_build():
	src = open(os.path.join(ROOT, "bc", "www", "bc.py"), encoding="utf-8").read()
	return re.search(r'SHELL_BUILD = "([^"]+)"', src).group(1)


def context():
	from bc.api.common import build_context_meta
	c = build_context_meta()
	c.update({"user": frappe.session.user, "fullName": "Lãnh đạo thử", "isSysManager": False,
		"assetVersion": V, "csrfToken": "x", "shellBuild": shell_build()})
	return c


CALLS: list = []


class H(BaseHTTPRequestHandler):
	def log_message(self, *a):
		pass

	def _send(self, code, body, ctype="application/json"):
		b = body.encode() if isinstance(body, str) else body
		self.send_response(code)
		self.send_header("Content-Type", ctype)
		self.send_header("Content-Length", str(len(b)))
		self.end_headers()
		self.wfile.write(b)

	def do_GET(self):
		path = urllib.parse.urlparse(self.path).path
		if path in ("/bc", "/"):
			try:
				return self._send(200, page_html(), "text/html; charset=utf-8")
			except Exception:
				return self._send(500, traceback.format_exc(), "text/plain")
		if path.startswith("/assets/bc/bc/"):
			rel = path[len("/assets/bc/bc/"):]
			full = os.path.normpath(os.path.join(PUBLIC, rel))
			if not full.startswith(PUBLIC) or not os.path.isfile(full):
				return self._send(404, "not found", "text/plain")
			ctype = {"js": "text/javascript", "css": "text/css", "html": "text/html", "png": "image/png",
				"svg": "image/svg+xml"}.get(full.rsplit(".", 1)[-1], "application/octet-stream")
			return self._send(200, open(full, "rb").read(), ctype)
		if path.startswith("/files/"):  # ảnh Item của Frappe — bộ thử trả PNG 1x1
			import base64
			return self._send(200, base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="), "image/png")
		if path.startswith("/bc_xuong"):
			return self._send(200, "<html><body>3d</body></html>", "text/html")
		return self._send(404, "not found", "text/plain")

	def do_POST(self):
		path = urllib.parse.urlparse(self.path).path
		if not path.startswith("/api/method/"):
			return self._send(404, "{}")
		dotted = path[len("/api/method/"):]
		n = int(self.headers.get("Content-Length") or 0)
		raw = self.rfile.read(n).decode()
		args = {k: v[0] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}
		CALLS.append((dotted, args))
		mod, fn = dotted.rsplit(".", 1)
		try:
			if not dotted.startswith("bc.api."):
				raise frappe.PermissionError("Not allowed")
			res = getattr(importlib.import_module(mod), fn)(**args)
			return self._send(200, json.dumps({"message": res}, default=str))
		except frappe.PermissionError as e:
			return self._send(403, json.dumps({"exc_type": "PermissionError",
				"_server_messages": json.dumps([json.dumps({"message": str(e)})])}))
		except frappe.ValidationError as e:
			return self._send(417, json.dumps({"exc_type": "ValidationError",
				"_server_messages": json.dumps([json.dumps({"message": str(e)})])}))
		except Exception as e:
			traceback.print_exc()
			return self._send(500, json.dumps({"exc_type": type(e).__name__, "exception": f"{type(e).__name__}: {e}"}))


def serve(port=0):
	srv = HTTPServer(("127.0.0.1", port), H)  # 1 luồng: pymysql conn không thread-safe
	return srv


if __name__ == "__main__":
	port = int(sys.argv[1]) if len(sys.argv) > 1 else 8124
	srv = serve(port)
	print(f"http://127.0.0.1:{srv.server_address[1]}/bc", flush=True)
	srv.serve_forever()
