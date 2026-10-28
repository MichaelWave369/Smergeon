# Smergeon v0.9: Real-PR Field Qualification

Unit tests are not proof that a GitHub-hosted Cloud Clinic run actually
queried the public GitHub API. This rung adds a **real self-clinic**.

On each opened, updated or reopened same-repository Smergeon PR, GitHub
Actions runs the **already-released** Cloud Clinic from main, not untrusted
PR code. Fork-origin PRs are skipped. It queries the actual open PR and
inspects GitHub check metadata, then confirms that the report names the
correct repository/PR and asserts its zero-authority safety fields.

The output includes three files:
- triage.json: fixed-schema, sanitized metadata with coverage limits
- SUMMARY.md: human-readable, sanitized check classification
- field-qualification.json: proof of a real read-only API observation,
  not proof that CI passed or a repair was performed

Find the seven-day artifact named smergeon-real-pr-field-qualification
on the new pull request's Actions run. Read the regular Python CI checks
separately before merging.

The field job may observe itself as IN PROGRESS and report RECOVERY.
CODE_BLUE, RECOVERY, CLEAR and UNKNOWN all describe **patient status**,
not whether the field-intake workflow succeeded. A green field workflow
only means that a bounded real public GitHub API observation completed
and passed its safety contract.

No target code checkout, target code execution, full log download,
write-scoped token, merge, draft PR, patch, signature or deployment
is involved. All target facts are read-only, partial and never an
authorization for any consequential action.

This workflow modifies Smergeon only. GitPorch and Anti-M remain
separate read-only handoff consumers.

**First, do no merge harm.**
