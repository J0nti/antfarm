---
name: review-task
description: Fresh-eyes review of an implemented task against its criteria and the vision; records findings in the task's review.md.
argument-hint: "T-<nnn>"
---
# Review task $ARGUMENTS

You are a reviewer with no prior context. Do not fix code.

1. Read the task.md, `pm/vision.md`, and the diff (`git diff` on the task branch/worktree vs its base).
2. Run the task's tests yourself (and the lint commands from `antfarm/pm/conventions.md` if it exists). Check the change follows the conventions and doesn't touch anything listed under "Must not change".
3. Check: each acceptance criterion is truly met (a `(human)` criterion must not be claimed as met; it needs a human test file in `antfarm/pm/milestones/<M>/human-tests/` with clear steps, flag a `[bug]` if missing), bugs/edge cases, security issues, tests actually test the behavior, scope creep, fit with the vision.
4. Append a round to `antfarm/pm/tasks/<task>/review.md`:
   ```
   ## Round <n> — YYYY-MM-DD
   Verdict: PASS | BUGS
   - [bug] file:line — problem — expected
   ```
   Only list real defects as `[bug]`; nits as `[nit]` (nits do not block).
5. Append timeline (role `reviewer`). Report verdict + bug list.
