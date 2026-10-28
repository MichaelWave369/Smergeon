/* Smergeon Pages Clinic v1.
 * Pure public-CI classification helpers. Never treats clinical observations as
 * branch-protection approval. Untrusted GitHub metadata never becomes HTML.
 */
export const FAILURES = new Set(["failure", "timed_out", "startup_failure", "action_required"]);
const CATEGORY_RULES = [
  ["permissions", /permission|access denied|not accessible|forbidden|unauthorized/i],
  ["dependencies", /dependency|install|npm |pip |module|package|lockfile/i],
  ["tests", /test|pytest|unittest|assertion|vitest|jest|smoke|spec/i],
  ["lint", /lint|format|ruff|flake8|eslint|prettier/i],
  ["build", /build|compile|typecheck|tsc|bundle|webpack|vite/i],
  ["timeout", /timeout|timed.out|time.limit/i],
  ["conflict", /merge.conflict|conflict.marker/i],
];
const SHA = /^[0-9a-f]{40}$/i;
const OWNER = /^[a-zA-Z0-9][a-zA-Z0-9-]{0,38}$/;
const REPO = /^[a-zA-Z0-9_.-]{1,100}$/;
export const LABELS = Object.freeze({
  code_blue: "CODE BLUE",
  recovery: "RECOVERY",
  clear: "CLEAR",
  unknown: "UNDETERMINED",
});

export function parseTarget(raw, rawNumber) {
  const input = String(raw ?? "").trim();
  const clean = input
    .replace(/^https:\/\/github\.com\//i, "")
    .replace(/\/+$/, "");
  const segments = clean.split("/");
  if (segments.length !== 2 || !OWNER.test(segments[0])
      || !REPO.test(segments[1]) || [".", ".."].includes(segments[1])) {
    throw new Error("Enter a public repository as OWNER/REPO.");
  }
  const number = String(rawNumber ?? "").trim();
  if (!/^[1-9]\d{0,8}$/.test(number)) {
    throw new Error("Enter an open pull request number (1 or greater).");
  }
  return {repo: clean, number: Number(number)};
}

export function classify(name) {
  const safe = typeof name === "string" ? name.slice(0, 180) : "";
  for (const [category, re] of CATEGORY_RULES) {
    if (re.test(safe)) return category;
  }
  return "unknown";
}

export function isSha(value) {
  return typeof value === "string" && SHA.test(value);
}

export function analyzeResults(contexts, opts = {}) {
  const categories = new Map();
  let failureCount = 0;
  let pendingCount = 0;
  let cancelledCount = 0;
  let observedCount = 0;
  let partial = Boolean(opts.partial);
  const seen = new Set();
  for (const context of contexts) {
    const items = Array.isArray(context.items) ? context.items.slice(0, 100) : [];
    if (context.total > items.length || (context.items?.length ?? 0) > 100) partial = true;
    for (const item of items) {
      if (!item || typeof item !== "object") continue;
      const unique = [context.kind, context.sha, item.id ?? observedCount].join(":");
      if (seen.has(unique)) continue;
      seen.add(unique);
      observedCount++;
      const conclusion = item.conclusion;
      const status = item.status;
      if (FAILURES.has(conclusion)) {
        failureCount++;
        const category = classify(item.name);
        categories.set(category, (categories.get(category) ?? 0) + 1);
      } else if (conclusion === "cancelled" || conclusion === "neutral") {
        cancelledCount++;
      } else if (!conclusion || status !== "completed") {
        pendingCount++;
      }
    }
  }
  const missingMerge = Boolean(opts.expectMerge) && !opts.mergeInspected;
  const noMergeProof = opts.mergeable === false || opts.mergeable == null;
  let state = "unknown";
  if (failureCount) state = "code_blue";
  else if (pendingCount) state = "recovery";
  else if (observedCount && !partial && !missingMerge && !noMergeProof && !cancelledCount) {
    state = "clear";
  }
  return {
    state,
    observedCount,
    failureCount,
    pendingCount,
    cancelledCount,
    categories: Object.fromEntries([...categories.entries()].sort()),
    coverage: partial ? "PARTIAL" : opts.mergeInspected ? "HEAD + TEST-MERGE" : "HEAD ONLY",
    partial,
    missingMerge,
    mergeable: opts.mergeable ?? null,
    mergeInspected: Boolean(opts.mergeInspected),
    limitations: [
      "Anonymous public GitHub API only; rate limits and missing data can block inspection.",
      "Checks and workflow runs may overlap; observed signals are not unique tests.",
      "The first 100 records per endpoint are inspected. Other refs may carry checks.",
      "CLEAR is not branch-protection approval, an independent CI attestation, or authority to merge.",
      "No job logs, source code, GitHub credentials, write operations, or private repositories are used.",
    ],
    authorization: {
      writes: false,
      drafts: false,
      mergeApproval: false,
    },
  };
}

export function validatePR(pr, target) {
  if (!pr || typeof pr !== "object" || pr.state !== "open"
      || pr.base?.repo?.private !== false
      || String(pr.base?.repo?.full_name || "").toLowerCase() !== target.repo.toLowerCase()
      || !isSha(pr.head?.sha) || pr.number !== target.number) {
    throw new Error("The PR must exist, be open, and belong to a public repository.");
  }
  return {headSha: pr.head.sha.toLowerCase(),
    mergeSha: isSha(pr.merge_commit_sha) ? pr.merge_commit_sha.toLowerCase() : null,
    mergeable: pr.mergeable};
}

export function validateFreshPR(initial, latest, target) {
  const current = validatePR(latest, target);
  if (current.headSha !== initial.headSha
      || current.mergeSha !== initial.mergeSha
      || current.mergeable !== initial.mergeable) {
    throw new Error("The PR changed during inspection. Run the check again.");
  }
  return true;
}

export function toDownloadReport(target, snapshot, diagnosis) {
  return {
    schema: "smergeon.pages-clinic.v1",
    source: {
      repository: target.repo,
      pull_request: target.number,
      inspected_head_sha: snapshot.headSha,
      inspected_test_merge_sha: diagnosis.mergeInspected ? snapshot.mergeSha : null,
    },
    observations: diagnosis,
    trust: "PUBLIC_METADATA_ONLY",
    verified_required_checks: false,
    merge_authorization: false,
  };
}
