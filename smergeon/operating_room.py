"""Operating Room: staged single-file repair and explicitly approved draft PRs.

The patient's original branch is NEVER modified by this module. Only one
human-supplied replacement file is permitted per operation. The first stage
does no GitHub writes. Write mode requires explicit authorization elsewhere.
"""

import hashlib
import hmac
import json
import re

from .consent import PlanError, SHA, verify_plan

SCHEMA = "smergeon.operating-room.v0.5"
PATH = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", re.ASCII)
ALLOWED_EXT = (".py", ".js", ".jsx", ".ts", ".tsx", ".css", ".html",
               ".json", ".md", ".txt", ".toml", ".yml", ".yaml")
MAX_PATCH_BYTES = 65536
CONFIRM_WORDS = "CREATE DRAFT PR"


class SurgeryError(ValueError):
    """Reject malformed or unapproved operations before changing anything."""


def _valid_path(value):
    if not isinstance(value, str) or len(value) > 180 or not PATH.fullmatch(value):
        return False
    parts = value.split("/")
    if any(s in (".", "..") or s.startswith(".") for s in parts):
        return False
    if parts[0].lower() in ("node_modules", "vendor", "dist", "build"):
        return False
    if parts[0] == ".github" or parts[-1].lower() in (".env", "codeowners", ".gitmodules"):
        return False
    return value.lower().endswith(ALLOWED_EXT)


def _blob_sha(content):
    payload = content.encode("utf-8")
    return hashlib.sha1(b"blob " + str(len(payload)).encode("ascii")
                        + b"\x00" + payload).hexdigest()


def _payload_digest(data):
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(b"smergeon-operating-room-v0.5\n" + payload).hexdigest()


def stage_repair(plan, request, repository, pr_number, current_head_sha,
                 expected_plan_id):
    """Stage a single-file exact replacement without reading or writing GitHub."""
    if not verify_plan(plan, repository, pr_number, current_head_sha,
                       expected_plan_id):
        raise SurgeryError("Consent fingerprint or current PR head is not valid.")
    if not isinstance(request, dict) or set(request) != {
            "path", "expected_blob_sha", "replacement_text"}:
        raise SurgeryError("Request needs path, expected_blob_sha and replacement_text only.")
    path = request["path"]
    if not _valid_path(path):
        raise SurgeryError("Unsafe or unsupported replacement path.")
    before = request["expected_blob_sha"]
    if not isinstance(before, str) or not SHA.fullmatch(before):
        raise SurgeryError("Expected original file blob SHA must be 40 hex characters.")
    replacement = request["replacement_text"]
    if not isinstance(replacement, str) or "\x00" in replacement:
        raise SurgeryError("Replacement must be UTF-8 text without NUL bytes.")
    size = len(replacement.encode("utf-8"))
    if not 1 <= size <= MAX_PATCH_BYTES:
        raise SurgeryError("Replacement size must be 1 to 65536 UTF-8 bytes.")
    after = _blob_sha(replacement)
    if hmac.compare_digest(before.lower(), after):
        raise SurgeryError("Replacement matches expected original blob; no-op refused.")
    binding = plan["binding"]
    small = {
        "schema": SCHEMA,
        "repository": repository,
        "source_pr": pr_number,
        "source_head_sha": current_head_sha.lower(),
        "source_plan_id": expected_plan_id,
        "file_path": path,
        "before_blob_sha": before.lower(),
        "after_blob_sha": after,
        "utf8_bytes": size,
    }
    digest = _payload_digest(small)
    branch = ("smergeon/repair-pr" + str(pr_number) + "-" +
              current_head_sha[:8].lower() + "-" + digest[:10])
    return {
        "schema": SCHEMA,
        "status": "review_required",
        "operation_id": digest,
        "binding": small,
        "proposed_branch": branch,
        "actions": ["Replace one verified text file in a NEW branch",
                    "Open a DRAFT PR targeting the failing PR's head branch"],
        "authority": {
            "explicit_authorization_required": True,
            "no_writes_by_default": True,
            "auto_merge": False,
            "source_branch_untouched": True,
        },
        "warnings": [
            "The expected blob SHA is verified against GitHub only in write mode.",
            "GitHub Actions on the draft PR may execute repository workflows.",
            "The plan fingerprint is a checksum, not proof of human consent.",
        ],
    }


def create_draft(writer, plan, operation, replacement, *, confirm):
    """Execute one strictly gated, authenticated draft PR operation.

    Caller must have already requested a fresh plan, compared its fingerprint,
    staged the patch and explicitly authorized this command. This function
    independently rechecks the live PR and expected blob before each write phase.
    It cannot approve, merge, delete, or modify the source branch.
    """
    if confirm != CONFIRM_WORDS:
        raise SurgeryError("Missing exact CREATE DRAFT PR authorization.")
    if not isinstance(operation, dict) or operation.get("status") != "review_required":
        raise SurgeryError("Missing staged review packet.")
    b = operation.get("binding")
    if not isinstance(b, dict) or b.get("schema") != SCHEMA:
        raise SurgeryError("Invalid operation binding.")
    if not isinstance(replacement, str) or _blob_sha(replacement) != b.get("after_blob_sha"):
        raise SurgeryError("Replacement text differs from staged content.")
    if not hmac.compare_digest(
            str(operation.get("operation_id", "")), _payload_digest(b)):
        raise SurgeryError("Operation fingerprint mismatch.")
    repo, number, head_sha = b["repository"], b["source_pr"], b["source_head_sha"]
    if writer.repo != repo or not verify_plan(
            plan, repo, number, head_sha, b["source_plan_id"]):
        raise SurgeryError("Target and surgical consent do not match.")
    if not _valid_path(b.get("file_path")):
        raise SurgeryError("Unsafe path in staged operation.")
    if not isinstance(b.get("before_blob_sha"), str) or not SHA.fullmatch(b["before_blob_sha"]):
        raise SurgeryError("Invalid original blob SHA.")
    if not isinstance(operation.get("proposed_branch"), str):
        raise SurgeryError("Missing proposed branch.")
    expected_branch = ("smergeon/repair-pr" + str(number) + "-" + head_sha[:8]
                       + "-" + operation["operation_id"][:10])
    if operation["proposed_branch"] != expected_branch:
        raise SurgeryError("Unexpected branch identity.")
    if not writer.token:
        raise SurgeryError("Authenticated, least-privilege GitHub token required.")

    def live_pr():
        current = writer.get("pulls/" + str(number))
        data = current.get("head") or {}
        source = data.get("repo") or {}
        if (current.get("state") != "open" or data.get("sha") != head_sha
                or source.get("full_name") != repo):
            raise SurgeryError("Source PR changed, closed, or belongs to a fork.")
        ref = data.get("ref")
        if not isinstance(ref, str) or not PATH.fullmatch(ref):
            raise SurgeryError("Unsupported PR head branch name.")
        if any(segment in ("", ".", "..") for segment in ref.split("/")):
            raise SurgeryError("Unsafe PR head branch name.")
        return ref

    head_ref = live_pr()
    remote = writer.get("contents/" + b["file_path"], {"ref": head_sha})
    if (remote.get("type") != "file"
            or remote.get("sha", "").lower() != b["before_blob_sha"]):
        raise SurgeryError("Original blob changed or is not a regular file.")
    origin = writer.get("git/commits/" + head_sha)
    tree_sha = (origin.get("tree") or {}).get("sha")
    if not isinstance(tree_sha, str) or not SHA.fullmatch(tree_sha):
        raise SurgeryError("Could not determine the source tree.")
    # The approval is for a specific head; inspect again before *any* write.
    if live_pr() != head_ref:
        raise SurgeryError("Original PR branch changed before write.")
    blob = writer.post("git/blobs", {"content": replacement, "encoding": "utf-8"})
    blob_sha = blob.get("sha")
    if blob_sha != b["after_blob_sha"]:
        raise SurgeryError("GitHub blob hash does not match the reviewed replacement.")
    tree = writer.post("git/trees", {
        "base_tree": tree_sha,
        "tree": [{"path": b["file_path"], "mode": "100644",
                  "type": "blob", "sha": blob_sha}],
    })
    tree_id = tree.get("sha")
    if not isinstance(tree_id, str) or not SHA.fullmatch(tree_id):
        raise SurgeryError("Invalid tree from GitHub.")
    commit = writer.post("git/commits", {
        "message": "fix: proposed repair for PR #" + str(number),
        "tree": tree_id, "parents": [head_sha],
    })
    commit_id = commit.get("sha")
    if not isinstance(commit_id, str) or not SHA.fullmatch(commit_id):
        raise SurgeryError("Invalid commit from GitHub.")
    # A race may leave unattached Git objects, but must not attach stale repairs.
    if live_pr() != head_ref:
        raise SurgeryError("Source PR advanced: no repair branch created.")
    writer.post("git/refs", {"ref": "refs/heads/" + expected_branch, "sha": commit_id})
    # Recheck: on a race, safely leave a branch without opening an outdated PR.
    if live_pr() != head_ref:
        raise SurgeryError("Source PR advanced: review orphaned repair branch " + expected_branch)
    created = writer.post("pulls", {
        "title": "Smergeon: proposed repair for PR #" + str(number),
        "head": expected_branch,
        "base": head_ref,
        "draft": True,
        "maintainer_can_modify": False,
        "body": ("Human-reviewed repair proposal for PR #" + str(number)
                 + "\n\nPlan fingerprint: " + b["source_plan_id"]
                 + "\nOperation fingerprint: " + operation["operation_id"]
                 + "\nFile: " + b["file_path"]
                 + "\n\nDraft only. Review the diff, verify CI, and merge manually."
                 + "\nNo automatic approval or merge."),
    })
    if created.get("draft") is not True or not created.get("html_url"):
        raise SurgeryError("GitHub draft PR creation response is incomplete.")
    return {"status": "draft_created", "url": created["html_url"],
            "pr_number": created.get("number"),
            "branch": expected_branch,
            "merges_performed": 0, "source_branch_untouched": True}
