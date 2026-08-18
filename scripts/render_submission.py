"""Render report/SUBMISSION.md to PDF via markdown -> HTML -> headless Chrome.

Usage: python scripts/render_submission.py
Re-run after every update to SUBMISSION.md; overwrites report/SUBMISSION.pdf.
"""

import base64
import pathlib
import re
import subprocess
import sys

import markdown

ROOT = pathlib.Path(__file__).resolve().parent.parent
MD = ROOT / "report/SUBMISSION.md"
HTML = ROOT / "report/SUBMISSION.html"
PDF = ROOT / "report/SUBMISSION.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page { margin: 18mm 16mm; }
body { font: 10.5pt/1.5 -apple-system, "Helvetica Neue", Arial, sans-serif;
       color: #1a1d21; max-width: 175mm; margin: 0 auto; }
h1 { font-size: 19pt; margin: 0 0 4pt; }
h2 { font-size: 13.5pt; margin: 18pt 0 6pt; border-bottom: 2px solid #2a78d6;
     padding-bottom: 3pt; page-break-after: avoid; }
h1 + p { color: #555; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 9pt;
        page-break-inside: avoid; }
th, td { border: 1px solid #ccd2d8; padding: 3.5pt 6pt; text-align: left; }
th { background: #eef3f9; }
img { max-width: 100%; margin: 6pt 0; page-break-inside: avoid; }
code { font: 8.5pt Menlo, monospace; background: #f2f4f6; padding: 1px 3px;
       border-radius: 3px; }
hr { border: 0; border-top: 1px solid #dde2e7; margin: 14pt 0; }
blockquote { margin: 6pt 0; padding-left: 10pt; border-left: 3px solid #ccd2d8;
             color: #444; }
li { margin: 2pt 0; }
"""


def main():
    md_text = MD.read_text()
    body = markdown.markdown(md_text, extensions=["tables", "sane_lists", "smarty"])

    # inline figures as data URIs so the PDF is self-contained
    def inline(m):
        src = m.group(1)
        p = (MD.parent / src).resolve()
        if not p.exists():
            print(f"  WARNING: missing figure {src}", file=sys.stderr)
            return m.group(0)
        b64 = base64.b64encode(p.read_bytes()).decode()
        return f'src="data:image/png;base64,{b64}"'

    body = re.sub(r'src="([^"]+\.png)"', inline, body)

    HTML.write_text(
        f"<meta charset='utf-8'><title>Ordo Take-Home Submission</title>"
        f"<style>{CSS}</style>\n{body}"
    )
    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={PDF}", HTML.as_uri()],
        check=True, capture_output=True, timeout=120,
    )
    print(f"wrote {PDF} ({PDF.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
