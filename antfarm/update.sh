#!/usr/bin/env bash
# Pull the latest antfarm template from git, then sync it into a project (pm/ data untouched).
# Usage: bash antfarm/update.sh [project-dir]   # default: the project this antfarm/ folder is in
set -e
LINK=~/.claude/skills/init-antfarm
[ -e "$LINK" ] || { echo "antfarm not installed: run install.sh from your antfarm clone first."; exit 1; }
TEMPLATE="$(cd "$(readlink -f "$LINK")/../.." && pwd)"   # .../antfarm (template folder)

echo "Pulling template in $(dirname "$TEMPLATE")"
git -C "$TEMPLATE" pull --ff-only

PROJECT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
PROJECT="$(cd "$PROJECT" && pwd)"
if [ "$PROJECT" = "$(dirname "$TEMPLATE")" ]; then
  echo "Template updated (no project given)."
  exit 0
fi
bash "$TEMPLATE/add-to-project.sh" "$PROJECT"
echo "Then commit + push so teammates get it."
