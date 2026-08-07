#!/usr/bin/env python3
"""PreToolUse hook: chat-side owned files are not writable by Claude Code."""
import json
import os
import sys

WRITE_PROTECTED = [
    "CLAUDE.md", "SPEC.md", "run_record.md",
    "spec_coverage.py", "settings.json", "guard_protected_files.py",
]
READ_PROTECTED = ["run_record.md"]
WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
READ_TOOLS = ("Read", "NotebookRead")


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    tool = payload.get("tool_name", "")
    ti = payload.get("tool_input") or {}
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

    if tool in READ_TOOLS and base in READ_PROTECTED:
        sys.stderr.write(
            "[guard] blocked read: " + full + "\n"
            + base + " must not be read. The spec is in SPEC.md.\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())