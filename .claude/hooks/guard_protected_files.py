#!/usr/bin/env python3
"""PreToolUse hook.

1. chat-side owned files are not writable by Claude Code
2. nothing may be written outside the repository, including /tmp
"""
import json
import os
import re
import sys

REPO = "c/users/user/dev/udc2026/yamaguchi-yusho-data"

WRITE_PROTECTED = [
    "CLAUDE.md", "SPEC.md", "run_record.md",
    "spec_coverage.py", "settings.json", "guard_protected_files.py",
]
READ_PROTECTED = ["run_record.md"]
WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
READ_TOOLS = ("Read", "NotebookRead")

OUTSIDE = re.compile(r"(?:>>?|-o|--output[= ])\s*('|\")?(/tmp/|/var/|/c/temp/|~/|\.\./)", re.I)


def norm(p):
    p = p.replace("\\", "/").lower()
    p = re.sub(r"^([a-z]):/", lambda m: "/" + m.group(1) + "/", p)
    return p


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    tool = payload.get("tool_name", "")
    ti = payload.get("tool_input") or {}

    if tool == "Bash":
        cmd = ti.get("command", "") or ""
        m = OUTSIDE.search(cmd)
        if m:
            sys.stderr.write(
                "[guard] blocked bash write outside the repo: " + m.group(0).strip() + "\n"
                "Write intermediate files under raw/ or evidence/ in the repo.\n"
                "Never write to /tmp or any path outside "
                "C:/Users/user/dev/udc2026/yamaguchi-yusho-data.\n")
            return 2
        return 0

    full = ""
    for key in ("file_path", "path", "notebook_path"):
        v = ti.get(key)
        if isinstance(v, str) and v:
            full = v
            break
    if not full:
        return 0
    base = os.path.basename(full.replace("\\", "/"))

    if tool in WRITE_TOOLS and base in WRITE_PROTECTED:
        sys.stderr.write(
            "[guard] blocked write: " + full + "\n"
            + base + " is owned by the chat side. Not editable here.\n"
            "Write your concern to PROGRESS.md and stop.\n")
        return 2

    if tool in WRITE_TOOLS and REPO not in norm(full):
        sys.stderr.write(
            "[guard] blocked write outside the repo: " + full + "\n"
            "All output must live under "
            "C:/Users/user/dev/udc2026/yamaguchi-yusho-data.\n")
        return 2

    if tool in READ_TOOLS and base in READ_PROTECTED:
        sys.stderr.write(
            "[guard] blocked read: " + full + "\n"
            + base + " must not be read. The spec is in SPEC.md.\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())