"""Deterministic, review-only repair prescriptions for known CI failure families.

A prescription is a *hypothesis*, never an automatic patch or root-cause claim.
This module deliberately ignores untrusted log bodies, summaries and job names.
"""

# Every suggestion is authored locally and fixed in source, not generated from
# GitHub-provided text. A human must verify applicability before editing code.
CATALOG = {
    "permissions": {
        "title": "Narrow workflow permission mismatch",
        "hypothesis": "The failing job may be missing a required permission.",
        "proposed_fix": "Compare the failing step's documented permission requirement with the workflow's effective token scopes. Adjust only the specific permission after review.",
        "reproduction": "Re-run the failing workflow in a test branch with the same event type and token permission settings.",
        "verification": "Confirm the intended operation succeeds without broadening unrelated permissions.",
    },
    "dependencies": {
        "title": "Restore a missing or incompatible dependency",
        "hypothesis": "The environment may not contain the package or version required by the job.",
        "proposed_fix": "Identify the owning package and expected version; update the appropriate dependency declaration and lockfile only if a mismatch is confirmed.",
        "reproduction": "Use a clean disposable environment with the same runtime and the project's documented install/test commands.",
        "verification": "Confirm a clean dependency install and rerun the originally failing check.",
    },
    "tests": {
        "title": "Reproduce the failing assertion",
        "hypothesis": "The failing test may expose a behavior or expectation mismatch.",
        "proposed_fix": "Reproduce the smallest failing test; correct the implementation or test expectation only after confirming the intended contract.",
        "reproduction": "Run the exact failing test command in a disposable environment matching CI.",
        "verification": "Run the targeted test and the full affected suite to check for regressions.",
    },
    "lint": {
        "title": "Resolve a verified lint violation",
        "hypothesis": "A static analysis rule may reject the current source.",
        "proposed_fix": "Read the specific rule and location, then apply the smallest conforming source change without relaxing lint policy.",
        "reproduction": "Run the repository's pinned lint version and command on the affected files.",
        "verification": "Re-run lint plus relevant tests; check that rules and configuration were not weakened.",
    },
    "build": {
        "title": "Fix the first actionable compiler or build error",
        "hypothesis": "A compilation, type or build-stage error may be blocking CI.",
        "proposed_fix": "Locate the earliest compiler diagnostic and fix its verified source cause rather than suppressing errors or changing unrelated files.",
        "reproduction": "Rebuild with the repository's pinned toolchain, dependencies and CI command.",
        "verification": "Rebuild from a clean environment and run downstream checks.",
    },
    "timeout": {
        "title": "Investigate job timeout",
        "hypothesis": "The job may exceed its expected execution or resource budget.",
        "proposed_fix": "Measure where execution stalls and review network retries, resource use and loops before considering a justified timeout adjustment.",
        "reproduction": "Reproduce with the same runner class and time limits while measuring elapsed steps.",
        "verification": "Confirm a repeatable completion within the expected resource budget.",
    },
    "conflict": {
        "title": "Review conflicting Git changes",
        "hypothesis": "Incompatible edits may block a clean branch update.",
        "proposed_fix": "Inspect both sides of each conflicting hunk and manually resolve intended behavior on an isolated branch; never force-push a protected branch.",
        "reproduction": "Attempt the same merge in a throwaway branch or worktree; inspect conflict markers.",
        "verification": "Run git diff --check and the impacted test suite after the reviewed resolution.",
    },
}

# More specific prescriptions are possible only for allowlisted log signatures.
SIGNATURE_NOTES = {
    "missing Python module": "Check the Python interpreter, import name, declared package and installed environment; these names can differ.",
    "missing JavaScript module": "Inspect the lockfile, module resolution mode, package exports and workspace dependency graph.",
    "package install error": "Inspect the exact failed package and registry/network cause before updating the lockfile.",
    "assertion failure": "Compare actual and expected behavior, not just the test runner's final exit code.",
    "test suite failure": "Find the first failed test and its assertion; the suite summary is not the underlying cause.",
    "lint rule violation": "Identify the specific rule and file instead of disabling the linter.",
    "TypeScript compiler error": "Start from the first TypeScript error code and source location.",
    "compiler error": "Inspect the earliest actionable compiler diagnostic.",
    "permission denied": "Inspect the exact operation and effective token scope, not the entire credential.",
    "timeout detected": "Confirm whether the job stalled, deadlocked or exhausted its allotted time.",
}

COMMON_CHECKS = (
    "git status --short",
    "git diff --check",
)


def prescribe(packet, limit=6):
    """Attach at most one safe, static prescription per recognized category.

    Prefer opt-in bounded-log signatures over step-name heuristics. The
    resulting data contains no arbitrary source messages, paths or commands.
    """
    if not isinstance(limit, int) or not 1 <= limit <= 12:
        raise ValueError("Prescription limit must be between 1 and 12.")
    if packet.get("status") != "code_blue":
        return []
    candidates = {}
    for finding in packet.get("findings", []):
        category = finding.get("category")
        if category not in CATALOG:
            continue
        from_log = finding.get("source") == "bounded_log_signature"
        evidence_text = str(finding.get("evidence") or "")
        signature = evidence_text.partition(" (line ")[0].removeprefix("Log signature: ")
        valid_signature = signature in SIGNATURE_NOTES if from_log else False
        priority = 2 if valid_signature else 1
        old = candidates.get(category)
        if old is None or priority > old[0]:
            candidates[category] = (priority, finding, signature if valid_signature else None)
    output = []
    for category, (priority, finding, signature) in sorted(
            candidates.items(), key=lambda x: (-x[1][0], x[0])):
        template = CATALOG[category]
        output.append({
            "id": "smergeon.rx." + category + ".v0.3",
            "category": category,
            "confidence": "medium" if priority == 2 else "low",
            "confidence_basis": ("Recognized signature in opt-in bounded job log"
                                 if priority == 2 else
                                 "GitHub job/check metadata only"),
            "title": template["title"],
            "hypothesis": template["hypothesis"],
            "proposed_fix": template["proposed_fix"],
            "reproduction": template["reproduction"],
            "verification": template["verification"],
            "extra_inspection": SIGNATURE_NOTES.get(signature) if signature else None,
            "local_preflight_commands": list(COMMON_CHECKS),
            "evidence": {
                "url": finding.get("url"),
                "run_id": finding.get("run_id"),
                "line": finding.get("line") if priority == 2 else None,
            },
            "approval_required": True,
            "patch_created": False,
        })
        if len(output) == limit:
            break
    return output


def attach_prescriptions(packet):
    """Opt-in supplement. Does not mutate its input or execute any commands."""
    updated = dict(packet)
    updated["prescriptions"] = prescribe(packet)
    updated["prescription_policy"] = {
        "review_only": True,
        "commands_executed": 0,
        "patches_created": 0,
        "merges_performed": 0,
        "not_a_root_cause_diagnosis": True,
        "no_recipe_for_unknown_category": True,
    }
    return updated
