"""Fail-closed surgical consent packets bound to one inspected PR head.

These records are **not** signatures or authorization. They prevent accidental
reuse of stale plans and provide an auditable specification for a future,
separately approved repair-PR executor. Nothing here writes to GitHub.
"""

import hashlib
import hmac
import json
import re

from .prescriptions import CATALOG

SCHEMA = "smergeon.surgical-consent.v0.4"
DOMAIN = b"smergeon-consent-v0.4\n"
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", re.ASCII)
SHA = re.compile(r"[0-9a-fA-F]{40}", re.ASCII)
HEX_DIGEST = re.compile(r"[0-9a-f]{64}", re.ASCII)


class PlanError(ValueError):
    """A plan cannot be safely prepared from the available evidence."""


def _digest(binding):
    payload = json.dumps(binding, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(DOMAIN + payload).hexdigest()


def _validate_target(repository, subject):
    if not isinstance(repository, str) or not REPO.fullmatch(repository):
        raise PlanError("A canonical OWNER/REPO is required.")
    if not isinstance(subject, dict) or subject.get("kind") != "pull_request":
        raise PlanError("Surgical plans must target an inspected pull request.")
    number = subject.get("number")
    if type(number) is not int or number < 1:
        raise PlanError("The pull request number is invalid.")
    sha = subject.get("head_sha")
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise PlanError("A full 40-character PR head SHA is required.")
    return number, sha.lower()


def make_plan(packet):
    """Make a canonical, low-trust review packet; never modify the target."""
    if not isinstance(packet, dict) or packet.get("status") != "code_blue":
        raise PlanError("Only observed CODE BLUE failures can be planned.")
    safety = packet.get("safety")
    if (not isinstance(safety, dict) or safety.get("read_only") is not True
            or safety.get("changes_written") != 0 or safety.get("merges_performed") != 0):
        raise PlanError("Refusing a packet without a read-only safety record.")
    repository = packet.get("repository")
    pr, sha = _validate_target(repository, packet.get("subject"))
    items = packet.get("prescriptions")
    if not isinstance(items, list) or not items:
        raise PlanError("No recognized repair prescription: use --prescribe.")
    selections = {}
    for item in items:
        if not isinstance(item, dict):
            raise PlanError("Invalid prescription object.")
        category = item.get("category")
        if category not in CATALOG:
            raise PlanError("Unknown recipe category in prescription.")
        if item.get("id") != "smergeon.rx." + category + ".v0.3":
            raise PlanError("Prescription ID and category disagree.")
        if item.get("approval_required") is not True or item.get("patch_created") is not False:
            raise PlanError("Prescription is missing required safety guards.")
        level = item.get("confidence")
        if level not in ("low", "medium"):
            raise PlanError("Unknown confidence level.")
        evidence = item.get("evidence")
        if not isinstance(evidence, dict):
            raise PlanError("Missing evidence reference.")
        rid = evidence.get("run_id")
        if rid is not None and (type(rid) is not int or rid < 1):
            raise PlanError("Invalid evidence run ID.")
        # Fixed fields only; never copy external check names, URLs, or raw logs.
        row = {"recipe_id": item["id"], "category": category,
               "confidence": level, "run_id": rid}
        previous = selections.get(category)
        if previous is None or (previous["confidence"] == "low" and level == "medium"):
            selections[category] = row
    if not selections:
        raise PlanError("No actionable categories to review.")
    binding = {
        "schema": SCHEMA,
        "repository": repository,
        "pull_request": pr,
        "head_sha": sha,
        "recipes": sorted(selections.values(),
                          key=lambda r: (r["category"], r["run_id"] or 0)),
    }
    fingerprint = _digest(binding)
    return {
        "schema": SCHEMA,
        "plan_fingerprint": fingerprint,
        "binding": binding,
        "status": "review_required",
        "requirements": [
            "Confirm the proposed repair against the failing source and tests.",
            "Re-read the PR head SHA immediately before preparing any patch.",
            "Apply the smallest human-reviewed change on a separate branch.",
            "Use an independent CI run and draft PR review before any merge.",
        ],
        "limitations": [
            "Fingerprint is a consistency checksum, not a digital signature or authentication.",
            "Matching a plan never grants permission to push, approve or merge.",
            "Possible synthetic-merge-SHA and API pagination gaps remain.",
        ],
        "authority": {
            "human_approval_required": True,
            "github_writes_enabled": False,
            "patches_created": 0,
            "merges_performed": 0,
        },
    }


def verify_plan(plan, repository, pr_number, current_head_sha,
                expected_fingerprint):
    """Check exact plan identity and current PR head; grant *zero* write rights.

    This is useful to detect stale or accidentally modified plans. A checksum
    cannot prove who approved it; real authorization belongs to GitHub's
    authenticated, privilege-scoped review/branch protection controls.
    """
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA:
        return False
    binding = plan.get("binding")
    if not isinstance(binding, dict) or binding.get("schema") != SCHEMA:
        return False
    try:
        number, sha = _validate_target(
            binding.get("repository"),
            {"kind": "pull_request", "number": binding.get("pull_request"),
             "head_sha": binding.get("head_sha")},
        )
    except PlanError:
        return False
    recipes = binding.get("recipes")
    if not isinstance(recipes, list) or not recipes:
        return False
    # Require all metadata to follow the exact minimal schema.
    if set(binding) != {"schema", "repository", "pull_request", "head_sha", "recipes"}:
        return False
    if any(not isinstance(item, dict)
           or set(item) != {"recipe_id", "category", "confidence", "run_id"}
           or item.get("category") not in CATALOG
           or item.get("recipe_id") != "smergeon.rx." + item["category"] + ".v0.3"
           or item.get("confidence") not in ("low", "medium")
           or (item.get("run_id") is not None
               and (type(item["run_id"]) is not int or item["run_id"] < 1))
           for item in recipes):
        return False
    if recipes != sorted(recipes, key=lambda r: (r["category"], r["run_id"] or 0)):
        return False
    if len({item["category"] for item in recipes}) != len(recipes):
        return False
    actual = plan.get("plan_fingerprint")
    if not isinstance(actual, str) or not HEX_DIGEST.fullmatch(actual):
        return False
    if not isinstance(expected_fingerprint, str) or not HEX_DIGEST.fullmatch(expected_fingerprint):
        return False
    if not isinstance(current_head_sha, str) or not SHA.fullmatch(current_head_sha):
        return False
    return (
        binding["repository"] == repository
        and number == pr_number
        and sha == current_head_sha.lower()
        and hmac.compare_digest(actual, expected_fingerprint)
        and hmac.compare_digest(actual, _digest(binding))
    )
