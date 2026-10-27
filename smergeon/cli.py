"""Read-only PR and Actions CLI. Code BLUE exits 1; intake errors exit 2."""

import argparse
import json
import sys

from .diagnosis import packet
from .github import GitHubClient, GitHubError


def collect(client, pr=None, run=None):
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
    return packet(client.repo, subject, runs, client.jobs, checks, warnings)


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
    args = parser.parse_args(argv)
    if (args.pr is not None and args.pr < 1) or (args.run is not None and args.run < 1):
        parser.error("Identifiers must be positive.")
    try:
        result = collect(GitHubClient(args.repo), args.pr, args.run)
    except (ValueError, KeyError, GitHubError) as exc:
        print("Intake failed: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json else display(result))
    return 1 if result["status"] == "code_blue" else 0


if __name__ == "__main__":
    raise SystemExit(main())
