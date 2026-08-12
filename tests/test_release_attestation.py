"""Contract test for the external exact-release attestation."""
from __future__ import annotations

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
            pages_reported_head_sha="b" * 40,
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
        self.assertFalse(record["upstream_pages"]["reported_head_sha_matches_subject"])
        self.assertEqual(
            "public_assets_match_subject_checkout_bytes",
            record["upstream_pages"]["subject_linkage"],
        )
        self.assertEqual(151, record["verification"]["tests"]["passed"])
        self.assertEqual(6, record["verification"]["accepted_source_count"])
        self.assertTrue(
            all(item["baseline_match"] for item in record["verification"]["accepted_sources"])
        )
        self.assertTrue(
            all(item["commit_bytes_match"] for item in record["verification"]["public_assets"])
        )
        self.assertEqual(
            {"実用度": 3.5, "完成度": 4.0, "挑戦度": 3.0},
            record["verification"]["scorecard"]["scores"],
        )
        self.assertEqual(70.0, record["verification"]["scorecard"]["overall_comparison_index"])
        self.assertEqual(0, record["scope"]["other_work_inputs"])

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
                pages_reported_head_sha="b" * 40,
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
