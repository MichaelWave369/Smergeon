import contextlib
import io
import json
import unittest
from unittest.mock import patch

from smergeon.cli import collect, display, main
from smergeon.diagnosis import classify, packet
from smergeon.github import GitHubClient


class FakeClient:
    repo = "owner/repo"

    def pr(self, number):
        return {"head": {"sha": "abc"}, "html_url": "https://example.invalid/pr"}

    def runs(self, sha):
        assert sha == "abc"
        return {"total_count": 1, "workflow_runs": [
            {"id": 11, "conclusion": "success", "status": "completed"}]}

    def checks(self, sha):
        return {"total_count": 0, "check_runs": []}

    def jobs(self, run):
        raise AssertionError("Passing run should not fetch jobs")


class SmergeonTests(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(classify("npm", "Cannot find module")[0], "dependencies")
        self.assertEqual(classify("CI", "Resource not accessible by integration")[0], "permissions")
        self.assertEqual(classify("unknown")[0], "unknown")

    def test_failed_step(self):
        runs = [{"id": 33, "name": "CI", "conclusion": "failure", "status": "completed"}]
        jobs = {"jobs": [{"name": "Tests", "conclusion": "failure", "steps": [
            {"name": "Run unittest", "conclusion": "failure"}]}]}
        result = packet("a/b", {}, runs, lambda _: jobs)
        self.assertEqual(result["status"], "code_blue")
        self.assertEqual(result["findings"][0]["category"], "tests")
        self.assertEqual(result["safety"]["changes_written"], 0)

    def test_failed_check(self):
        check = {"name": "Lint", "conclusion": "failure", "status": "completed",
                 "output": {"summary": "x" * 500}}
        result = packet("a/b", {}, [], lambda _: {}, [check])
        self.assertEqual(result["status"], "code_blue")
        self.assertEqual(len(result["findings"][0]["evidence"]), 200)

    def test_pending_clear_unknown(self):
        self.assertEqual(packet("a/b", {}, [], lambda _: {})["status"], "unknown")
        self.assertEqual(packet("a/b", {}, [{"status": "in_progress"}],
                                lambda _: {})["status"], "recovery")
        self.assertEqual(packet("a/b", {}, [{"status": "completed",
                                             "conclusion": "success"}],
                                lambda _: {})["status"], "clear")

    def test_read_only_cli(self):
        result = collect(FakeClient(), pr=3)
        self.assertEqual(result["status"], "clear")
        self.assertIn("READ ONLY", display(result))
        out = io.StringIO()
        with patch("smergeon.cli.GitHubClient", return_value=FakeClient()):
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["--repo", "owner/repo", "--pr", "3",
                                       "--json"]), 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "clear")

    def test_invalid_repo(self):
        with self.assertRaises(ValueError):
            GitHubClient("../outside")


if __name__ == "__main__":
    unittest.main()
