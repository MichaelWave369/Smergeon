"""Read-only PR and Actions CLI. Code BLUE exits 1; intake errors exit 2."""

import argparse
import json
import sys

from .diagnosis import packet
from .github import GitHubClient, GitHubError
from .prescriptions import attach_prescriptions
from .consent import PlanError, make_plan, verify_plan


def collect(client, pr=None, run=None, with_logs=False, max_log_kib=256,
            prescribe_fixes=False):
    warnings = []
    if pr is not None:
        pull = client.pr(pr)
        sha = pull["head"]["sha"]
        subject = {
            "kind": "pull_request", "number": pr,
            "url": pull.get("html_url"), "head_sha": sha,
        }
        response = client.runs(sha)
        runs = response.get("workflow_runs", [])
        if response.get("total_count", 0) > len(runs):
            warnings.append("Only the first 100 matching workflow runs were inspected.")
        warnings.append("Head-SHA queries can miss workflows using synthetic merge commits.")
        try:
            response = client.checks(sha)
            checks = response.get("check_runs", [])
            if response.get("total_count", 0) > len(checks):
                warnings.append("Only the first 100 check runs were inspected.")
        except GitHubError:
            checks = []
            warnings.append("Check runs unavailable; inspection is incomplete.")
    else:
        item = client.run(run)
        subject = {
            "kind": "workflow_run", "number": run,
            "url": item.get("html_url"), "head_sha": item.get("head_sha"),
        }
        runs, checks = [item], []
    result = packet(client.repo, subject, runs, client.jobs, checks, warnings,
                    load_log=client.job_log if with_logs else None,
                    max_log_bytes=max_log_kib * 1024)
    return attach_prescriptions(result) if prescribe_fixes else result


def display(result):
    lines = [
        "SMERGEON / " + result["status"].upper().replace("_", " "),
        result["repository"] + " / " + result["subject"]["kind"] +
        " #" + str(result["subject"]["number"]),
        "",
    ]
    for i, finding in enumerate(result["findings"], 1):
        lines.extend([
            str(i) + ". [" + finding["category"] + "] " +
            str(finding["step"] or finding["job"] or "Workflow"),
            "   Evidence: " + finding["evidence"],
            "   Next: " + finding["next_step"],
            "   URL: " + str(finding["url"] or "(unavailable)"),
        ])
    if not result["findings"]:
        lines.append("No explicit failures in the records inspected.")
    if "prescriptions" in result:
        lines.append("\nREPAIR PRESCRIPTIONS (review-only; not a proven fix):")
        if not result["prescriptions"]:
            lines.append("No validated prescription for the inspected findings.")
        for rx in result["prescriptions"]:
            lines.extend([
                " [" + rx["confidence"] + "] " + rx["title"],
                "   Hypothesis: " + rx["hypothesis"],
                "   Suggested fix: " + rx["proposed_fix"],
                "   Reproduce: " + rx["reproduction"],
                "   Verify: " + rx["verification"],
            ])
            if rx["extra_inspection"]:
                lines.append("   Inspect: " + rx["extra_inspection"])
            lines.append("   Source: " + str(rx["evidence"]["url"] or "(unavailable)"))
        lines.append("Approval required; no scripts, changes or merges executed.")
    if "surgery_plan" in result:
        plan = result["surgery_plan"]
        lines.extend([
            "\nSURGICAL CONSENT (review packet only):",
            "   Plan fingerprint: " + plan["plan_fingerprint"],
            "   Bound PR head: " + plan["binding"]["head_sha"],
            "   Recipes: " + ", ".join(r["category"] for r in plan["binding"]["recipes"]),
            "   Status: " + plan["status"],
            "   No GitHub write, approval, or merge authority granted.",
        ])
        if "fingerprint_matches" in result:
            lines.append("   Fingerprint consistency: " +
                         ("MATCHES" if result["fingerprint_matches"] else "MISMATCH"))
    if result["warnings"]:
        lines.append("\nLIMITATIONS:")
        lines.extend(" - " + note for note in result["warnings"])
    lines.append("\nREAD ONLY: no patches, retries, approvals or merges.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Smergeon read-only GitHub CI triage")
    parser.add_argument("--repo", required=True, help="OWNER/REPO")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--pr", type=int, help="Pull request number")
    target.add_argument("--run", type=int, help="Workflow run ID")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--surgery-plan", action="store_true",
                        help="Create a checksum-bound, read-only PR repair review packet")
    parser.add_argument("--confirm-plan-id", type=str, metavar="SHA256",
                        help="Check a previously copied plan fingerprint against fresh PR state")
    parser.add_argument("--prescribe", action="store_true",
                        help="Opt in to static, review-only repair prescriptions")
    parser.add_argument("--with-logs", action="store_true",
                        help="Opt in to bounded, signature-only job log inspection")
    parser.add_argument("--max-log-kib", type=int, default=256,
                        help="Log read budget per failed job, 1-1024 KiB (default 256)")
    args = parser.parse_args(argv)
    if (args.pr is not None and args.pr < 1) or (args.run is not None and args.run < 1):
        parser.error("Identifiers must be positive.")
    if args.surgery_plan and args.pr is None:
        parser.error("--surgery-plan requires --pr (not --run).")
    if args.confirm_plan_id and not args.surgery_plan:
        parser.error("--confirm-plan-id requires --surgery-plan.")
    if not 1 <= args.max_log_kib <= 1024:
        parser.error("--max-log-kib must be between 1 and 1024.")
    if not args.with_logs and args.max_log_kib != 256:
        parser.error("--max-log-kib requires --with-logs.")
    try:
        result = collect(GitHubClient(args.repo), args.pr, args.run,
                         args.with_logs, args.max_log_kib,
                         args.prescribe or args.surgery_plan)
        if args.surgery_plan:
            plan = make_plan(result)
            result["surgery_plan"] = plan
            if args.confirm_plan_id:
                result["fingerprint_matches"] = verify_plan(
                    plan, result["repository"], args.pr, result["subject"]["head_sha"],
                    args.confirm_plan_id)
                if not result["fingerprint_matches"]:
                    raise PlanError("Plan fingerprint does not match the fresh PR head and diagnosis.")
    except (ValueError, KeyError, GitHubError) as exc:
        print("Intake failed: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json else display(result))
    return 1 if result["status"] == "code_blue" else 0


if __name__ == "__main__":
    raise SystemExit(main())
