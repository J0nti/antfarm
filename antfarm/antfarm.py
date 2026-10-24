#!/usr/bin/env python3
"""Same as install.sh / add-to-project.sh / update.sh, but without bash: works from cmd, PowerShell, macOS and Linux.

Usage: python antfarm/antfarm.py install              # one-time per machine: makes /init-antfarm available everywhere
       python antfarm/antfarm.py add <project-dir>    # copy (or update) antfarm into a project; antfarm/pm/ is never touched
       python antfarm/antfarm.py update [project-dir] # git pull the template, then sync it into the project
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
SKILLS = Path.home() / ".claude" / "skills"
LINK = SKILLS / "init-antfarm"


def install():
    SKILLS.mkdir(parents=True, exist_ok=True)
    for old in (SKILLS / "init-project-workflow", LINK):  # old name, and a previous link
        if not os.path.lexists(old):
            continue
        if os.path.realpath(old) == os.path.abspath(old):
            sys.exit(f"{old} is a real folder, not a link: remove it yourself, then rerun.")
        os.unlink(old)  # removes the symlink/junction only, never its target
    if os.name == "nt":  # junction: unlike a symlink it needs no admin rights or Developer Mode
        subprocess.run(["cmd", "/c", "mklink", "/J", str(LINK), str(SRC / "skills" / "init-antfarm")], check=True, stdout=subprocess.DEVNULL)
    else:
        os.symlink(SRC / "skills" / "init-antfarm", LINK)
    print("Installed. In any project containing antfarm/, run /init-antfarm")


def add(dest):
    dest = Path(dest).resolve()
    if not dest.is_dir():
        sys.exit(f"No such directory: {dest}")
    if dest == SRC.parent:
        sys.exit("That is the template repo itself.")
    mode = "updated" if (dest / "antfarm").exists() else "added"
    skip = lambda d, names: [n for n in names if n == "__pycache__" or (Path(d) == SRC and n in {"pm", ".view.html"})]
    shutil.copytree(SRC, dest / "antfarm", ignore=skip, dirs_exist_ok=True)
    if not LINK.exists():
        install()
    print(f"antfarm {mode} in {dest / 'antfarm'}")
    if (dest / "ai-workflow").is_dir():
        print("Found old ai-workflow/ folder: /init-antfarm will migrate it.")
    if not (dest / ".git").is_dir():
        print("Not a git repo yet: /init-antfarm will offer git init.")
    print(f"Next: cd {dest} and run claude, then /init-antfarm")


def update(project=None):
    if not LINK.exists():
        sys.exit("antfarm not installed: run `python antfarm.py install` from your antfarm clone first.")
    template = Path(os.path.realpath(LINK)).parent.parent  # .../antfarm (template folder)
    print(f"Pulling template in {template.parent}")
    subprocess.run(["git", "-C", str(template), "pull", "--ff-only"], check=True)
    project = Path(project or SRC.parent).resolve()
    if project == template.parent:
        return print("Template updated (no project given).")
    subprocess.run([sys.executable, str(template / "antfarm.py"), "add", str(project)], check=True)  # the freshly pulled copy
    print("Then commit + push so teammates get it.")


if __name__ == "__main__":
    cmd, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("", [])
    if cmd == "install" and not args:
        install()
    elif cmd == "add" and len(args) == 1:
        add(*args)
    elif cmd == "update" and len(args) <= 1:
        update(*args)
    else:
        sys.exit(__doc__)
