---
name: plan-vision
description: Interview the user about a project idea, challenge it, write the vision, then have a fresh planner create milestones, features and tasks with criteria and tests.
disable-model-invocation: true
argument-hint: "[short idea]"
---
# Plan vision

## Phase 1 — Interview (you)
If `antfarm/pm/vision.md` exists, ask whether to revise it or start over.
If the project already has code, skim it first so questions are grounded, and ask what works today, what is broken, and what must not change.

Interview the user with AskUserQuestion / plain questions, a few at a time, until you can fill the vision template. Cover:
- Purpose: what problem, for whom, why does it matter, why now.
- Users and core use cases. What does success look like in concrete, testable terms?
- Non-goals: what is it explicitly NOT.
- Constraints: stack, platform, time, money, hosting.
- Challenge the idea: does it already exist? Why not use X? What is the riskiest assumption? What is the smallest version that proves it? Push back on vague answers and scope creep.

Write `antfarm/pm/vision.md` from `antfarm/templates/vision.md`. Keep the interview log verbatim-ish. For an existing project, add a `## Current state` section to vision.md: what is already built and working (with paths), known issues. Show the user a summary and get explicit approval before Phase 2.

## Phase 2 — Planning (fresh agent)
Spawn a fresh `Plan` (or general-purpose) agent. Give it only: the path to vision.md, the templates folder, the existing code (if any), and these instructions:
- Split the vision into milestones M1..Mn; each delivers something usable/testable. M1 is the smallest working slice.
- Each milestone: features, tasks, milestone acceptance criteria.
- Each task: small (one agent session), acceptance criteria, concrete test commands, expected files, `blocked_by`.
- Agents can't check everything: criteria that need a real account login, hardware, a phone, a payment, or a human judgement (looks right, feels fast) are marked `(human)` at the start of the criterion text.
- Task IDs: T-001-<initials>, T-002-<initials>... IDs are `T-<nnn>-<initials>` (initials from `git config user.name`, e.g. Jane Roe → `jr`); `<nnn>` = highest existing number + 1 after a `git pull`. This keeps IDs unique when several people plan in parallel.
- Existing project: plan only the remaining work. Never create tasks for features listed under "Current state" unless they need changes; reference existing files in tasks.
- Return the full content of each file it wants written.

Then you write the files: `pm/milestones/M<n>-<slug>.md`, `pm/tasks/T-<nnn>-<initials>-<slug>/task.md`. Present the milestone overview to the user and adjust on feedback.

Append to timeline, then tell the user: "Next: /manage-milestone M1".
