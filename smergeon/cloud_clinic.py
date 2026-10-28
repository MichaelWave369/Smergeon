"""Cloud Clinic: sanitized, read-only public PR triage in GitHub Actions.

Reports contain fixed classifications, counts and author-controlled recipes
only. Arbitrary names, check summaries, logs and token-bearing strings NEVER
enter the report. CODE BLUE is a patient status, not a workflow failure.
"""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import sys

from .cli import collect
from .diagnosis import packet
from .github import GitHubClient, GitHubError
from .prescriptions import CATALOG

SCHEMA = "smergeon.cloud-clinic.v0.2"
ALLOWED_STATUS = {"code_blue", "recovery", "clear", "unknown"}
SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+\Z")
CATEGORIES = set(CATALOG) | {"unknown"}
MAX_SIGNALS = 500
LIMITATIONS = (
    "Public GitHub PRs only; private repositories are rejected.",
    "Head and test-merge SHA contexts are both inspected when available; neither proves all required checks were seen.",
    "Only the first 100 runs, checks and jobs per API endpoint are examined.",
    "GitHub can recalculate test merge commits; stale or unavailable contexts remain uncertain.",
    "No full logs, source checkout, untrusted check text, or secrets are exported.",
    "Metadata-based categories are unverified clues, not established root causes.",
    "CLEAR is not the GitHub required-check gate and never authorizes a merge.",
)


class CloudClinicError(ValueError):
    """Fail-closed safe diagnostic error."""


def inspect_public_pr(repo, number, client=None):
    """Produce a fixed-schema, sanitized diagnostic record."""
    if not isinstance(repo, str) or not REPO.fullmatch(repo):
        raise CloudClinicError("Repository must be OWNER/REPO.")
    if type(number) is not int or number < 1:
        raise CloudClinicError("PR number must be positive.")
    reader = client if client is not None else GitHubClient(repo)
    if reader.repo.lower() != repo.lower():
        raise CloudClinicError("Reader targets an unrelated repository.")
    pr = reader.pr(number)
    if not isinstance(pr, dict):
        raise CloudClinicError("Missing PR response.")
    base_repo = (pr.get("base") or {}).get("repo") or {}
    if (base_repo.get("private") is not False
            or str(base_repo.get("full_name", "")).lower() != repo.lower()):
        raise CloudClinicError("Only confirmed public PR repositories are allowed.")
    if pr.get("state") != "open":
        raise CloudClinicError("Only open PRs are eligible.")
    sha = (pr.get("head") or {}).get("sha")
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise CloudClinicError("PR head SHA unavailable.")

    # Explicitly no log fetch, code edits, checkout or repair plan.
    observed = collect(reader, pr=number, with_logs=False, prescribe_fixes=False)
    if (observed.get("status") not in ALLOWED_STATUS
            or str(observed.get("subject", {}).get("head_sha", "")).lower() != sha.lower()
            or observed.get("safety", {}).get("read_only") is not True):
        raise CloudClinicError("Head SHA changed or safety record invalid.")
    signals = list(observed.get("findings") or [])
    warnings = observed.get("warnings") or []
    partial = any(
        "unavailable" in warning.lower() or "first 100" in warning.lower()
        or "only part" in warning.lower() or "failed to load" in warning.lower()
        for warning in warnings
    )
    status = observed["status"]
    merge_sha = pr.get("merge_commit_sha")
    merge_status = "NOT_CHECKED"
    inspected_merge_sha = None
    # A merge SHA is GitHub's ephemeral test-merge commit for open PRs.
    # It is *not* the head SHA and must never be treated as a signed check.
    if (pr.get("mergeable") is True
            and isinstance(merge_sha, str) and SHA.fullmatch(merge_sha)
            and merge_sha.lower() != sha.lower()):
        inspected_merge_sha = merge_sha.lower()
        try:
            data = reader.checks(merge_sha)
            checks = data.get("check_runs", [])
            if data.get("total_count", 0) > len(checks):
                partial = True
            if len(checks) > 100:
                raise CloudClinicError("Unexpected merge check response size.")
            # No workflows or logs are requested in the merge context.
            merge_packet = packet(repo, {"kind": "pull_request", "number": number,
                                         "head_sha": sha}, [], lambda run_id: {},
                                  checks=checks)
            merge_status = merge_packet["status"].upper()
            signals.extend(merge_packet["findings"])
            if status != "code_blue":
                if merge_packet["status"] == "code_blue":
                    status = "code_blue"
                elif status == "recovery" or merge_packet["status"] == "recovery":
                    status = "recovery"
                elif status == "unknown":
                    status = merge_packet["status"]
        except GitHubError:
            partial = True
            merge_status = "UNAVAILABLE"
    elif pr.get("mergeable") is True:
        # A reported mergeable PR without its expected SHA is incomplete.
        partial = True
        merge_status = "UNAVAILABLE"

    # Reject if GitHub's live source changed during our multi-call inspection.
    current = reader.pr(number)
    if (current.get("state") != "open"
            or (current.get("head") or {}).get("sha") != sha
            or current.get("merge_commit_sha") != merge_sha
            or ((current.get("base") or {}).get("repo") or {}).get("private") is not False):
        raise CloudClinicError("PR head or test-merge SHA changed during inspection.")

    if len(signals) > MAX_SIGNALS:
        raise CloudClinicError("Too many findings for bounded output.")
    if partial and status == "clear":
        # Missing checks are NOT an all-clear, even if the inspected ones passed.
        status = "unknown"
    counts = Counter()
    for item in signals:
        category = item.get("category")
        counts[category if category in CATEGORIES else "unknown"] += 1
    hints = [
        {
            "category": category,
            "reproduce": CATALOG[category]["reproduction"],
            "verify": CATALOG[category]["verification"],
        }
        for category in sorted(counts) if category in CATALOG
    ]
    return {
        "schema": SCHEMA,
        "source": {
            "repository": repo,
            "pull_request": number,
            "observed_head_sha": sha.lower(),
            "observed_merge_sha": inspected_merge_sha,
            "review_url": "https://github.com/" + repo + "/pull/" + str(number),
        },
        "observed": {
            "status": status.upper(),
            "signal_count": len(signals),
            "categories": {c: counts[c] for c in sorted(counts)},
            "merge_context_status": merge_status,
            "coverage": "PARTIAL" if partial else (
                "HEAD_AND_TEST_MERGE_SHA" if inspected_merge_sha else "HEAD_SHA_ONLY"),
        },
        "review_guidance": hints,
        "limitations": list(LIMITATIONS),
        "authority": {
            "github_read_only": True, "raw_logs_exported": False,
            "patches_created": 0, "drafts_created": 0,
            "merges_performed": 0, "merge_approval": False,
        },
    }


def summary_markdown(report):
    """Static phrases and validated input only; no arbitrary check-run text."""
    subject, status = report["source"], report["observed"]
    lines = [
        "## Smergeon Cloud Clinic / " + status["status"],
        "",
        "**Patient:** " + subject["repository"] + " PR #" + str(subject["pull_request"]),
        "",
        "**Observed PR head:** " + subject["observed_head_sha"],
        "",
        "**Inspected test merge:** " + (subject["observed_merge_sha"] or "NOT AVAILABLE"),
        "",
        "**Test merge status:** " + status["merge_context_status"],
        "",
        "**Coverage:** " + status["coverage"] + " (not a merge gate)",
        "",
        "**Failure signals observed:** " + str(status["signal_count"]),
        "",
        "| Category | Signals |",
        "| :-- | --: |",
    ]
    for category, count in status["categories"].items():
        lines.append("| " + category + " | " + str(count) + " |")
    if not status["categories"]:
        lines.append("| None recognized | 0 |")
    lines += [
        "",
        "**Interpretation:** Metadata observations, not verified root causes.",
        "CLEAR does not replace required checks or human review.",
        "",
        "**Limitations:** " + " ".join(LIMITATIONS),
        "",
        "First, do no merge harm.",
        "",
    ]
    return "\n".join(lines)


def write_report(report, output_dir, summary_path=None):
    """Create only new, bounded artifacts."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    body = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    summary = summary_markdown(report)
    if len(body.encode("utf-8")) > 65536:
        raise CloudClinicError("Diagnostic output is too large.")
    with (root / "triage.json").open("x", encoding="utf-8") as f:
        f.write(body)
    with (root / "SUMMARY.md").open("x", encoding="utf-8") as f:
        f.write(summary)
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(summary)
    return {"status": report["observed"]["status"],
            "json": str(root / "triage.json")}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only GitHub-hosted triage for an open public PR.")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--out-dir", default="cloud-clinic-out")
    args = parser.parse_args(argv)
    try:
        report = inspect_public_pr(args.repo, args.pr)
        outcome = write_report(report, args.out_dir, os.getenv("GITHUB_STEP_SUMMARY"))
    except (CloudClinicError, GitHubError, KeyError, TypeError, OSError):
        print("Cloud Clinic intake refused. Review target, public access, and permissions.",
              file=sys.stderr)
        return 2
    print("Cloud Clinic completed: " + outcome["status"] +
          "; sanitized report created; zero GitHub writes.")
    return 0  # CODE BLUE is a target status, not a diagnosis workflow failure.


if __name__ == "__main__":
    raise SystemExit(main())
