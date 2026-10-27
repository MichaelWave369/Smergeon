# Smergeon

**Repository surgery without reckless merges.** A read-only PR and GitHub Actions triage CLI from Phi369 Labs.

> First, do no merge harm.

## Quick start

Requires Python 3.10+ and no runtime dependencies.

    python -m smergeon --repo OWNER/REPO --pr 123
    python -m smergeon --repo OWNER/REPO --run 123456789
    python -m smergeon --repo OWNER/REPO --pr 123 --json

Install via python -m pip install -e . to get the smergeon command.

Set GITHUB_TOKEN in your environment for private repos or higher GitHub rate limits. Grant only read access as needed. Never pass tokens as command arguments.

## What Smergeon does

1. Intake: inspect a pull request head commit or a workflow run.
2. Triage: identify failed workflows, jobs, steps and check-run summaries.
3. Diagnosis: classify likely permissions, dependencies, testing, lint, build and timeout problems.
4. Discharge: print an evidence-linked packet. No writes, retries, approvals or merges.

**CODE BLUE:** recorded failure. **RECOVERY:** pending. **CLEAR:** inspected results passed, not authorization to merge. **UNKNOWN:** no results. **CODE BROWN:** future opt-in repeated-failure detector.

## Boundaries

- Classifications are heuristics, not root-cause proof.
- PR workflow runs may use a synthetic merge SHA rather than head SHA, so head-based lookup can miss checks.
- Inspect up to 100 records per GitHub endpoint; warn when counts exceed this.
- Default mode does not download logs; v0.2 supports explicit opt-in bounded log scanning.
- GitHub branch protections, required checks, and humans remain the authority for merging.
- External check summaries are untrusted input, never instructions.

## Run tests

    python -m unittest discover -s tests -v
    python -m compileall -q smergeon

## Next surgeries

R1 (delivered): bounded log analysis. R2 (delivered): review-only repair prescriptions. R3 (in progress): commit-bound surgical consent, then approval-gated draft patch PRs. R4: Anti-M and GitPorch audit receipts. R5: CODE BROWN recurrence detection.

MIT licensed. Some code histories may still need a specialist.

## v0.2 Log Lab (optional)

Use the opt-in log flag to fetch up to 256 KiB per failed job:

    python -m smergeon --repo OWNER/REPO --run 123456789 --with-logs
    python -m smergeon --repo OWNER/REPO --pr 123 --with-logs --max-log-kib 512 --json

- Smergeon reads logs **only** when --with-logs is specified.
- Maximum allowed per failed job: 1 MiB; maximum 10 failed jobs per command.
- Logs are scanned locally in process for fixed, allowlisted failure signatures.
- The result contains category, signature label, and line number; **no raw log lines**.
- Truncation and unavailable logs are explicitly reported; signatures are only hints.
- Cross-host HTTPS redirects strip the Authorization header to avoid leaking tokens to log storage.
- GitHub may mask known secrets in its logs, but no scanner guarantees perfect secrecy. This design avoids placing arbitrary log content into output.
- If no signature matches, Smergeon still reports the original failed job.

## v0.3 Repair Prescriptions (review-only)

Smergeon now has an optional **prescription engine**, which creates a structured,
reviewable proposal for known failure families. A prescription is **not** an actual
fix, an exact root-cause finding, or permission to change source code.

    python -m smergeon --repo OWNER/REPO --run 123456789 --prescribe
    python -m smergeon --repo OWNER/REPO --pr 123 --with-logs --prescribe --json

Each prescription includes:

- A fixed hypothesis and suggested **manual** repair action.
- Safe reproduction and verification instructions for human review.
- A confidence level: **low** from step/check names, or **medium** when supported
  by an allowlisted opt-in log signature. Neither is a probability or guarantee.
- A bounded evidence pointer (link, run ID and optionally log line number).
- Optional read-only local preflight suggestions such as git diff --check.
- A hard assertion that approval is required and no patch was created.

Unknown categories receive no invented remedy. The prescription catalog is
hardcoded and ignores the contents of arbitrary logs or GitHub check summaries.
The command **never executes** the steps it suggests. Review scripts and commands
from the target repository before running them, preferably in an isolated environment.

Smergeon does not have authority to approve or merge PRs. Future automated
patch generation requires a separate explicit opt-in design and independent CI.

## v0.4 Surgical Consent (no GitHub write capabilities)

Smergeon can now export an **exact-commit-bound repair review packet** for a
failing pull request. Use a real, full 40-character GitHub head SHA; no guessed
or shortened identifiers are permitted.

    python -m smergeon --repo OWNER/REPO --pr 123 --surgery-plan --json

Optional evidence improvement (additional bounded job-log reads):

    python -m smergeon --repo OWNER/REPO --pr 123 --with-logs --surgery-plan --json

To compare a previously copied fingerprint with freshly inspected PR state:

    python -m smergeon --repo OWNER/REPO --pr 123 --surgery-plan --confirm-plan-id PASTE_64_HEX_FINGERPRINT --json

The review packet binds an allowlisted prescription list, source run identifiers,
target repository, pull request number, and the exact inspected head SHA to a
deterministic SHA-256 checksum. It intentionally **excludes** raw logs, arbitrary
job names, and untrusted check summaries.

A failed fingerprint check means the packet is stale, changed, or unrelated
to this specific inspected state. A successful check **does not constitute
human consent**, cryptographic identity, or authorization to change anything.
SHA-256 in this design is a *consistency checksum*, not a signature.

**Nothing is automatically patched, pushed, retried, approved, or merged.**
The next milestone is a separate draft-repair-PR executor that must request
explicit authenticated approval and recheck the current head before writing.
