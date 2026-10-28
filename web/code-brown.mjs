/* CODE BROWN v1: evidence-limited, on-demand recurring workflow failure watch.
 * Public GitHub Actions metadata only. NEVER uses names or logs as a causal
 * fingerprint; matches only stable workflow IDs on three distinct PR commits.
 */
const SHA = /^[0-9a-f]{40}$/i;
const SEGMENT = /^[A-Za-z0-9_-]+(?:[A-Za-z0-9_.-]*[A-Za-z0-9_-])?$/;
const FAIL = new Set(['failure','timed_out','startup_failure','action_required']);
const BLOCKED = new Set(['.', '..']);
const MAX_RESULTS = 50;

function validPositive(x) {
  return Number.isSafeInteger(x) && x > 0;
}
export function safeBranch(ref) {
  return typeof ref === 'string' && ref.length <= 150
    && ref.length > 0 && !ref.startsWith('-')
    && !ref.includes('..') && !ref.includes('@{')
    && ref.split('/').every(piece => SEGMENT.test(piece) && !BLOCKED.has(piece));
}
export function bindCodeBrownSource(pr, target) {
  const head = pr?.head;
  if (pr?.state !== 'open' || pr?.base?.repo?.private !== false ||
      String(pr?.base?.repo?.full_name || '').toLowerCase() !== target.repo.toLowerCase() ||
      pr?.number !== target.number ||
      !SHA.test(head?.sha || '') ||
      String(head?.repo?.full_name || '').toLowerCase() !== target.repo.toLowerCase() ||
      !safeBranch(head?.ref)) {
    throw new Error('CODE BROWN requires an open, same-repository public PR with a safe branch.');
  }
  return Object.freeze({
    repository: target.repo,
    pull_request: target.number,
    branch: head.ref,
    observed_head_sha: head.sha.toLowerCase(),
  });
}
export function confirmSameCodeBrownSource(before, current, target) {
  const after = bindCodeBrownSource(current,target);
  if(before.repository !== after.repository ||
     before.pull_request !== after.pull_request ||
     before.branch !== after.branch ||
     before.observed_head_sha !== after.observed_head_sha)
    throw new Error('The PR head or source branch changed during the trend check.');
  return true;
}
function eligible(run, source) {
  if (!run || typeof run !== 'object' ||
      !validPositive(run.id) || !validPositive(run.workflow_id) ||
      !SHA.test(run.head_sha || '') ||
      run.event !== 'pull_request' ||
      run.head_branch !== source.branch ||
      String(run.head_repository?.full_name || '').toLowerCase() !== source.repository.toLowerCase() ||
      !Array.isArray(run.pull_requests) ||
      !run.pull_requests.some(pr => pr && pr.number === source.pull_request) ||
      typeof run.created_at !== 'string' ||
      !Number.isFinite(Date.parse(run.created_at))) return false;
  return true;
}
export function analyzeCodeBrown(data, source) {
  if (!data || !Array.isArray(data.workflow_runs) ||
      !validPositive(source?.pull_request) || !safeBranch(source?.branch) ||
      !SHA.test(source?.observed_head_sha || '')) {
    throw new Error('Trend source or GitHub run page is invalid.');
  }
  if (data.workflow_runs.length > MAX_RESULTS ||
      !Number.isSafeInteger(data.total_count) || data.total_count < data.workflow_runs.length) {
    throw new Error('GitHub run history is malformed or exceeds the 50-run bound.');
  }
  const partial = data.total_count > data.workflow_runs.length;
  const seenIds = new Set();
  const byWorkflow = new Map();
  const eligibleRuns = data.workflow_runs.filter(run => {
    if (!eligible(run,source) || seenIds.has(run.id)) return false;
    seenIds.add(run.id); return true;
  });
  eligibleRuns.sort((a,b) => Date.parse(b.created_at)-Date.parse(a.created_at) || b.id-a.id);
  for(const run of eligibleRuns){
    if(!byWorkflow.has(run.workflow_id)) byWorkflow.set(run.workflow_id,[]);
    byWorkflow.get(run.workflow_id).push(run);
  }
  const workflows = [];
  for(const [workflowId, runs] of byWorkflow){
    // Ignore re-runs of the same revision: three attempts on one bad commit
    // do not prove recurrence across code revisions.
    const seenShas = new Set();
    const revisions = runs.filter(run => {
      const sha=run.head_sha.toLowerCase();
      if(seenShas.has(sha)) return false;
      seenShas.add(sha); return true;
    });
    const completed = revisions.filter(run => run.status === 'completed');
    let failedStreak = 0;
    for(const run of completed){
      if (!FAIL.has(run.conclusion)) break;
      failedStreak++;
    }
    const latest3 = completed.slice(0,3);
    const evidence = latest3.filter(run => FAIL.has(run.conclusion));
    const pending = revisions.filter(run => run.status !== 'completed').length;
    const record = {
      workflow_id: workflowId,
      recent_completed_revisions: completed.length,
      pending_revisions: pending,
      consecutive_failed_revisions: failedStreak,
      recent_run_ids: latest3.map(run => run.id),
      evidence_run_ids: failedStreak >= 3 ? latest3.map(run => run.id) : [],
      current_head_has_run: revisions.some(run =>
        run.head_sha.toLowerCase() === source.observed_head_sha.toLowerCase()),
      status: failedStreak >= 3 ? 'REPEATED_FAILURE_OBSERVED' :
        failedStreak >= 2 ? 'WATCH' : 'NOT_ESTABLISHED',
    };
    workflows.push(record);
  }
  workflows.sort((a,b) => b.consecutive_failed_revisions - a.consecutive_failed_revisions
    || a.workflow_id-b.workflow_id);
  const repeated = workflows.filter(w => w.status === 'REPEATED_FAILURE_OBSERVED');
  const watching = workflows.filter(w => w.status === 'WATCH');
  return {
    schema: 'smergeon.code-brown.v1',
    source: {...source},
    outcome: repeated.length ? 'CODE_BROWN' :
      watching.length ? 'WATCH' : 'INSUFFICIENT_EVIDENCE',
    examined_runs: data.workflow_runs.length,
    bound_to_pr_runs: eligibleRuns.length,
    workflows: workflows.slice(0,25),
    repeated_workflows: repeated.length,
    watching_workflows: watching.length,
    coverage: partial || eligibleRuns.length === 0 ? 'PARTIAL' : 'RECENT_50_ONLY',
    trust: 'PUBLIC_METADATA_ONLY',
    causal_equivalence_proven: false,
    current_failure_proven: false,
    merge_authorization: false,
    permissions_granted: false,
    note: 'Matching workflow IDs across distinct revisions is recurrence of workflow failure status, not proof of identical errors or root causes.',
  };
}
