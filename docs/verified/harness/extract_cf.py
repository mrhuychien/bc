"""Gom custom field khai bằng code (dict {doctype: [field]}) trong install.py các app → extra_custom_fields.json."""
import importlib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paths import BC_ROOT, app
sys.path.insert(0, BC_ROOT)
for a in ("ketoan", "vanchuyen", "salep", "pkd", "nextnpp", "ns", "sx"):
    sys.path.insert(1, app(a))
import frappe  # fake
out = []
for mod in ("ketoan.install", "vanchuyen.install", "salep.install", "bc.install"):
    try:
        m = importlib.import_module(mod)
    except Exception as e:
        print("skip", mod, type(e).__name__, e); continue
    for k, v in vars(m).items():
        if isinstance(v, dict) and v and all(isinstance(x, list) for x in v.values()):
            for dt, fields in v.items():
                for f in fields:
                    if isinstance(f, dict) and f.get("fieldname"):
                        out.append(dict(f, dt=dt))
            print(mod, k, sum(len(x) for x in v.values()))
json.dump(out, open(os.path.join(HERE, "extra_custom_fields.json"), "w"), ensure_ascii=False, indent=0)
print(len(out), "fields")
