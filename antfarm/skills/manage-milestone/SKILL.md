---
name: manage-milestone
description: Manager agent for one milestone - orders tasks by dependency, runs up to 2 implementer subagents, drives review and bug-fix loops, and reports to the user.
disable-model-invocation: true
argument-hint: "M<n>"
---
# Manage milestone $ARGUMENTS

You are the manager. You do not write feature code yourself; you plan, delegate, verify and report.

**Run id:** at start, set `RUN = <milestone>-<YYYYMMDD-HHMM>-<initials>` (e.g. `M1-20261009-1030-jr`). Use it in the run column of every timeline line you write, log `started run` / `ended run`, log `spawned <role> for <task>` each time you spawn an agent, and put `Run id: <RUN>` in every subagent prompt.

## 1. Plan the order
- `git pull` first.
- User feedback first: if `antfarm/pm/milestones/$ARGUMENTS/reviews/` has reviews with `status: open`, or `human-tests/` has results with `handled: false`, follow `.claude/skills/fetch-feedback/SKILL.md` for this milestone before planning (it may add fix tasks).
- Read `pm/vision.md`, the milestone file, and every task.md in it.
- Build the dependency order from `blocked_by`. Skip tasks assigned to someone else. If the session tools exist (`ListAgents`; skip silently in the CLI), check for other sessions already working on a task of this milestone: treat those tasks as running and their files as busy, and wait for them instead of starting anything that depends on them.
- **Ask once for the whole milestone** (AskUserQuestion), and set each task you list to `status: awaiting-approval` while you wait. Show: the tasks in order, for each what will be implemented and the files it touches ("Files expected to touch"), which run in parallel, which wait on others, and anything that will need a separate answer later (new dependencies, deletions, scope changes). Make it explicit that approving also lets you **claim** each task when it starts (commit + push its task.md). That one yes covers starting every task in the list. Ask again only for a task the user excluded, or one added to the milestone later (fix tasks from feedback, `/plan-features`). Commit and push still need their own yes (finish-task). Tasks the user excluded go back to `todo`.

**New feedback while you run:** if a background file monitor is available (e.g. the Monitor tool), watch `antfarm/pm/milestones/$ARGUMENTS/reviews/` and `human-tests/` for new or changed files. When one appears, tell the user and handle it with the fetch-feedback flow once the current task step is done. Without a monitor, check those folders between tasks.

## 2. For each ready task (max 2 in progress at once)
A task is **ready** when every `blocked_by` task is done and none of its "Files expected to touch" is listed by a running task (yours or another session's). Overlapping files always run one after the other, never in parallel. For each ready, approved task, without asking again:
1. `git pull`. If the task now has another `assignee` or is no longer `awaiting-approval`/`todo`, someone else claimed it: skip it and tell the user.
2. Set `status: in-progress`, `assignee: <git config user.name>`, commit `claim <task-id>` (only task.md + timeline), push. If the push is rejected, pull and re-check step 1.
3. Then spawn an implementer subagent, always with `isolation: "worktree"` (its own worktree, even when it runs alone), with the prompt: "Run the start-task workflow in .claude/skills/start-task/SKILL.md for <task-id>. Run id: <RUN>. Approval is already given. Do not commit."

Other sessions can't see your subagents. If a session messages you about one of your tasks, answer for it or pass it on to the agent, and note it in that task.md.

## 3. Review loop (per task, after implementer reports)
1. Spawn a FRESH reviewer subagent: "Follow .claude/skills/review-task/SKILL.md for <task-id>. Run id: <RUN>". Never reuse the implementer.
2. If it reports bugs: spawn a FRESH bug-fixer subagent (role `bug-fixer`, same run id) with the review.md findings; it logs each fix to the timeline, then a FRESH reviewer again. Repeat until clean. After 3 rounds, set `status: blocked` (`blocked_reason: review loop`), stop and ask the user.
3. When clean: follow `.claude/skills/finish-task/SKILL.md` yourself (tests, user approval for commit and push, merge worktree). Then start every task that just became ready.

## 4. Report
After each task: tell the user what was done, review rounds, test results, any human tests waiting for them (dashboard → Human tests), and what is next. Append to timeline at every step (role `manager`).

## 5. Milestone end
When all tasks are done or cancelled, check the milestone acceptance criteria, then write the demo:

Spawn a FRESH demo agent (role `demo`, same run id) to write `antfarm/pm/milestones/$ARGUMENTS/demo.md` for the user's review:
- **What was built:** per feature, a few sentences, with the task ids.
- **How to use it:** step by step, with the real commands / clicks, and what you see.
- **How it works:** a Mermaid flowchart or sequence diagram of the flow.
- **Screenshots:** real screenshots of the feature in use, taken with whatever tool is available (headless Chromium/Firefox, Playwright, `grim`/`scrot`/`gnome-screenshot`/`import` for desktop apps, `freeze`/`vhs`/`termshot` or terminal output rendered to HTML and screenshotted for CLIs/TUIs, …). Run the app for real. Never install a tool without asking the user. Save images as `antfarm/pm/milestones/$ARGUMENTS/demo-<n>.png` and reference them relatively (`![…](demo-1.png)`). If screenshots are impossible, say why and include captured terminal output in code blocks instead.
- **Human tests:** for anything the demo agent could not run or see for real, write a human test (see `antfarm/templates/human-test.md`) instead of guessing.

The milestone can only be `done` when none of its human tests is `pending`, `broken` or `needs-change` with fixes outstanding. If some are waiting, set the milestone `status: in-review`, tell the user how many and to open the dashboard's Human tests tab, and stop; the next `/manage-milestone` run picks up their results. Otherwise set milestone `status: done` and tell the user:
"Milestone done. Review it in the dashboard (`python3 antfarm/dashboard.py` → Review tab): approve, comment or request changes, screenshots welcome. Also run `/review-vision drift` to check we are still on the vision before the next milestone."
