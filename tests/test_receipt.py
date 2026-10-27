"""Portable surgical handoff contracts: always unsigned, never a green CI signal."""

import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from smergeon.cli import main
from smergeon.consent import make_plan
from smergeon.operating_room import stage_repair
from smergeon.receipt import ReceiptError, export_receipt, make_receipt, verify_receipt

REPO = "owner/repo"
HEAD = "a" * 40
BEFORE = "b" * 40


def fixtures():
    packet = {
        "status": "code_blue",
        "repository": REPO,
        "subject": {"kind": "pull_request", "number": 7, "head_sha": HEAD},
        "safety": {"read_only": True, "changes_written": 0, "merges_performed": 0},
        "prescriptions": [{
            "id": "smergeon.rx.tests.v0.3", "category": "tests",
            "approval_required": True, "patch_created": False,
            "confidence": "low", "evidence": {"run_id": 24},
        }],
    }
    plan = make_plan(packet)
    request = {
        "path": "src/fix.py", "expected_blob_sha": BEFORE,
        "replacement_text": "# reviewed\nprint('fixed')\n",
    }
    operation = stage_repair(plan, request, REPO, 7, HEAD, plan["plan_fingerprint"])
    draft = {
        "status": "draft_created", "pr_number": 8,
        "url": "https://github.com/owner/repo/pull/8",
        "branch": operation["proposed_branch"],
        "merges_performed": 0, "source_branch_untouched": True,
    }
    return plan, request, operation, draft


class FailedClient:
    repo = REPO

    def pr(self, number):
        return {"head": {"sha": HEAD},
                "html_url": "https://github.com/owner/repo/pull/7"}

    def runs(self, sha):
        return {"total_count": 1, "workflow_runs": [{
            "id": 24, "name": "Tests", "status": "completed",
            "conclusion": "failure",
            "html_url": "https://github.com/owner/repo/actions/runs/24",
        }]}

    def checks(self, sha):
        return {"total_count": 0, "check_runs": []}

    def jobs(self, number):
        return {"total_count": 1, "jobs": [{
            "name": "test suite", "conclusion": "failure",
            "steps": [{"name": "Run unittest", "conclusion": "failure"}],
        }]}


class ReceiptTests(unittest.TestCase):
    def test_staged_is_unverified_and_read_only(self):
        plan, request, operation, draft = fixtures()
        record = make_receipt(plan, operation)
        self.assertTrue(verify_receipt(record))
        self.assertEqual(record["body"]["event"], "STAGED_ONLY")
        self.assertIsNone(record["body"]["draft"]["url"])
        self.assertEqual(record["trust"], "UNSIGNED_UNVERIFIED")
        self.assertFalse(record["body"]["handoff"]["anti_m"]["done"])
        self.assertFalse(record["body"]["handoff"]["anti_m"]["execution_authority"])
        self.assertEqual(record["body"]["handoff"]["gitporch"]["outcome"], "UNVERIFIED")
        self.assertFalse(record["body"]["handoff"]["gitporch"]["signed_evidence"])
        self.assertEqual(record["body"]["claims"]["merges_performed"], 0)
        self.assertNotIn(request["replacement_text"], json.dumps(record))

    def test_draft_created_is_not_reported_as_merged_or_ci_passed(self):
        plan, request, operation, draft = fixtures()
        record = make_receipt(plan, operation, draft)
        self.assertTrue(verify_receipt(record))
        self.assertEqual(record["body"]["event"], "DRAFT_CREATED")
        self.assertEqual(record["body"]["draft"]["number"], 8)
        self.assertFalse(record["body"]["claims"]["ci_verified"])
        self.assertFalse(record["body"]["claims"]["permission_granted"])
        self.assertFalse(record["body"]["handoff"]["anti_m"]["closure_authority"])

    def test_tamper_rejected(self):
        plan, request, operation, draft = fixtures()
        record = make_receipt(plan, operation, draft)
        altered = copy.deepcopy(record)
        altered["body"]["draft"]["number"] = 99
        self.assertFalse(verify_receipt(altered))
        altered = copy.deepcopy(record)
        altered["body"]["claims"]["ci_verified"] = True
        altered["checksum_sha256"] = "0" * 64
        self.assertFalse(verify_receipt(altered))
        altered = copy.deepcopy(record)
        altered["body"]["handoff"]["anti_m"]["done"] = True
        self.assertFalse(verify_receipt(altered))

    def test_known_digest_must_match(self):
        plan, request, operation, draft = fixtures()
        record = make_receipt(plan, operation)
        self.assertTrue(verify_receipt(record, record["checksum_sha256"]))
        self.assertFalse(verify_receipt(record, "0" * 64))

    def test_invalid_draft_claims_rejected(self):
        plan, request, operation, draft = fixtures()
        for changed in (
                dict(draft, status="merged"),
                dict(draft, url="https://evil.example/collect"),
                dict(draft, merges_performed=1),
                dict(draft, source_branch_untouched=False),
                dict(draft, branch="main"),
                dict(draft, pr_number=True)):
            with self.subTest(changed=changed):
                with self.assertRaises(ReceiptError):
                    make_receipt(plan, operation, changed)

    def test_plan_mismatch_refused(self):
        plan, request, operation, draft = fixtures()
        altered = copy.deepcopy(plan)
        altered["plan_fingerprint"] = "0" * 64
        with self.assertRaises(ReceiptError):
            make_receipt(altered, operation)

    def test_local_export_exclusive_and_reloadable(self):
        plan, request, operation, draft = fixtures()
        record = make_receipt(plan, operation)
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "handoff.json")
            output = export_receipt(record, target)
            self.assertEqual(output["trust"], "UNSIGNED_UNVERIFIED")
            with open(target, encoding="ascii") as fp:
                imported = json.load(fp)
            self.assertEqual(imported, record)
            self.assertTrue(verify_receipt(imported))
            with self.assertRaises(FileExistsError):
                export_receipt(record, target)

    def test_no_auto_export_from_standard_cli(self):
        output = io.StringIO()
        with patch("smergeon.cli.GitHubClient", return_value=FailedClient()), \
             patch("smergeon.cli.export_receipt") as exporter:
            with contextlib.redirect_stdout(output):
                exit_code = main(["--repo", REPO, "--pr", "7", "--surgery-plan", "--json"])
        self.assertEqual(exit_code, 1)
        exporter.assert_not_called()

    def test_cli_staged_handoff_export(self):
        plan, request, operation, draft = fixtures()
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "receipt.json")
            request_path = os.path.join(directory, "request.json")
            with open(request_path, "w", encoding="utf-8") as fp:
                json.dump(request, fp)
            output = io.StringIO()
            with patch("smergeon.cli.GitHubClient", return_value=FailedClient()), \
                 patch("smergeon.cli.GitHubDraftWriter") as writer:
                with contextlib.redirect_stdout(output):
                    code = main([
                        "--repo", REPO, "--pr", "7", "--surgery-plan",
                        "--confirm-plan-id", plan["plan_fingerprint"],
                        "--repair-request", request_path,
                        "--handoff-out", target, "--json"])
            self.assertEqual(code, 1)
            writer.assert_not_called()
            with open(target, encoding="ascii") as fp:
                handoff = json.load(fp)
            self.assertTrue(verify_receipt(handoff))
            self.assertEqual(handoff["body"]["event"], "STAGED_ONLY")
            self.assertIn("handoff_export", json.loads(output.getvalue()))


if __name__ == "__main__":
    unittest.main()
