---
name: fetch-feedback
description: Pick up the user's feedback from the dashboard - milestone reviews and human test results - and turn it into tasks or ticked criteria.
argument-hint: "[M<n>]"
---
# Fetch feedback $ARGUMENTS

The user writes feedback in the dashboard (`python3 antfarm/dashboard.py`):
- **Reviews** (Review tab): `antfarm/pm/milestones/<M>/reviews/R-<nnn>-<initials>.md`, `status: open`.
- **Human test results** (Human tests tab): `antfarm/pm/milestones/<M>/human-tests/HT-<nnn>-<initials>.md` with `handled: false` and a new `## Result <n>` section.

Screenshots sit next to those files. **Look at every image** they reference (Read the image file).

1. `git pull`, then collect open reviews and unhandled human-test results (only milestone $ARGUMENTS if given). Nothing: say so and stop.
2. Oldest first, summarize to the user in your own words what each one says, so misunderstandings surface now.
3. **Reviews**, by verdict:
   - **request-changes** → propose fix tasks (what, files, acceptance criteria that would satisfy the review, tests). IDs `T-<nnn>-<initials>` (highest + 1), frontmatter `review: <R-id>`, screenshot paths in Notes. After the user approves: write them, add them to the milestone's task table, set the milestone `status: in-progress`, set the review `status: in-progress` and `tasks: [T-…]`.
   - **comment** → answer under `## Response (<date>)` in the review file. If it implies work, propose tasks as above; otherwise `status: closed`.
   - **approve** → `approved: <date> by <author>` in the milestone file, review `status: closed`.
4. **Human test results**, by the latest result:
   - **pass** → tick the matching `(human)` acceptance criterion in the linked task.md (`criterion:` says which), set `handled: true`.
   - **broken** / **needs-change** → propose a fix task like a change request, with `review: <HT-id>` and the result text + screenshots in Notes. After approval: write it, set the milestone `status: in-progress`, and set `handled: true` plus `tasks: [T-…]` in the HT file.
5. Append a timeline line per item (role `feedback-intake`), e.g. `HT-001-jr broken → T-019-jr`.
6. Ask before committing; commit the status changes and new tasks together.
7. Tell the user what's next, usually `/manage-milestone <M>`.

When the last fix task linked to a review or human test is done, `finish-task` closes the loop (review `addressed`, or a new retest HT).
