"""Compare accepted local source files with their official downloads.

The checker is deliberately read-only with respect to accepted source and
derived data.  It streams remote bytes into SHA-256, emits a small result
record, and never adopts a changed source automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import re
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "data" / "source_freshness_manifest.json"
ALLOWED_HOSTS = frozenset({
    "wwwtb.mlit.go.jp",
    "yamaguchi-opendata.jp",
    "ajt-mobusta-gtfs.mcapps.jp",
})
ALLOWED_SOURCE_TYPES = frozenset({"registry_pdf", "gtfs_zip"})
STATUSES = ("unchanged", "changed", "unavailable", "oversize", "invalid_baseline")
EXIT_CODES = {
    "unchanged": 0,
    "changed": 1,
    "unavailable": 2,
    "oversize": 2,
    "invalid_baseline": 3,
}
REQUIRED_SOURCE_FIELDS = frozenset(
    {
        "source_id",
        "source_type",
        "official_url",
        "local_path",
        "baseline_sha256",
        "baseline_bytes",
        "baseline_acquired_at",
        "max_download_bytes",
    }
)
SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CHUNK_SIZE = 64 * 1024
USER_AGENT = "yamaguchi-yusho-data-source-freshness/1.0"


class RemotePolicyError(ValueError):
    """The requested or redirected remote URL violates the fetch policy."""


def validate_remote_url(url: str) -> str:
    if not isinstance(url, str):
        raise RemotePolicyError("official_url_not_string")
    try:
        parsed = urllib.parse.urlsplit(url)
        parsed_port = parsed.port
    except ValueError as error:
        raise RemotePolicyError("url_parse_error") from error
    if parsed.scheme != "https":
        raise RemotePolicyError("https_required")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise RemotePolicyError("host_not_allowed")
    if parsed.username is not None or parsed.password is not None:
        raise RemotePolicyError("userinfo_not_allowed")
    if parsed_port not in (None, 443):
        raise RemotePolicyError("port_not_allowed")
    if parsed.query:
        raise RemotePolicyError("query_not_allowed")
    if parsed.fragment:
        raise RemotePolicyError("fragment_not_allowed")
    return url


class RestrictedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_remote_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def default_opener(url: str, timeout: float):
    validate_remote_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/pdf, application/zip, application/octet-stream;q=0.9, */*;q=0.1",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(RestrictedRedirectHandler())
    return opener.open(request, timeout=timeout)


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            byte_count += len(chunk)
            digest.update(chunk)
    return byte_count, digest.hexdigest()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_local_baseline(repo_root: Path, local_path: Any) -> Path:
    if not isinstance(local_path, str) or "\\" in local_path:
        raise ValueError("local_path_must_use_posix_separators")
    pure_path = PurePosixPath(local_path)
    if pure_path.is_absolute() or ".." in pure_path.parts or not pure_path.parts:
        raise ValueError("local_path_traversal")
    if pure_path.parts[0] != "raw":
        raise ValueError("local_path_must_be_under_raw")
    resolved_root = repo_root.resolve()
    resolved = resolved_root.joinpath(*pure_path.parts).resolve()
    if not _is_relative_to(resolved, resolved_root / "raw"):
        raise ValueError("local_path_outside_raw")
    return resolved


def validate_source_shape(source: Any, repo_root: Path, duplicate_ids: set[str]) -> tuple[Path | None, str | None]:
    if not isinstance(source, dict):
        return None, "source_not_object"
    missing = REQUIRED_SOURCE_FIELDS.difference(source)
    if missing:
        return None, "missing_fields"
    source_id = source["source_id"]
    if not isinstance(source_id, str) or not SOURCE_ID_RE.fullmatch(source_id):
        return None, "invalid_source_id"
    if source_id in duplicate_ids:
        return None, "duplicate_source_id"
    if not isinstance(source["source_type"], str) or source["source_type"] not in ALLOWED_SOURCE_TYPES:
        return None, "invalid_source_type"
    try:
        validate_remote_url(source["official_url"])
    except (RemotePolicyError, ValueError):
        return None, "invalid_official_url"
    if not isinstance(source["baseline_sha256"], str) or not SHA256_RE.fullmatch(source["baseline_sha256"]):
        return None, "invalid_baseline_sha256"
    if not isinstance(source["baseline_bytes"], int) or isinstance(source["baseline_bytes"], bool) or source["baseline_bytes"] < 0:
        return None, "invalid_baseline_bytes"
    if not isinstance(source["max_download_bytes"], int) or isinstance(source["max_download_bytes"], bool) or source["max_download_bytes"] <= 0:
        return None, "invalid_max_download_bytes"
    if source["baseline_bytes"] > source["max_download_bytes"]:
        return None, "baseline_exceeds_download_limit"
    if not isinstance(source["baseline_acquired_at"], str) or not DATE_RE.fullmatch(source["baseline_acquired_at"]):
        return None, "invalid_baseline_acquired_at"
    try:
        date.fromisoformat(source["baseline_acquired_at"])
    except ValueError:
        return None, "invalid_baseline_acquired_at"
    try:
        local_file = resolve_local_baseline(repo_root, source["local_path"])
    except ValueError as error:
        return None, str(error)
    if not local_file.is_file():
        return None, "baseline_file_missing"
    byte_count, digest = sha256_file(local_file)
    if byte_count != source["baseline_bytes"]:
        return None, "baseline_size_mismatch"
    if digest != source["baseline_sha256"]:
        return None, "baseline_sha256_mismatch"
    return local_file, None


def _base_result(source: Any) -> dict[str, Any]:
    source = source if isinstance(source, dict) else {}
    return {
        "source_id": source.get("source_id", "<invalid-source>"),
        "source_type": source.get("source_type"),
        "official_url": source.get("official_url"),
        "local_path": source.get("local_path"),
        "baseline_sha256": source.get("baseline_sha256"),
        "baseline_bytes": source.get("baseline_bytes"),
        "status": None,
        "fetched_sha256": None,
        "fetched_bytes": None,
        "error_category": None,
        "http_status": None,
    }


def _content_length(response: Any) -> int | None:
    raw_value = response.headers.get("Content-Length") if getattr(response, "headers", None) is not None else None
    if raw_value in (None, ""):
        return None
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def fetch_source(source: dict[str, Any], opener: Callable[[str, float], Any], timeout: float) -> dict[str, Any]:
    result = _base_result(source)
    try:
        response_context = opener(source["official_url"], timeout)
        with response_context as response:
            final_url = response.geturl() if hasattr(response, "geturl") else source["official_url"]
            validate_remote_url(final_url)
            declared_size = _content_length(response)
            if declared_size is not None and declared_size > source["max_download_bytes"]:
                result.update(status="oversize", fetched_bytes=declared_size, error_category="content_length_exceeds_limit")
                return result

            digest = hashlib.sha256()
            byte_count = 0
            while True:
                remaining_probe = source["max_download_bytes"] - byte_count + 1
                chunk = response.read(min(CHUNK_SIZE, remaining_probe))
                if not chunk:
                    break
                byte_count += len(chunk)
                if byte_count > source["max_download_bytes"]:
                    result.update(status="oversize", fetched_bytes=byte_count, error_category="stream_exceeds_limit")
                    return result
                digest.update(chunk)

            fetched_hash = digest.hexdigest()
            result.update(
                status="unchanged" if fetched_hash == source["baseline_sha256"] else "changed",
                fetched_sha256=fetched_hash,
                fetched_bytes=byte_count,
            )
            return result
    except RemotePolicyError:
        result.update(status="unavailable", error_category="remote_policy_violation")
    except urllib.error.HTTPError as error:
        result.update(status="unavailable", error_category="http_error", http_status=error.code)
    except (socket.timeout, TimeoutError):
        result.update(status="unavailable", error_category="timeout")
    except ssl.SSLError:
        result.update(status="unavailable", error_category="tls_error")
    except urllib.error.URLError as error:
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            category = "timeout"
        elif isinstance(error.reason, ssl.SSLError):
            category = "tls_error"
        else:
            category = "network_error"
        result.update(status="unavailable", error_category=category)
    except http.client.HTTPException:
        result.update(status="unavailable", error_category="http_protocol_error")
    except OSError:
        result.update(status="unavailable", error_category="network_error")
    return result


def build_report(results: list[dict[str, Any]], checked_at: str) -> dict[str, Any]:
    counts = Counter(result["status"] for result in results)
    exit_code = max((EXIT_CODES.get(result["status"], 3) for result in results), default=3)
    return {
        "schema_version": "WORK1-FRESHNESS-1-result-v1",
        "checked_at": checked_at,
        "baseline_mode": "read_only_no_automatic_adoption",
        "source_count": len(results),
        "summary": {status: counts.get(status, 0) for status in STATUSES},
        "exit_code": exit_code,
        "sources": results,
    }


def invalid_manifest_report(category: str, checked_at: str) -> dict[str, Any]:
    result = _base_result({"source_id": "<manifest>"})
    result.update(status="invalid_baseline", error_category=category)
    return build_report([result], checked_at)


def check_sources(
    manifest: Any,
    repo_root: Path = REPO_ROOT,
    opener: Callable[[str, float], Any] | None = None,
    timeout: float = 30.0,
    checked_at: str | None = None,
) -> dict[str, Any]:
    checked_at = checked_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "WORK1-FRESHNESS-1":
        return invalid_manifest_report("invalid_manifest_schema", checked_at)
    sources = manifest.get("sources")
    expected_count = manifest.get("expected_source_count")
    if (
        not isinstance(sources, list)
        or not isinstance(expected_count, int)
        or isinstance(expected_count, bool)
        or expected_count <= 0
        or len(sources) != expected_count
    ):
        return invalid_manifest_report("invalid_source_count", checked_at)

    source_ids = [
        source.get("source_id")
        for source in sources
        if isinstance(source, dict) and isinstance(source.get("source_id"), str)
    ]
    duplicate_ids = {source_id for source_id, count in Counter(source_ids).items() if count > 1}
    fetch = opener or default_opener
    results: list[dict[str, Any]] = []
    for source in sources:
        _, validation_error = validate_source_shape(source, repo_root, duplicate_ids)
        if validation_error:
            result = _base_result(source)
            result.update(status="invalid_baseline", error_category=validation_error)
        else:
            result = fetch_source(source, fetch, timeout)
        results.append(result)
    return build_report(results, checked_at)


def load_manifest(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_output_path_safe(output_path: Path, repo_root: Path = REPO_ROOT) -> Path:
    resolved = output_path.resolve()
    protected_roots = (repo_root / "raw", repo_root / "data", repo_root / "docs")
    if any(_is_relative_to(resolved, protected.resolve()) for protected in protected_roots):
        raise ValueError("output_path_is_protected")
    if resolved.suffix.lower() != ".json":
        raise ValueError("output_path_must_be_json")
    return resolved


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, help="Optional JSON result path; raw/, data/, and docs/ are refused")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    try:
        manifest = load_manifest(args.manifest)
    except (OSError, UnicodeError, json.JSONDecodeError):
        report = invalid_manifest_report("manifest_unreadable", checked_at)
    else:
        report = check_sources(manifest, repo_root=REPO_ROOT, timeout=args.timeout_seconds, checked_at=checked_at)

    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        try:
            safe_output = ensure_output_path_safe(args.output)
            safe_output.parent.mkdir(parents=True, exist_ok=True)
            safe_output.write_text(payload, encoding="utf-8", newline="\n")
        except (OSError, ValueError) as error:
            print(f"source freshness result write failed: {type(error).__name__}", file=sys.stderr)
            return 3
    print(payload, end="")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
