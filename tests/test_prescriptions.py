"""Repair prescriptions must stay deterministic, low-trust and read-only."""

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from smergeon.cli import collect, display, main
from smergeon.prescriptions import attach_prescriptions, prescribe


def base_packet(findings, status="code_blue"):
    return {
        "schema": "smergeon.triage.v0.1",
        "repository": "owner/repo",
        "subject": {"kind": "workflow_run", "number": 42},
        "status": status,
        "findings": findings,
        "warnings": [],
        "safety": {"read_only": True, "changes_written": 0, "merges_performed": 0},
    }


def evidence(category="tests", source=None, summary="Run test suite", line=None):
    result = {
        "category": category,
        "evidence": summary,
        "url": "https://github.com/owner/repo/actions/runs/42",
        "run_id": 42,
        "job": "test",
        "step": "Execute suite",
    }
    if source:
        result["source"] = source
        result["line"] = line
    return result


class FakeFailures:
    repo = "owner/repo"

    def run(self, number):
        return {"id": number, "name": "CI", "status": "completed",
                "conclusion": "failure", "html_url": "https://github.com/owner/repo/actions/runs/42"}

    def jobs(self, number):
        return {"total_count": 1, "jobs": [
            {"id": 99, "name": "Unit test", "conclusion": "failure",
             "html_url": "https://github.com/owner/repo/actions/runs/42/job/99",
             "steps": [{"name": "Run unittest", "conclusion": "failure"}]}]}

    def job_log(self, job_id, max_bytes):
        return ("AssertionError: DONT_ECHO_ME\n", False)


class PrescriptionTests(unittest.TestCase):
    def test_metadata_only_has_low_confidence(self):
        result = prescribe(base_packet([evidence()]))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["confidence"], "low")
        self.assertEqual(result[0]["category"], "tests")
        self.assertFalse(result[0]["patch_created"])
        self.assertTrue(result[0]["approval_required"])

    def test_log_signature_preferred_and_medium(self):
        metadata = evidence("tests", summary="CI tests failed")
        signature = evidence("tests", "bounded_log_signature",
                             "Log signature: assertion failure (line 17)", 17)
        result = prescribe(base_packet([metadata, signature]))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["confidence"], "medium")
        self.assertEqual(result[0]["evidence"]["line"], 17)
        self.assertIn("actual and expected", result[0]["extra_inspection"])

    def test_no_arbitrary_log_or_check_text_in_prescription(self):
        item = evidence("dependencies", summary="Bearer SECRET_DO_NOT_COPY")
        item["job"] = "SECRET_JOB_NAME"
        result = attach_prescriptions(base_packet([item]))
        rendered = json.dumps(result["prescriptions"])
        self.assertNotIn("SECRET_DO_NOT_COPY", rendered)
        self.assertNotIn("SECRET_JOB_NAME", rendered)
        self.assertEqual(result["prescription_policy"]["commands_executed"], 0)

    def test_unknown_and_clear_do_not_invent_cures(self):
        self.assertEqual(prescribe(base_packet([evidence("unknown")])), [])
        self.assertEqual(prescribe(base_packet([evidence()], "clear")), [])

    def test_prescription_limit_and_category_deduplication(self):
        categories = ["tests", "tests", "build", "lint", "permissions", "timeout",
                      "dependencies", "conflict"]
        outputs = prescribe(base_packet([evidence(category) for category in categories]), limit=3)
        self.assertEqual(len(outputs), 3)
        self.assertEqual(len({o["category"] for o in outputs}), 3)
        with self.assertRaises(ValueError):
            prescribe(base_packet([]), limit=0)

    def test_no_flag_does_not_add_prescriptions(self):
        packet = collect(FakeFailures(), run=42)
        self.assertNotIn("prescriptions", packet)

    def test_flag_adds_prescriptions_without_log_download(self):
        packet = collect(FakeFailures(), run=42, prescribe_fixes=True)
        self.assertTrue(packet["prescriptions"])
        self.assertEqual(packet["prescriptions"][0]["confidence"], "low")
        self.assertIn("REPAIR PRESCRIPTIONS", display(packet))

    def test_flag_with_logs_promotes_confidence(self):
        packet = collect(FakeFailures(), run=42, with_logs=True, prescribe_fixes=True)
        self.assertEqual(packet["prescriptions"][0]["confidence"], "medium")
        self.assertNotIn("DONT_ECHO_ME", json.dumps(packet["prescriptions"]))

    def test_json_cli_mode(self):
        stdout = io.StringIO()
        with patch("smergeon.cli.GitHubClient", return_value=FakeFailures()):
            with contextlib.redirect_stdout(stdout):
                code = main(["--repo", "owner/repo", "--run", "42", "--prescribe", "--json"])
        self.assertEqual(code, 1)
        result = json.loads(stdout.getvalue())
        self.assertTrue(result["prescriptions"])
        self.assertEqual(result["prescription_policy"]["merges_performed"], 0)


if __name__ == "__main__":
    unittest.main()
