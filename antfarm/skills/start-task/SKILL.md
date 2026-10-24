---
name: start-task
description: Implement one task from antfarm/pm/tasks until its acceptance criteria and tests pass.
argument-hint: "T-<nnn>"
---
# Start task $ARGUMENTS

0. If `antfarm/pm/conventions.md` exists, its commands, commit format and branch naming override the defaults below.
1. Read `antfarm/pm/vision.md`, `antfarm/pm/conventions.md` and `antfarm/pm/architecture.md` if they exist, the task.md and its milestone. Check that every `blocked_by` task is `done`; if not, stop and report.
2. If run directly by the user (not by the manager), ask the user first: what you will implement, files you will touch, whether it blocks other tasks. Wait for approval, then claim it as described in step 2 of `.claude/skills/manage-milestone/SKILL.md` (pull, check assignee, set assignee, commit + push the claim).
3. Set `status: in-progress` and `branch:`. Use a branch `task/<id>` (or the conventions' branch naming, or the worktree you were given). Append timeline entry (role `implementer`).
3b. **Neighbours** (only if the session tools exist; skip silently in the CLI): run directly by the user, rename this session to `<task-id> <short title>` (`mcp__ccd_session_mgmt__set_session_title`, `session_id: "self"`) so other sessions can find it. Then `ListAgents`: if another session works on a task whose files overlap yours, `SendMessage` it once with the files you will change, and ask what it is in the middle of. Questions about another task's files, decisions or status go to that session, not the user; note the answer in task.md. Never message a session whose task is already `done`.
4. Implement. Stay inside the task scope; if you need to touch files not listed or change scope, stop and report back instead of guessing.
5. Write/update the tests listed in the task. Run them. Iterate until they pass.
5b. **What you can't check yourself** (a `(human)` criterion, or anything else that needs a real login, hardware, a device, a payment or human judgement): never claim it works. Mark the criterion `(human)` if it isn't yet, and write a human test from `antfarm/templates/human-test.md` to `antfarm/pm/milestones/<M>/human-tests/HT-<nnn>-<initials>.md` (highest HT number + 1): why a human is needed, exact steps, expected result, `task:` and `criterion:` filled in. Test as much as you can automatically first, so the human only does the part only a human can.
6. Set `status: in-review`, add notes to task.md (what changed, files touched, how to verify). Append timeline.
7. Do NOT commit or push. Report back: summary, files changed, test output, any human tests you wrote, and the agent and exact model id that did the work (e.g. `Claude Code / claude-opus-5-5`), for the commit's `Agent:`/`Model:` lines.
