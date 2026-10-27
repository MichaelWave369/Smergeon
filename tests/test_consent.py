"""Surgical consent: plans are bound to exact PR commits and never authorize writes."""

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from smergeon.cli import collect, main
from smergeon.consent import PlanError, make_plan, verify_plan
from smergeon.prescriptions import attach_prescriptions


SHA = "a" * 40
NEW_SHA = "b" * 40
REPO = "owner/repo"


class FakeFailureClient:
    repo = REPO

    def pr(self, number):
        return {"head": {"sha": SHA},
                "html_url": "https://github.com/owner/repo/pull/" + str(number)}

    def runs(self, sha):
        assert sha == SHA
        return {"total_count": 1, "workflow_runs": [
            {"id": 44, "name": "CI", "status": "completed", "conclusion": "failure",
             "html_url": "https://github.com/owner/repo/actions/runs/44"}]}

    def checks(self, sha):
        return {"total_count": 0, "check_runs": []}

    def jobs(self, run_id):
        return {"total_count": 1, "jobs": [
            {"id": 90, "name": "Tests", "conclusion": "failure",
             "html_url": "https://github.com/owner/repo/actions/runs/44/job/90",
             "steps": [{"name": "Run unittest", "conclusion": "failure"}]}]}


def packet():
    result = collect(FakeFailureClient(), pr=7, prescribe_fixes=True)
    assert result["status"] == "code_blue"
    return result


class ConsentTests(unittest.TestCase):
    def test_make_plan_deterministic_and_bound(self):
        first, second = make_plan(packet()), make_plan(packet())
        self.assertEqual(first, second)
        self.assertEqual(first["binding"]["head_sha"], SHA)
        self.assertEqual(first["binding"]["pull_request"], 7)
        self.assertEqual(len(first["plan_fingerprint"]), 64)
        self.assertTrue(first["authority"]["human_approval_required"])
        self.assertFalse(first["authority"]["github_writes_enabled"])
        self.assertEqual(first["authority"]["merges_performed"], 0)
        self.assertTrue(verify_plan(first, REPO, 7, SHA, first["plan_fingerprint"]))

    def test_stale_head_and_wrong_target_fail_closed(self):
        plan = make_plan(packet())
        digest = plan["plan_fingerprint"]
        self.assertFalse(verify_plan(plan, REPO, 7, NEW_SHA, digest))
        self.assertFalse(verify_plan(plan, "someone/else", 7, SHA, digest))
        self.assertFalse(verify_plan(plan, REPO, 8, SHA, digest))
        self.assertFalse(verify_plan(plan, REPO, 7, SHA, "0" * 64))

    def test_modified_recipe_breaks_fingerprint(self):
        plan = make_plan(packet())
        old = plan["plan_fingerprint"]
        plan["binding"]["recipes"][0]["confidence"] = "medium"
        self.assertFalse(verify_plan(plan, REPO, 7, SHA, old))

    def test_arbitrary_names_logs_never_enter_binding(self):
        p = packet()
        p["findings"][0]["evidence"] = "TOKEN_secret_DONT_COPY"
        p["findings"][0]["job"] = "UNTRUSTED_JOB_NAME"
        p["warnings"].append("UNTRUSTED_LOG_TEXT")
        plan = make_plan(p)
        encoded = json.dumps(plan)
        for forbidden in ("TOKEN_secret_DONT_COPY", "UNTRUSTED_JOB_NAME",
                          "UNTRUSTED_LOG_TEXT"):
            self.assertNotIn(forbidden, encoded)

    def test_no_recipe_cannot_generate_plan(self):
        p = packet()
        p["prescriptions"] = []
        with self.assertRaises(PlanError):
            make_plan(p)

    def test_run_and_clear_not_eligible(self):
        p = packet()
        p["subject"]["kind"] = "workflow_run"
        with self.assertRaises(PlanError):
            make_plan(p)
        p = packet()
        p["status"] = "clear"
        with self.assertRaises(PlanError):
            make_plan(p)

    def test_requires_full_sha_and_read_only_record(self):
        p = packet()
        p["subject"]["head_sha"] = "abc"
        with self.assertRaises(PlanError):
            make_plan(p)
        p = packet()
        p["safety"]["changes_written"] = 1
        with self.assertRaises(PlanError):
            make_plan(p)

    def test_tampered_prescription_rejected(self):
        p = packet()
        p["prescriptions"][0]["id"] = "smergeon.rx.other.v0.3"
        with self.assertRaises(PlanError):
            make_plan(p)

    def test_cli_remains_opt_in(self):
        result = collect(FakeFailureClient(), pr=7)
        self.assertNotIn("prescriptions", result)
        self.assertNotIn("surgery_plan", result)

    def test_cli_json_plan_and_fresh_id_match(self):
        output = io.StringIO()
        with patch("smergeon.cli.GitHubClient", return_value=FakeFailureClient()):
            with contextlib.redirect_stdout(output):
                exit_code = main(["--repo", REPO, "--pr", "7",
                                  "--surgery-plan", "--json"])
        self.assertEqual(exit_code, 1)  # observed CODE BLUE, not success
        value = json.loads(output.getvalue())
        self.assertEqual(value["surgery_plan"]["binding"]["head_sha"], SHA)
        self.assertEqual(value["surgery_plan"]["status"], "review_required")
        digest = value["surgery_plan"]["plan_fingerprint"]
        output = io.StringIO()
        with patch("smergeon.cli.GitHubClient", return_value=FakeFailureClient()):
            with contextlib.redirect_stdout(output):
                exit_code = main(["--repo", REPO, "--pr", "7",
                                  "--surgery-plan", "--confirm-plan-id", digest,
                                  "--json"])
        self.assertEqual(exit_code, 1)
        self.assertTrue(json.loads(output.getvalue())["fingerprint_matches"])

    def test_mismatch_rejected_in_cli(self):
        error = io.StringIO()
        with patch("smergeon.cli.GitHubClient", return_value=FakeFailureClient()):
            with contextlib.redirect_stderr(error):
                code = main(["--repo", REPO, "--pr", "7",
                             "--surgery-plan", "--confirm-plan-id", "0" * 64])
        self.assertEqual(code, 2)
        self.assertIn("does not match", error.getvalue())


if __name__ == "__main__":
    unittest.main()
