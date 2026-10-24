# Conventions

Project rules every antfarm agent follows. Where they differ from antfarm's defaults, these win.

## Scope
<whole repo, or the path antfarm covers in a monorepo>

## Commands
| What | Command | Notes |
|---|---|---|
| Install / setup | | |
| Build | | |
| Fast tests (per area) | | e.g. `pytest tests/api -q` |
| Full test suite | | how long it takes |
| Lint / format | | |

## Git
- Commit message format: <e.g. `feat(api): ... [T-012-jr]`; antfarm's task id goes where shown>
- Branch naming: <e.g. `feature/<task-id>-<slug>`>
- Merging: <MR/PR required? squash? who reviews?>

## CI
<what runs on push / MR, and what must pass>

## Must not change
<public APIs, data formats, files or areas agents must not touch without asking>
