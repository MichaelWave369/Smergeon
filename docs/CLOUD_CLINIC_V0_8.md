# Cloud Clinic v0.8 · Dual-SHA Reality Scan

Smergeon now inspects **two read-only GitHub check contexts**, when they exist:

1. The open pull request's actual branch head SHA.
2. The separate, ephemeral GitHub **test-merge SHA**, reported through
   \`merge_commit_sha\` when the PR is mergeable.

Previously the Cloud Clinic could miss checks attached only to the synthetic
test merge. V0.8 considers those checks without fetching log bodies, running
target code, checking out the target repository or changing GitHub state.

## Report and safety

New JSON/summary fields include \`observed_merge_sha\`,
\`merge_context_status\` and an explicit coverage level:

- \`HEAD_AND_TEST_MERGE_SHA\`: both commit contexts queried.
- \`HEAD_SHA_ONLY\`: merge context not eligible/available.
- \`PARTIAL\`: unavailable or truncated check data.

An incomplete scan can still report an observed \`CODE_BLUE\`, but cannot
report \`CLEAR\` if required diagnostic data were missing. Instead it reports
\`UNKNOWN\`. A second PR metadata read rejects an inspection when the PR
head or merge SHA changed during the queries.

The report is **not** a required-check gate, signed attestation, independent
execution verification, branch-protection decision or merge authorization.
GitHub may recompute a test-merge commit, may paginate beyond the inspected
100 records and may expose checks on refs not covered here. Check signals
are observations, not a deduplicated or complete test count.

The workflow remains **manual-only**, accepts open **public** PRs, and has
only GitHub read permissions. No full logs, raw check summaries, patching,
approvals, workflow reruns, source execution or merges are performed.

## Run from GitHub

Open [Smergeon Cloud Clinic](https://github.com/MichaelWave369/Smergeon/actions/workflows/cloud-clinic.yml),
select **Run workflow**, enter the public repository and open PR number, then
inspect the workflow summary and seven-day sanitized artifact.

Example: \`MichaelWave369/LENZ\` / PR \`2\`, if still open.

See [Cloud Clinic v0.7](CLOUD_CLINIC_V0_7.md) for initial setup and
download instructions.

First, do no merge harm.
