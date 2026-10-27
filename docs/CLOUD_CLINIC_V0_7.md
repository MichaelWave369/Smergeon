# Cloud Clinic v0.7 · GitHub-only public PR diagnosis

Smergeon can now run its **read-only diagnostic clinic entirely in GitHub
Actions**. You do not need Python, Node.js, a local clone, a Windows command
line, or a personal access token on your computer.

The original CLI and approval-gated repair machinery remain separate. The
Cloud Clinic NEVER authorizes a repair, downloads full logs, writes code,
creates a draft PR, merges anything, or executes the target PR's code.

## Run it from GitHub

After v0.7 merges to Smergeon's main branch:

1. Open the repository's **Actions** tab.
2. Choose **Smergeon Cloud Clinic (public PR, read-only)** in the workflow list.
3. Click **Run workflow**, select main, then enter:
   - **repository:** target public repository in OWNER/REPO format
   - **pull_request:** an **open** pull request number in that repository
4. Select **Run workflow**.
5. Open the resulting run. The **Summary** tab shows the sanitized triage.
   Under **Artifacts**, download **smergeon-cloud-clinic-report** to view
   triage.json and SUMMARY.md. Artifacts are retained for seven days.

You can also run the same program as a Python CLI:

    python -m smergeon.cloud_clinic --repo OWNER/REPO --pr 123 --out-dir cloud-clinic-out

The standard GitHub Actions GITHUB_TOKEN is passed only to the read-only
diagnostic client. The workflow's permissions are read-scoped; permissions
do not grant write access to target repositories. Public cross-repository
API access can still be subject to provider restrictions or rate limits.
If an API cannot be read, the workflow fails without inventing results.

## What the report means

- **CODE_BLUE:** one or more failure signals in inspected records.
- **RECOVERY:** checks are still running/queued.
- **CLEAR:** no failure signals among inspected results; NOT confirmation
  that required checks or the entire branch-protection gate passed.
- **UNKNOWN:** no recognized results inspected.
- **Coverage** is HEAD_SHA_ONLY or PARTIAL. Some PR workflows run on a synthetic
  merge SHA, and GitHub may paginate check runs or jobs beyond the inspected
  first 100 records. Results should never be treated as comprehensive.
- **Advice** is fixed review guidance for recognized failure categories, not
  an automatic fix or proven root cause.

For safety, the downloadable report NEVER includes raw logs, check names,
check summaries, job messages, untrusted URLs, tokens, or arbitrary target
repository content. Categories and recommended inspections come only from
Smergeon's checked-in catalog.

A **CODE_BLUE** result is a successful clinical observation and deliberately
does **not** make the Cloud Clinic workflow red. Real intake errors return
a nonzero status and mark that workflow failed.

## Limitations

- Public repositories only. Private repositories are refused, even if your
  GitHub token could otherwise read them. Do not put private details in inputs.
- Open pull requests only. Use the original CLI for targeted run inspection
  or historic cases.
- No background watching or scheduled triage is added.
- No GitHub Pages service, exposed webhook, API endpoint, or elevated OAuth
  permissions.
- Human approval and GitHub's real required-check gate remain authoritative.

## Tests

The GitHub Actions unit matrix tests public-only intake, metadata redaction,
the CODE_BLUE success semantics, immutable artifact writing, deterministic
coverage reports, fail-closed private targets, and absence of repair flags.

**First, do no merge harm.**
