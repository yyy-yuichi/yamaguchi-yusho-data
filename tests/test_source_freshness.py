"""WORK1-FRESHNESS-1 source comparison and automation contracts."""
from __future__ import annotations

import copy
import hashlib
import http.client
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import check_source_freshness as freshness  # noqa: E402


class FakeResponse:
    def __init__(self, body: bytes, url: str, content_length: int | None = None):
        self._body = io.BytesIO(body)
        self._url = url
        self.headers = {} if content_length is None else {"Content-Length": str(content_length)}

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class SourceFreshnessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest_path = REPO_ROOT / "data" / "source_freshness_manifest.json"
        cls.manifest = json.loads(cls.manifest_path.read_text(encoding="utf-8"))

    def make_fixture(self, body: bytes = b"accepted baseline"):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        local_file = root / "raw" / "baseline.bin"
        local_file.parent.mkdir(parents=True)
        local_file.write_bytes(body)
        source = {
            "source_id": "fixture-source",
            "source_type": "gtfs_zip",
            "official_url": "https://yamaguchi-opendata.jp/fixture.zip",
            "local_path": "raw/baseline.bin",
            "baseline_sha256": hashlib.sha256(body).hexdigest(),
            "baseline_bytes": len(body),
            "baseline_acquired_at": "2026-08-10",
            "max_download_bytes": 1024,
        }
        manifest = {"schema_version": "WORK1-FRESHNESS-1", "expected_source_count": 1, "sources": [source]}
        return temporary, root, manifest, source

    def test_manifest_has_seven_unique_accepted_baselines(self):
        self.assertEqual(self.manifest["schema_version"], "WORK1-FRESHNESS-1")
        self.assertEqual(self.manifest["expected_source_count"], 7)
        self.assertEqual(len(self.manifest["sources"]), 7)
        self.assertEqual(len({item["source_id"] for item in self.manifest["sources"]}), 7)
        for item in self.manifest["sources"]:
            path = freshness.resolve_local_baseline(REPO_ROOT, item["local_path"])
            size, digest = freshness.sha256_file(path)
            self.assertEqual(size, item["baseline_bytes"], item["source_id"])
            self.assertEqual(digest, item["baseline_sha256"], item["source_id"])

    def test_manifest_urls_and_paths_obey_fixed_policy(self):
        for item in self.manifest["sources"]:
            self.assertEqual(freshness.validate_remote_url(item["official_url"]), item["official_url"])
            self.assertGreaterEqual(item["max_download_bytes"], item["baseline_bytes"])
            self.assertNotIn("..", Path(item["local_path"]).parts)
        with self.assertRaises(freshness.RemotePolicyError):
            freshness.validate_remote_url("http://wwwtb.mlit.go.jp/source.pdf")
        with self.assertRaises(freshness.RemotePolicyError):
            freshness.validate_remote_url("https://example.com/source.pdf")
        self.assertEqual(
            freshness.validate_remote_url("https://ajt-mobusta-gtfs.mcapps.jp/static/15/current_data.zip"),
            "https://ajt-mobusta-gtfs.mcapps.jp/static/15/current_data.zip",
        )
        with self.assertRaises(freshness.RemotePolicyError):
            freshness.validate_remote_url("https://wwwtb.mlit.go.jp/source.pdf?token=not-allowed")
        with self.assertRaises(freshness.RemotePolicyError):
            freshness.validate_remote_url("https://wwwtb.mlit.go.jp:invalid/source.pdf")

    def test_unchanged_is_exit_zero(self):
        temporary, root, manifest, source = self.make_fixture()
        self.addCleanup(temporary.cleanup)
        body = (root / source["local_path"]).read_bytes()
        report = freshness.check_sources(
            manifest,
            repo_root=root,
            opener=lambda url, timeout: FakeResponse(body, url, len(body)),
            checked_at="2026-08-11T00:00:00Z",
        )
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual(report["sources"][0]["status"], "unchanged")

    def test_changed_is_reported_without_body(self):
        temporary, root, manifest, _ = self.make_fixture()
        self.addCleanup(temporary.cleanup)
        changed = b"new unaccepted source bytes"
        report = freshness.check_sources(
            manifest,
            repo_root=root,
            opener=lambda url, timeout: FakeResponse(changed, url),
            checked_at="2026-08-11T00:00:00Z",
        )
        self.assertEqual(report["exit_code"], 1)
        self.assertEqual(report["sources"][0]["status"], "changed")
        self.assertEqual(report["sources"][0]["fetched_sha256"], hashlib.sha256(changed).hexdigest())
        self.assertNotIn(changed.decode(), json.dumps(report))

    def test_unavailable_is_exit_two(self):
        temporary, root, manifest, _ = self.make_fixture()
        self.addCleanup(temporary.cleanup)

        def unavailable(url, timeout):
            raise urllib.error.URLError("offline")

        report = freshness.check_sources(manifest, repo_root=root, opener=unavailable)
        self.assertEqual(report["exit_code"], 2)
        self.assertEqual(report["sources"][0]["status"], "unavailable")
        self.assertEqual(report["sources"][0]["error_category"], "network_error")
        self.assertNotIn("offline", json.dumps(report))
        report = freshness.check_sources(
            manifest,
            repo_root=root,
            opener=lambda url, timeout: (_ for _ in ()).throw(http.client.HTTPException("truncated")),
        )
        self.assertEqual(report["sources"][0]["error_category"], "http_protocol_error")
        self.assertNotIn("truncated", json.dumps(report))

    def test_oversize_content_length_is_exit_two_without_reading(self):
        temporary, root, manifest, source = self.make_fixture()
        self.addCleanup(temporary.cleanup)
        response = FakeResponse(b"not read", source["official_url"], content_length=2048)
        report = freshness.check_sources(manifest, repo_root=root, opener=lambda url, timeout: response)
        result = report["sources"][0]
        self.assertEqual((report["exit_code"], result["status"]), (2, "oversize"))
        self.assertEqual(result["error_category"], "content_length_exceeds_limit")
        self.assertEqual(response.read(), b"not read")

    def test_oversize_stream_is_stopped_at_limit_plus_one(self):
        temporary, root, manifest, source = self.make_fixture()
        self.addCleanup(temporary.cleanup)
        manifest["sources"][0]["max_download_bytes"] = len(b"accepted baseline")
        body = b"x" * (manifest["sources"][0]["max_download_bytes"] + 100)
        report = freshness.check_sources(
            manifest,
            repo_root=root,
            opener=lambda url, timeout: FakeResponse(body, source["official_url"]),
        )
        result = report["sources"][0]
        self.assertEqual(result["status"], "oversize")
        self.assertEqual(result["fetched_bytes"], manifest["sources"][0]["max_download_bytes"] + 1)

    def test_invalid_local_size_blocks_network_and_is_exit_three(self):
        temporary, root, manifest, _ = self.make_fixture()
        self.addCleanup(temporary.cleanup)
        manifest["sources"][0]["baseline_bytes"] += 1
        calls = []
        report = freshness.check_sources(manifest, repo_root=root, opener=lambda url, timeout: calls.append(url))
        self.assertEqual(report["exit_code"], 3)
        self.assertEqual(report["sources"][0]["status"], "invalid_baseline")
        self.assertEqual(report["sources"][0]["error_category"], "baseline_size_mismatch")
        self.assertEqual(calls, [])

    def test_invalid_local_hash_blocks_network(self):
        temporary, root, manifest, _ = self.make_fixture()
        self.addCleanup(temporary.cleanup)
        manifest["sources"][0]["baseline_sha256"] = "0" * 64
        report = freshness.check_sources(manifest, repo_root=root, opener=lambda url, timeout: self.fail("network called"))
        self.assertEqual(report["sources"][0]["error_category"], "baseline_sha256_mismatch")

    def test_duplicate_id_and_traversal_are_invalid_baselines(self):
        temporary, root, manifest, source = self.make_fixture()
        self.addCleanup(temporary.cleanup)
        duplicate = copy.deepcopy(source)
        manifest["sources"].append(duplicate)
        manifest["expected_source_count"] = 2
        report = freshness.check_sources(manifest, repo_root=root, opener=lambda url, timeout: self.fail("network called"))
        self.assertEqual([item["error_category"] for item in report["sources"]], ["duplicate_source_id"] * 2)
        manifest = {"schema_version": "WORK1-FRESHNESS-1", "expected_source_count": 1, "sources": [source | {"local_path": "raw/../outside"}]}
        report = freshness.check_sources(manifest, repo_root=root, opener=lambda url, timeout: self.fail("network called"))
        self.assertEqual(report["sources"][0]["error_category"], "local_path_traversal")
        invalid_type = copy.deepcopy(source)
        invalid_type["source_id"] = ["not", "hashable"]
        invalid_type["source_type"] = ["gtfs_zip"]
        manifest = {"schema_version": "WORK1-FRESHNESS-1", "expected_source_count": 1, "sources": [invalid_type]}
        report = freshness.check_sources(manifest, repo_root=root, opener=lambda url, timeout: self.fail("network called"))
        self.assertEqual(report["sources"][0]["error_category"], "invalid_source_id")
        invalid_date = copy.deepcopy(source)
        invalid_date["baseline_acquired_at"] = "2026-99-99"
        manifest = {"schema_version": "WORK1-FRESHNESS-1", "expected_source_count": 1, "sources": [invalid_date]}
        report = freshness.check_sources(manifest, repo_root=root, opener=lambda url, timeout: self.fail("network called"))
        self.assertEqual(report["sources"][0]["error_category"], "invalid_baseline_acquired_at")

    def test_redirect_target_policy_is_enforced(self):
        handler = freshness.RestrictedRedirectHandler()
        request = type("Request", (), {"full_url": "https://wwwtb.mlit.go.jp/source.pdf"})()
        with self.assertRaises(freshness.RemotePolicyError):
            handler.redirect_request(request, None, 302, "Found", {}, "https://example.com/replacement.pdf")
        with self.assertRaises(freshness.RemotePolicyError):
            handler.redirect_request(request, None, 302, "Found", {}, "http://wwwtb.mlit.go.jp/replacement.pdf")
        with self.assertRaises(freshness.RemotePolicyError):
            handler.redirect_request(request, None, 302, "Found", {}, "https://wwwtb.mlit.go.jp:invalid/replacement.pdf")

    def test_exit_code_priority_is_zero_one_two_three(self):
        for statuses, expected in (
            (["unchanged"], 0),
            (["unchanged", "changed"], 1),
            (["changed", "unavailable"], 2),
            (["oversize", "invalid_baseline"], 3),
        ):
            results = [{"status": status} for status in statuses]
            self.assertEqual(freshness.build_report(results, "2026-08-11T00:00:00Z")["exit_code"], expected)

    def test_checker_does_not_mutate_accepted_input_on_change_or_failure(self):
        for remote in (b"changed", None):
            temporary, root, manifest, source = self.make_fixture()
            self.addCleanup(temporary.cleanup)
            path = root / source["local_path"]
            before = path.read_bytes()
            if remote is None:
                def opener(url, timeout):
                    raise urllib.error.URLError("offline")
            else:
                opener = lambda url, timeout, body=remote: FakeResponse(body, url)
            freshness.check_sources(manifest, repo_root=root, opener=opener)
            self.assertEqual(path.read_bytes(), before)

    def test_protected_output_paths_are_refused(self):
        for relative in ("raw/result.json", "data/result.json", "docs/result.json"):
            with self.assertRaises(ValueError):
                freshness.ensure_output_path_safe(REPO_ROOT / relative)
        self.assertEqual(
            freshness.ensure_output_path_safe(REPO_ROOT / "evidence" / "result.json"),
            (REPO_ROOT / "evidence" / "result.json").resolve(),
        )

    def test_workflow_is_weekly_manual_read_only_and_non_mutating(self):
        text = (REPO_ROOT / ".github" / "workflows" / "source-freshness.yml").read_text(encoding="utf-8")
        for marker in ("schedule:", "cron:", "workflow_dispatch:", "contents: read", "upload-artifact@"):
            self.assertIn(marker, text)
        for banned in ("contents: write", "git commit", "git push", "issues: write", "pages: write", "deploy-pages"):
            self.assertNotIn(banned, text)

    def test_readme_and_status_distinguish_fixed_acceptance_from_latest_run(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        status = (REPO_ROOT / "docs" / "status.html").read_text(encoding="utf-8")
        actions_url = "https://github.com/yyy-yuichi/yamaguchi-yusho-data/actions/workflows/source-freshness.yml"
        for text in (readme, status):
            for marker in (
                "WORK1-FRESHNESS-1",
                "unchanged",
                "changed",
                "unavailable",
                "固定確認日",
                "最新状態",
                actions_url,
                "自動更新しません",
            ):
                self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
