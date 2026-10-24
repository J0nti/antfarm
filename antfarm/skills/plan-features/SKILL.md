---
name: plan-features
description: Add new features/tasks to the plan based on the current code, vision and milestones.
disable-model-invocation: true
argument-hint: "<feature idea>"
---
# Plan features: $ARGUMENTS

1. Read `pm/vision.md`, all milestones, task statuses, and the relevant code.
2. Ask the user clarifying questions. Say if the feature conflicts with the vision or non-goals — if they still want it, record it under "Vision changes" in vision.md (dated) instead of rewriting history.
3. Propose: which milestone it belongs to (prefer the earliest not-done one that makes sense, or a new milestone), new tasks with criteria (mark the ones only a human can check with `(human)`: real logins, hardware, devices, payments, look and feel), tests, files, `blocked_by`, and any existing tasks it affects (obsolete ones get `status: cancelled` + a note why, never deleted).
4. On approval, `git pull`, then write task files. IDs are `T-<nnn>-<initials>` (initials from `git config user.name`, e.g. Jane Roe → `jr`); `<nnn>` = highest existing number + 1 after a `git pull`. This keeps IDs unique when several people plan in parallel. Update milestone files, then commit and push the new task files right away (ask the user first) so others see them. Append timeline (role `feature-planner`).
