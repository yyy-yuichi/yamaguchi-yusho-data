"""Rebuild accepted Work 1 outputs inside an isolated commit snapshot.

The drill never downloads or adopts source data.  It archives one exact commit,
checks the seven accepted originals, removes only generated files in a temporary
copy, rebuilds them, and proves that an injected missing output can be restored.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import subprocess
import sys
import tarfile
import tempfile
from typing import Any, Sequence


STAGE = "WORK1-INDEPENDENT-REPRODUCTION-DRILL-1"
EXPECTED_ORIGIN = "https://github.com/yyy-yuichi/yamaguchi-yusho-data.git"

BUILDERS = (
    "src/parse.py",
    "src/build_gtfs_status.py",
    "src/calculate_gtfs_supply_metrics.py",
    "src/calculate_jrbus_supply_metrics.py",
    "src/build_site_data.py",
)

GENERATED_TARGETS = (
    "data/operators.csv",
    "data/operators.json",
    "data/vehicles.csv",
    "data/vehicles.json",
    "data/gtfs_feeds.csv",
    "data/gtfs_feeds.json",
    "data/municipality_gtfs.csv",
    "data/municipality_gtfs.json",
    "data/gtfs_supply_metrics.json",
    "data/jrbus_chugoku_supply_metrics.json",
    "docs/data/operators.json",
    "docs/data/vehicles.json",
    "docs/data/gtfs_feeds.json",
    "docs/data/municipality_gtfs.json",
    "docs/data/gtfs_supply_metrics.json",
    "docs/data/jrbus_chugoku_supply_metrics.json",
    "docs/data/municipal_supply.json",
)

RECOVERY_TARGET = "docs/data/municipal_supply.json"
RECOVERY_BUILDER = "src/build_site_data.py"
RECORDED_DEPENDENCIES = ("pdfplumber",)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def normalized_text_bytes(payload: bytes) -> bytes:
    """Ignore only operating-system newline representation."""

    return payload.replace(b"\r\n", b"\n")


def installed_dependency_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for package in RECORDED_DEPENDENCIES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def child_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve(strict=False)
    root_resolved = root.resolve(strict=True)
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"path escapes snapshot: {relative}") from exc
    return candidate


def extract_archive(payload: bytes, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"unsafe archive path: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise ValueError(f"unsupported archive entry: {member.name}")
        archive.extractall(destination, filter="data")


def run_command(command: Sequence[str], cwd: Path, *, timeout: int = 600) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    combined = (completed.stdout + "\n" + completed.stderr).strip().splitlines()
    return {
        "command": list(command),
        "exit_code": completed.returncode,
        "output_tail": combined[-20:],
    }


def accepted_source_checks(snapshot: Path) -> list[dict[str, Any]]:
    manifest_path = child_path(snapshot, "data/source_freshness_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("expected_source_count") != 7:
        raise ValueError("accepted source count is not 7")
    checks = []
    for item in manifest["sources"]:
        path = child_path(snapshot, item["local_path"])
        payload = path.read_bytes()
        actual_sha = sha256_bytes(payload)
        actual_bytes = len(payload)
        checks.append(
            {
                "source_id": item["source_id"],
                "local_path": item["local_path"],
                "bytes": actual_bytes,
                "sha256": actual_sha,
                "baseline_match": actual_bytes == item["baseline_bytes"]
                and actual_sha == item["baseline_sha256"],
            }
        )
    return checks


def compare_targets(expected: Path, actual: Path) -> list[dict[str, Any]]:
    results = []
    for relative in GENERATED_TARGETS:
        expected_path = child_path(expected, relative)
        actual_path = child_path(actual, relative)
        if not actual_path.is_file():
            results.append(
                {
                    "path": relative,
                    "recreated": False,
                    "byte_match": False,
                    "normalized_match": False,
                }
            )
            continue
        expected_bytes = expected_path.read_bytes()
        actual_bytes = actual_path.read_bytes()
        results.append(
            {
                "path": relative,
                "recreated": True,
                "expected_bytes": len(expected_bytes),
                "actual_bytes": len(actual_bytes),
                "expected_sha256": sha256_bytes(expected_bytes),
                "actual_sha256": sha256_bytes(actual_bytes),
                "byte_match": actual_bytes == expected_bytes,
                "normalized_match": normalized_text_bytes(actual_bytes)
                == normalized_text_bytes(expected_bytes),
            }
        )
    return results


def initialize_snapshot_git(snapshot: Path) -> list[dict[str, Any]]:
    commands = (
        ("git", "init", "-q"),
        ("git", "remote", "add", "origin", EXPECTED_ORIGIN),
    )
    results = []
    for command in commands:
        result = run_command(command, snapshot)
        results.append(result)
        if result["exit_code"] != 0:
            raise RuntimeError(f"snapshot git setup failed: {' '.join(command)}")
    return results


def run_tests(snapshot: Path) -> dict[str, Any]:
    count = run_command(
        (
            sys.executable,
            "-c",
            "import unittest; print(unittest.defaultTestLoader.discover('tests').countTestCases())",
        ),
        snapshot,
    )
    if count["exit_code"] != 0 or not count["output_tail"]:
        return {"discovered": 0, "passed": 0, "success": False, "count_command": count}
    discovered = int(count["output_tail"][-1])
    execution = run_command(
        (sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-q"),
        snapshot,
        timeout=900,
    )
    return {
        "discovered": discovered,
        "passed": discovered if execution["exit_code"] == 0 else 0,
        "success": execution["exit_code"] == 0,
        "execution": execution,
    }


def render_markdown(report: dict[str, Any]) -> str:
    reconstruction = report.get("reconstruction", {})
    recovery = report.get("recovery", {})
    tests = report.get("tests", {})
    lines = [
        "# Work 1 independent reproduction drill",
        "",
        f"- Decision: **{report.get('decision', 'NO_GO')}**",
        f"- Subject: `{report.get('subject', {}).get('commit_sha', '')}`",
        f"- Accepted originals: {report.get('accepted_sources', {}).get('matched', 0)} / 7",
        f"- Recreated targets: {reconstruction.get('normalized_matched', 0)} / {len(GENERATED_TARGETS)}",
        f"- Exact-byte matches: {reconstruction.get('byte_matched', 0)} / {len(GENERATED_TARGETS)}",
        f"- Recovery: {'success' if recovery.get('success') else 'failed'}",
    ]
    if tests.get("requested"):
        lines.append(f"- Tests: {tests.get('passed', 0)} / {tests.get('discovered', 0)}")
    lines.extend(
        [
            f"- Errors: {len(report.get('errors', []))}",
            "",
            "The drill used only the accepted files contained in the exact commit snapshot.",
            "It did not download, adopt, or overwrite source data in the checked-out repository.",
            "",
        ]
    )
    return "\n".join(lines)


def acceptance_checks(
    report: dict[str, Any],
    *,
    include_tests: bool,
    require_exact_byte_match: bool,
) -> dict[str, bool]:
    reconstruction = report.get("reconstruction", {})
    return {
        "tests": not include_tests or report.get("tests", {}).get("success", False),
        "accepted_sources": report.get("accepted_sources", {}).get("matched") == 7,
        "normalized_reconstruction": reconstruction.get("normalized_matched")
        == len(GENERATED_TARGETS),
        "exact_byte_reconstruction": not require_exact_byte_match
        or reconstruction.get("byte_matched") == len(GENERATED_TARGETS),
        "recovery": report.get("recovery", {}).get("success", False),
        "temporary_snapshot_removed": report.get("boundaries", {}).get(
            "temporary_snapshot_removed", False
        ),
    }


def execute_drill(
    repo: Path,
    subject_sha: str,
    *,
    include_tests: bool,
    require_exact_byte_match: bool = False,
) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    errors: list[str] = []
    report: dict[str, Any] = {
        "schema_version": 1,
        "stage": STAGE,
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "decision": "NO_GO",
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "dependencies": installed_dependency_versions(),
        },
        "contract": {"require_exact_byte_match": require_exact_byte_match},
        "errors": errors,
    }

    resolved = run_command(("git", "rev-parse", f"{subject_sha}^{{commit}}"), repo)
    if resolved["exit_code"] != 0 or not resolved["output_tail"]:
        errors.append("subject commit could not be resolved")
        report["subject"] = {"requested": subject_sha, "commit_sha": ""}
        return report
    commit_sha = resolved["output_tail"][-1].strip()
    head = run_command(("git", "rev-parse", "HEAD"), repo)
    head_sha = head["output_tail"][-1].strip() if head["output_tail"] else ""
    status = run_command(("git", "status", "--porcelain=v1"), repo)
    report["subject"] = {
        "requested": subject_sha,
        "commit_sha": commit_sha,
        "checked_out_head": head_sha,
        "head_match": commit_sha == head_sha,
        "invoking_worktree_clean": not status["output_tail"],
    }
    if commit_sha != head_sha:
        errors.append("subject commit does not match checked-out HEAD")

    archive = subprocess.run(
        (
            "git",
            "-c",
            "core.autocrlf=false",
            "archive",
            "--format=tar",
            commit_sha,
        ),
        cwd=repo,
        capture_output=True,
        check=False,
        timeout=120,
    )
    if archive.returncode != 0:
        errors.append("git archive failed")
        return report
    report["snapshot"] = {
        "method": "git archive with core.autocrlf=false",
        "archive_bytes": len(archive.stdout),
        "archive_sha256": sha256_bytes(archive.stdout),
    }

    temp_path: Path | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="work1-reproduction-drill-") as temp_name:
            temp_path = Path(temp_name).resolve(strict=True)
            expected = temp_path / "expected" / "yamaguchi-yusho-data"
            work = temp_path / "work" / "yamaguchi-yusho-data"
            extract_archive(archive.stdout, expected)
            extract_archive(archive.stdout, work)

            source_checks = accepted_source_checks(expected)
            source_matches = sum(item["baseline_match"] for item in source_checks)
            report["accepted_sources"] = {
                "expected": 7,
                "matched": source_matches,
                "checks": source_checks,
            }
            if source_matches != 7:
                errors.append("accepted source baseline mismatch")

            for relative in GENERATED_TARGETS:
                path = child_path(work, relative)
                if not path.is_file():
                    raise FileNotFoundError(f"expected generated baseline missing: {relative}")
                path.unlink()

            builder_results = []
            for script in BUILDERS:
                result = run_command((sys.executable, "-B", script), work)
                builder_results.append(result)
                if result["exit_code"] != 0:
                    errors.append(f"builder failed: {script}")
                    break

            comparisons = compare_targets(expected, work)
            normalized_matched = sum(item["normalized_match"] for item in comparisons)
            byte_matched = sum(item["byte_match"] for item in comparisons)
            recreated = sum(item["recreated"] for item in comparisons)
            report["reconstruction"] = {
                "builder_results": builder_results,
                "target_count": len(GENERATED_TARGETS),
                "recreated": recreated,
                "normalized_matched": normalized_matched,
                "byte_matched": byte_matched,
                "comparisons": comparisons,
            }
            if normalized_matched != len(GENERATED_TARGETS):
                errors.append("reconstructed target content mismatch")
            if require_exact_byte_match and byte_matched != len(GENERATED_TARGETS):
                errors.append("exact-byte target mismatch under strict mode")

            recovery_path = child_path(work, RECOVERY_TARGET)
            recovery_path.unlink()
            missing_detected = not recovery_path.exists()
            recovery_command = run_command((sys.executable, "-B", RECOVERY_BUILDER), work)
            expected_recovery = child_path(expected, RECOVERY_TARGET).read_bytes()
            actual_recovery = recovery_path.read_bytes() if recovery_path.is_file() else b""
            recovery_match = normalized_text_bytes(actual_recovery) == normalized_text_bytes(
                expected_recovery
            )
            post_recovery = compare_targets(expected, work)
            post_recovery_all_match = all(item["normalized_match"] for item in post_recovery)
            recovery_success = (
                missing_detected
                and recovery_command["exit_code"] == 0
                and recovery_match
                and post_recovery_all_match
            )
            report["recovery"] = {
                "injected_failure": f"removed {RECOVERY_TARGET} in temporary snapshot",
                "missing_detected": missing_detected,
                "command": recovery_command,
                "normalized_match": recovery_match,
                "post_recovery_all_targets_match": post_recovery_all_match,
                "success": recovery_success,
            }
            if not recovery_success:
                errors.append("injected missing-output recovery failed")

            if include_tests:
                report["snapshot_git_setup"] = initialize_snapshot_git(work)
                test_result = run_tests(work)
                report["tests"] = {"requested": True, **test_result}
                if not test_result["success"]:
                    errors.append("reconstructed snapshot tests failed")
            else:
                report["tests"] = {"requested": False}
    except Exception as exc:  # report the evidence instead of losing it
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        report["boundaries"] = {
            "temporary_snapshot_removed": bool(temp_path) and not temp_path.exists(),
            "checked_out_source_writes": 0,
            "source_downloads": 0,
            "source_adoptions": 0,
            "other_work_inputs": 0,
            "participant_contacts": 0,
            "udc_submissions": 0,
            "bodik_registrations": 0,
        }

    checks = acceptance_checks(
        report,
        include_tests=include_tests,
        require_exact_byte_match=require_exact_byte_match,
    )
    report["acceptance"] = {
        "exact_byte_match_required": require_exact_byte_match,
        "checks": checks,
    }
    if not errors and all(checks.values()):
        report["decision"] = "GO"
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--subject-sha", default="HEAD")
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument(
        "--require-byte-match",
        action="store_true",
        help="Require all generated targets to match the commit bytes exactly.",
    )
    parser.add_argument("--output-dir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = execute_drill(
        Path(args.repo),
        args.subject_sha,
        include_tests=args.run_tests,
        require_exact_byte_match=args.require_byte_match,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "reproduction-drill.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "reproduction-drill.md").write_text(
        render_markdown(report), encoding="utf-8"
    )
    print(render_markdown(report))
    return 0 if report["decision"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
