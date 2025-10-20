from __future__ import annotations
from PySide6.QtGui import QAction
import sys, json, traceback
from comfyvn.sandbox.runner import run

def main():
    try:
        module = sys.argv[1]; func = sys.argv[2]
        payload = json.loads(sys.stdin.read() or "{}")
        perms = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        out = run(module, func, payload, perms)
        sys.stdout.write(json.dumps(out))
    except Exception as e:
        sys.stdout.write(json.dumps({"ok": False, "error": str(e), "trace": traceback.format_exc()}))

if __name__ == "__main__":
    main()