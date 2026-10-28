"""Fail-closed contract checks for the real GitHub PR self-clinic workflow."""

from pathlib import Path
import unittest


WORKFLOW = (Path(__file__).resolve().parent.parent /
            ".github/workflows/field-qualification.yml")


class FieldWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_real_pr_trigger_no_privileged_target(self):
        self.assertIn("  pull_request:", self.source)
        self.assertIn("opened, synchronize, reopened", self.source)
        self.assertNotIn("pull_request_target:", self.source)

    def test_same_repo_only_and_trusted_source(self):
        self.assertIn("head.repo.full_name == github.repository", self.source)
        self.assertIn("ref: main", self.source)
        self.assertIn("persist-credentials: false", self.source)

    def test_read_scopes_only(self):
        for item in ("contents: read", "actions: read",
                     "checks: read", "pull-requests: read"):
            self.assertIn(item, self.source)
        for item in ("\n  contents: write", "\n  actions: write",
                     "\n  checks: write", "\n  pull-requests: write"):
            self.assertNotIn(item, self.source)

    def test_no_repair_flags_or_code_from_target(self):
        for term in ("--write-draft", "--with-logs", "--repair-request",
                     "--confirm-write", "git push", "gh pr merge"):
            self.assertNotIn(term, self.source)
        self.assertIn("python -m smergeon.cloud_clinic", self.source)

    def test_actual_pr_context_used(self):
        self.assertIn("github.event.pull_request.number", self.source)
        self.assertIn("github.repository", self.source)
        self.assertIn("CLINIC_PR", self.source)

    def test_real_observation_without_green_claim(self):
        self.assertIn("REAL_PUBLIC_GITHUB_METADATA_OBSERVED", self.source)
        self.assertIn('"CODE_BLUE", "RECOVERY", "CLEAR", "UNKNOWN"', self.source)
        self.assertIn('"human_review_required": True', self.source)
        self.assertIn('"merge_approved": False', self.source)

    def test_explicit_zero_authority(self):
        for key in ('"patches_created": 0', '"drafts_created": 0',
                    '"merges_performed": 0', '"merge_approval": False',
                    '"target_code_executed": False'):
            self.assertIn(key, self.source)

    def test_artifact_retention_and_presence(self):
        self.assertIn("actions/upload-artifact@v4", self.source)
        self.assertIn("retention-days: 7", self.source)
        self.assertIn("field-qualification-out/", self.source)
        self.assertIn("if-no-files-found: error", self.source)


if __name__ == "__main__":
    unittest.main()
