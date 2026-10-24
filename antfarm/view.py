#!/usr/bin/env python3
"""Open a Markdown file in the browser with Mermaid diagrams rendered.

Usage: python3 antfarm/view.py [file.md]   # default: antfarm/README.md
Needs internet (loads marked + mermaid from jsdelivr). Writes antfarm/.view.html (gitignored; inside the project so snap Firefox can read it). The .md is untouched.
"""
import json
import sys
import webbrowser
from pathlib import Path

md_path = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent / "README.md").resolve()
md = md_path.read_text(encoding="utf-8")

page = f"""<!doctype html><meta charset="utf-8"><title>{md_path.name}</title>
<base href="{md_path.parent.as_uri()}/">
<style>
body{{font:16px system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 16px;line-height:1.5;background:#fff;color:#202124}}
pre{{background:#f4f4f4;padding:12px;overflow:auto}} table{{border-collapse:collapse}} td,th{{border:1px solid #ccc;padding:4px 8px}}
.mermaid{{margin:1rem 0}} .err{{color:#c00;font-weight:bold}}
</style>
<div id="c"></div>
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<script>
const c = document.getElementById('c');
c.innerHTML = marked.parse({json.dumps(md)});
c.querySelectorAll('code.language-mermaid').forEach(code => {{
  const d = document.createElement('div'); d.className = 'mermaid'; d.textContent = code.textContent;
  code.parentElement.replaceWith(d);
}});
mermaid.initialize({{startOnLoad: false}});
mermaid.run().catch(e => c.insertAdjacentHTML('afterbegin', '<p class="err">Diagram error: ' + e.message + '</p>'));
</script>"""

out = Path(__file__).resolve().parent / ".view.html"
out.write_text(page, encoding="utf-8")
print(f"Opening {md_path} ({out})")
webbrowser.open(out.as_uri())
