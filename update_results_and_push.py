#!/usr/bin/env python3
"""Run Tour de France updater, commit and push changes."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent

def run(cmd):
    return subprocess.run(cmd, cwd=BASE, text=True, capture_output=True, check=False)

def main() -> int:
    pull = run(["git", "pull", "--ff-only", "origin", "main"])
    if pull.returncode != 0:
        print("git pull failed", pull.stdout, pull.stderr, file=sys.stderr)
        return pull.returncode

    upd = run(["python3", "update_results.py"])
    if upd.returncode != 0:
        print(upd.stdout, upd.stderr, file=sys.stderr)
        return upd.returncode

    status = run(["git", "status", "--porcelain"])
    if not status.stdout.strip():
        return 0

    run(["git", "add", "tour-de-france-2026.json", "tour-de-france-2026.ics", "update_results.py", "generate_ics.py"])
    status = run(["git", "diff", "--cached", "--quiet"])
    if status.returncode == 0:
        return 0

    msg = "chore: update Tour de France 2026 results " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    commit = run(["git", "commit", "-m", msg])
    if commit.returncode != 0:
        print(commit.stdout, commit.stderr, file=sys.stderr)
        return commit.returncode

    push = run(["git", "push", "origin", "main"])
    if push.returncode != 0:
        print(push.stdout, push.stderr, file=sys.stderr)
        return push.returncode

    if upd.stdout.strip():
        print(upd.stdout.strip())
    else:
        print("Tour de France 2026 results updated and pushed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
