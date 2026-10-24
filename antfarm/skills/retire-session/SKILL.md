---
name: retire-session
description: Wrap up the current session - record state and next steps in the timeline so a fresh session can resume.
disable-model-invocation: true
---
# Retire session

1. Make sure every task touched this session has an accurate `status` and notes in task.md. Uncommitted work: list it, ask the user whether to commit (never commit without asking).
2. Append to timeline (role `session`):
   ```
   - YYYY-MM-DD HH:MM | session | - | - | HANDOFF: done=<...>; in-progress=<...>; blockers=<...>; next=<exact command, e.g. /manage-milestone M2>
   ```
3. Tell the user the summary and that it is safe to `/clear` or close. The next session should start by reading the last HANDOFF line in the timeline.
