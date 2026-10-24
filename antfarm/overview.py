#!/usr/bin/env python3
"""Generate antfarm/pm/overview.html: timeline, manager runs and the agents they spawned,
review findings/bugs per task, and the code each task changed (git commits whose message contains the task id).

Usage: python3 antfarm/overview.py [--no-open]
"""
import html
import re
import subprocess
import sys
import webbrowser

from dashboard import COLORS, PM, load, pct, milestone_tests

ROOT = PM.parent.parent
e = html.escape


def timeline():
    """Lines: `- date time | role | task | run | what` (old 4-field lines have run '-')."""
    f = PM / "timeline.md"
    rows = []
    for line in (f.read_text(encoding="utf-8").splitlines() if f.exists() else []):
        parts = [p.strip() for p in line.lstrip("- ").split("|")]
        if len(parts) == 4:
            parts.insert(3, "-")
        if len(parts) >= 5:
            rows.append(dict(zip(["when", "role", "task", "run", "what"], parts[:4] + ["|".join(parts[4:])])))
    return rows


def git(*args):
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return ""


def diff_html(patch):
    lines = patch.splitlines()
    # ponytail: truncate huge diffs, open the commit in git for the full thing
    more = f"\n… {len(lines) - 1500} more lines (git show)" if len(lines) > 1500 else ""
    out = []
    for l in lines[:1500]:
        cls = "add" if l.startswith("+") and not l.startswith("+++") else \
              "del" if l.startswith("-") and not l.startswith("---") else \
              "hunk" if l.startswith("@@") or l.startswith("diff ") else ""
        out.append(f'<span class="{cls}">{e(l)}</span>' if cls else e(l))
    return "<pre class='diff'>" + "\n".join(out) + e(more) + "</pre>"


def commits(task_id):
    out = []
    fmt = "--format=%h%x09%ad%x09%an%x09%(trailers:key=Model,valueonly,separator=%x2C)%x09%s"
    for line in git("log", "--all", "--fixed-strings", f"--grep={task_id}", fmt, "--date=short").splitlines():
        h, date, author, model, subject = line.split("\t", 4)
        stat = git("show", "--stat", "--format=", h).strip()
        model = f" <span class='chip'>{e(model)}</span>" if model else ""
        out.append(f"<details><summary><code>{h}</code> {e(date)} {e(author)}{model} — {e(subject)}</summary>"
                   f"<pre>{e(stat)}</pre>{diff_html(git('show', '--format=', h))}</details>")
    return "".join(out) or "<p class='dim'>No commits mention this task yet.</p>"


def tl_table(rows):
    if not rows:
        return "<p class='dim'>No entries.</p>"
    body = "".join(f"<tr class='r-{e(r['role'])}'><td>{e(r['when'])}</td><td>{e(r['role'])}</td><td>{e(r['task'])}</td>"
                   f"<td>{e(r['run'])}</td><td>{e(r['what'])}</td></tr>" for r in rows)
    return f"<table><tr><th>When</th><th>Agent</th><th>Task</th><th>Run</th><th>What</th></tr>{body}</table>"


def render():
    milestones, tl = load(), timeline()
    tasks = [t for m in milestones.values() for t in m["tasks"]]

    runs = {}
    for r in tl:
        if r["run"] != "-":
            runs.setdefault(r["run"], []).append(r)
    run_html = []
    for run, rows in runs.items():
        agents = {}
        for r in rows:
            if r["role"] != "manager":
                agents[r["role"]] = agents.get(r["role"], 0) + 1
        chips = " ".join(f"<span class='chip'>{e(k)} × {v}</span>" for k, v in agents.items())
        task_ids = sorted({r["task"] for r in rows if r["task"] != "-"})
        run_html.append(f"<details><summary><b>{e(run)}</b> · {e(rows[0]['when'])} → {e(rows[-1]['when'])} · "
                        f"tasks: {e(', '.join(task_ids)) or '-'} · {chips}</summary>{tl_table(rows)}</details>")

    tests = [h for mid in milestones for h in milestone_tests(mid)]
    task_html = []
    for t in tasks:
        tid = t["id"]
        review_files = list((PM / "tasks").glob(f"{tid}*/review.md"))
        review = review_files[0].read_text(encoding="utf-8") if review_files else ""
        bugs = [l for l in review.splitlines() if "[bug]" in l]
        rounds = len(re.findall(r"^## Round", review, re.M))
        task_html.append(
            f"<details><summary><b>{e(tid)}</b> {e(t.get('title', ''))} "
            f"<span class='pill' style='background:{COLORS[t['status']]}'>{t['status']}</span> "
            f"<span class='dim'>{e(t.get('assignee', ''))} · review rounds: {rounds} · bugs: {len(bugs)}</span></summary>"
            f"<h4>Actions</h4>{tl_table([r for r in tl if r['task'] == tid])}"
            f"<h4>Review findings</h4>" + (f"<pre>{e(review)}</pre>" if review else "<p class='dim'>No review yet.</p>") +
            "".join(f"<h4>Human test {e(h['id'])}: {e(h['status'])}</h4><pre>{e(h['md'])}</pre>" for h in tests if h["task"] == tid) +
            f"<h4>Code changes</h4>{commits(tid)}</details>")

    all_bugs = sum(1 for f in (PM / "tasks").glob("*/review.md") for l in f.read_text(encoding="utf-8").splitlines() if "[bug]" in l)
    return f"""<!doctype html><meta charset="utf-8"><title>Project overview</title>
<style>
body{{font:15px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 16px;background:#fff;color:#202124}}
@media(prefers-color-scheme:dark){{body{{background:#1f1f1f;color:#e8eaed}} pre{{background:#2a2a2a!important}} th,td{{border-color:#444!important}}}}
details{{border:1px solid #8884;border-radius:6px;padding:6px 10px;margin:6px 0}} summary{{cursor:pointer}}
table{{width:100%;border-collapse:collapse;font-size:14px}} th,td{{text-align:left;padding:3px 6px;border-bottom:1px solid #ddd;vertical-align:top}}
pre{{background:#f6f8fa;padding:10px;overflow:auto;font-size:13px}}
.diff .add{{color:#188038}} .diff .del{{color:#d93025}} .diff .hunk{{color:#1a73e8}}
.pill{{color:#fff;padding:1px 8px;border-radius:10px;font-size:12px}} .chip{{background:#8882;padding:1px 8px;border-radius:10px;font-size:12px}}
.dim{{opacity:.65}} .r-manager td{{font-weight:600}} .r-reviewer td:last-child{{color:#f29900}} .r-bug-fixer td:last-child{{color:#d93025}}
</style>
<h1>Project overview</h1>
<p><b>{pct(tasks)}%</b> done · {len(tasks)} tasks · {len(runs)} manager runs · {len(tl)} timeline entries · {all_bugs} bugs found in review</p>
<h2>Manager runs</h2>{''.join(run_html) or "<p class='dim'>No manager runs yet.</p>"}
<h2>Tasks</h2>{''.join(task_html) or "<p class='dim'>No tasks yet.</p>"}
<h2>Full timeline</h2>{tl_table(tl)}
<p class="dim">Snapshot — rerun python3 antfarm/overview.py to refresh.</p>"""


if __name__ == "__main__":
    out = PM / "overview.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(), encoding="utf-8")
    print(f"Wrote {out}")
    if "--no-open" not in sys.argv:
        webbrowser.open(out.as_uri())
