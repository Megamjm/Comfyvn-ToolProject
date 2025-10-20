from __future__ import annotations
from PySide6.QtGui import QAction
# comfyvn/server/modules/home_api.py
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>ComfyVN</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:2rem;}
h1{margin-bottom:0.5rem} ul{line-height:1.9}
code{background:#f2f2f2;padding:2px 4px;border-radius:4px}
</style></head>
<body>
<h1>ComfyVN</h1>
<p>Quick links:</p>
<ul>
  <li><a href="/docs">/docs</a> (OpenAPI)</li>
  <li><a href="/system/health">/system/health</a></li>
  <li><a href="/render/health">/render/health</a></li>
  <li><a href="/scanner/health">/scanner/health</a></li>
  <li><a href="/jobs/health">/jobs/health</a></li>
  <li><a href="/meta/health">/meta/health</a>, <a href="/meta/info">/meta/info</a>, <a href="/meta/routes">/meta/routes</a></li>
</ul>
</body></html>"""  # noqa: E501

@router.get("/", response_class=HTMLResponse)
def root():
    return HTML