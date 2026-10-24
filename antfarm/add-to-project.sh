#!/usr/bin/env bash
# Copy (or update) antfarm into a project. Project data in antfarm/pm/ is never touched.
# Usage: bash antfarm/add-to-project.sh <project-dir>
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:?usage: add-to-project.sh <project-dir>}"
[ -d "$DEST" ] || { echo "No such directory: $DEST"; exit 1; }
DEST="$(cd "$DEST" && pwd)"
[ "$DEST" = "$(dirname "$SRC")" ] && { echo "That is the template repo itself."; exit 1; }

[ -d "$DEST/antfarm" ] && MODE=updated || MODE=added
mkdir -p "$DEST/antfarm"  # tar, not rsync: tar also ships with macOS and Git Bash on Windows
tar -C "$SRC" --exclude ./pm --exclude ./.view.html --exclude __pycache__ -cf - . | tar -C "$DEST/antfarm" -xf -

# /init-antfarm must be available globally
[ -e ~/.claude/skills/init-antfarm ] || bash "$SRC/install.sh"

echo "antfarm ${MODE} in $DEST/antfarm"
[ -d "$DEST/ai-workflow" ] && echo "Found old ai-workflow/ folder: /init-antfarm will migrate it."
[ -d "$DEST/.git" ] || echo "Not a git repo yet: /init-antfarm will offer git init."
echo "Next: cd $DEST && claude, then run /init-antfarm"
