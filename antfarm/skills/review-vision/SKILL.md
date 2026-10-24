---
name: review-vision
description: Compare the project against its vision - "drift" after a milestone, "final" as the end review.
disable-model-invocation: true
argument-hint: "drift | final"
---
# Review vision ($ARGUMENTS)

Spawn a fresh general-purpose agent to do the review so it is unbiased; give it this file's instructions. Then present its report to the user.

## drift (after a milestone)
- Read vision.md (incl. interview log and Vision changes), done milestones, timeline, and the code.
- Report: what moves toward the success criteria, what drifts (features not in vision, non-goals creeping in, shortcuts that will block later milestones), and whether the remaining milestones still make sense.
- Recommend: continue / adjust next milestone / `/plan-features`.

## final (end review)
- Run every test and check every success criterion in vision.md: pass / fail / partial, with evidence.
- Compare what was built with the original interview log: what changed from the initial vision, and why (from timeline + Vision changes).
- List open issues and suggested next steps.

Write the report to `antfarm/pm/reviews/<YYYY-MM-DD>-<mode>.md`. Append timeline (role `vision-reviewer`).
