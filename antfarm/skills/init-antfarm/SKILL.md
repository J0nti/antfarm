---
name: init-antfarm
description: Initialize or upgrade antfarm (the agent workflow) in the current project - installs the workflow skills into .claude/skills, creates antfarm/pm, and adds workflow rules to CLAUDE.md.
disable-model-invocation: true
---
# Init antfarm

Safe to re-run: if `antfarm/pm/` already exists this is an **upgrade** — never touch vision, milestones, task content, reviews or timeline history except the migration in step 4c.

0. **Old name migration:** if the project has an `ai-workflow/` folder (antfarm's old name): ask the user, then `git mv ai-workflow antfarm` (keep `pm/` data; if both folders exist, move `ai-workflow/pm` into `antfarm/pm` and remove the rest of `ai-workflow/`). In `CLAUDE.md` the old `## AI workflow` section is replaced in step 4. Then continue as an upgrade.
1. Confirm `antfarm/skills/` exists in the project root. If not, stop and tell the user to copy the `antfarm` folder into the project root first.
2. Install skills (skip init-antfarm itself, it lives globally):
   ```bash
   mkdir -p .claude/skills
   for d in antfarm/skills/*/; do n=$(basename "$d"); [ "$n" = init-antfarm ] || cp -r "$d" .claude/skills/; done
   ```
   PowerShell:
   ```powershell
   New-Item -ItemType Directory -Force .claude\skills | Out-Null
   Get-ChildItem antfarm\skills -Directory | Where-Object Name -ne init-antfarm | Copy-Item -Recurse -Force -Destination .claude\skills
   ```
   If a skill already exists in `.claude/skills/` and differs, show the user which ones changed and ask once before overwriting them all.
3. Create `antfarm/pm/milestones/`, `antfarm/pm/tasks/` and `antfarm/pm/timeline.md` with header `# Timeline` (do not overwrite an existing timeline).
4. Put this block in `CLAUDE.md` (create it if missing). If an `## Antfarm` section (or the old `## AI workflow` section) already exists, replace it (up to the next `## ` heading) with this version:
   ```markdown
   ## Antfarm
   - First session in this clone: if `antfarm/.dashboard-intro` does not exist, start your first reply by telling the user about the dashboard in 2-3 lines (a live web view of tasks, docs, milestone demos to review and human tests; start it any time with `python antfarm/dashboard.py`, or double-click `antfarm\dashboard.cmd` on Windows) and ask whether to start it now. If yes, run `python antfarm/dashboard.py` (`python3` on macOS/Linux) in the background; it opens the browser itself; give the user the URL it prints. Either way, then create the empty file `antfarm/.dashboard-intro` so this happens only once.
   - Vision: `antfarm/pm/vision.md` — read it before planning or implementing. Existing projects also have `antfarm/pm/architecture.md` and `antfarm/pm/conventions.md`; the conventions (commands, commit format, branch naming, "must not change") override antfarm's defaults.
   - Tasks: `antfarm/pm/tasks/T-*/task.md`, milestones: `antfarm/pm/milestones/`.
   - Every agent appends to `antfarm/pm/timeline.md`: `- YYYY-MM-DD HH:MM | <agent-role> | <task-id or -> | <run-id or -> | <what was done>` (run-id = the manager run that spawned the agent; agents use the run-id given in their prompt). Bug-fixer role is `bug-fixer`.
   - Commit messages for task work start with the task id: `<task-id>: <summary>` (the overview links code changes to tasks this way).
   - Every commit ends with who made it: `Agent: <tool>` and `Model: <exact model id>` (after any `Co-Authored-By`); a commit written by hand has just `Agent: human`. `antfarm/git-hooks/commit-msg` enforces it. Merge and fixup commits are exempt.
   - Ask the user before starting a task (`/manage-milestone` asks once for the whole milestone), before `git commit`, before `git push`.
   - Other Claude sessions on this machine may work on other tasks: ask them directly (`ListAgents` + `SendMessage`) about their files, decisions or status, instead of asking the user. Never message a session whose task is done.
   - A task is done only when its acceptance criteria and tests pass.
   - User feedback: reviews (`antfarm/pm/milestones/<M>/reviews/R-*.md`, `status: open`) and human test results (`antfarm/pm/milestones/<M>/human-tests/HT-*.md`, `handled: false`) come from the dashboard, with screenshots. Handle them with /fetch-feedback and look at the images.
   - Never claim something works that you could not check: mark the criterion `(human)` and write a human test (`antfarm/templates/human-test.md`). A milestone is done only when its human tests pass.
   - Team: `git pull` before planning or claiming; never work on a task assigned to someone else; on `timeline.md` merge conflicts keep both sides' lines.
   ```
4c. Upgrade only — migrate task.md frontmatter to the current schema (`templates/task.md`), show the user the planned changes first:
   - old statuses: `approved` → `in-progress`, `review` / `fixing` → `in-review`; anything else unknown → ask
   - add missing `assignee:` and `blocked_reason:` keys (empty)
   - keep existing task IDs as they are (old `T-001` IDs stay valid; new tasks get `T-<nnn>-<initials>` continuing the highest number)
5. If the project is not a git repo, ask whether to `git init` (worktrees need git).
5b. **Commit hook** (enforces the `Agent:`/`Model:` lines): if `git config core.hooksPath` is empty and `.git/hooks/` has no hooks of its own (only `*.sample`), ask, then run `git config core.hooksPath antfarm/git-hooks`. On macOS/Linux also `chmod +x antfarm/git-hooks/commit-msg`, and `git add --chmod=+x antfarm/git-hooks/commit-msg` so teammates get it executable (Windows ignores the bit). If the project already has hooks or a `core.hooksPath` (husky, pre-commit, …), don't change it: tell the user to call `antfarm/git-hooks/commit-msg "$1"` from their own commit-msg hook. Each teammate runs the `git config` line once per clone.
6. If the project already has code, note that in the timeline; the next step is then `/adopt-antfarm` (survey, architecture, conventions, baseline M0, backlog) instead of `/plan-vision`.
7. Append timeline entry (`init` or `upgrade` + what changed), then tell the user: "Ready. Next: /plan-vision" (or "/adopt-antfarm" when the project already has code) (or for an upgrade: what changed, and to commit + push so teammates get it) and tell them to restart the session or run `/skills` if the new skills don't show yet.
