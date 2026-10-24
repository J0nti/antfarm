#!/usr/bin/env bash
# One-time per machine: makes /init-antfarm available in every project.
set -e
mkdir -p ~/.claude/skills
rm -f ~/.claude/skills/init-project-workflow  # old name
SKILL="$(cd "$(dirname "$0")" && pwd)/skills/init-antfarm"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)  # Windows (Git Bash): ln -s copies, so use a junction (no admin needed)
    rm -f ~/.claude/skills/init-antfarm
    MSYS_NO_PATHCONV=1 cmd /c mklink /J "$(cygpath -w ~/.claude/skills/init-antfarm)" "$(cygpath -w "$SKILL")" >/dev/null ;;
  *) ln -sfn "$SKILL" ~/.claude/skills/init-antfarm ;;
esac
echo "Installed. In any project containing antfarm/, run /init-antfarm"
