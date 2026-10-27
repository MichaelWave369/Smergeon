"""Portable, unsigned handoff receipts for GitPorch and Anti-M reviewers.

No automatic integration or trust promotion is performed. All receipts are
self-reported descriptions of proposed or draft-only repair activities.
Their SHA-256 checksum detects accidental changes only when the fingerprint
has been independently preserved. It is NOT a signature or approval.
"""

import hashlib
import hmac
import json
import os
import re
from urllib.parse import urlsplit

from .consent import HEX_DIGEST, REPO, SHA
from .operating_room import SCHEMA as OP_SCHEMA, _valid_path

SCHEMA = "smergeon.surgical-handoff.v0.6"
DOMAIN = b"smergeon-surgical-handoff-v0.6\n"
BRIDGE_NAMES = ("gitporch", "anti_m")
BRANCH = re.compile(r"smergeon/repair-pr[1-9][0-9]*-[0-9a-f]{8}-[0-9a-f]{10}")
STATUSES = ("STAGED_ONLY", "DRAFT_CREATED")
MAX_RECEIPT_BYTES = 16384


class ReceiptError(ValueError):
    """Receipt invalid or storage refused."""


def _checksum(data):
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(DOMAIN + encoded).hexdigest()


def _exact_draft_link(repository, number, url):
    if type(number) is not int or number < 1 or not isinstance(url, str):
        return False
    parsed = urlsplit(url)
    return (parsed.scheme == "https" and parsed.netloc == "github.com"
            and not parsed.query and not parsed.fragment
            and parsed.path == "/" + repository + "/pull/" + str(number)
            and parsed.username is None and parsed.password is None)


def make_receipt(plan, operation, draft_pr=None):
    """Convert a v0.5 operation into an intentionally non-authoritative receipt."""
    if not isinstance(plan, dict) or not isinstance(operation, dict):
        raise ReceiptError("Plan and operation are required.")
    binding = operation.get("binding")
    if not isinstance(binding, dict) or binding.get("schema") != OP_SCHEMA:
        raise ReceiptError("Invalid v0.5 operation binding.")
    repo = binding.get("repository")
    source = binding.get("source_pr")
    head = binding.get("source_head_sha")
    plan_id = binding.get("source_plan_id")
    operation_id = operation.get("operation_id")
    expected = binding.get("after_blob_sha")
    prior = binding.get("before_blob_sha")
    path = binding.get("file_path")
    new_branch = operation.get("proposed_branch")
    if (not isinstance(repo, str) or not REPO.fullmatch(repo)
            or type(source) is not int or source < 1
            or not isinstance(head, str) or not SHA.fullmatch(head)
            or not all(isinstance(d, str) and HEX_DIGEST.fullmatch(d)
                       for d in (plan_id, operation_id))
            or not all(isinstance(d, str) and SHA.fullmatch(d)
                       for d in (expected, prior))
            or not _valid_path(path)
            or not isinstance(new_branch, str) or not BRANCH.fullmatch(new_branch)):
        raise ReceiptError("Malformed operation target or fingerprints.")
    if (plan.get("plan_fingerprint") != plan_id
            or (plan.get("binding") or {}).get("repository") != repo
            or (plan.get("binding") or {}).get("pull_request") != source
            or (plan.get("binding") or {}).get("head_sha") != head):
        raise ReceiptError("Source plan and operation are not bound together.")
    if operation.get("status") != "review_required":
        raise ReceiptError("Expected a reviewed but unexecuted staging packet.")
    branch_expected = ("smergeon/repair-pr" + str(source) + "-"
                       + head[:8] + "-" + operation_id[:10])
    if branch_expected != new_branch:
        raise ReceiptError("Inconsistent repair branch.")
    if (operation.get("authority") or {}).get("auto_merge") is not False:
        raise ReceiptError("Repair packet does not forbid auto-merge.")
    if not isinstance(binding.get("utf8_bytes"), int) or not 1 <= binding["utf8_bytes"] <= 65536:
        raise ReceiptError("Invalid replacement byte size.")

    state = "STAGED_ONLY"
    draft_number, draft_url = None, None
    if draft_pr is not None:
        if not isinstance(draft_pr, dict) or draft_pr.get("status") != "draft_created":
            raise ReceiptError("Only a recorded draft creation can populate this field.")
        if (draft_pr.get("source_branch_untouched") is not True
                or draft_pr.get("merges_performed") != 0
                or draft_pr.get("branch") != new_branch):
            raise ReceiptError("Draft result violates source-branch safety.")
        draft_number = draft_pr.get("pr_number")
        draft_url = draft_pr.get("url")
        if not _exact_draft_link(repo, draft_number, draft_url):
            raise ReceiptError("Noncanonical GitHub draft PR link.")
        state = "DRAFT_CREATED"

    body = {
        "schema": SCHEMA,
        "event": state,
        "source": {
            "repository": repo,
            "pull_request": source,
            "head_sha": head,
            "plan_fingerprint": plan_id,
        },
        "operation": {
            "id": operation_id, "branch": new_branch, "file_path": path,
            "before_blob_sha": prior, "after_blob_sha": expected,
        },
        "draft": {"number": draft_number, "url": draft_url},
        "handoff": {
            "gitporch": {
                "kind": "UNSIGNED_REPAIR_PROPOSAL",
                "worker_execution_verified": False,
                "signed_evidence": False,
                "witnessed": False,
                "outcome": "UNVERIFIED",
            },
            "anti_m": {
                "kind": "SHADOW_REVIEW_ONLY",
                "execution_authority": False,
                "closure_authority": False,
                "ledger_write": False,
                "done": False,
                "provenance": "OPERATOR_REPORT",
            },
        },
        "claims": {
            "origin": "LOCAL_SELF_REPORT",
            "verified_root_cause": False,
            "ci_verified": False,
            "independently_witnessed": False,
            "source_branch_modified": False,
            "merges_performed": 0,
            "permission_granted": False,
        },
    }
    return {
        "schema": SCHEMA,
        "body": body,
        "checksum_sha256": _checksum(body),
        "trust": "UNSIGNED_UNVERIFIED",
        "warning": ("Checksum is not a signature, CI result, authenticated custody, "
                    "Anti-M completion, GitPorch worker record, or approval to merge."),
    }


def verify_receipt(receipt, independently_known_checksum=None):
    """Validate exact v0.6 shape; NEVER return an execution authorization.

    An attacker replacing an entire receipt can recompute the hash. Supplying
    an independently preserved digest detects such replacement; it still
    does not authenticate the original issuer.
    """
    if not isinstance(receipt, dict) or set(receipt) != {
            "schema", "body", "checksum_sha256", "trust", "warning"}:
        return False
    if receipt.get("schema") != SCHEMA or receipt.get("trust") != "UNSIGNED_UNVERIFIED":
        return False
    if receipt.get("warning") != (
            "Checksum is not a signature, CI result, authenticated custody, "
            "Anti-M completion, GitPorch worker record, or approval to merge."):
        return False
    body = receipt.get("body")
    if not isinstance(body, dict) or set(body) != {
            "schema", "event", "source", "operation", "draft", "handoff", "claims"}:
        return False
    if body.get("schema") != SCHEMA or body.get("event") not in STATUSES:
        return False
    source, op, draft, handoff, claims = (
        body.get("source"), body.get("operation"), body.get("draft"),
        body.get("handoff"), body.get("claims"),
    )
    if not all(isinstance(x, dict) for x in (source, op, draft, handoff, claims)):
        return False
    if set(source) != {"repository", "pull_request", "head_sha", "plan_fingerprint"}:
        return False
    if set(op) != {"id", "branch", "file_path", "before_blob_sha", "after_blob_sha"}:
        return False
    if set(draft) != {"number", "url"} or set(handoff) != set(BRIDGE_NAMES):
        return False
    repo, n, head, plan_id = (
        source["repository"], source["pull_request"],
        source["head_sha"], source["plan_fingerprint"],
    )
    op_id, branch, path = op["id"], op["branch"], op["file_path"]
    if (not isinstance(repo, str) or not REPO.fullmatch(repo)
            or type(n) is not int or n < 1
            or not isinstance(head, str) or not SHA.fullmatch(head)
            or not isinstance(plan_id, str) or not HEX_DIGEST.fullmatch(plan_id)
            or not isinstance(op_id, str) or not HEX_DIGEST.fullmatch(op_id)
            or not _valid_path(path)
            or not isinstance(branch, str) or not BRANCH.fullmatch(branch)
            or branch != "smergeon/repair-pr" + str(n) + "-" + head[:8] + "-" + op_id[:10]):
        return False
    if any(not isinstance(op.get(k), str) or not SHA.fullmatch(op[k])
           for k in ("before_blob_sha", "after_blob_sha")):
        return False
    if op["before_blob_sha"] == op["after_blob_sha"]:
        return False
    if body["event"] == "STAGED_ONLY":
        if draft != {"number": None, "url": None}:
            return False
    else:
        if not _exact_draft_link(repo, draft["number"], draft["url"]):
            return False
    if handoff["gitporch"] != {
            "kind": "UNSIGNED_REPAIR_PROPOSAL",
            "worker_execution_verified": False, "signed_evidence": False,
            "witnessed": False, "outcome": "UNVERIFIED"}:
        return False
    if handoff["anti_m"] != {
            "kind": "SHADOW_REVIEW_ONLY",
            "execution_authority": False, "closure_authority": False,
            "ledger_write": False, "done": False, "provenance": "OPERATOR_REPORT"}:
        return False
    if claims != {
            "origin": "LOCAL_SELF_REPORT",
            "verified_root_cause": False, "ci_verified": False,
            "independently_witnessed": False, "source_branch_modified": False,
            "merges_performed": 0, "permission_granted": False}:
        return False
    actual = receipt.get("checksum_sha256")
    if not isinstance(actual, str) or not HEX_DIGEST.fullmatch(actual):
        return False
    if independently_known_checksum is not None:
        if (not isinstance(independently_known_checksum, str)
                or not HEX_DIGEST.fullmatch(independently_known_checksum)
                or not hmac.compare_digest(actual, independently_known_checksum)):
            return False
    return hmac.compare_digest(actual, _checksum(body))


def export_receipt(receipt, destination):
    """Operator-requested exclusive local JSON creation; never overwrite."""
    if not verify_receipt(receipt):
        raise ReceiptError("Refusing to export an invalid unsigned handoff.")
    if not isinstance(destination, str) or not destination:
        raise ReceiptError("An output file path is required.")
    data = (json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=True)
            + "\n").encode("ascii")
    if len(data) > MAX_RECEIPT_BYTES:
        raise ReceiptError("Receipt exceeds the safe 16 KiB export limit.")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(destination, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
    except BaseException:
        try:
            os.unlink(destination)
        except OSError:
            pass
        raise
    return {"path": destination, "checksum_sha256": receipt["checksum_sha256"],
            "trust": "UNSIGNED_UNVERIFIED", "bytes": len(data)}
