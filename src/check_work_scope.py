#!/usr/bin/env python3
"""Fail closed unless an operation stays inside the Work 1 repository."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence


class ScopeViolation(RuntimeError):
    """Raised when the repository, origin, or a candidate path is out of scope."""


def _trusted_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_config(root: Path) -> dict[str, Any]:
    config_path = root / "work_scope.json"
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScopeViolation("scope_config_unreadable") from exc

    required = {
        "schema_version": int,
        "work_id": str,
        "repository_id": str,
        "expected_root_name": str,
        "expected_origin_urls": list,
        "deny_outside_repository": bool,
        "other_works_policy": str,
    }
    for key, expected_type in required.items():
        if not isinstance(data.get(key), expected_type):
            raise ScopeViolation(f"scope_config_invalid:{key}")
    if data["schema_version"] != 1:
        raise ScopeViolation("scope_config_schema")
    if data["work_id"] != "WORK1":
        raise ScopeViolation("scope_work_id")
    if data["expected_root_name"] != root.name:
        raise ScopeViolation("scope_root_name")
    if data["deny_outside_repository"] is not True:
        raise ScopeViolation("scope_not_deny_by_default")
    if data["other_works_policy"] != "no_read_no_write_no_execute":
        raise ScopeViolation("scope_other_works_policy")
    urls = data["expected_origin_urls"]
    if not urls or any(not isinstance(url, str) or not url for url in urls):
        raise ScopeViolation("scope_origin_allowlist")
    return data


def _run_git(root: Path, args: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise ScopeViolation("scope_git_unavailable") from exc
    return completed.stdout.strip()


def path_is_within(root: Path, candidate: Path) -> bool:
    root_resolved = root.resolve(strict=True)
    candidate_resolved = candidate.resolve(strict=False)
    try:
        return os.path.commonpath((str(root_resolved), str(candidate_resolved))) == str(root_resolved)
    except ValueError:
        return False


def resolve_candidate(root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    if not path_is_within(root, candidate):
        raise ScopeViolation("scope_path_outside_repository")
    return candidate.resolve(strict=False)


def validate_scope(repo_argument: str, candidate_paths: Sequence[str]) -> dict[str, Any]:
    trusted_root = _trusted_root()
    requested = Path(repo_argument)
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    if requested.resolve(strict=False) != trusted_root:
        raise ScopeViolation("scope_repository_argument")

    config = _load_config(trusted_root)
    git_root = Path(_run_git(trusted_root, ["rev-parse", "--show-toplevel"]))
    if git_root.resolve(strict=True) != trusted_root:
        raise ScopeViolation("scope_git_root")

    origin = _run_git(trusted_root, ["remote", "get-url", "origin"])
    if origin not in config["expected_origin_urls"]:
        raise ScopeViolation("scope_origin")

    checked_paths = [resolve_candidate(trusted_root, item) for item in candidate_paths]
    return {
        "status": "allowed",
        "work_id": config["work_id"],
        "repository_id": config["repository_id"],
        "root": trusted_root.as_posix(),
        "origin": origin,
        "checked_path_count": len(checked_paths),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="must resolve to this Work 1 repository")
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        dest="paths",
        help="candidate target path; repeat for every target",
    )
    parser.add_argument("--json", action="store_true", help="emit the allowed result as JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = validate_scope(args.repo, args.paths)
    except ScopeViolation as exc:
        print(f"WORK1_SCOPE_DENIED:{exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print("WORK1_SCOPE_ALLOWED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
