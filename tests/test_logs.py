"""Offline tests: bounded log inspection and credential-safe packet design."""

import io
import unittest
from unittest.mock import patch
from urllib.request import Request

from smergeon.cli import collect, display
from smergeon.diagnosis import packet
from smergeon.github import GitHubClient, GitHubError
from smergeon.logs import scan_log


class FailedRun:
    repo = "owner/repo"

    def run(self, number):
        return {"id": number, "name": "CI", "status": "completed", "conclusion": "failure",
                "html_url": "https://example.invalid/ci"}

    def jobs(self, number):
        return {"total_count": 1, "jobs": [
            {"id": 42, "name": "Test job", "conclusion": "failure",
             "html_url": "https://example.invalid/job/42", "steps": [
                {"name": "Run tests", "conclusion": "failure"}]}]}

    def job_log(self, job_id, max_bytes):
        assert job_id == 42
        assert max_bytes == 4096
        return ("2026-10-27 INFO hello\n"
                "AssertionError: SECRET_DO_NOT_EXPOSE ghp_anothersecret\n"
                "FAILED (failures=1)\n", True)


class LogLabTests(unittest.TestCase):
    def test_signatures_are_allowlisted_not_log_text(self):
        source = ("Authorization: Bearer super_secret_value\n"
                  "ModuleNotFoundError: No module named SECRET_MODULE_NAME\n"
                  "AssertionError: SECRET_TOKEN\n")
        signals = scan_log(source)
        flattened = str(signals)
        self.assertIn("missing Python module", flattened)
        self.assertIn("assertion failure", flattened)
        self.assertNotIn("SECRET_", flattened)
        self.assertNotIn("super_secret_value", flattened)

    def test_duplicate_signatures_and_budget(self):
        source = ("AssertionError: first\n" * 20) + "error TS2304: missing\n"
        signals = scan_log(source, maximum_signals=2)
        self.assertEqual(len(signals), 2)
        self.assertEqual(signals[0]["line"], 1)
        self.assertEqual(signals[1]["line"], 21)

    def test_log_intake_emits_safe_evidence_and_truncation_note(self):
        source = FailedRun()
        result = collect(source, run=12, with_logs=True, max_log_kib=4)
        self.assertEqual(result["status"], "code_blue")
        self.assertTrue(any(item.get("source") == "bounded_log_signature"
                            for item in result["findings"]))
        self.assertTrue(any("byte budget" in note for note in result["warnings"]))
        text = display(result)
        self.assertNotIn("SECRET_DO_NOT_EXPOSE", text)
        self.assertNotIn("ghp_anothersecret", text)

    def test_no_log_download_without_opt_in(self):
        source = FailedRun()
        result = collect(source, run=12)
        self.assertEqual(result["status"], "code_blue")
        self.assertFalse(any(item.get("source") == "bounded_log_signature"
                             for item in result["findings"]))

    def test_bounded_download_and_https_redirect_security(self):
        class Opener:
            def open(self, req, timeout):
                return io.BytesIO(b"x" * 1200)

        with patch("urllib.request.build_opener", return_value=Opener()) as factory:
            client = GitHubClient("owner/repo", token="SENSITIVE_TEST_TOKEN")
            body, was_cut = client.job_log(11, max_bytes=1024)
        self.assertTrue(was_cut)
        self.assertEqual(len(body), 1024)

        handler_cls = factory.call_args.args[0]
        handler = handler_cls()
        request = Request("https://api.github.com/repos/owner/repo/actions/jobs/11/logs",
                          headers={"Authorization": "Bearer SENSITIVE_TEST_TOKEN"})
        redirect = handler.redirect_request(request, None, 302, "Found", {},
                                            "https://downloads.example.org/job.txt")
        self.assertFalse(redirect.has_header("Authorization"))
        with self.assertRaises(GitHubError):
            handler.redirect_request(request, None, 302, "Found", {},
                                     "http://downloads.example.org/job.txt")

    def test_job_log_rejects_bad_size(self):
        client = GitHubClient("owner/repo")
        with self.assertRaises(ValueError):
            client.job_log(5, 1025 * 1024)


if __name__ == "__main__":
    unittest.main()
