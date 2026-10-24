---
name: adopt-antfarm
description: Bring an existing (large) codebase into antfarm - survey the code, record architecture and conventions, add a done baseline milestone M0, import the backlog, then interview for what comes next. Use instead of /plan-vision on a project that already has code.
disable-model-invocation: true
argument-hint: "[path to scope to, e.g. services/api]"
---
# Adopt antfarm: $ARGUMENTS

Run once, after `/init-antfarm`, on a project that already has code. Scope = `$ARGUMENTS` if given (a monorepo package or service), otherwise the whole repo. Read-only on the code: you only write under `antfarm/pm/`. If `antfarm/pm/vision.md` already exists, ask whether to redo the adoption or stop.

## 1. Survey (parallel, read-only)
List the top-level areas of the scope (packages, services, apps, libs; skip vendored, generated and build output). Split them into at most 4 groups and spawn one read-only `Explore` agent per group, in parallel. Ask each to return, for its area:
- what it does, its main entry points and key files (paths)
- user-visible features that already work, each with the files that implement it
- how it talks to the other areas (calls, APIs, queues, shared DB)
- tests: where they are, how to run just this area's tests, roughly how long they take
- obvious problems: dead code, TODO/FIXME clusters, missing tests, risky spots

Meanwhile, read the project-wide conventions yourself: README/CONTRIBUTING, CI config (`.gitlab-ci.yml`, `.github/workflows`), linters/formatters, `package.json`/`pyproject.toml`/`Makefile`/etc. scripts, `git log --oneline -30` (commit message style), `git branch -r` (branch naming), existing `CLAUDE.md`.

## 2. Write the picture of today
- `antfarm/pm/architecture.md`: one paragraph overview, a Mermaid diagram of the components and how they connect, then one short section per area (purpose, entry points, key files, tests).
- `antfarm/pm/conventions.md` from `antfarm/templates/conventions.md`: build, test (fast per-area commands and the full suite), lint/format commands, commit message format, branch naming, CI, review/merge rules, anything that must not change. Where antfarm's defaults clash, write how they combine, e.g. commit format `<task-id>: <their format>` or `feat(api): … [T-012-jr]`; branch `<their prefix>/<task-id>-<slug>`.
- Show both files to the user and fix what they correct before going on. These are the facts every later agent relies on.

## 3. Baseline milestone M0 (already done)
- `antfarm/pm/milestones/M0-existing-system.md` (`status: done`, `baseline: true`): what exists today, grouped as features.
- One task per existing feature, `status: done`, `baseline: true` in frontmatter, `assignee:` empty, acceptance criteria describing what works today (all ticked), `Files` pointing at the implementation, `Tests` with the existing test command if there is one. IDs `T-<nnn>-<initials>` from 001. Keep features coarse (10–30 for a big system, not one per function).
- Known problems found in the survey are **not** baseline tasks; they go to the backlog in step 4.

## 4. Backlog (proposed, nothing created without approval)
Collect candidates from:
- TODO/FIXME/HACK comments (grouped per area, not one task per comment)
- roadmap / planning docs in the repo
- survey findings (missing tests, risky spots)
- open issues: only if `glab` (GitLab) or `gh` (GitHub) is installed and logged in; ask the user before reading them (`glab issue list --state opened`).

Write them to `antfarm/pm/backlog.md` as a table (source, summary, area, rough size), then go through it with the user: each item becomes a task in a later milestone, is merged with another, or is dropped.

## 5. Vision interview
Follow `.claude/skills/plan-vision/SKILL.md`, with these changes:
- the interview is about **where the project goes next**, grounded in `architecture.md`, M0 and the accepted backlog; don't re-ask what the survey already answered
- `vision.md`'s `## Current state` summarizes M0 and links `architecture.md` and `conventions.md`
- the planner starts at M1, never re-plans M0 features, and folds the accepted backlog items into milestones
- tasks name the per-area test command from `conventions.md`, not the full suite

## 6. Finish
- Append timeline lines (role `adopter`): survey done, M0 with N features, backlog N accepted / M dropped, vision approved.
- Ask before committing; commit `antfarm/pm/` as one commit in the project's commit format.
- Tell the user: what M0 contains, where the architecture diagram is (dashboard → Docs), and the next step: `/manage-milestone M1`.
