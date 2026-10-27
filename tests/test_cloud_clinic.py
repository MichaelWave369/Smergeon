"""Offline Cloud Clinic tests: sanitized artifacts and GitHub-only workflow."""

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from smergeon.cloud_clinic import (
    CloudClinicError, inspect_public_pr, main, summary_markdown, write_report,
)


HEAD = "a" * 40


class FakeGitHub:
    repo = "owner/repo"

    def __init__(self, *, private=False, status="failure", checks=True, state="open"):
        self.private = private
        self.status = status
        self.check_enabled = checks
        self.state = state
        self.calls = []

    def pr(self, number):
        self.calls.append("pr")
        return {
            "state": self.state,
            "head": {"sha": HEAD},
            "base": {"repo": {"private": self.private, "full_name": self.repo}},
            "html_url": "https://github.com/owner/repo/pull/7",
        }

    def runs(self, sha):
        self.calls.append("runs")
        return {
            "total_count": 1,
            "workflow_runs": [
                {"id": 123, "name": "SECRET WORKFLOW TEXT",
                 "conclusion": self.status, "status": "completed",
                 "html_url": "https://github.com/owner/repo/actions/runs/123"},
            ],
        }

    def checks(self, sha):
        self.calls.append("checks")
        return {"total_count": 1 if self.check_enabled else 0,
                "check_runs": ([{
                    "name": "SECRET_FROM_CHECK_NAME",
                    "conclusion": "failure", "status": "completed",
                    "output": {"summary": "SECRET_FROM_CHECK_SUMMARY ghp_DO_NOT_PRINT"},
                }] if self.check_enabled else [])}

    def jobs(self, run_id):
        self.calls.append("jobs")
        return {"total_count": 1, "jobs": [
            {"name": "Test suite", "conclusion": "failure",
             "html_url": "https://github.com/owner/repo/actions/runs/123/job/9",
             "steps": [{"name": "Run unittest", "conclusion": "failure"}]},
        ]}

    def job_log(self, job_id, budget):
        raise AssertionError("Cloud Clinic must never fetch raw logs.")

    def post(self, *args):
        raise AssertionError("Cloud Clinic cannot modify GitHub.")


class CloudClinicTests(unittest.TestCase):
    def test_code_blue_is_a_report_not_a_clinic_failure(self):
        report = inspect_public_pr("owner/repo", 7, FakeGitHub())
        self.assertEqual(report["observed"]["status"], "CODE_BLUE")
        self.assertGreater(report["observed"]["signal_count"], 0)
        self.assertFalse(report["authority"]["merge_approval"])
        self.assertEqual(report["authority"]["merges_performed"], 0)
        self.assertTrue(report["authority"]["github_read_only"])

    def test_no_arbitrary_checks_or_secrets_in_report(self):
        report = inspect_public_pr("owner/repo", 7, FakeGitHub())
        output = json.dumps(report) + summary_markdown(report)
        for secret in ("SECRET_FROM_CHECK_NAME", "SECRET_FROM_CHECK_SUMMARY",
                       "ghp_DO_NOT_PRINT", "SECRET WORKFLOW TEXT"):
            self.assertNotIn(secret, output)
        self.assertIn("tests", report["observed"]["categories"])

    def test_private_repository_is_rejected_before_diagnosis(self):
        client = FakeGitHub(private=True)
        with self.assertRaises(CloudClinicError):
            inspect_public_pr("owner/repo", 7, client)
        self.assertEqual(client.calls, ["pr"])

    def test_closed_pr_is_rejected(self):
        with self.assertRaises(CloudClinicError):
            inspect_public_pr("owner/repo", 7, FakeGitHub(state="closed"))

    def test_invalid_repository_or_number_rejected(self):
        for repo in ("bad", "../escape", "owner/.git", "owner/.."):
            with self.subTest(repo=repo), self.assertRaises(CloudClinicError):
                inspect_public_pr(repo, 7, FakeGitHub())
        for number in (0, -1, True):
            with self.assertRaises(CloudClinicError):
                inspect_public_pr("owner/repo", number, FakeGitHub())

    def test_clear_is_not_merge_authorization(self):
        report = inspect_public_pr("owner/repo", 7, FakeGitHub(status="success", checks=False))
        self.assertEqual(report["observed"]["status"], "CLEAR")
        self.assertEqual(report["observed"]["signal_count"], 0)
        self.assertFalse(report["authority"]["merge_approval"])
        self.assertIn("not the GitHub required-check gate", " ".join(report["limitations"]))

    def test_artifacts_created_exclusively_and_bounded(self):
        report = inspect_public_pr("owner/repo", 7, FakeGitHub())
        with tempfile.TemporaryDirectory() as root:
            output = write_report(report, root)
            self.assertEqual(output["status"], "CODE_BLUE")
            self.assertEqual(json.loads(Path(root, "triage.json").read_text()), report)
            self.assertIn("metadata", Path(root, "SUMMARY.md").read_text().lower())
            with self.assertRaises(FileExistsError):
                write_report(report, root)

    def test_github_step_summary_appended_without_untrusted_text(self):
        report = inspect_public_pr("owner/repo", 7, FakeGitHub())
        with tempfile.TemporaryDirectory() as root:
            summary = Path(root, "step-summary.md")
            summary.write_text("EXISTING STEP NOTE\n")
            write_report(report, str(Path(root, "out")), str(summary))
            text = summary.read_text()
            self.assertIn("EXISTING STEP NOTE", text)
            self.assertIn("Smergeon Cloud Clinic", text)
            self.assertNotIn("SECRET_FROM_CHECK_SUMMARY", text)

    def test_cli_success_even_when_target_checks_fail(self):
        with tempfile.TemporaryDirectory() as root:
            stdout = io.StringIO()
            with patch("smergeon.cloud_clinic.GitHubClient", return_value=FakeGitHub()), \
                    patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""}):
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(["--repo", "owner/repo", "--pr", "7",
                                      "--out-dir", root])
            self.assertEqual(exit_code, 0)
            self.assertIn("CODE_BLUE", stdout.getvalue())
            self.assertTrue(Path(root, "triage.json").exists())

    def test_cli_private_target_fails_without_artifact(self):
        with tempfile.TemporaryDirectory() as root:
            stderr = io.StringIO()
            with patch("smergeon.cloud_clinic.GitHubClient",
                       return_value=FakeGitHub(private=True)):
                with contextlib.redirect_stderr(stderr):
                    code = main(["--repo", "owner/repo", "--pr", "7",
                                 "--out-dir", root])
            self.assertEqual(code, 2)
            self.assertFalse(Path(root, "triage.json").exists())
            self.assertNotIn("token", stderr.getvalue().lower())

    def test_workflow_is_manual_only_and_never_checks_out_target(self):
        workflow = Path(__file__).resolve().parent.parent / ".github/workflows/cloud-clinic.yml"
        source = workflow.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("pull_request:\n", source)
        self.assertNotIn("contents: write", source)
        self.assertNotIn("pull-requests: write", source)
        self.assertNotIn("write-draft", source)
        self.assertNotIn("with-logs", source)
        self.assertIn("actions/upload-artifact@v4", source)


if __name__ == "__main__":
    unittest.main()
