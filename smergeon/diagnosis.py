"""Evidence-based classification from GitHub metadata, without modifying GitHub."""

import re

FAIL = {"failure", "timed_out", "startup_failure", "action_required"}
RULES = (
    ("permissions", r"resource not accessible by integration|permission denied|access denied",
     "Check effective token and workflow permissions; do not expand scope blindly."),
    ("dependencies", r"modulenotfounderror|cannot find module|no module named|dependency|npm err",
     "Inspect dependency resolution and locked versions."),
    ("tests", r"assertionerror|tests? failed|pytest|unittest|test suite",
     "Find the earliest assertion and reproduce the test."),
    ("lint", r"ruff|flake8|eslint|prettier|black --check|lint|format check",
     "Inspect linter output and fix only the affected lines."),
    ("build", r"typescript|typecheck|compile|build|tsc",
     "Inspect the first compiler error before editing downstream code."),
    ("timeout", r"timed out|timeout|time limit exceeded",
     "Check duration, resource limits and the last completed step."),
    ("conflict", r"merge conflict|conflict marker|could not apply",
     "Inspect conflicting hunks; do not force-push without approval."),
)


def classify(name, detail=""):
    evidence = str(name or "") + "\n" + str(detail or "")
    for category, pattern, advice in RULES:
        if re.search(pattern, evidence, re.IGNORECASE):
            return category, advice
    return "unknown", "Inspect the failed logs for the earliest actionable error."


def _finding(name, url, run_id=None, job=None, step=None, summary=""):
    category, advice = classify(name, summary)
    return {
        "category": category,
        "evidence": " ".join(str(summary or name).split())[:200],
        "next_step": advice,
        "url": url,
        "run_id": run_id,
        "job": job,
        "step": step,
    }


def packet(repo, subject, runs, load_jobs, checks=(), warnings=()):
    notices = list(warnings)
    findings = []
    pending = False
    seen = False
    for run in runs:
        seen = True
        conclusion = run.get("conclusion")
        if not conclusion or run.get("status") != "completed":
            pending = True
        if conclusion == "cancelled":
            notices.append("Run " + str(run.get("id")) + " was cancelled.")
        if conclusion not in FAIL:
            continue
        try:
            data = load_jobs(run["id"])
        except Exception:
            data = {"jobs": []}
            notices.append("Failed to load jobs for run " + str(run.get("id")) + ".")
        jobs = data.get("jobs", [])
        if data.get("total_count", 0) > len(jobs):
            notices.append("Only part of the jobs were inspected for run " + str(run["id"]) + ".")
        count = 0
        for job in jobs:
            if job.get("conclusion") not in FAIL:
                continue
            failed = [s for s in job.get("steps", []) if s.get("conclusion") in FAIL]
            for step in failed or [None]:
                name = (step or {}).get("name") or job.get("name") or "Failed job"
                findings.append(_finding(
                    name, job.get("html_url") or run.get("html_url"),
                    run.get("id"), job.get("name"), (step or {}).get("name")))
                count += 1
        if not count:
            findings.append(_finding(run.get("name") or "Failed workflow",
                                     run.get("html_url"), run.get("id")))
    for check in checks:
        seen = True
        conclusion = check.get("conclusion")
        if not conclusion or check.get("status") != "completed":
            pending = True
        if conclusion in FAIL:
            output = check.get("output") or {}
            findings.append(_finding(
                check.get("name") or "Failed check", check.get("html_url"),
                summary=output.get("summary") or output.get("title") or ""))
    state = ("code_blue" if findings else "recovery" if pending
             else "clear" if seen else "unknown")
    return {
        "schema": "smergeon.triage.v0.1",
        "repository": repo,
        "subject": subject,
        "status": state,
        "findings": findings,
        "warnings": notices,
        "safety": {"read_only": True, "changes_written": 0, "merges_performed": 0},
    }
