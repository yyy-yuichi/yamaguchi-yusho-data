import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import check_work_scope


class WorkScopeTests(unittest.TestCase):
    def test_repository_scope_is_allowed(self):
        result = check_work_scope.validate_scope(str(REPO_ROOT), [])
        self.assertEqual("allowed", result["status"])
        self.assertEqual("WORK1", result["work_id"])
        self.assertEqual("yyy-yuichi/yamaguchi-yusho-data", result["repository_id"])

    def test_relative_path_inside_repository_is_allowed(self):
        resolved = check_work_scope.resolve_candidate(REPO_ROOT, "docs/status.html")
        self.assertEqual((REPO_ROOT / "docs" / "status.html").resolve(), resolved)

    def test_parent_traversal_is_denied(self):
        with self.assertRaisesRegex(check_work_scope.ScopeViolation, "scope_path_outside_repository"):
            check_work_scope.resolve_candidate(REPO_ROOT, "../outside-work/item.txt")

    def test_absolute_path_outside_repository_is_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(check_work_scope.ScopeViolation, "scope_path_outside_repository"):
                check_work_scope.resolve_candidate(REPO_ROOT, str(Path(directory) / "item.txt"))

    def test_wrong_repository_argument_is_denied_before_git(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(check_work_scope.ScopeViolation, "scope_repository_argument"):
                check_work_scope.validate_scope(directory, [])

    def test_cli_json_reports_only_work1(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "src" / "check_work_scope.py"),
                "--repo",
                str(REPO_ROOT),
                "--path",
                "README.md",
                "--json",
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        result = json.loads(completed.stdout)
        self.assertEqual("WORK1", result["work_id"])
        self.assertEqual(1, result["checked_path_count"])

    def test_cli_denies_parent_path_without_echoing_it(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "src" / "check_work_scope.py"),
                "--repo",
                str(REPO_ROOT),
                "--path",
                "../outside-work/item.txt",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(2, completed.returncode)
        self.assertEqual("WORK1_SCOPE_DENIED:scope_path_outside_repository", completed.stderr.strip())
        self.assertNotIn("outside-work", completed.stderr)

    def test_scope_config_is_deny_by_default(self):
        config = json.loads((REPO_ROOT / "work_scope.json").read_text(encoding="utf-8"))
        self.assertIs(True, config["deny_outside_repository"])
        self.assertEqual("no_read_no_write_no_execute", config["other_works_policy"])
        self.assertEqual(
            [
                "https://github.com/yyy-yuichi/yamaguchi-yusho-data.git",
                "https://github.com/yyy-yuichi/yamaguchi-yusho-data",
            ],
            config["expected_origin_urls"],
        )

    def test_agents_policy_forbids_cross_repository_access(self):
        text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Never discover, list, search, read, hash, copy, edit, execute in", text)
        self.assertIn("Do not enumerate parent or sibling directories", text)
        self.assertIn("python src/check_work_scope.py --repo .", text)

    def test_scope_workflow_is_read_only_and_runs_guard(self):
        text = (REPO_ROOT / ".github" / "workflows" / "work1-scope-lock.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("contents: read", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("git push", text)
        self.assertIn("python src/check_work_scope.py --repo .", text)
        self.assertIn("python -m unittest tests.test_work_scope -v", text)

    def test_public_status_shows_separate_lanes_and_human_gate(self):
        text = (REPO_ROOT / "docs" / "status.html").read_text(encoding="utf-8")
        self.assertIn('id="work-scope-title"', text)
        self.assertIn("作品②は別Chat・別リポジトリが所有", text)
        self.assertIn("比較・注力判断は人が行う", text)
        self.assertIn("blob/main/WORK_SCOPE.md", text)


if __name__ == "__main__":
    unittest.main()
