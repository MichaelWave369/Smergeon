# Smergeon CODE BROWN v1 · Repeating CI Failure Watch

The Repository Hospital now has an **opt-in, read-only history check** inside
the Patient Chart. It does not perform repairs or automatically monitor the
user's repositories.

## Run it

1. Visit https://michaelwave369.github.io/Smergeon/ .
2. Admit a **public, open pull request** using regular browser triage.
3. Under the Patient Chart, press **SCAN REPEAT FAILURES**.
4. Review the CODE BROWN or WATCH result, workflow IDs, and source GitHub run
   links. Independently inspect the individual runs to identify root causes.

The trend feature requires a **same-repository PR branch**. Fork-origin
branches are refused for this history matching method.

### What CODE BROWN actually means

For a specific PR and stable GitHub Actions \`workflow_id\`:

- Examine at most 50 recent public Actions runs, constrained by the PR branch.
- Only admit runs whose GitHub metadata explicitly links the **same PR
  number, repository, branch and pull_request event**.
- De-duplicate reruns of the **same commit SHA** so repeatedly retrying a
  single broken commit cannot masquerade as recurrence across revisions.
- Require the most recent **three completed revisions** of that workflow
  to have failing conclusions before announcing **CODE BROWN**.
- Exactly two such failing revisions yield **WATCH**, not CODE BROWN.
- A successful or cancelled completed revision interrupts the consecutive
  failed-run streak. Pending revisions are separately disclosed and do not
  establish a new completed outcome.
- A workflow with a different numeric GitHub \`workflow_id\` is **not**
  treated as the same workflow merely because its display name matches.

The result identifies repeated **workflow failure status**, not the same
compiler error, failing test, shared cause or verified current head health.
GitHub workflows may have been renamed or rewritten under the same ID. The
report explicitly sets:

\`causal_equivalence_proven: false\`
\`current_failure_proven: false\`
\`merge_authorization: false\`
\`permissions_granted: false\`

### Uncertainty and privacy

The first 50 run records may be incomplete or unrelated to the exact PR.
If GitHub pagination truncates the query, the report states **PARTIAL**
coverage. If there are no eligible bound runs, the result is
**INSUFFICIENT EVIDENCE**, never "no recurring failures."

The browser fetches data **only on explicit click**, using its existing
anonymous, credential-free GitHub GET client. PR source head and branch are
checked again before and after the history query to refuse a stale reading.

Only validated **numeric workflow IDs, run IDs, commit comparisons, counts
and fixed labels** are displayed. Remote run names, job text, user comments,
raw log bodies or arbitrary URLs never appear in the report. Source links
are reconstructed from the validated target repository and numeric run IDs.

No token, login, local storage, uploads, webhook, cron, background polling,
patch, worker queue, automatic test retry or merge action is involved.

### Verification

GitHub CI runs new Node tests for three distinct failed revisions,
same-commit rerun de-duplication, intervening successes, pending updates,
foreign PR exclusion, workflow-ID isolation, truncated results, malicious
names and invalid history. Python static checks verify the opt-in click
surface and absence of write operations.

**First, do no merge harm. Ledger above ego.**
