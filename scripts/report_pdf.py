"""docs/report/REPORT.md -> docs/report/REPORT.html -> REPORT.pdf (Chromium via Playwright)."""
import subprocess
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
md = (ROOT / "docs/report/REPORT.md").read_text(encoding="utf-8")
body = markdown.markdown(md, extensions=["tables", "fenced_code"])
css = """body{font-family:Georgia,serif;font-size:10.5pt;line-height:1.35;max-width:780px;
margin:auto}
h1{font-size:18pt}h2{font-size:13pt;margin-top:14pt;border-bottom:1px solid #999}
h3{font-size:11pt}table{border-collapse:collapse;font-size:8.5pt;margin:6pt 0}
td,th{border:1px solid #bbb;padding:2px 5px}code{font-size:8.5pt}pre{font-size:8pt;
background:#f4f4f4;padding:6px;white-space:pre-wrap}"""
html = f"<!doctype html><meta charset=utf-8><title>GigBid R&D report</title><style>{css}</style>{body}"  # noqa: E501
out = ROOT / "docs/report/REPORT.html"
out.write_text(html, encoding="utf-8")
js = f"""const {{chromium}}=require('playwright');(async()=>{{const b=await chromium.launch();
const p=await b.newPage();await p.goto('file:///{out.as_posix()}');
await p.pdf({{path:'{(ROOT / "docs/report/REPORT.pdf").as_posix()}',format:'A4',
margin:{{top:'14mm',bottom:'14mm',left:'14mm',right:'14mm'}}}});await b.close();}})();"""
subprocess.run(["node", "-e", js], cwd=ROOT / "apps/web", check=True)
print("wrote docs/report/REPORT.pdf")
