#!/usr/bin/env python3
"""Antfarm dashboard for the pm/ markdown files.

Usage: python3 antfarm/dashboard.py            # local server on http://127.0.0.1:8737, pushes changes over a WebSocket, Ctrl+C to stop
       python3 antfarm/dashboard.py --port N   # other port (default: first free from 8737)
       python3 antfarm/dashboard.py --static   # write pm/dashboard.html instead (read-only, no saving)
       python3 antfarm/dashboard.py --tui      # terminal, live
       add --once for a single snapshot (static/tui), --no-open to skip opening the browser
"""
import base64
import ctypes
import ctypes.util
import hashlib
import html
import json
import mimetypes
import os
import re
import select
import socket
import struct
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PM = Path(__file__).resolve().parent / "pm"
ROOT = PM.parent.parent
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".pytest_cache"}
STATUSES = ["todo", "awaiting-approval", "in-progress", "blocked", "in-review", "done", "cancelled"]
VERDICTS = ["approve", "comment", "request-changes"]
TEST_RESULTS = ["pass", "broken", "needs-change"]
IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}
COLORS = {"todo": "#9aa0a6", "awaiting-approval": "#9334e6", "cancelled": "#5f6368", "in-progress": "#1a73e8", "blocked": "#d93025",
          "in-review": "#f29900", "done": "#188038"}


def frontmatter(path):
    m = re.match(r"---\n(.*?)\n---", path.read_text(encoding="utf-8"), re.S)
    meta = {}
    for line in (m.group(1).splitlines() if m else []):
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.split("#", 1)[0].strip()
    return meta


def sections(md):
    """'## Heading' -> text, keyed by lowercase heading."""
    out, cur = {}, None
    for line in md.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip().lower()
            out[cur] = ""
        elif cur:
            out[cur] += line + "\n"
    return {k: v.strip() for k, v in out.items()}


def load():
    milestones = {}
    for f in sorted((PM / "milestones").glob("*.md")):
        meta = frontmatter(f)
        mid = meta.get("id") or f.stem.split("-")[0]
        milestones[mid] = {"title": meta.get("title", f.stem), "tasks": []}
    for f in sorted((PM / "tasks").glob("*/task.md")):
        t = frontmatter(f)
        t.setdefault("id", f.parent.name)
        t["_key"] = f.parent.name
        t["_md"] = re.sub(r"\A---\n.*?\n---\n?", "", f.read_text(encoding="utf-8"), flags=re.S)
        t["_sections"] = sections(t["_md"])
        t["_criteria"] = re.findall(r"^\s*[-*] \[([ xX])\] (.+)$", t["_sections"].get("acceptance criteria", ""), re.M)
        r = f.parent / "review.md"
        t["_review_md"] = r.read_text(encoding="utf-8") if r.exists() else ""
        if t.get("status") not in STATUSES:
            t["status"] = "todo"
        milestones.setdefault(t.get("milestone", "?"), {"title": "(no milestone file)", "tasks": []})["tasks"].append(t)
    return milestones


def docs():
    """Markdown docs for the Docs tab: {group: [{path, title, md}]}. Paths are relative to the project root."""
    def entry(f):
        md = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^#\s+(.+)$", md, re.M)
        return {"path": f.relative_to(ROOT).as_posix(), "title": m.group(1).strip() if m else f.stem, "md": md}

    def md_files(base, recursive=True):
        if not base.is_dir():
            return []
        files = base.rglob("*.md") if recursive else base.glob("*.md")
        return sorted(f for f in files if f.stat().st_size < 1_000_000
                      and not SKIP_DIRS & set(f.relative_to(base).parts) and not any(p.startswith(".") for p in f.relative_to(base).parts))

    groups = {
        "Project": md_files(ROOT, recursive=False) + md_files(ROOT / "docs"),
        "Vision & plan": [f for f in (PM / n for n in ("vision.md", "architecture.md", "conventions.md", "backlog.md")) if f.exists()]
                         + md_files(PM / "reviews"),
        "Milestones": md_files(PM / "milestones", recursive=False),
        "Antfarm": md_files(PM.parent, recursive=False),
    }
    return {g: [entry(f) for f in fs] for g, fs in groups.items() if fs}


def milestone_reviews(mid):
    """Demo + user reviews of one milestone, from pm/milestones/<mid>/demo.md and reviews/R-*.md."""
    d = PM / "milestones" / mid
    reviews = []
    for f in sorted((d / "reviews").glob("R-*.md")):
        meta = frontmatter(f)
        reviews.append({**{k: meta.get(k, "") for k in ("id", "verdict", "status", "author", "created", "tasks")},
                        "md": re.sub(r"\A---\n.*?\n---\n?", "", f.read_text(encoding="utf-8"), flags=re.S)})
    demo = d / "demo.md"
    return {"demo": demo.read_text(encoding="utf-8") if demo.exists() else "", "reviews": reviews}


def milestone_tests(mid):
    """Human tests of one milestone: pm/milestones/<mid>/human-tests/HT-*.md, written by agents, answered in the dashboard."""
    tests = []
    for f in sorted((PM / "milestones" / mid / "human-tests").glob("HT-*.md")):
        meta = frontmatter(f)
        tests.append({**{k: meta.get(k, "") for k in ("id", "title", "task", "criterion", "status", "handled", "retest_of", "created")},
                      "md": re.sub(r"\A---\n.*?\n---\n?", "", f.read_text(encoding="utf-8"), flags=re.S)})
    return tests


def git_user():
    try:
        return subprocess.run(["git", "-C", str(ROOT), "config", "user.name"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
    except OSError:
        return ""


def initials(user):
    return "".join(w[0] for w in user.split()[:2]).lower() or "x"


def save_images(folder, prefix, images, text):
    """Decode pasted data: URLs to <folder>/<prefix>-<i>.<ext>, point the (attach:i) links at them. Returns the text."""
    if len(images) > 20:
        raise ValueError("at most 20 images")
    files = []
    for i, img in enumerate(images, 1):
        m = re.match(r"data:(image/[a-z]+);base64,(.+)", str(img), re.S)
        if not m or m.group(1) not in IMAGE_TYPES:
            raise ValueError(f"image {i}: only png, jpeg, gif or webp")
        raw = base64.b64decode(m.group(2))
        if len(raw) > 10_000_000:
            raise ValueError(f"image {i} is over 10 MB")
        files.append((f"{prefix}-{i}{IMAGE_TYPES[m.group(1)]}", raw))
    folder.mkdir(parents=True, exist_ok=True)
    for i, (name, raw) in enumerate(files, 1):
        (folder / name).write_bytes(raw)
        text = text.replace(f"(attach:{i})", f"({name})")
    return text


def log(line):
    with open(PM / "timeline.md", "a", encoding="utf-8") as tl:
        tl.write(f"- {time.strftime('%Y-%m-%d %H:%M')} | user | {line}\n")


def save_test_result(data, milestone_ids):
    """Append a result to pm/milestones/<M>/human-tests/<id>.md and mark it for /fetch-feedback. Returns the test id."""
    mid, tid, result, text = data.get("milestone"), str(data.get("id", "")), data.get("result"), str(data.get("text", ""))
    images = data.get("images") or []
    if mid not in milestone_ids:
        raise ValueError("unknown milestone")
    f = PM / "milestones" / mid / "human-tests" / f"{tid}.md"
    if not re.fullmatch(r"HT-\d+-[a-z]+", tid) or not f.is_file():
        raise ValueError("unknown human test")
    if result not in TEST_RESULTS:
        raise ValueError("bad result")
    if result != "pass" and not text.strip() and not images:
        raise ValueError("describe what is wrong")
    if len(text) > 200_000:
        raise ValueError("text too large")
    md = f.read_text(encoding="utf-8")
    n = len(re.findall(r"^## Result ", md, re.M)) + 1
    text = save_images(f.parent, f"{tid}-r{n}", images, text)
    user, now = git_user(), time.strftime("%Y-%m-%d %H:%M")
    head, sep, body = md.partition("\n---\n")
    for key, val in (("status", result), ("handled", "false")):
        if re.search(rf"^{key}:", head, re.M):
            head = re.sub(rf"^{key}:[ \t]*[^\s#]*", f"{key}: {val}", head, count=1, flags=re.M)
        else:
            head += f"\n{key}: {val}"
    body = body.rstrip() + f"\n\n## Result {n}: {result} ({user}, {now})\n\n{text.strip() or 'Works as expected.'}\n"
    f.write_text(head + sep + body, encoding="utf-8")
    log(f"{frontmatter(f).get('task') or '-'} | - | human test {tid} on {mid}: {result} ({len(images)} image(s)), waiting for /fetch-feedback")
    return tid


def save_review(data, milestone_ids):
    """Write pm/milestones/<M>/reviews/R-<nnn>-<initials>.md (+ images) and log it. Returns the review id."""
    mid, verdict, text = data.get("milestone"), data.get("verdict"), str(data.get("text", ""))
    images = data.get("images") or []
    if mid not in milestone_ids:
        raise ValueError("unknown milestone")
    if verdict not in VERDICTS:
        raise ValueError("bad verdict")
    if not text.strip() and not images:
        raise ValueError("empty review")
    if len(text) > 200_000:
        raise ValueError("review too large")
    user = git_user()
    nums = [int(m.group(1)) for f in PM.glob("milestones/*/reviews/R-*.md") if (m := re.match(r"R-(\d+)", f.name))]
    rid = f"R-{max(nums, default=0) + 1:03d}-{initials(user)}"
    folder = PM / "milestones" / mid / "reviews"
    text = save_images(folder, rid, images, text)
    folder.mkdir(parents=True, exist_ok=True)
    now = time.strftime("%Y-%m-%d %H:%M")
    (folder / f"{rid}.md").write_text(
        f"---\nid: {rid}\nmilestone: {mid}\nverdict: {verdict}\nstatus: open        # open | in-progress | addressed | closed\n"
        f"author: {user}\ncreated: {now}\ntasks: []           # tasks created from this review\n---\n"
        f"# {rid}: {verdict} on {mid}\n\n{text.strip()}\n", encoding="utf-8")
    log(f"- | - | review {rid} on {mid}: {verdict} ({len(images)} image(s)), waiting for /fetch-feedback")
    return rid


def pct(tasks, status="done"):
    tasks = [t for t in tasks if t["status"] != "cancelled"]
    return round(100 * sum(t["status"] == status for t in tasks) / len(tasks)) if tasks else 0


def bar(tasks):
    done, prog, rev = pct(tasks), pct(tasks, "in-progress"), pct(tasks, "in-review")
    extra = " · ".join(x for x in (f"+{prog}% in progress" if prog else "", f"+{rev}% in review" if rev else "") if x)
    return (f'<div class="bar" title="{done}% done, {prog}% in progress, {rev}% in review"><div style="width:{done}%"></div>'
            f'<div class="prog" style="width:{prog}%"></div><div class="rev" style="width:{rev}%"></div></div><b>{done}%</b>'
            + (f' <span class="muted prog-label">{extra}</span>' if extra else ""))


CSS = """
:root{--bg:#fff;--fg:#202124;--muted:#5f6368;--line:#dadce0;--card:#f8f9fa;--track:#e8eaed;--accent:#1a73e8}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#1f1f1f;--fg:#e8eaed;--muted:#9aa0a6;--line:#3c4043;--card:#2a2b2e;--track:#3c4043;--accent:#8ab4f8}}
:root[data-theme=dark]{--bg:#1f1f1f;--fg:#e8eaed;--muted:#9aa0a6;--line:#3c4043;--card:#2a2b2e;--track:#3c4043;--accent:#8ab4f8}
body{font:15px system-ui,sans-serif;margin:0;padding:16px clamp(16px,3vw,40px);background:var(--bg);color:var(--fg)}
header{display:flex;align-items:center;gap:12px;flex-wrap:wrap} header h1{margin:0;font-size:22px;flex:1}
nav{display:flex;gap:4px;margin:16px 0;border-bottom:1px solid var(--line)}
nav button{background:none;border:0;border-bottom:2px solid transparent;color:var(--muted);padding:8px 14px;font:inherit;cursor:pointer}
nav button[aria-selected=true]{color:var(--fg);border-color:var(--accent);font-weight:600}
.icon{background:var(--card);border:1px solid var(--line);color:var(--fg);border-radius:8px;padding:6px 10px;cursor:pointer;font:inherit}
.bar{display:inline-flex;width:min(40vw,520px);height:10px;background:var(--track);border-radius:5px;margin-right:8px;vertical-align:middle;overflow:hidden}
.bar div{height:100%;background:#188038}
.bar .prog{background:repeating-linear-gradient(135deg,#8ab4f8 0 5px,#c6dafc 5px 10px);border-left:2px solid var(--bg)}
.bar .rev{background:repeating-linear-gradient(135deg,#f9ab00 0 5px,#fde293 5px 10px);border-left:2px solid var(--bg)}
.bar [style="width:0%"]{display:none} .bar div:first-child[style="width:0%"]+.prog,.bar div:first-child[style="width:0%"]+.prog[style="width:0%"]+.rev{border-left:0} .prog-label{font-size:12px;color:#4285f4}
.pill{color:#fff;padding:1px 8px;border-radius:10px;font-size:12px;white-space:nowrap}
details{border:1px solid var(--line);border-radius:8px;margin:10px 0;background:var(--card)}
summary{cursor:pointer;padding:10px 12px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;list-style:none}
summary::-webkit-details-marker{display:none} summary::before{content:"▸";color:var(--muted)} details[open]>summary::before{content:"▾"}
summary h2{font-size:16px;margin:0;flex:1;min-width:200px}
.wrap{overflow-x:auto;padding:0 12px 10px}
table{width:100%;border-collapse:collapse} th,td{text-align:left;padding:5px 6px;border-bottom:1px solid var(--line)} th{color:var(--muted);font-weight:500}
.settings label{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--line);max-width:480px}
.settings select{font:inherit;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:4px}
.docs{display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:20px;align-items:start}
.docs aside{position:sticky;top:12px;border:1px solid var(--line);border-radius:8px;background:var(--card);padding:8px;max-height:calc(100vh - 40px);overflow:auto;order:2}
.docs aside h3{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin:10px 6px 4px}
.docs aside button{display:block;width:100%;text-align:left;background:none;border:0;color:var(--fg);padding:5px 8px;border-radius:6px;font:inherit;font-size:14px;cursor:pointer}
.docs aside button:hover{background:var(--track)} .docs aside button[aria-current=true]{background:var(--accent);color:var(--bg)}
.doc{min-width:0;line-height:1.55} .doc pre{background:var(--card);border:1px solid var(--line);padding:10px;overflow:auto;border-radius:6px}
.doc code{font-size:13px} .doc img{max-width:100%} .doc table{width:auto} .doc .mermaid{background:var(--card);border-radius:6px;padding:8px;overflow:auto}
.doc .path{font-size:12px;color:var(--muted)}
@media(max-width:720px){.docs{grid-template-columns:1fr}.docs aside{position:static;order:0;max-height:none}}
tr.task{cursor:pointer} tr.task:hover td{background:var(--track)} .caret{display:inline-block;color:var(--muted);transition:transform .15s}
tr.task[aria-expanded=true] .caret{transform:rotate(90deg)} .crit{font-size:12px}
.task-detail{padding:4px 8px 12px 22px;line-height:1.5} .task-detail h4{margin:12px 0 4px;font-size:13px}
.task-detail .meta{display:flex;flex-wrap:wrap;gap:4px 18px;font-size:13px} .task-detail pre{background:var(--bg);border:1px solid var(--line);padding:8px;border-radius:6px;overflow:auto}
.criteria{list-style:none;padding:0;margin:0} .criteria li{padding:2px 0} .criteria li.ok{color:#188038}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]) .criteria li.ok{color:#81c995}} :root[data-theme=dark] .criteria li.ok{color:#81c995}
details.more{background:var(--bg);margin:8px 0} details.more summary{padding:6px 10px;font-size:13px} details.more .doc{padding:0 12px 8px}
.hideBtn{padding:2px 8px;font-size:12px} details.is-hidden{opacity:.55;border-style:dashed}
.review{display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:20px;align-items:start}
.review aside{position:sticky;top:12px;border:1px solid var(--line);border-radius:8px;background:var(--card);padding:8px;order:2}
.review aside button{display:block;width:100%;text-align:left;background:none;border:0;color:var(--fg);padding:6px 8px;border-radius:6px;font:inherit;font-size:14px;cursor:pointer}
.review aside button:hover{background:var(--track)} .review aside button[aria-current=true]{background:var(--accent);color:var(--bg)}
.review .card{border:1px solid var(--line);border-radius:8px;background:var(--card);padding:12px 16px;margin:0 0 16px}
.review .card h3{margin:0 0 8px;font-size:15px} .rv-meta{font-size:13px;color:var(--muted)}
.review textarea{width:100%;min-height:180px;box-sizing:border-box;font:14px ui-monospace,monospace;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:10px}
.review .drop{border:2px dashed var(--line);border-radius:8px;padding:10px;margin:8px 0;color:var(--muted);font-size:13px}
.review .drop.over{border-color:var(--accent)} .thumbs{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.thumbs figure{margin:0;position:relative} .thumbs img{height:90px;border-radius:6px;border:1px solid var(--line)}
.thumbs figcaption{font-size:11px;color:var(--muted)} .thumbs button{position:absolute;top:2px;right:2px;padding:0 6px}
.verdicts{display:flex;gap:14px;flex-wrap:wrap;margin:8px 0} .primary{background:var(--accent);color:var(--bg);border:0;border-radius:8px;padding:8px 16px;font:inherit;cursor:pointer}
.t-pending{background:#9334e6} .t-pass{background:#188038} .t-broken{background:#d93025} .t-needs-change{background:#f29900}
details.passed{background:none} details.passed>summary h3{margin:0;font-size:15px} .passed-body{padding:0 12px 4px}
.ht-form{border-top:1px solid var(--line);margin-top:12px;padding-top:4px} .ht-form textarea{min-height:90px}
.badge{background:#9334e6;color:#fff;border:0;border-radius:14px;padding:4px 12px;cursor:pointer;font:inherit;font-size:13px}
.criteria li.human::after{content:" 🧪";} .htchip{font-size:12px;color:#9334e6}
.v-approve{background:#188038} .v-comment{background:#5f6368} .v-request-changes{background:#d93025}
@media(max-width:720px){.review{grid-template-columns:1fr}.review aside{position:static;order:0}}
.live{font-size:13px} .live.on{color:#188038} .live.off{color:var(--muted)}
.stale{background:var(--card);border:1px solid var(--accent);border-radius:8px;padding:6px 12px}
.muted{color:var(--muted)} [hidden]{display:none!important}
body.hide-done tr.s-done, body.hide-cancelled tr.s-cancelled{display:none}
"""

JS = """
const K='antfarm-dashboard';
let DOCS=JSON.parse(document.getElementById('docs-data').textContent);
let ALL=Object.values(DOCS).flat();
let libsReady=false,libs;
function loadLibs(){return libs||(libs=Promise.all(['https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js','https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js']
  .map(src=>new Promise((ok,err)=>{const s=document.createElement('script');s.src=src;s.onload=ok;s.onerror=()=>err(src);document.head.appendChild(s);}))).then(()=>libsReady=true));}
function isDark(){return root.getAttribute('data-theme')==='dark'||(!root.hasAttribute('data-theme')&&matchMedia('(prefers-color-scheme: dark)').matches);}
function buildSidebar(){const a=document.getElementById('docList');
  a.innerHTML=ALL.length?'':'<p class=muted>No Markdown docs found.</p>';
  for(const [g,items] of Object.entries(DOCS)){const h=document.createElement('h3');h.textContent=g;a.appendChild(h);
    for(const d of items){const b=document.createElement('button');b.textContent=d.title;b.title=d.path;b.dataset.path=d.path;b.onclick=()=>openDoc(d.path);a.appendChild(b);}}}
function openDoc(path){const d=ALL.find(x=>x.path===path)||ALL[0];if(!d)return;st.doc=d.path;save();
  document.querySelectorAll('#docList button').forEach(b=>b.setAttribute('aria-current',b.dataset.path===d.path));
  const c=document.getElementById('docBody');
  loadLibs().then(()=>{c.innerHTML='<p class=path>'+d.path+'</p>'+marked.parse(d.md);
    c.querySelectorAll('code.language-mermaid').forEach(code=>{const m=document.createElement('div');m.className='mermaid';m.textContent=code.textContent;code.parentElement.replaceWith(m);});
    c.querySelectorAll('a[href]').forEach(a=>{const h=a.getAttribute('href');if(/^[a-z]+:|^#/.test(h))return;
      const base=d.path.split('/').slice(0,-1);for(const part of h.split('#')[0].split('/')){if(part==='..')base.pop();else if(part&&part!=='.')base.push(part);}
      const target=base.join('/');if(ALL.some(x=>x.path===target))a.onclick=ev=>{ev.preventDefault();openDoc(target);scrollTo(0,0);};});
    mermaid.initialize({startOnLoad:false,theme:isDark()?'dark':'default'});
    mermaid.run({nodes:c.querySelectorAll('.mermaid')}).catch(e=>c.insertAdjacentHTML('afterbegin','<p style="color:#d93025">Diagram error: '+e.message+'</p>'));
  }).catch(src=>{c.innerHTML='<p class=muted>Could not load '+src+' (needs internet). Raw Markdown:</p><pre></pre>';c.querySelector('pre').textContent=d.md;});}
let st={theme:'auto',tab:'tasks',closed:[],hidden:[],showHidden:false,hideDone:false,hideCancelled:false};
try{Object.assign(st,JSON.parse(localStorage.getItem(K)||'{}'))}catch(e){}
const save=()=>{try{localStorage.setItem(K,JSON.stringify(st))}catch(e){}};
const root=document.documentElement;
function applyTheme(){if(st.tab==='docs'&&libsReady)openDoc(st.doc);st.theme==='auto'?root.removeAttribute('data-theme'):root.setAttribute('data-theme',st.theme);
  const dark=st.theme==='dark'||(st.theme==='auto'&&matchMedia('(prefers-color-scheme: dark)').matches);
  document.getElementById('themeBtn').textContent=dark?'☀️ Light':'🌙 Dark';}
function showTab(t){st.tab=t;save();if(t==='docs')openDoc(st.doc);if(t==='review')openReview(st.rv);if(t==='tests')openTests(st.ht);document.getElementById('stale').hidden=true;document.querySelectorAll('nav button').forEach(b=>b.setAttribute('aria-selected',b.dataset.tab===t));
  document.querySelectorAll('[data-panel]').forEach(p=>p.hidden=p.dataset.panel!==t);}
function applyFilters(){document.body.classList.toggle('hide-done',st.hideDone);document.body.classList.toggle('hide-cancelled',st.hideCancelled);}
document.getElementById('themeBtn').onclick=()=>{const dark=root.getAttribute('data-theme')==='dark'||(!root.hasAttribute('data-theme')&&matchMedia('(prefers-color-scheme: dark)').matches);
  st.theme=dark?'light':'dark';save();applyTheme();document.getElementById('setTheme').value=st.theme;};
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>showTab(b.dataset.tab));
function bindTasks(){
document.querySelectorAll('details[data-m]').forEach(d=>{d.open=!st.closed.includes(d.dataset.m);
  d.ontoggle=()=>{st.closed=st.closed.filter(m=>m!==d.dataset.m);if(!d.open)st.closed.push(d.dataset.m);save();};});
document.querySelectorAll('.hideBtn').forEach(b=>b.onclick=ev=>{ev.preventDefault();ev.stopPropagation();const m=b.closest('details').dataset.m;
  st.hidden=st.hidden.includes(m)?st.hidden.filter(x=>x!==m):[...st.hidden,m];save();applyHidden();});
applyHidden();
document.querySelectorAll('tr.task').forEach(row=>{setTask(row,st.openTasks.includes(row.dataset.task));
  const toggle=()=>{const open=row.getAttribute('aria-expanded')!=='true';setTask(row,open);
    st.openTasks=st.openTasks.filter(k=>k!==row.dataset.task);if(open)st.openTasks.push(row.dataset.task);save();};
  row.onclick=toggle;row.onkeydown=ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();toggle();}};});
document.querySelectorAll('details.more').forEach(d=>d.ontoggle=()=>{if(!d.open||d.dataset.done)return;d.dataset.done=1;
  const [kind,key]=d.dataset.md.split(/:(.*)/);const md=TASKS[key][kind];const box=d.querySelector('.doc');
  loadLibs().then(()=>box.innerHTML=marked.parse(md)).catch(()=>{box.innerHTML='<pre></pre>';box.querySelector('pre').textContent=md;});});}
const setAll=open=>document.querySelectorAll('details[data-m]').forEach(d=>d.open=open);
document.getElementById('expandAll').onclick=()=>setAll(true);
document.getElementById('collapseAll').onclick=()=>setAll(false);
function applyHidden(){let n=0;document.querySelectorAll('details[data-m]').forEach(d=>{const h=st.hidden.includes(d.dataset.m);n+=h;
  d.classList.toggle('is-hidden',h);d.hidden=h&&!st.showHidden;d.querySelector('.hideBtn').textContent=h?'Unhide':'Hide';});
  const b=document.getElementById('showHidden');b.hidden=!n;b.textContent=(st.showHidden?'Hide hidden':'Show hidden')+' ('+n+')';}
document.getElementById('showHidden').onclick=()=>{st.showHidden=!st.showHidden;save();applyHidden();};
let TASKS=JSON.parse(document.getElementById('task-data').textContent);
st.openTasks=st.openTasks||[];
function setTask(row,open){const d=document.querySelector('tr.detail[data-for="'+row.dataset.task+'"]');d.hidden=!open;row.setAttribute('aria-expanded',open);}
const bind=(id,key,cast)=>{const el=document.getElementById(id);el[el.type==='checkbox'?'checked':'value']=st[key];
  el.onchange=()=>{st[key]=cast(el.type==='checkbox'?el.checked:el.value);save();applyTheme();applyFilters();};};
bind('setTheme','theme',String);bind('setDone','hideDone',Boolean);bind('setCancelled','hideCancelled',Boolean);
"""


REVIEW_JS = r"""
let RV=JSON.parse(document.getElementById('review-data').textContent);
const SERVER=RV.server, BASE=RV.base;
function fixImages(box,folder){box.querySelectorAll('img[src]').forEach(i=>{const s=i.getAttribute('src');if(!/^([a-z]+:|\/)/.test(s))i.src=BASE+folder+s;});}
function md(box,text,folder){loadLibs().then(()=>{box.innerHTML=marked.parse(text);fixImages(box,folder);
  box.querySelectorAll('code.language-mermaid').forEach(c=>{const m=document.createElement('div');m.className='mermaid';m.textContent=c.textContent;c.parentElement.replaceWith(m);});
  mermaid.initialize({startOnLoad:false,theme:isDark()?'dark':'default'});mermaid.run({nodes:box.querySelectorAll('.mermaid')}).catch(()=>{});})
  .catch(()=>{box.innerHTML='<pre></pre>';box.querySelector('pre').textContent=text;});}

// One feedback form (choice + text + pasted screenshots), used by the Review and Human tests tabs.
function makeForm(el,{title,name,choices,placeholder,draftKey,endpoint,payload,needText}){
  el.innerHTML='<h3></h3><div class=verdicts></div><textarea></textarea>'+
    '<div class=drop>Drop images here, paste into the text, or <label style="text-decoration:underline;cursor:pointer">choose files<input type=file accept="image/png,image/jpeg,image/gif,image/webp" multiple hidden></label><div class=thumbs></div></div>'+
    '<button class=primary>Save</button> <span class=muted></span>';
  el.querySelector('h3').textContent=title;
  const v=el.querySelector('.verdicts');for(const [val,label] of choices){const l=document.createElement('label');l.innerHTML='<input type=radio> ';
    const i=l.querySelector('input');i.name=name;i.value=val;l.append(label);v.appendChild(l);}
  const ta=el.querySelector('textarea'),drop=el.querySelector('.drop'),thumbs=el.querySelector('.thumbs'),msg=el.querySelector('.muted:last-child');let attach=[];
  ta.placeholder=placeholder;try{ta.value=localStorage.getItem(K+'-draft-'+draftKey)||''}catch(e){}
  ta.oninput=()=>{try{localStorage.setItem(K+'-draft-'+draftKey,ta.value)}catch(e){}};
  const renderThumbs=()=>{thumbs.innerHTML='';attach.forEach((a,i)=>{if(!a)return;const f=document.createElement('figure');
    f.innerHTML='<img alt=""><figcaption></figcaption><button class=icon title=Remove>×</button>';f.querySelector('img').src=a;f.querySelector('figcaption').textContent='screenshot '+(i+1);
    f.querySelector('button').onclick=()=>{attach[i]=null;ta.value=ta.value.split('![screenshot '+(i+1)+'](attach:'+(i+1)+')').join('');ta.oninput();renderThumbs();};thumbs.appendChild(f);});};
  const addFiles=files=>{for(const f of files){if(!/^image\/(png|jpeg|gif|webp)$/.test(f.type))continue;const r=new FileReader();
    r.onload=()=>{attach.push(r.result);const n=attach.length,tag='\n![screenshot '+n+'](attach:'+n+')\n';
      const p=ta.selectionStart??ta.value.length;ta.value=ta.value.slice(0,p)+tag+ta.value.slice(p);ta.oninput();renderThumbs();};r.readAsDataURL(f);}};
  el.addFiles=addFiles;
  ta.addEventListener('paste',ev=>{const fs=[...ev.clipboardData.files];if(fs.length){ev.preventDefault();addFiles(fs);}});
  ['dragover','dragenter'].forEach(t=>drop.addEventListener(t,ev=>{ev.preventDefault();drop.classList.add('over');}));
  ['dragleave','drop'].forEach(t=>drop.addEventListener(t,()=>drop.classList.remove('over')));
  drop.addEventListener('drop',ev=>{ev.preventDefault();addFiles(ev.dataTransfer.files);});
  el.querySelector('input[type=file]').onchange=ev=>{addFiles(ev.target.files);ev.target.value='';};
  el.querySelector('button.primary').onclick=async()=>{const choice=(el.querySelector('input[type=radio]:checked')||{}).value;
    if(!choice){msg.textContent='Pick one of the options.';return;}
    if(needText&&needText(choice)&&!ta.value.trim()&&!attach.some(Boolean)){msg.textContent='Describe what is wrong (text or screenshot).';return;}
    const idx=attach.map((a,i)=>a?i:-1).filter(i=>i>=0);let text=ta.value;const images=[];
    idx.forEach((i,j)=>{text=text.split('(attach:'+(i+1)+')').join('(attach:'+(j+1)+')');images.push(attach[i]);});
    msg.textContent='Saving…';
    try{const res=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...payload(choice),text,images})});
      const out=await res.json();if(!res.ok)throw new Error(out.error||res.status);
      try{localStorage.removeItem(K+'-draft-'+draftKey)}catch(e){}
      msg.textContent='Saved '+out.id+'. Run /fetch-feedback in Claude Code (a running manager picks it up automatically).';setTimeout(()=>refresh().then(()=>showTab(st.tab)),800);}
    catch(e){msg.textContent='Could not save: '+e.message;}};
  return el;}

function sideList(id,count,open){const a=document.getElementById(id);a.innerHTML='';
  for(const [mid,m] of Object.entries(RV.milestones)){const b=document.createElement('button');const n=count(m);
    b.textContent=mid+': '+m.title+(n?' ('+n+')':'');b.dataset.m=mid;b.onclick=()=>open(mid);a.appendChild(b);}}
function pick(mid,listId){const ids=Object.keys(RV.milestones);if(!ids.length)return null;if(!RV.milestones[mid])mid=ids[0];
  document.querySelectorAll('#'+listId+' button').forEach(b=>b.setAttribute('aria-current',b.dataset.m===mid));return mid;}
function card(meta,mdText,folder){const c=document.createElement('div');c.className='card';c.innerHTML='<div class=rv-meta></div><div class=doc></div>';
  for(const [txt,cls] of meta){const sp=document.createElement(cls?'span':'b');if(cls)sp.className='pill '+cls;sp.textContent=txt;c.firstChild.append(sp,' ');}
  md(c.querySelector('.doc'),mdText,folder);return c;}

// Review tab
function openReview(mid){mid=pick(mid,'rvList');if(!mid){document.getElementById('rvTitle').textContent='No milestones yet.';return;}
  st.rv=mid;save();const m=RV.milestones[mid];document.getElementById('rvTitle').textContent=mid+': '+m.title;
  const demo=document.getElementById('rvDemo');
  if(m.demo)md(demo,m.demo,'milestones/'+mid+'/');else demo.innerHTML='<p class=muted>No demo yet. The manager writes milestones/'+mid+'/demo.md (with screenshots) when the milestone is done.</p>';
  const list=document.getElementById('rvPrev');list.innerHTML=m.reviews.length?'':'<p class=muted>No reviews yet.</p>';
  for(const r of [...m.reviews].reverse())list.appendChild(card([[r.verdict,'v-'+r.verdict],[r.id],['status '+r.status],[r.author+' · '+r.created+(r.tasks&&r.tasks!=='[]'?' · tasks '+r.tasks:'')]],r.md,'milestones/'+mid+'/reviews/'));
  const f=document.getElementById('rvForm');f.hidden=!SERVER;document.getElementById('rvStatic').hidden=SERVER;
  if(SERVER)makeForm(f,{title:'Your review',name:'verdict',choices:[['approve','Approve'],['comment','Comment'],['request-changes','Request changes']],
    placeholder:'What is wrong, or how should it work? Paste screenshots straight into this box (Ctrl+V).',draftKey:mid,endpoint:'/api/review',
    payload:v=>({milestone:mid,verdict:v}),needText:v=>v!=='approve'});}

// Human tests tab
const waiting=t=>t.status==='pending';
function openTests(mid){mid=pick(mid,'htList');if(!mid){document.getElementById('htTitle').textContent='No milestones yet.';return;}
  st.ht=mid;save();const m=RV.milestones[mid];document.getElementById('htTitle').textContent=mid+': '+m.title;
  const list=document.getElementById('htBody');list.innerHTML=m.tests.length?'':'<p class=muted>No human tests for this milestone. Agents add them when they cannot check something themselves (real logins, hardware, devices, how it feels).</p>';
  const order={pending:0,broken:1,'needs-change':2,pass:3};
  const passed=m.tests.filter(t=>t.status==='pass');let passedBox=null;
  if(passed.length){passedBox=document.createElement('details');passedBox.className='passed';passedBox.open=!!st.htPassedOpen;
    passedBox.innerHTML='<summary><h3>✅ Passed ('+passed.length+')</h3></summary><div class=passed-body></div>';
    passedBox.ontoggle=()=>{st.htPassedOpen=passedBox.open;save();};}
  for(const t of [...m.tests].sort((a,b)=>(order[a.status]??9)-(order[b.status]??9))){
    const meta=[[t.status,'t-'+t.status],[t.id],[t.title]];if(t.task)meta.push(['task '+t.task]);if(t.retest_of)meta.push(['retest of '+t.retest_of]);
    if(t.status!=='pending'&&t.handled!=='true')meta.push(['waiting for agent']);
    const c=card(meta,t.md,'milestones/'+mid+'/human-tests/');(t.status==='pass'?passedBox.querySelector('.passed-body'):list).appendChild(c);
    if(SERVER){const f=document.createElement('div');f.className='ht-form';c.appendChild(f);
      makeForm(f,{title:t.status==='pending'?'Your result':'Test again',name:'r-'+t.id,choices:[['pass','✅ Works'],['broken','❌ Broken'],['needs-change','✏️ Needs change']],
        placeholder:'What did you see? For broken / needs change: what happened and what you expected. Paste screenshots here.',draftKey:'ht-'+t.id,endpoint:'/api/human-test',
        payload:r=>({milestone:mid,id:t.id,result:r}),needText:r=>r!=='pass'});}}
  if(passedBox)list.appendChild(passedBox);
  if(m.tests.length&&!m.tests.some(t=>t.status!=='pass'))list.insertAdjacentHTML('afterbegin','<p class=muted>All human tests for this milestone passed. 🎉</p>');
  if(!SERVER)list.insertAdjacentHTML('afterbegin','<p class=muted>Read-only file. Start <code>python3 antfarm/dashboard.py</code> (without --static) to record results.</p>');}
function bindHeader(){document.getElementById('htBadge').onclick=()=>showTab('tests');}
function buildLists(){
  sideList('rvList',m=>m.reviews.filter(r=>r.status==='open'||r.status==='in-progress').length,openReview);
  sideList('htList',m=>m.tests.filter(waiting).length,openTests);
  for(const [id,cur] of [['rvList',st.rv],['htList',st.ht]])document.querySelectorAll('#'+id+' button').forEach(b=>b.setAttribute('aria-current',b.dataset.m===cur));
  buildSidebar();}

// Live updates: the server pushes "changed" over a WebSocket; we swap in the new data and Tasks view, no reload.
async function refresh(){
  const doc=new DOMParser().parseFromString(await (await fetch('/',{cache:'no-store'})).text(),'text/html');
  const json=id=>JSON.parse(doc.getElementById(id).textContent);
  const views={review:()=>JSON.stringify(RV.milestones[st.rv]),tests:()=>JSON.stringify(RV.milestones[st.ht]),docs:()=>JSON.stringify(DOCS)};
  const before=views[st.tab]&&views[st.tab]();
  for(const id of ['progress','counts','updated','milestones','htBadge'])document.getElementById(id).replaceWith(doc.getElementById(id));
  TASKS=json('task-data');RV=json('review-data');DOCS=json('docs-data');ALL=Object.values(DOCS).flat();
  bindHeader();bindTasks();applyFilters();buildLists();
  if(before!==undefined&&before!==views[st.tab]())document.getElementById('stale').hidden=false;}
document.getElementById('staleBtn').onclick=()=>showTab(st.tab);
function connect(delay=1000){if(!SERVER)return;const live=document.getElementById('live');
  const ws=new WebSocket('ws://'+location.host+'/ws');
  ws.onopen=()=>{live.className='live on';live.textContent='● live';if(delay>1000)refresh();delay=1000;};
  ws.onmessage=()=>refresh().catch(()=>{});
  ws.onclose=()=>{live.className='live off';live.textContent='○ reconnecting';setTimeout(()=>connect(Math.min(delay*2,15000)),delay);};}

// start-up runs last, after every tab's code is defined
bindHeader();bindTasks();buildLists();applyTheme();applyFilters();showTab(st.tab);connect(2000);
"""


def inline(text):
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(text))


def task_detail(t):
    e = html.escape
    sec, crit, rev = t["_sections"], t["_criteria"], t["_review_md"]
    met = sum(c[0] != " " for c in crit)
    crit_html = ("<ul class='criteria'>" + "".join(
        f"<li class='{'ok' if c != ' ' else ''}{' human' if '(human)' in txt else ''}'>{'✓' if c != ' ' else '○'} {inline(txt)}</li>" for c, txt in crit) + "</ul>"
        if crit else "<p class='muted'>No acceptance criteria written.</p>")
    what = sec.get("what", "")
    files = [l.lstrip("-* ").strip() for l in sec.get("files expected to touch", "").splitlines() if l.strip()]
    tests = sec.get("tests", "")
    rounds = len(re.findall(r"^## Round", rev, re.M))
    verdicts = re.findall(r"^Verdict:\s*(\S+)", rev, re.M)
    meta = [("Feature", t.get("feature", "")), ("Branch", t.get("branch", "")), ("Blocked by", t.get("blocked_by", "")),
            ("Blocked reason", t.get("blocked_reason", ""))]
    meta_html = "".join(f"<div><span class='muted'>{k}</span> {e(v)}</div>" for k, v in meta if v and v != "[]")
    review_html = (f"{rounds} round(s), last verdict <b>{e(verdicts[-1]) if verdicts else '?'}</b> · "
                   f"{rev.count('[bug]')} bugs · {rev.count('[nit]')} nits" if rev else "<span class='muted'>Not reviewed yet.</span>")
    return (f"<div class='task-detail'>"
            f"{'<div class=meta>' + meta_html + '</div>' if meta_html else ''}"
            f"{'<h4>What</h4><div class=what>' + inline(what).replace(chr(10), '<br>') + '</div>' if what else ''}"
            f"<h4>Done when <span class='muted'>({met}/{len(crit)} met)</span></h4>{crit_html}"
            f"{'<h4>Tests</h4><pre>' + e(tests) + '</pre>' if tests else ''}"
            f"{'<h4>Files expected</h4><p>' + ', '.join('<code>' + e(x.strip('`')) + '</code>' for x in files) + '</p>' if files else ''}"
            f"<h4>Review</h4><p>{review_html}</p>"
            + ("<h4>Human tests</h4><p>" + " · ".join(f"<span class='pill t-{e(h['status'])}'>{e(h['status'])}</span> {e(h['id'])} {e(h['title'])}" for h in t.get("_tests", [])) + "</p>"
               if t.get("_tests") else "")
            + f"<details class='more' data-md='task:{e(t['_key'])}'><summary>Full task file</summary><div class='doc'></div></details>"
            f"{'<details class=more data-md=review:' + e(t['_key']) + '><summary>Review file</summary><div class=doc></div></details>' if rev else ''}"
            f"</div>")


def render(milestones, server=False):
    e = html.escape
    all_tasks = [t for m in milestones.values() for t in m["tasks"]]
    tests = {mid: milestone_tests(mid) for mid in milestones}
    pending = sum(t["status"] == "pending" for ts in tests.values() for t in ts)
    for mid, m in milestones.items():
        for t in m["tasks"]:
            t["_tests"] = [h for h in tests[mid] if h["task"] == t["id"]]
    counts = " ".join(f'<span class="pill" style="background:{COLORS[s]}">{s}: '
                      f'{sum(t["status"] == s for t in all_tasks)}</span>' for s in STATUSES)
    sections = []
    for mid, m in milestones.items():
        rows = "".join(
            f'<tr class="task s-{t["status"]}" data-task="{e(t["_key"])}" tabindex="0" aria-expanded="false">'
            f'<td><span class="caret">▸</span> {e(t["id"])}</td><td>{e(t.get("title", ""))}'
            + (f' <span class="muted crit">✓ {sum(c[0] != " " for c in t["_criteria"])}/{len(t["_criteria"])}</span>' if t["_criteria"] else "")
            + f'</td><td>{e(t.get("assignee", ""))}</td>'
            f'<td><span class="pill" style="background:{COLORS[t["status"]]}">{t["status"]}</span></td>'
            f'<td>{e(t.get("blocked_by", ""))} {e(t.get("blocked_reason", ""))}</td></tr>'
            f'<tr class="detail s-{t["status"]}" data-for="{e(t["_key"])}" hidden><td colspan="5">{task_detail(t)}</td></tr>'
            for t in m["tasks"])
        done = sum(t["status"] == "done" for t in m["tasks"])
        waiting = sum(h["status"] == "pending" for h in tests[mid])
        sections.append(f'<details open data-m="{e(mid)}"><summary><h2>{e(mid)}: {e(m["title"])}</h2>'
                        f'<span class="muted">{done}/{len(m["tasks"])}</span>{bar(m["tasks"])}'
                        + (f'<span class="htchip">🧪 {waiting} waiting</span>' if waiting else "") + f'<button class="icon hideBtn" title="Hide this milestone">Hide</button></summary>'
                        f'<div class="wrap"><table><tr><th>Task</th><th>Title</th><th>Assignee</th><th>Status</th><th>Blocked by / reason</th></tr>'
                        f'{rows}</table></div></details>')
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Antfarm dashboard</title>
<script>try{{const t=JSON.parse(localStorage.getItem('antfarm-dashboard')||'{{}}').theme;if(t&&t!=='auto')document.documentElement.setAttribute('data-theme',t)}}catch(e){{}}</script>
<style>{CSS}</style></head><body>
<header><h1>🐜 Project progress</h1><button class="badge" id="htBadge"{"" if pending else " hidden"}>🧪 {pending} human test{"s" if pending != 1 else ""} waiting</button><span id="live" class="live off">{"○ connecting" if server else "static snapshot"}</span><button class="icon" id="themeBtn">🌙 Dark</button></header>
<div id="progress">{bar(all_tasks)}</div><p id="counts">{counts}</p>
<p id="stale" class="stale" hidden>This view has new changes. <button class="icon" id="staleBtn">Refresh view</button></p>
<nav role="tablist"><button data-tab="tasks" role="tab">Tasks</button><button data-tab="docs" role="tab">Docs</button><button data-tab="review" role="tab">Review</button><button data-tab="tests" role="tab">Human tests</button><button data-tab="settings" role="tab">Settings</button></nav>
<section data-panel="tasks">
<p><button class="icon" id="expandAll">Expand all</button> <button class="icon" id="collapseAll">Collapse all</button> <button class="icon" id="showHidden" hidden></button></p>
<div id="milestones">{''.join(sections) or '<p>No milestones yet. Run /plan-vision.</p>'}</div>
</section>
<section data-panel="docs" class="docs" hidden><article class="doc" id="docBody"><p class="muted">Loading…</p></article><aside id="docList"></aside></section>
<section data-panel="review" class="review" hidden>
<div><h2 id="rvTitle" style="margin-top:0"></h2>
<div class="card"><h3>Demo: what was built and how to use it</h3><div class="doc" id="rvDemo"></div></div>
<div class="card" id="rvForm"></div>
<div class="card" id="rvStatic" hidden><p class="muted">Read-only file. Start <code>python3 antfarm/dashboard.py</code> (without --static) to write reviews.</p></div>
<h3>Earlier reviews</h3><div id="rvPrev"></div></div>
<aside id="rvList"></aside></section>
<section data-panel="tests" class="review" hidden>
<div><h2 id="htTitle" style="margin-top:0"></h2><p class="muted">Things the agents could not check themselves. Follow the steps, then tell them how it went.</p><div id="htBody"></div></div>
<aside id="htList"></aside></section>
<section data-panel="settings" class="settings" hidden>
<label>Theme <select id="setTheme"><option value="auto">System</option><option value="light">Light</option><option value="dark">Dark</option></select></label>
<label>Hide done tasks <input type="checkbox" id="setDone"></label>
<label>Hide cancelled tasks <input type="checkbox" id="setCancelled"></label>
<p class="muted">Settings are saved in this browser only.</p>
</section>
<p class="muted" id="updated">Updated {time.strftime("%H:%M:%S")} · {"live: changes are pushed over a WebSocket" if server else "static snapshot: reload the page to see changes"}</p>
<script type="application/json" id="task-data">{json.dumps({t["_key"]: {"task": t["_md"], "review": t["_review_md"]} for t in all_tasks}).replace("</", "<\\/")}</script>
<script type="application/json" id="review-data">{json.dumps({"server": server, "base": "/files/" if server else PM.as_uri() + "/",
    "milestones": {mid: {"title": m["title"], "tests": tests[mid], **milestone_reviews(mid)} for mid, m in milestones.items()}}).replace("</", "<\\/")}</script>
<script type="application/json" id="docs-data">{json.dumps(docs()).replace("</", "<\\/")}</script>
<script>{JS}{REVIEW_JS}</script></body></html>"""


ANSI = {"todo": "90", "awaiting-approval": "35", "cancelled": "2;9", "in-progress": "34", "blocked": "31", "in-review": "33", "done": "32"}


def tui(milestones):
    def tbar(tasks, w=30):
        p, q, r = pct(tasks), pct(tasks, "in-progress"), pct(tasks, "in-review")
        n, k, j = p * w // 100, q * w // 100, r * w // 100
        return (f"\033[32m{'█' * n}\033[94m{'▒' * k}\033[93m{'▒' * j}\033[90m{'░' * (w - n - k - j)}\033[0m {p:3}%"
                + (f" \033[94m+{q}% in progress\033[0m" if q else "") + (f" \033[93m+{r}% in review\033[0m" if r else ""))
    all_tasks = [t for m in milestones.values() for t in m["tasks"]]
    print(f"\033[1mPROJECT\033[0m  {tbar(all_tasks)}")
    print("  " + "  ".join(f"\033[{ANSI[s]}m{s}: {sum(t['status'] == s for t in all_tasks)}\033[0m" for s in STATUSES))
    for mid, m in milestones.items():
        print(f"\n\033[1m{mid}: {m['title']}\033[0m  {tbar(m['tasks'])}")
        for t in m["tasks"]:
            extra = " ".join(filter(None, [t.get("blocked_by", "").strip("[]"), t.get("blocked_reason", "")]))
            print(f"  {t['id']:<10} \033[{ANSI[t['status']]}m{t['status']:<17}\033[0m {t.get('title', '')}" + (f" \033[2m@{t['assignee']}\033[0m" if t.get("assignee") else "")
                  + (f"  \033[31m({extra})\033[0m" if t["status"] == "blocked" and extra else ""))
    if not milestones:
        print("No milestones yet. Run /plan-vision.")


class Watcher:
    """Blocks in wait() until a pm/ file or a project doc changes. Linux: inotify (no polling).
    Elsewhere: compares file mtimes every 2 s."""
    MASK = 0x8 | 0x40 | 0x80 | 0x100 | 0x200  # CLOSE_WRITE, MOVED_FROM, MOVED_TO, CREATE, DELETE
    IN_ISDIR = 0x40000000

    def __init__(self):
        self.dirs = [(PM, True), (ROOT, False), (ROOT / "docs", True)]  # (dir, recursive)
        self.libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True) if sys.platform.startswith("linux") else None
        self.fd, self.wds = -1, {}
        if self.libc:
            self.fd = self.libc.inotify_init1(0)
            for d, rec in self.dirs:
                self.watch(d, rec)
        if self.fd < 0:
            self.libc, self.snap = None, self.snapshot()

    def watch(self, d, recursive):
        if not d.is_dir() or (d != ROOT and SKIP_DIRS & set(d.parts)):
            return
        wd = self.libc.inotify_add_watch(self.fd, str(d).encode(), self.MASK)
        if wd >= 0:
            self.wds[wd] = (d, recursive)
        if recursive:
            for sub in d.iterdir():
                if sub.is_dir() and not sub.name.startswith("."):
                    self.watch(sub, True)

    @staticmethod
    def relevant(path):
        return not path.name.startswith(".") and path.suffix.lower() in {".md", ".png", ".jpg", ".jpeg", ".gif", ".webp"}

    def snapshot(self):
        files = [f for d, rec in self.dirs if d.is_dir() for f in (d.rglob("*") if rec else d.glob("*"))
                 if f.is_file() and self.relevant(f) and not SKIP_DIRS & set(f.parts)]
        return {f: f.stat().st_mtime_ns for f in files}

    def events(self, timeout=None):
        """Read pending inotify events; True if any touched a relevant file."""
        hit = False
        while select.select([self.fd], [], [], timeout)[0]:
            buf, i, timeout = os.read(self.fd, 65536), 0, 0
            while i < len(buf):
                wd, mask, _, n = struct.unpack_from("iIII", buf, i)
                name = buf[i + 16:i + 16 + n].rstrip(b"\0").decode(errors="replace")
                i += 16 + n
                d, rec = self.wds.get(wd, (None, False))
                if d is None:
                    continue
                if mask & self.IN_ISDIR:
                    if rec and mask & 0x180:  # new or moved-in folder: watch it, and count it as a change
                        self.watch(d / name, True)
                        hit = True
                elif self.relevant(d / name):
                    hit = True
        return hit

    def wait(self):
        if not self.libc:
            while True:  # ponytail: mtime scan every 2 s where inotify is missing (macOS/Windows)
                time.sleep(2)
                snap = self.snapshot()
                if snap != self.snap:
                    self.snap = snap
                    return
        while not self.events():
            pass
        while self.events(0.3):  # debounce: one push for a burst of writes
            pass


WS_CLIENTS, WS_LOCK = set(), threading.Lock()


def ws_send(sock, text):
    data = text.encode()
    head = bytes([0x81, len(data)]) if len(data) < 126 else bytes([0x81, 126]) + struct.pack(">H", len(data))
    sock.sendall(head + data)


def broadcast(text):
    with WS_LOCK:
        for sock in list(WS_CLIENTS):
            try:
                ws_send(sock, text)
            except OSError:
                WS_CLIENTS.discard(sock)


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, ctype="text/html; charset=utf-8"):
        body = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def same_origin(self):
        origin = self.headers.get("Origin", "")
        return not origin or origin in {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}

    def websocket(self):
        """RFC 6455 server side, just enough to push 'changed' messages and answer ping/close."""
        key = self.headers.get("Sec-WebSocket-Key", "")
        if not key or not self.same_origin():
            return self.send(403, "forbidden", "text/plain")
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        self.wfile.write(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                         f"Sec-WebSocket-Accept: {accept}\r\n\r\n".encode())
        self.wfile.flush()
        sock, self.close_connection = self.connection, True
        with WS_LOCK:
            WS_CLIENTS.add(sock)
        try:
            while True:
                head = self.rfile.read(2)
                if len(head) < 2:
                    break
                op, n = head[0] & 0x0F, head[1] & 0x7F
                n = struct.unpack(">H", self.rfile.read(2))[0] if n == 126 else struct.unpack(">Q", self.rfile.read(8))[0] if n == 127 else n
                mask = self.rfile.read(4) if head[1] & 0x80 else b"\0\0\0\0"
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(self.rfile.read(n)))
                if op == 8:  # close
                    break
                if op == 9:  # ping -> pong
                    with WS_LOCK:
                        sock.sendall(bytes([0x8A, len(payload)]) + payload)
        except (OSError, struct.error):
            pass
        finally:
            with WS_LOCK:
                WS_CLIENTS.discard(sock)
                try:
                    sock.sendall(b"\x88\x00")
                except OSError:
                    pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/ws" and self.headers.get("Upgrade", "").lower() == "websocket":
            return self.websocket()
        if path == "/":
            return self.send(200, render(load(), server=True))
        if path.startswith("/files/"):
            f = (PM / path[len("/files/"):]).resolve()
            ctype = mimetypes.guess_type(f.name)[0]
            if f.is_file() and f.is_relative_to(PM) and ctype in IMAGE_TYPES:
                return self.send(200, f.read_bytes(), ctype)
        self.send(404, "not found", "text/plain")

    def do_POST(self):
        # localhost only, and refuse cross-site posts: JSON content type forces a CORS preflight we never answer
        handlers = {"/api/review": save_review, "/api/human-test": save_test_result}
        if self.path not in handlers or self.headers.get("Content-Type", "") != "application/json" or not self.same_origin():
            return self.send(403, json.dumps({"error": "forbidden"}), "application/json")
        size = int(self.headers.get("Content-Length") or 0)
        if size > 120_000_000:
            return self.send(413, json.dumps({"error": "too large"}), "application/json")
        try:
            rid = handlers[self.path](json.loads(self.rfile.read(size)), set(load()))
        except (ValueError, json.JSONDecodeError, base64.binascii.Error) as ex:
            return self.send(400, json.dumps({"error": str(ex)}), "application/json")
        self.send(200, json.dumps({"id": rid}), "application/json")

    def log_message(self, *args):
        pass


def serve():
    ports = [int(sys.argv[sys.argv.index("--port") + 1])] if "--port" in sys.argv else range(8737, 8757)
    for port in ports:
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    else:
        sys.exit("no free port, pass --port N")
    def push():
        watcher = Watcher()
        while True:
            watcher.wait()
            broadcast("changed")
    threading.Thread(target=push, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_port}/"
    print(f"Antfarm dashboard on {url} (Ctrl+C to stop)")
    if "--no-open" not in sys.argv:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    once, out = "--once" in sys.argv, PM / "dashboard.html"
    if "--tui" not in sys.argv and "--static" not in sys.argv:
        serve()
        sys.exit()
    if "--tui" not in sys.argv:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render(load()), encoding="utf-8")
        print(f"Wrote {out}" + ("" if once else " (live, Ctrl+C to stop)"))
        if "--no-open" not in sys.argv:
            webbrowser.open(out.as_uri())
    if os.name == "nt":
        os.system("")  # turns on ANSI colours in the Windows console
        sys.stdout.reconfigure(encoding="utf-8")  # bar characters crash cp1252 (Git Bash, pipes)
    watcher = None if once else Watcher()
    try:
        while True:
            if "--tui" in sys.argv:
                print("" if once else "\033[H\033[2J", end="")
                tui(load())
                sys.stdout.flush()
            else:
                out.write_text(render(load()), encoding="utf-8")
            if once:
                break
            watcher.wait()
    except KeyboardInterrupt:
        pass
