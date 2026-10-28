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

R1 (delivered): bounded log analysis. R2 (delivered): review-only repair prescriptions. R3 (delivered): SHA-bound consent and explicitly approved draft-only repair PRs. R4 (in progress): unsigned GitPorch and Anti-M handoff receipts, then explicit verified adapters. R5: CODE BROWN recurrence detection.

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

## v0.5 The Operating Room: approval-gated, draft-only repair branches

This milestone introduces an **explicitly gated** draft repair executor. The
doctor never generates replacement code: a human must supply and review the
exact replacement text in a local JSON file. The normal read-only CLI remains
the default. The source PR branch is never modified by the repair executor.

**1. Inspect a failing PR and record its plan fingerprint:**

    python -m smergeon --repo OWNER/REPO --pr 123 --surgery-plan --json

**2. Obtain the blob SHA of the exact source file.** For a public repo,
visit \`https://api.github.com/repos/OWNER/REPO/contents/path/to/file.py?ref=FULL_HEAD_SHA\`
and use its \`sha\` field. This is the Git blob SHA, **not** the PR commit SHA.
Do not upload secrets or credentials as replacement text.

**3. Create a local repair request file** (e.g., \`repair.json\`):

    {
      "path": "src/example.py",
      "expected_blob_sha": "REPLACE_WITH_40_HEX_GIT_BLOB_SHA",
      "replacement_text": "# human-reviewed full replacement file\n"
    }

One file per operation. Supported text extensions: Python, JavaScript, TypeScript,
HTML, CSS, JSON, Markdown, TOML, YAML and TXT. Max 64 KiB UTF-8. Hidden,
generated and workflow paths are excluded. The replacement is a **full file**,
not a diff hunk, and it must actually differ from the expected original blob.

**4. Dry-run first (no GitHub write access required):**

    python -m smergeon --repo OWNER/REPO --pr 123 --surgery-plan \
      --confirm-plan-id PASTE_64_HEX_PLAN_FINGERPRINT --repair-request repair.json --json

Dry run prints a deterministic operation fingerprint, target head, before/after
blob SHA and proposed isolated branch. It never prints the replacement text.
Do not proceed if the fingerprint or review details are unexpected.

**5. Only after explicitly reviewing and approving the replacement:**

    python -m smergeon --repo OWNER/REPO --pr 123 --surgery-plan \
      --confirm-plan-id PASTE_64_HEX_PLAN_FINGERPRINT --repair-request repair.json \
      --write-draft --confirm-write "CREATE DRAFT PR" --json

For this command, \`GITHUB_TOKEN\` must be an authenticated token with only the
repository's required contents and pull-request write permissions. Keep the
token out of scripts, shell command arguments and printed logs.

### Enforcement and limitations

- Confirmed write mode rechecks the PR's open status, the exact head commit,
  same-repo ownership, and the expected file blob before any GitHub mutation.
- It creates new Git blob/tree/commit objects, then a separate
  \`smergeon/repair-pr...\` branch and a **draft PR targeting the original PR's
  head branch**, not main. It does **not** push to that source branch.
- A stale PR or unexpected blob fails closed. GitHub requests are HTTPS-only
  with no redirects; API errors never reproduce token-bearing headers.
- Only one existing regular file can be replaced in this version. No deletes,
  new files, command execution, workflow changes, approvals or merges.
- A race or API failure can leave unattached objects or a repair branch without
  a draft PR. Review and clean up such branches manually.
- GitHub may run CI when a draft PR opens. Review the replacement and the
  repository's workflows before authorizing creation.
- The v0.4 SHA-256 fingerprint checks **consistency**, not identity or legal
  consent. The extra write command is an explicit local action; GitHub still
  enforces authenticated account permissions and repository rules.
- Independent CI, peer review and manual merge are required to complete a fix.

**The default remains diagnostic-only.** No background automation or
self-authorized changes to other repositories are enabled.

## v0.6 Surgical Receipts · GitPorch / Anti-M shadow handoff

Portable, **unsigned and explicitly unverified** handoff records can now be
exported with \`--handoff-out NEW_FILE.json\` after preparing an exact-head
surgery plan and repair request. The export is opt-in, local-only and
never overwrites an existing file. The normal read-only CLI does not export.

See [Surgical Handoff v0.6](docs/SURGICAL_HANDOFF_V0_6.md) for example
commands, receipt fields, integrity limitations, and GitPorch/Anti-M
trust boundaries. **This does not install a GitPorch or Anti-M importer,
create signed evidence, grant completion authority, or merge anything.**

## v0.7 Cloud Clinic (no local install)

Run read-only triage from **GitHub → Actions → Smergeon Cloud Clinic** after
v0.7 is merged to main. Enter the public OWNER/REPO and an open PR number,
then view its workflow summary and download the sanitized \`triage.json\`
artifact. No logs, code edits or merge permissions are involved.

See [Cloud Clinic instructions](docs/CLOUD_CLINIC_V0_7.md).

## v0.8 · Dual-SHA Reality Scan

The Cloud Clinic now checks both an open PR's head commit and its available
GitHub test-merge commit. Missing or truncated checks are marked PARTIAL;
an incomplete inspection cannot claim CLEAR. No merge permissions are added.

See [Dual-SHA Reality Scan](docs/CLOUD_CLINIC_V0_8.md).

## v0.9 · Real-PR Field Qualification

GitHub Actions now runs the released Cloud Clinic against actual open
Smergeon pull requests (same-repository only). It saves three sanitized
artifacts proving API intake, not a successful repair or merge approval.

See [Real-PR Field Qualification](docs/FIELD_QUALIFICATION_V0_9.md).

## Repository Hospital · GitHub Pages

The public website **[Smergeon Repository Hospital](https://michaelwave369.github.io/Smergeon/)**
provides a custom, static clinic UI for read-only, anonymous metadata
checks of open public pull requests, plus one-click access to the
full GitHub Actions Cloud Clinic.

The browser checker does **not** invoke the Python engine, inspect logs,
download target source, or grant merge authority. GitHub Pages needs
to be enabled under **Settings → Pages → Source → GitHub Actions**
before the URL works.

See [GitHub Pages clinic deployment & test guide](docs/GITHUB_PAGES_CLINIC_V1.md).

## CODE BROWN · On-demand recurring-failure watch

In the [Repository Hospital](https://michaelwave369.github.io/Smergeon/),
admit an open public PR, then explicitly press **SCAN REPEAT FAILURES**.
The browser compares recent failures of the same GitHub workflow across
distinct PR revisions. It requires three consecutive failed revisions to
report **CODE BROWN**, without falsely claiming the same bug or root cause.

See [CODE BROWN v1 contract](docs/CODE_BROWN_V1.md).
