"""Contract test for the external exact-release attestation."""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import unittest
import urllib.parse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import build_release_attestation as attestation  # noqa: E402


class ReleaseAttestationContractTest(unittest.TestCase):
    def test_exact_release_attestation_contract_and_fail_closed_behavior(self):
        target_sha = "a" * 40

        def local_pages_fetcher(url: str):
            parsed = urllib.parse.urlsplit(url)
            prefix = "/yamaguchi-yusho-data/"
            self.assertTrue(parsed.path.startswith(prefix))
            public_path = parsed.path[len(prefix) :]
            local = dict(attestation.PUBLIC_ASSETS)[public_path]
            return 200, url, (REPO_ROOT / local).read_bytes()

        record = attestation.build_attestation(
            repo_root=REPO_ROOT,
            target_sha=target_sha,
            pages_run_id=101,
            pages_run_url="https://github.com/yyy-yuichi/yamaguchi-yusho-data/actions/runs/101",
            pages_reported_head_sha=target_sha,
            attestation_run_id=202,
            attestation_run_attempt=1,
            attestation_run_url="https://github.com/yyy-yuichi/yamaguchi-yusho-data/actions/runs/202",
            tests_discovered=151,
            tests_passed=True,
            scope_guard_passed=True,
            fetcher=local_pages_fetcher,
            checked_at="2026-08-13T00:00:00+00:00",
            actual_head=target_sha,
        )
        self.assertEqual("GO", record["decision"])
        self.assertEqual(target_sha, record["subject"]["commit_sha"])
        self.assertEqual(202, record["workflow"]["run_id"])
        self.assertEqual(101, record["upstream_pages"]["run_id"])
        self.assertTrue(record["upstream_pages"]["reported_head_sha_matches_subject"])
        self.assertEqual(
            "pages_reported_sha_and_public_assets_match_subject",
            record["upstream_pages"]["subject_linkage"],
        )
        self.assertEqual(151, record["verification"]["tests"]["passed"])
        self.assertEqual(7, record["verification"]["accepted_source_count"])
        self.assertTrue(
            all(item["baseline_match"] for item in record["verification"]["accepted_sources"])
        )
        self.assertTrue(
            all(item["commit_bytes_match"] for item in record["verification"]["public_assets"])
        )
        self.assertEqual(4, len(record["verification"]["public_assets"]))
        self.assertEqual(
            {"実用度": 3.5, "完成度": 4.0, "挑戦度": 3.0},
            record["verification"]["scorecard"]["scores"],
        )
        self.assertEqual(70.0, record["verification"]["scorecard"]["overall_comparison_index"])
        observations = record["scope"]["workflow_observations"]
        declarations = record["scope"]["declared_boundaries"]
        self.assertEqual(4, len(observations["requested_public_assets"]))
        self.assertTrue(all(item["method"] == "GET" for item in observations["requested_public_assets"]))
        self.assertEqual(
            "stage_execution_declaration_not_external_measurement",
            declarations["evidence_type"],
        )
        self.assertEqual(0, declarations["other_work_inputs"])

        snapshot_path = (
            REPO_ROOT
            / "docs"
            / "data"
            / "release-attestation-ed1f0b4997acd19016da45e21c88821ef57bb365.json"
        )
        exact_b64_path = Path(str(snapshot_path) + ".b64")
        snapshot = snapshot_path.read_bytes()
        exact_source = base64.b64decode(exact_b64_path.read_text(encoding="ascii").strip())
        audit = json.loads(
            (REPO_ROOT / "docs" / "data" / "work1_release_attestation_audit.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(7257, len(snapshot))
        self.assertEqual(
            "c430b4d5b8721cd84e20339c27a1fc31d3cb6597bc47d2f6a78b438039e62eb2",
            hashlib.sha256(snapshot).hexdigest(),
        )
        self.assertEqual(7446, len(exact_source))
        self.assertEqual(
            "6b47326a3066e7cf08231e901f2470d91086d34a7a2025baf47f00f09abf85ab",
            hashlib.sha256(exact_source).hexdigest(),
        )
        self.assertEqual(json.loads(snapshot), json.loads(exact_source))
        self.assertEqual("GO", audit["decision"])
        self.assertEqual(3, audit["severity"]["P2"])
        self.assertTrue(audit["hardening_resolution"]["durable_snapshot"])

        with self.subTest("Pages-reported SHA mismatch fails closed"):
            stale_pages = attestation.build_attestation(
                repo_root=REPO_ROOT,
                target_sha=target_sha,
                pages_run_id=101,
                pages_run_url="https://github.com/yyy-yuichi/yamaguchi-yusho-data/actions/runs/101",
                pages_reported_head_sha="b" * 40,
                attestation_run_id=202,
                attestation_run_attempt=1,
                attestation_run_url="https://github.com/yyy-yuichi/yamaguchi-yusho-data/actions/runs/202",
                tests_discovered=151,
                tests_passed=True,
                scope_guard_passed=True,
                fetcher=local_pages_fetcher,
                actual_head=target_sha,
            )
            self.assertEqual("NO_GO", stale_pages["decision"])
            self.assertIn("pages_reported_head_sha_mismatch", stale_pages["errors"])

        with self.subTest("public mismatch fails closed"):
            def changed_fetcher(url: str):
                status, final_url, payload = local_pages_fetcher(url)
                if urllib.parse.urlsplit(url).path.endswith("status.html"):
                    payload += b"changed"
                return status, final_url, payload

            changed = attestation.build_attestation(
                repo_root=REPO_ROOT,
                target_sha=target_sha,
                pages_run_id=101,
                pages_run_url="https://github.com/yyy-yuichi/yamaguchi-yusho-data/actions/runs/101",
                pages_reported_head_sha=target_sha,
                attestation_run_id=202,
                attestation_run_attempt=1,
                attestation_run_url="https://github.com/yyy-yuichi/yamaguchi-yusho-data/actions/runs/202",
                tests_discovered=151,
                tests_passed=True,
                scope_guard_passed=True,
                fetcher=changed_fetcher,
                actual_head=target_sha,
            )
            self.assertEqual("NO_GO", changed["decision"])
            self.assertIn("public_asset_mismatch:status.html", changed["errors"])

        workflow = (REPO_ROOT / ".github" / "workflows" / "release-attestation.yml").read_text(
            encoding="utf-8"
        )
        for marker in (
            "workflow_run:",
            "pages-build-deployment",
            "github.event.workflow_run.head_sha",
            "runs-on: windows-latest",
            "PYTHONUTF8: \"1\"",
            "core.autocrlf false",
            "pip install --disable-pip-version-check -r requirements.txt",
            "ref: refs/heads/main",
            "python -B -m unittest discover -s tests -v",
            "--scope-guard-passed",
            "actions/upload-artifact@v7",
            "retention-days: 90",
        ):
            self.assertIn(marker, workflow)


if __name__ == "__main__":
    unittest.main()
