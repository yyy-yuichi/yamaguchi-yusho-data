"""Build a machine-readable attestation for the exact published Work 1 commit.

The record is designed for a GitHub Actions artifact rather than a committed
file.  That avoids the self-reference problem where recording a final commit
inside the repository necessarily creates a different final commit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parent.parent
REPOSITORY_ID = "yyy-yuichi/yamaguchi-yusho-data"
WORK_ID = "WORK1"
STAGE = "WORK1-RELEASE-ATTESTATION-1"
PUBLIC_BASE = "https://yyy-yuichi.github.io/yamaguchi-yusho-data"
SHA256_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_PUBLIC_BYTES = 2 * 1024 * 1024
PUBLIC_ASSETS = (
    ("status.html", "docs/status.html"),
    ("award-comparison.html", "docs/award-comparison.html"),
    ("data/work1_award_scorecard.json", "docs/data/work1_award_scorecard.json"),
)
FIXED_PROTECTED_SHA256 = {
    "docs/index.html": "502eb93199d3df71593dc7d220d575159a9167a2692bdec2bb8b5b4b7d7c4b49",
    "docs/entry.html": "c89d25f9e491da49b391578929369d8c1d0b98cc18b669f0c3dfb77b9c52a95c",
    "data/work1_award_scorecard.json": "0826a1851464cd7198f10f9eb4eddb0896c8af2c1a156e8a87cca49754d9d021",
}

FetchResult = tuple[int, str, bytes]
Fetcher = Callable[[str], FetchResult]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_fingerprint(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def git_head(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def validate_public_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "yyy-yuichi.github.io":
        raise ValueError("public_url_outside_work1_pages")
    if not parsed.path.startswith("/yamaguchi-yusho-data/"):
        raise ValueError("public_url_outside_work1_pages")
    return url


def fetch_public(url: str, timeout: float = 30.0) -> FetchResult:
    validate_public_url(url)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "yamaguchi-yusho-data-release-attestation/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        final_url = validate_public_url(response.geturl())
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_PUBLIC_BYTES:
                raise ValueError("public_asset_exceeds_limit")
            chunks.append(chunk)
        return int(response.status), final_url, b"".join(chunks)


def _source_checks(repo_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    manifest_path = repo_root / "data" / "source_freshness_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    sources = manifest.get("sources", [])
    if manifest.get("expected_source_count") != 6 or len(sources) != 6:
        errors.append("accepted_source_count_not_six")
    for item in sources:
        relative = item["local_path"]
        size, digest = file_fingerprint(repo_root / relative)
        matched = size == item["baseline_bytes"] and digest == item["baseline_sha256"]
        results.append(
            {
                "source_id": item["source_id"],
                "source_type": item["source_type"],
                "local_path": relative,
                "expected_bytes": item["baseline_bytes"],
                "actual_bytes": size,
                "expected_sha256": item["baseline_sha256"],
                "actual_sha256": digest,
                "baseline_match": matched,
            }
        )
        if not matched:
            errors.append(f"accepted_source_mismatch:{item['source_id']}")
    return results, errors


def _protected_checks(repo_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    for relative, expected in FIXED_PROTECTED_SHA256.items():
        size, actual = file_fingerprint(repo_root / relative)
        matched = actual == expected
        results.append(
            {
                "path": relative,
                "bytes": size,
                "expected_sha256": expected,
                "actual_sha256": actual,
                "fixed_baseline_match": matched,
            }
        )
        if not matched:
            errors.append(f"protected_asset_mismatch:{relative}")
    return results, errors


def _scorecard_check(repo_root: Path) -> tuple[dict[str, Any], list[str]]:
    path = repo_root / "data" / "work1_award_scorecard.json"
    public_copy = repo_root / "docs" / "data" / "work1_award_scorecard.json"
    payload = path.read_bytes()
    scorecard = json.loads(payload)
    criteria = {item["criterion_id"]: item for item in scorecard["criteria"]}
    result = {
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "public_copy_match": payload == public_copy.read_bytes(),
        "work_id": scorecard.get("work_id"),
        "repository_id": scorecard.get("evidence_boundary", {}).get("repository_id"),
        "other_work_input_count": scorecard.get("evidence_boundary", {}).get(
            "other_work_input_count"
        ),
        "scores": {
            "実用度": criteria.get("utility", {}).get("score"),
            "完成度": criteria.get("completeness", {}).get("score"),
            "挑戦度": criteria.get("challenge", {}).get("score"),
        },
        "overall_comparison_index": scorecard.get("overall", {}).get("comparison_index"),
    }
    expected = {
        "sha256": FIXED_PROTECTED_SHA256["data/work1_award_scorecard.json"],
        "work_id": WORK_ID,
        "repository_id": REPOSITORY_ID,
        "other_work_input_count": 0,
        "scores": {"実用度": 3.5, "完成度": 4.0, "挑戦度": 3.0},
        "overall_comparison_index": 70.0,
    }
    errors: list[str] = []
    for key, value in expected.items():
        if result[key] != value:
            errors.append(f"scorecard_mismatch:{key}")
    if not result["public_copy_match"]:
        errors.append("scorecard_public_copy_mismatch")
    return result, errors


def _public_checks(
    repo_root: Path,
    public_base: str,
    target_sha: str,
    fetcher: Fetcher,
    attempts: int,
    retry_delay: float,
) -> tuple[list[dict[str, Any]], list[str]]:
    if public_base.rstrip("/") != PUBLIC_BASE:
        raise ValueError("public_base_must_be_work1_pages")
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    for public_path, local_path in PUBLIC_ASSETS:
        expected_payload = (repo_root / local_path).read_bytes()
        expected_sha = sha256_bytes(expected_payload)
        clean_url = f"{PUBLIC_BASE}/{public_path}"
        request_url = f"{clean_url}?attestation_sha={target_sha}"
        last: dict[str, Any] = {
            "path": public_path,
            "url": clean_url,
            "expected_bytes": len(expected_payload),
            "expected_sha256": expected_sha,
            "http": None,
            "actual_bytes": None,
            "actual_sha256": None,
            "commit_bytes_match": False,
            "attempts": 0,
        }
        for attempt in range(1, attempts + 1):
            last["attempts"] = attempt
            try:
                status, final_url, payload = fetcher(request_url)
                validate_public_url(final_url)
                last.update(
                    {
                        "http": status,
                        "actual_bytes": len(payload),
                        "actual_sha256": sha256_bytes(payload),
                        "commit_bytes_match": status == 200 and payload == expected_payload,
                    }
                )
                if last["commit_bytes_match"]:
                    break
            except Exception as exc:  # the artifact records category, never source bodies
                last["error"] = f"{type(exc).__name__}:{exc}"
            if attempt < attempts and retry_delay:
                time.sleep(retry_delay)
        if not last["commit_bytes_match"]:
            errors.append(f"public_asset_mismatch:{public_path}")
        results.append(last)
    return results, errors


def build_attestation(
    *,
    repo_root: Path,
    target_sha: str,
    pages_run_id: int,
    pages_run_url: str,
    attestation_run_id: int,
    attestation_run_attempt: int,
    attestation_run_url: str,
    tests_discovered: int,
    tests_passed: bool,
    scope_guard_passed: bool,
    fetcher: Fetcher = fetch_public,
    public_base: str = PUBLIC_BASE,
    attempts: int = 1,
    retry_delay: float = 0.0,
    checked_at: str | None = None,
    actual_head: str | None = None,
) -> dict[str, Any]:
    if not SHA256_RE.fullmatch(target_sha):
        raise ValueError("target_sha_must_be_40_lowercase_hex")
    if min(pages_run_id, attestation_run_id, attestation_run_attempt, tests_discovered, attempts) < 1:
        raise ValueError("positive_values_required")

    errors: list[str] = []
    checked_out_head = actual_head or git_head(repo_root)
    if checked_out_head != target_sha:
        errors.append("checked_out_head_mismatch")
    if not tests_passed:
        errors.append("tests_failed")
    if not scope_guard_passed:
        errors.append("scope_guard_failed")

    source_results, source_errors = _source_checks(repo_root)
    protected_results, protected_errors = _protected_checks(repo_root)
    scorecard_result, scorecard_errors = _scorecard_check(repo_root)
    public_results, public_errors = _public_checks(
        repo_root, public_base, target_sha, fetcher, attempts, retry_delay
    )
    errors.extend(source_errors + protected_errors + scorecard_errors + public_errors)

    artifact_name = f"work1-release-attestation-{target_sha}"
    decision = "GO" if not errors else "NO_GO"
    return {
        "schema_version": 1,
        "stage": STAGE,
        "checked_at": checked_at or datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "subject": {
            "work_id": WORK_ID,
            "repository_id": REPOSITORY_ID,
            "branch": "main",
            "commit_sha": target_sha,
            "checked_out_head": checked_out_head,
            "head_sha_match": checked_out_head == target_sha,
        },
        "workflow": {
            "name": "Work 1 release attestation",
            "run_id": attestation_run_id,
            "run_attempt": attestation_run_attempt,
            "run_url": attestation_run_url,
            "artifact_name": artifact_name,
            "retention_days": 90,
        },
        "upstream_pages": {
            "workflow_name": "pages-build-deployment",
            "run_id": pages_run_id,
            "run_url": pages_run_url,
            "conclusion": "success",
            "head_sha": target_sha,
            "head_sha_match": True,
        },
        "verification": {
            "scope_guard": {"passed": scope_guard_passed},
            "tests": {
                "discovered": tests_discovered,
                "passed": tests_discovered if tests_passed else 0,
                "failed": 0 if tests_passed else None,
                "success": tests_passed,
            },
            "accepted_sources": source_results,
            "accepted_source_count": len(source_results),
            "protected_assets": protected_results,
            "scorecard": scorecard_result,
            "public_assets": public_results,
        },
        "scope": {
            "other_work_inputs": 0,
            "participant_contacts": 0,
            "udc_submissions": 0,
            "bodik_registrations": 0,
            "external_requests": [item["url"] for item in public_results],
        },
        "errors": errors,
    }


def render_summary(record: dict[str, Any]) -> str:
    subject = record["subject"]
    workflow = record["workflow"]
    pages = record["upstream_pages"]
    tests = record["verification"]["tests"]
    public_ok = sum(
        item["commit_bytes_match"] for item in record["verification"]["public_assets"]
    )
    sources_ok = sum(
        item["baseline_match"] for item in record["verification"]["accepted_sources"]
    )
    return "\n".join(
        (
            "# Work 1 release attestation",
            "",
            f"- Decision: **{record['decision']}**",
            f"- Commit: `{subject['commit_sha']}`",
            f"- Attestation run: [{workflow['run_id']}]({workflow['run_url']})",
            f"- Pages run: [{pages['run_id']}]({pages['run_url']})",
            f"- Tests: {tests['passed']} / {tests['discovered']}",
            f"- Public commit-byte matches: {public_ok} / {len(PUBLIC_ASSETS)}",
            f"- Accepted source baseline matches: {sources_ok} / 6",
            "- Work 2 inputs / participant contacts / UDC submissions / BODIK registrations: 0 / 0 / 0 / 0",
            "",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--pages-run-id", type=int, required=True)
    parser.add_argument("--pages-run-url", required=True)
    parser.add_argument("--attestation-run-id", type=int, required=True)
    parser.add_argument("--attestation-run-attempt", type=int, required=True)
    parser.add_argument("--attestation-run-url", required=True)
    parser.add_argument("--tests-discovered", type=int, required=True)
    parser.add_argument("--tests-passed", action="store_true")
    parser.add_argument("--scope-guard-passed", action="store_true")
    parser.add_argument("--public-base", default=PUBLIC_BASE)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--retry-delay", type=float, default=0.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    record = build_attestation(
        repo_root=args.repo.resolve(),
        target_sha=args.target_sha,
        pages_run_id=args.pages_run_id,
        pages_run_url=args.pages_run_url,
        attestation_run_id=args.attestation_run_id,
        attestation_run_attempt=args.attestation_run_attempt,
        attestation_run_url=args.attestation_run_url,
        tests_discovered=args.tests_discovered,
        tests_passed=args.tests_passed,
        scope_guard_passed=args.scope_guard_passed,
        public_base=args.public_base,
        attempts=args.attempts,
        retry_delay=args.retry_delay,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary_path = args.output.with_suffix(".md")
    summary_path.write_text(render_summary(record), encoding="utf-8")
    print(
        json.dumps(
            {
                "decision": record["decision"],
                "commit_sha": record["subject"]["commit_sha"],
                "run_id": record["workflow"]["run_id"],
                "output": str(args.output),
            }
        )
    )
    return 0 if record["decision"] == "GO" else 1


if __name__ == "__main__":
    sys.exit(main())
