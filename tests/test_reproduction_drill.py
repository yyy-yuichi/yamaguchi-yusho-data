import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from src import run_reproduction_drill as drill


REPO_ROOT = Path(__file__).resolve().parents[1]


class ReproductionDrillContractTest(unittest.TestCase):
    def test_target_and_builder_contract_is_complete(self):
        self.assertEqual(17, len(drill.GENERATED_TARGETS))
        self.assertEqual(17, len(set(drill.GENERATED_TARGETS)))
        self.assertEqual(5, len(drill.BUILDERS))
        self.assertIn(drill.RECOVERY_TARGET, drill.GENERATED_TARGETS)
        for path in (*drill.GENERATED_TARGETS, *drill.BUILDERS):
            self.assertTrue((REPO_ROOT / path).is_file(), path)

    def test_newline_normalization_changes_only_crlf(self):
        source = b"one\r\ntwo\nthree\r\n"
        self.assertEqual(b"one\ntwo\nthree\n", drill.normalized_text_bytes(source))

    def test_child_path_rejects_escape(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            with self.assertRaises(ValueError):
                drill.child_path(root, "../outside.txt")

    def test_archive_extraction_rejects_traversal(self):
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w") as archive:
            info = tarfile.TarInfo("../outside.txt")
            body = b"unsafe"
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "snapshot"
            with self.assertRaises(ValueError):
                drill.extract_archive(payload.getvalue(), destination)

    def test_seven_accepted_sources_match_manifest(self):
        checks = drill.accepted_source_checks(REPO_ROOT)
        self.assertEqual(7, len(checks))
        self.assertTrue(all(item["baseline_match"] for item in checks))

    def test_workflow_is_read_only_and_uploads_evidence(self):
        workflow = (REPO_ROOT / ".github/workflows/reproduction-drill.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("contents: read", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("src/run_reproduction_drill.py", workflow)
        self.assertIn("--run-tests", workflow)
        self.assertIn("actions/upload-artifact@v7", workflow)
        for forbidden in ("git push", "pull_request_target", "contents: write"):
            self.assertNotIn(forbidden, workflow)

    def test_readme_exposes_reproduction_instructions(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("独立再現・復旧ドリル", readme)
        self.assertIn("actions/workflows/reproduction-drill.yml", readme)
        self.assertIn("--subject-sha HEAD", readme)

    def test_markdown_summary_has_no_internal_score(self):
        report = {
            "decision": "GO",
            "subject": {"commit_sha": "a" * 40},
            "accepted_sources": {"matched": 7},
            "reconstruction": {"normalized_matched": 17, "byte_matched": 17},
            "recovery": {"success": True},
            "tests": {"requested": True, "passed": 188, "discovered": 188},
            "errors": [],
        }
        text = drill.render_markdown(report)
        self.assertIn("Decision: **GO**", text)
        self.assertNotIn("総合比較", text)
        self.assertNotIn("work1_award_scorecard", text)


if __name__ == "__main__":
    unittest.main()
