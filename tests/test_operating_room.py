"""Operating Room tests: dry-run default, stale-state rejection, and draft-only writes."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from smergeon.cli import collect, main
from smergeon.consent import make_plan
from smergeon.operating_room import (
    CONFIRM_WORDS, SurgeryError, _blob_sha, create_draft, stage_repair,
)
from smergeon.prescriptions import attach_prescriptions

REPO = "owner/repo"
HEAD = "a" * 40
BEFORE = "b" * 40
AFTER = "c" * 40


class FakeClient:
    repo = REPO

    def pr(self, number):
        return {"head": {"sha": HEAD, "ref": "feature/test",
                         "repo": {"full_name": REPO}},
                "html_url": "https://github.com/owner/repo/pull/" + str(number),
                "state": "open"}

    def runs(self, sha):
        return {"total_count": 1, "workflow_runs": [{
            "id": 24, "name": "CI", "status": "completed", "conclusion": "failure",
            "html_url": "https://github.com/owner/repo/actions/runs/24"}]}

    def checks(self, sha):
        return {"total_count": 0, "check_runs": []}

    def jobs(self, run):
        return {"total_count": 1, "jobs": [{
            "id": 100, "name": "tests", "conclusion": "failure",
            "html_url": "https://github.com/owner/repo/actions/runs/24/job/100",
            "steps": [{"name": "Run unittest", "conclusion": "failure"}]}]}


class FakeWriter:
    repo = REPO
    token = "mock-token"

    def __init__(self, before=BEFORE, head=HEAD, fork=False):
        self.before = before
        self.head = head
        self.fork = fork
        self.calls = []

    def get(self, resource, params=None):
        self.calls.append(("GET", resource))
        if resource.startswith("pulls/"):
            return {"state": "open", "head": {
                "sha": self.head, "ref": "feature/test",
                "repo": {"full_name": "other/repo" if self.fork else REPO}}}
        if resource.startswith("contents/"):
            return {"type": "file", "sha": self.before}
        if resource.startswith("git/commits/"):
            return {"tree": {"sha": "d" * 40}}
        raise AssertionError("Unexpected GET: " + resource)

    def post(self, resource, payload):
        self.calls.append(("POST", resource, payload))
        if resource == "git/blobs":
            return {"sha": _blob_sha(payload["content"])}
        if resource == "git/trees":
            return {"sha": "e" * 40}
        if resource == "git/commits":
            return {"sha": "f" * 40}
        if resource == "git/refs":
            return {"ref": payload["ref"]}
        if resource == "pulls":
            return {"draft": True, "html_url": "https://github.com/owner/repo/pull/8",
                    "number": 8}
        raise AssertionError("Unexpected POST: " + resource)


def inputs():
    result = collect(FakeClient(), pr=7, prescribe_fixes=True)
    plan = make_plan(result)
    replacement = "# Reviewed fix\nprint('safe')\n"
    request = {"path": "src/fix.py", "expected_blob_sha": BEFORE,
               "replacement_text": replacement}
    operation = stage_repair(plan, request, REPO, 7, HEAD,
                             plan["plan_fingerprint"])
    return plan, request, operation


class OperatingRoomTests(unittest.TestCase):
    def test_stage_binds_specific_head_path_and_blobs(self):
        plan, request, op = inputs()
        self.assertEqual(op["status"], "review_required")
        self.assertEqual(op["binding"]["before_blob_sha"], BEFORE)
        self.assertEqual(op["binding"]["after_blob_sha"], _blob_sha(request["replacement_text"]))
        self.assertEqual(op["binding"]["source_head_sha"], HEAD)
        self.assertTrue(op["proposed_branch"].startswith("smergeon/repair-pr7-"))
        self.assertTrue(op["authority"]["no_writes_by_default"])
        self.assertNotIn(request["replacement_text"], json.dumps(op))

    def test_same_inputs_same_operation(self):
        self.assertEqual(inputs()[2], inputs()[2])

    def test_stale_head_fails(self):
        plan, request, op = inputs()
        with self.assertRaises(SurgeryError):
            stage_repair(plan, request, REPO, 7, AFTER, plan["plan_fingerprint"])

    def test_no_op_and_invalid_path_rejected(self):
        plan, request, op = inputs()
        for bad in ("../secrets.py", ".github/workflows/publish.yml", "/tmp/a.py",
                    "src/../../x.py", "src/.env", "src/x.exe", "src//x.py"):
            with self.subTest(path=bad):
                edit = dict(request, path=bad)
                with self.assertRaises(SurgeryError):
                    stage_repair(plan, edit, REPO, 7, HEAD, plan["plan_fingerprint"])
        edit = dict(request, expected_blob_sha=_blob_sha(request["replacement_text"]))
        with self.assertRaises(SurgeryError):
            stage_repair(plan, edit, REPO, 7, HEAD, plan["plan_fingerprint"])

    def test_malformed_or_oversized_rejected(self):
        plan, request, op = inputs()
        for bad in (dict(request, replacement_text=""),
                    dict(request, replacement_text="x" * 65537),
                    dict(request, replacement_text="hello\x00world"),
                    dict(request, unexpected=True)):
            with self.assertRaises(SurgeryError):
                stage_repair(plan, bad, REPO, 7, HEAD, plan["plan_fingerprint"])

    def test_not_authorized_no_api_call(self):
        plan, request, op = inputs()
        writer = FakeWriter()
        with self.assertRaises(SurgeryError):
            create_draft(writer, plan, op, request["replacement_text"],
                         confirm="NOT APPROVED")
        self.assertEqual(writer.calls, [])

    def test_replace_text_tampering_rejected(self):
        plan, request, op = inputs()
        writer = FakeWriter()
        with self.assertRaises(SurgeryError):
            create_draft(writer, plan, op, "unreviewed text", confirm=CONFIRM_WORDS)
        self.assertEqual(writer.calls, [])

    def test_stale_or_forked_source_denied_before_writes(self):
        plan, request, op = inputs()
        for writer in (FakeWriter(head=AFTER), FakeWriter(fork=True),
                       FakeWriter(before=AFTER)):
            with self.assertRaises(SurgeryError):
                create_draft(writer, plan, op, request["replacement_text"],
                             confirm=CONFIRM_WORDS)
            self.assertFalse(any(call[0] == "POST" for call in writer.calls))

    def test_write_creates_only_separate_branch_and_draft(self):
        plan, request, op = inputs()
        writer = FakeWriter()
        result = create_draft(writer, plan, op, request["replacement_text"],
                              confirm=CONFIRM_WORDS)
        self.assertEqual(result["status"], "draft_created")
        self.assertEqual(result["merges_performed"], 0)
        self.assertTrue(result["source_branch_untouched"])
        endpoints = [call[1] for call in writer.calls if call[0] == "POST"]
        self.assertEqual(endpoints, ["git/blobs", "git/trees", "git/commits",
                                     "git/refs", "pulls"])
        ref = next(c[2]["ref"] for c in writer.calls if c[1] == "git/refs")
        self.assertEqual(ref, "refs/heads/" + op["proposed_branch"])
        new_pr = next(c[2] for c in writer.calls if c[1] == "pulls")
        self.assertIs(new_pr["draft"], True)
        self.assertEqual(new_pr["base"], "feature/test")
        self.assertNotEqual(new_pr["base"], "main")
        self.assertNotIn("merge", endpoints)

    def test_default_cli_stages_without_writing(self):
        plan, request, op = inputs()
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json",
                                         delete=False) as handle:
            json.dump(request, handle)
            filename = handle.name
        try:
            stdout = io.StringIO()
            with patch("smergeon.cli.GitHubClient", return_value=FakeClient()), \
                 patch("smergeon.cli.GitHubDraftWriter") as write_transport:
                with contextlib.redirect_stdout(stdout):
                    result = main(["--repo", REPO, "--pr", "7", "--surgery-plan",
                                   "--confirm-plan-id", plan["plan_fingerprint"],
                                   "--repair-request", filename, "--json"])
            self.assertEqual(result, 1)  # Existing CODE BLUE semantics.
            self.assertEqual(json.loads(stdout.getvalue())["operating_room"]["status"],
                             "review_required")
            write_transport.assert_not_called()
        finally:
            os.unlink(filename)

    def test_explicit_cli_write_creates_draft_only(self):
        plan, request, op = inputs()
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json",
                                         delete=False) as handle:
            json.dump(request, handle)
            filename = handle.name
        try:
            stdout = io.StringIO()
            writer = FakeWriter()
            with patch("smergeon.cli.GitHubClient", return_value=FakeClient()), \
                 patch("smergeon.cli.GitHubDraftWriter", return_value=writer):
                with contextlib.redirect_stdout(stdout):
                    result = main(["--repo", REPO, "--pr", "7", "--surgery-plan",
                                   "--confirm-plan-id", plan["plan_fingerprint"],
                                   "--repair-request", filename, "--write-draft",
                                   "--confirm-write", CONFIRM_WORDS, "--json"])
            self.assertEqual(result, 0)
            result_data = json.loads(stdout.getvalue())
            self.assertEqual(result_data["draft_pr"]["status"], "draft_created")
        finally:
            os.unlink(filename)


if __name__ == "__main__":
    unittest.main()
