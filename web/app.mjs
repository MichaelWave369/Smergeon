/* Browser-only Smergeon public-clinic intake.
 * All GitHub API calls require a user form submission. No tokens, storage,
 * raw logs, source checkout, GitHub mutations, or executable remote content.
 */
import {
  LABELS, analyzeResults, isSha, parseTarget, toDownloadReport,
  validateFreshPR, validatePR,
} from "./clinic-core.mjs";
import {
  analyzeCodeBrown, bindCodeBrownSource, confirmSameCodeBrownSource
} from "./code-brown.mjs";

const form = document.getElementById("intake-form");
const repoInput = document.getElementById("repo");
const prInput = document.getElementById("pr-number");
const output = document.getElementById("input-status");
const button = document.getElementById("inspect-button");
const panel = document.getElementById("report-panel");
const badge = document.getElementById("diagnosis-badge");
const categoryList = document.getElementById("category-list");
const downloadButton = document.getElementById("download-report");
const brownButton = document.getElementById("brown-button");
const brownStatus = document.getElementById("brown-status");
const brownResults = document.getElementById("brown-results");
let lastReport = null;
let trendPatient = null;
let active = false;
let trendBusy = false;

const explanations = {
  code_blue: "Failed checks were observed. Follow the original GitHub checks and investigate their first actionable errors. This is not a proven root cause.",
  recovery: "Some observed workflows or checks have not finished. Do not treat an in-progress patient as cleared.",
  clear: "No failures were seen in the inspected contexts, but this is NOT GitHub's required-check gate or authorization to merge.",
  unknown: "Evidence is absent, incomplete, cancelled, inaccessible, or mergeability is unresolved. No clean bill of health can be issued.",
};

const params = new URLSearchParams(location.search);
if (params.has("repo")) repoInput.value = params.get("repo")?.slice(0, 150) ?? "";
if (params.has("pr")) prInput.value = params.get("pr")?.slice(0, 9) ?? "";

function setInputStatus(text, error = false) {
  output.textContent = text;
  output.classList.toggle("error", error);
}

function reportUrl(repo, path) {
  return "https://api.github.com/repos/" + repo + "/" + path;
}

async function apiGET(url, signal) {
  const response = await fetch(url, {
    method: "GET",
    headers: {"Accept": "application/vnd.github+json"},
    credentials: "omit",
    redirect: "error",
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    if (response.status === 403 || response.status === 429) {
      throw new Error("GitHub denied this read, possibly because of its anonymous API rate limit. Use Cloud Clinic in Actions or try later.");
    }
    if (response.status === 404) {
      throw new Error("GitHub did not find this public PR or check endpoint.");
    }
    throw new Error("GitHub public API returned HTTP " + response.status + ".");
  }
  return response.json();
}

function sanitizeArray(obj, field) {
  return Array.isArray(obj?.[field]) ? obj[field].slice(0, 100) : [];
}

async function fetchContext(target, sha, signal) {
  const path = reportUrl(target.repo, "");
  const apiCalls = [
    {kind:"run", url: path + "actions/runs?head_sha=" + sha + "&per_page=100", key:"workflow_runs"},
    {kind:"check", url: path + "commits/" + sha + "/check-runs?per_page=100", key:"check_runs"},
  ];
  const resolved = await Promise.allSettled(apiCalls.map(item => apiGET(item.url, signal)));
  const contexts = [];
  let incomplete = false;
  for (let i = 0; i < resolved.length; i++) {
    const result = resolved[i];
    const endpoint = apiCalls[i];
    if (result.status !== "fulfilled") {
      incomplete = true;
      continue;
    }
    const records = sanitizeArray(result.value, endpoint.key);
    const total = Number.isSafeInteger(result.value?.total_count)
      ? result.value.total_count : records.length;
    contexts.push({kind:endpoint.kind, sha, items:records, total});
    if (total > records.length) incomplete = true;
  }
  return {contexts, incomplete};
}

function categoryRow(name, count) {
  const el = document.createElement("div");
  el.className = "category";
  const text = document.createElement("span");
  text.textContent = name.toUpperCase();
  const value = document.createElement("b");
  value.textContent = String(count);
  el.append(text, value);
  return el;
}

function showReport(target, snapshot, diagnosis) {
  panel.hidden = false;
  badge.textContent = LABELS[diagnosis.state];
  badge.className = "diagnosis-badge " + diagnosis.state;
  document.getElementById("diagnosis-description").textContent = explanations[diagnosis.state];
  document.getElementById("metric-observed").textContent = String(diagnosis.observedCount);
  document.getElementById("metric-failed").textContent = String(diagnosis.failureCount);
  document.getElementById("metric-pending").textContent = String(diagnosis.pendingCount);
  document.getElementById("metric-coverage").textContent = diagnosis.coverage;
  categoryList.replaceChildren();
  const rows = Object.entries(diagnosis.categories);
  if (rows.length) {
    for (const [name, count] of rows) categoryList.append(categoryRow(name,count));
  } else {
    const el = document.createElement("p");
    el.textContent = "NO FAILED CHECK CATEGORIES OBSERVED.";
    categoryList.append(el);
  }
  const notes = [
    "Head SHA: " + snapshot.headSha.slice(0, 12) + "…",
    diagnosis.mergeInspected
      ? "Test-merge SHA: " + snapshot.mergeSha.slice(0, 12) + "…"
      : "Test-merge context: NOT INSPECTED",
    "GitHub mergeability: " + (
      snapshot.mergeable === true ? "REPORTED MERGEABLE" :
      snapshot.mergeable === false ? "NOT MERGEABLE" : "UNRESOLVED"),
    diagnosis.partial || diagnosis.missingMerge ?
      "Coverage is limited; this is not a comprehensive CI diagnosis." :
      "Inspected records only. GitHub remains the approval authority.",
  ];
  document.getElementById("source-status").textContent = notes.join("  ·  ");
  document.getElementById("view-pr").href =
    "https://github.com/" + target.repo + "/pull/" + target.number;
  lastReport = toDownloadReport(target, snapshot, diagnosis);
  setInputStatus("TRIAGE COMPLETE · " + LABELS[diagnosis.state] +
    " · NO GITHUB WRITES");
}

function getErrorMessage(error) {
  if (error?.name === "AbortError") return "GitHub took too long to respond. Please try again.";
  if (error instanceof TypeError) return "The GitHub API was unreachable from this browser. Try the full Actions Cloud Clinic.";
  if (error instanceof Error) return error.message;
  return "Inspection failed; no diagnostic claim can be made.";
}

async function triage(event) {
  event.preventDefault();
  if (active || trendBusy) return;
  let target;
  try {
    target = parseTarget(repoInput.value, prInput.value);
  } catch (error) {
    setInputStatus(getErrorMessage(error), true);
    return;
  }
  active = true;
  lastReport = null;
  trendPatient = null;
  brownButton.disabled = true;
  brownResults.hidden = true;
  brownStatus.textContent = "COMPLETE TRIAGE FIRST";
  button.disabled = true;
  button.textContent = "INSPECTING PUBLIC CI…";
  setInputStatus("CONTACTING GITHUB · METADATA READ ONLY");
  panel.hidden = true;
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), 20000);
  try {
    const source = reportUrl(target.repo, "pulls/" + target.number);
    const rawInitialPR = await apiGET(source, abort.signal);
    const initial = validatePR(rawInitialPR, target);
    const first = await fetchContext(target, initial.headSha, abort.signal);
    let contexts = first.contexts;
    let partial = first.incomplete;
    let mergeInspected = false;
    const expectMerge = initial.mergeable === true;
    if (expectMerge && initial.mergeSha && isSha(initial.mergeSha)
        && initial.mergeSha !== initial.headSha) {
      const second = await fetchContext(target, initial.mergeSha, abort.signal);
      contexts = contexts.concat(second.contexts);
      partial = partial || second.incomplete;
      mergeInspected = second.contexts.length > 0 && !second.incomplete;
    } else if (expectMerge) {
      partial = true;
    }
    if (contexts.length === 0) {
      throw new Error("No public check metadata was accessible. Use the full Cloud Clinic through GitHub Actions.");
    }
    validateFreshPR(initial, await apiGET(source, abort.signal), target);
    const diagnosis = analyzeResults(contexts, {
      partial,
      expectMerge,
      mergeInspected,
      mergeable: initial.mergeable,
    });
    showReport(target, initial, diagnosis);
    // This optional check deliberately refuses fork-origin PRs and unsupported
    // branch names; regular read-only CI triage still works for those PRs.
    try {
      trendPatient = bindCodeBrownSource(rawInitialPR, target);
      brownButton.disabled = false;
      brownStatus.textContent = "OPTIONAL · PUBLIC HISTORY · READ ONLY";
    } catch {
      brownButton.disabled = true;
      brownStatus.textContent = "UNAVAILABLE FOR FORK OR UNSUPPORTED BRANCH";
    }
    const path = new URL(location.href);
    path.searchParams.set("repo", target.repo);
    path.searchParams.set("pr", String(target.number));
    history.replaceState(null, "", path);
  } catch (error) {
    panel.hidden = true;
    setInputStatus("INTAKE REFUSED · " + getErrorMessage(error), true);
  } finally {
    clearTimeout(timer);
    active = false;
    button.disabled = false;
    button.innerHTML = 'BEGIN TRIAGE <span aria-hidden="true">↗</span>';
  }
}

function downloadReport() {
  if (!lastReport) return;
  const safe = lastReport.source.repository.replace("/", "-");
  const filename = "smergeon-" + safe + "-pr" + lastReport.source.pull_request + ".json";
  const json = JSON.stringify(lastReport, null, 2) + "\n";
  const blobUrl = URL.createObjectURL(new Blob([json], {type:"application/json"}));
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(blobUrl), 0);
}


function showTrend(trend) {
  brownResults.hidden = false;
  document.getElementById("brown-verdict").textContent = trend.outcome.replaceAll("_"," ");
  document.getElementById("brown-coverage").textContent = trend.coverage;
  document.getElementById("brown-summary").textContent =
    "Matched " + trend.bound_to_pr_runs + " of " + trend.examined_runs +
    " recent public run records. " + trend.repeated_workflows +
    " recurring workflow(s), " + trend.watching_workflows +
    " under watch. Neither diagnosis nor merge approval.";
  const container = document.getElementById("brown-workflows");
  container.replaceChildren();
  if (!trend.workflows.length) {
    const note = document.createElement("p");
    note.className = "small-note";
    note.textContent = "No eligible workflow runs could be tied to this specific PR and branch.";
    container.append(note);
  }
  for(const workflow of trend.workflows) {
    const entry = document.createElement("div");
    entry.className = "brown-workflow";
    const title = document.createElement("strong");
    title.textContent = "WORKFLOW #" + workflow.workflow_id +
      " · " + workflow.status.replaceAll("_", " ");
    const detail = document.createElement("span");
    detail.textContent = workflow.consecutive_failed_revisions +
      " consecutive failed completed revision(s) · " +
      workflow.pending_revisions + " pending · current head represented: " +
      (workflow.current_head_has_run ? "YES" : "NOT OBSERVED");
    entry.append(title, detail);
    if (workflow.evidence_run_ids.length) {
      const links = document.createElement("div");
      links.className = "brown-evidence";
      for(const runId of workflow.evidence_run_ids) {
        const a = document.createElement("a");
        a.href = "https://github.com/" + trend.source.repository +
          "/actions/runs/" + runId;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = "RUN #" + runId + " ↗";
        links.append(a);
      }
      entry.append(links);
    }
    container.append(entry);
  }
}

async function checkCodeBrown() {
  if (active || trendBusy || !trendPatient) return;
  trendBusy = true;
  brownButton.disabled = true;
  brownResults.hidden = true;
  brownStatus.classList.remove("error");
  brownStatus.textContent = "LOOKING FOR REPEATED FAILURES…";
  const source = {...trendPatient};
  const abort = new AbortController();
  const timer = setTimeout(()=>abort.abort(), 20000);
  try {
    const prUrl = reportUrl(source.repository, "pulls/" + source.pull_request);
    confirmSameCodeBrownSource(source, await apiGET(prUrl,abort.signal),
      {repo:source.repository,number:source.pull_request});
    const query = "actions/runs?event=pull_request&branch=" +
      encodeURIComponent(source.branch) + "&per_page=50";
    const data = await apiGET(reportUrl(source.repository, query),abort.signal);
    confirmSameCodeBrownSource(source, await apiGET(prUrl,abort.signal),
      {repo:source.repository,number:source.pull_request});
    const trend = analyzeCodeBrown(data,source);
    showTrend(trend);
    brownStatus.textContent = "READ-ONLY TREND INSPECTION COMPLETE";
  } catch(error) {
    brownResults.hidden = true;
    brownStatus.classList.add("error");
    brownStatus.textContent = "REFUSED · " + getErrorMessage(error);
  } finally {
    clearTimeout(timer);
    trendBusy = false;
    brownButton.disabled = !trendPatient || active;
  }
}

brownButton.addEventListener("click",()=>void checkCodeBrown());

form.addEventListener("submit", triage);
downloadButton.addEventListener("click", downloadReport);
