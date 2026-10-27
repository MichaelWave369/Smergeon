# Smergeon v0.6 · Surgical Handoff Receipts

Status: **portable, unsigned, self-reported interoperability proposal**.
This release does not change GitPorch, SuperPhiVessel, Anti-M, or any remote ledger.

## Why these boundaries matter

GitPorch already has Ed25519 operator reports, witness receipts, and a local
trust registry (see its SIGNED_EVIDENCE, WITNESS and TRUST_POLICY docs).
Those flows require completed worker records, enrolled keys, and verification.

Anti-M has V3/V3.1 **shadow-only** evidence controls and explicitly separates
source custody from severity and authorization. A checksum alone does not
establish custody, consent, truth of a claimed execution, or permission to close.

Smergeon's v0.6 handoff is therefore **not** an instance of either existing
system's trusted/native record schema. No importer, verifier, signing bridge,
automated DONE status, or CI approval is connected by this PR.

## CLI usage

After producing an exact-head v0.4 plan fingerprint and a reviewed v0.5
replacement request, export a **staged-only** handoff:

    python -m smergeon --repo OWNER/REPO --pr 123 \
      --surgery-plan --confirm-plan-id PASTE_64_HEX_PLAN_FINGERPRINT \
      --repair-request repair.json --handoff-out local-receipt.json --json

Nothing is pushed by this command. It merely makes a new, local JSON file
containing the reviewable handoff. The file **must not already exist**.

If the operator separately chooses to create a draft PR, the same flag can
capture the returned draft URL:

    python -m smergeon --repo OWNER/REPO --pr 123 \
      --surgery-plan --confirm-plan-id PASTE_64_HEX_PLAN_FINGERPRINT \
      --repair-request repair.json --write-draft \
      --confirm-write "CREATE DRAFT PR" \
      --handoff-out draft-receipt.json --json

Warning: the second command **does write to GitHub** by creating an isolated
branch and draft PR. Review the replacement and target repository's workflow
permissions first. GitHub Actions may run when a draft is created. This handoff
feature does not add new authority to the v0.5 write operation.

## Receipt contract

Schema: \`smergeon.surgical-handoff.v0.6\`.

The JSON includes only:
- exact source repository, PR number and observed head SHA
- v0.4 review-plan SHA-256 fingerprint and v0.5 operation fingerprint
- file path and before/after Git blob IDs; **never replacement text**
- whether the operation was **STAGED_ONLY** or reported **DRAFT_CREATED**
- in the latter case, a strictly formed GitHub draft PR URL and number
- two intentionally untrusted handoff lanes

### GitPorch lane

\`UNSIGNED_REPAIR_PROPOSAL\`, \`outcome: UNVERIFIED\`.
Fields \`signed_evidence\`, \`witnessed\`, and \`worker_execution_verified\`
are **false**. It cannot be fed to the GitPorch signed-evidence verifier as
though a sandbox job had finished. A future explicit adapter must map
Smergeon to a new, lower-trust *proposal* type before GitPorch can accept it.

### Anti-M lane

\`SHADOW_REVIEW_ONLY\`, provenance \`OPERATOR_REPORT\`, with
\`execution_authority\`, \`closure_authority\`, \`ledger_write\`, and
\`done\` all **false**. It does not masquerade as a V3.1 signed source,
an observed connectivity or impact fact, an assessed severity, or an Anti-M
DONE/closure receipt. Import/promote actions are not implemented.

### Integrity, not authenticity

\`checksum_sha256\` is SHA-256 over canonical JSON body bytes with a domain
separator. It detects accidental changes when the checksum is separately
preserved. An attacker who replaces both JSON and checksum can forge a
self-consistent receipt. No trusted signer identity, Ed25519, worker witness,
append-only storage, CI verification, or independent attestation is claimed.

\`verify_receipt(receipt, independently_known_checksum=None)\` checks exact
schema fields, restricted values and the checksum. It returns only a boolean,
**not approval or authorization**. The exporter creates files exclusively
(\`O_EXCL\`) and never overwrites a prior report. Keep receipts local/private
unless you intentionally disclose repository identifiers and repair details.

## Test and deployment scope

- Negative cases reject tampered status, forged PASS/DONE, malformed draft links,
  invalid plan coupling, wrong branch, mismatched fingerprints, and overwrite.
- Standard CLI has **no** receipt export by default.
- CI tests the Python implementation offline; it does not check GitPorch,
  Anti-M, human approval, or live GitHub draft creation.
- The next interoperability rung would require separately reviewed adapters
  and explicit acceptance tests in the consumer repositories.

**Ledger above ego. First, do no merge harm.**
