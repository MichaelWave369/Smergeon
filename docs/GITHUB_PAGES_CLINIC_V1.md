# Smergeon GitHub Pages · Repository Hospital v1

**Live location, once GitHub Pages is enabled and the main deployment succeeds:**
https://michaelwave369.github.io/Smergeon/

Smergeon's main GitHub Actions Cloud Clinic remains the canonical Python
diagnostic workflow. The new Pages site adds a friendly, completely static
front door with a separate **anonymous browser-only public PR checker**.

## What visitors can do

1. Open the public Repository Hospital page.
2. Enter an open public GitHub repository as OWNER/REPO and a PR number,
   or a standard https://github.com/OWNER/REPO URL.
3. Click **Begin Triage**. Only then does the browser request public
   PR, workflow-run and check-run metadata from GitHub's REST API.
4. Review observed statuses: CODE BLUE, RECOVERY, CLEAR or UNDETERMINED.
   See count of observed records, recognized failure categories, and
   explicit scope/head/test-merge coverage.
5. Open the source PR, or optionally save the sanitized, fixed-schema
   JSON report locally. The export includes no raw check names or logs.
6. For the Python diagnostic engine, click **GitHub Cloud Clinic**.
   GitHub's Actions workflow requires manual dispatch and input of
   the repository and PR number. The Pages site does NOT dispatch it.

The site works without a backend, external font/CDN, account connection,
GitHub OAuth permission, personal access token or local software install.

## Deployment

This PR introduces \`.github/workflows/pages.yml\`. On merge to \`main\`,
the workflow uploads only the \`web/\` directory and deploys it using
GitHub's official Pages actions.

If Pages is not already configured, the repository owner must visit:

**Repository Settings → Pages → Build and deployment → Source →
GitHub Actions.**

Then run **Deploy Smergeon Repository Hospital** from Actions if
necessary. Deployments only publish main, never unreviewed PR branches.
The page is public. The clinic inspects public PR metadata only.

## Scope and limitations

Browser clinic:
- Only *open, public* PRs; target code is never downloaded or executed.
- No writes, credential forwarding, patch generation, approvals, mergers
  or automatic reruns. Inputs do not grant GitHub permissions.
- GitHub's unauthenticated public API is rate-limited and subject to
  browser CORS/connectivity. Error states are honest and fail closed.
- Checks and runs may overlap or exist on other refs. The first
  100 records per head/test-merge endpoint are examined.
- All displayed data from GitHub are limited to validated target
  identifiers, SHA prefixes, fixed statuses and allowlisted categories.
  Untrusted titles/check descriptions are never interpolated as HTML.
- A second live PR read rejects changed head/test-merge commits before
  issuing a report. A clean result is still **not** the required-check
  gate, test attestation, code review, or permission to merge.
- The exported JSON is a **local metadata snapshot**, not a verified
  GitPorch worker report or Anti-M closure receipt.
- No recurring CI-failure detector is claimed: CODE BROWN remains planned.

Security:
- Browser uses only anonymous GET operations to api.github.com,
  with \`credentials: "omit"\` and no Authorization header.
- Static site assets are bundled locally and served by Pages.
- No localStorage, cookies, telemetry, advertising, workers, analytics
  or server-side submission of user inputs.
- GitHub Pages deployment needs \`pages: write\` and \`id-token: write\`
  for the official Pages job. **Those privileges belong only to that
  deployment workflow**, not to the site/browser, and do not authorize
  repository repair or merges.

## Verification

Normal Smergeon CI adds \`pages-clinic-tests\` (Node 22) alongside
Python 3.10 and 3.12. Node tests cover input validation, merge-only
failures, partial reports, pending/cancelled outcomes, stale commits
and redacted exports. Python tests verify the local-only static asset
surface and the release-only Pages deployment policy.

Field/browser checks after deployment:
- Confirm desktop and mobile layout, keyboard navigation and reduced
  motion; check all links in a browser.
- On a genuinely open public PR, click Begin Triage. Compare reported
  SHA and observed checks to GitHub's PR Checks tab.
- Observe a pending test if available; it must never be marked CLEAR.
- Try closed/private PRs, invalid repository names and unavailable
  API/rate-limit conditions; the site must not invent success.
- Exercise Export JSON and verify no check names or access tokens.
- Confirm Pages did not run any repair or merge and does not claim
  complete CI qualification.

**First, do no merge harm. Ledger above ego.**
