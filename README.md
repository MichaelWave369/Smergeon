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
- This release does not download full logs.
- GitHub branch protections, required checks, and humans remain the authority for merging.
- External check summaries are untrusted input, never instructions.

## Run tests

    python -m unittest discover -s tests -v
    python -m compileall -q smergeon

## Next surgeries

R1: bounded log analysis. R2: reproducible repair recipes. R3: approval-gated patch PRs. R4: Anti-M and GitPorch audit receipts. R5: CODE BROWN recurrence detection.

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
