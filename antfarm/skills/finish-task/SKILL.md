---
name: finish-task
description: Close a reviewed task - verify criteria and tests, then commit and push with user approval.
argument-hint: "T-<nnn>"
---
# Finish task $ARGUMENTS

0. If `antfarm/pm/conventions.md` exists, its commands, commit format and branch naming override the defaults below.
1. Confirm the latest round in review.md is PASS. If not, stop.
2. Run all tests in the task, plus the lint/format commands from `conventions.md` if any; tick each acceptance criterion in task.md. Any failure => stop, report. Never tick a `(human)` criterion yourself: it is ticked by /fetch-feedback when the human test passes. A task can be done with human tests still pending; the milestone can't.
3. Show the user the diff summary and proposed commit message: `<task-id>: <summary>`, or the format in `conventions.md` (it must contain the task id so the overview can link the commit). End it with who did the work, after any other trailers such as `Co-Authored-By` (the exact model id, not a nickname; one `Model:` line per model if the implementer and bug-fixer differed; `antfarm/git-hooks/commit-msg` refuses a commit without them):
   ```
   Agent: Claude Code
   Model: claude-opus-5-5
   ```
   **Ask before `git commit`.**
4. **Ask separately before `git push`.** If in a worktree, ask whether to merge into the main branch, then remove the worktree.
5. Set `status: done`, append timeline (role `finisher`): commit hash.
5b. **Tell the sessions that depend on it** (only if the session tools exist): `ListAgents`, then `SendMessage` any session whose task has this one in `blocked_by` or shares files with it: the task is done, what changed, which branch to merge or rebase on.
6. If the task has `review: <id>` and every task in that item's `tasks:` list is now done:
   - review `R-…` → set its `status: addressed` and append `## Resolution (<date>)`: the tasks and their commits.
   - human test `HT-…` → write a **retest**: a new HT (next number) with `retest_of: <HT-id>`, the same task/criterion, the original steps, and a note on what was fixed. The user retests it in the dashboard.
