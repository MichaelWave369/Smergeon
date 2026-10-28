import test from 'node:test';
import assert from 'node:assert/strict';
import {
  safeBranch, bindCodeBrownSource, confirmSameCodeBrownSource, analyzeCodeBrown
} from '../code-brown.mjs';

const REPO = 'MichaelWave369/Smergeon';
const TARGET = {repo:REPO,number:11};
const SHAS = [ 'a'.repeat(40), 'b'.repeat(40), 'c'.repeat(40), 'd'.repeat(40)];
const SOURCE = {repository:REPO,pull_request:11,branch:'feat/fix',observed_head_sha:SHAS[0]};
function pr(){
  return {
    number:11,state:'open',
    base:{repo:{private:false,full_name:REPO}},
    head:{sha:SHAS[0],ref:'feat/fix',repo:{full_name:REPO}}
  };
}
function run(id,workflowId,commit,conclusion='failure',options={}){
  return {
    id,workflow_id:workflowId,head_sha:commit,
    head_branch:'feat/fix',head_repository:{full_name:REPO},
    event:'pull_request',status:'completed',conclusion,
    created_at:new Date(Date.UTC(2026,9,26,0,id%60)).toISOString(),
    pull_requests:[{number:11}],
    name:'UNTRUSTED NAME <script>doNotRender()</script>',
    ...options
  };
}
const page=runs=>({total_count:runs.length,workflow_runs:runs});

test('same-repo open PR and branch are required for history binding',()=>{
  assert.deepEqual(bindCodeBrownSource(pr(),TARGET),SOURCE);
  for (const bad of [
    p=>{p.state='closed'},
    p=>{p.base.repo.private=true},
    p=>{p.head.repo.full_name='other/repo'},
    p=>{p.head.ref='../unsafe'},
    p=>{p.head.ref='-unsafe'},
    p=>{p.number=99},
    p=>{p.head.sha='not-a-sha'},
  ]) {
    const candidate=pr();bad(candidate);
    assert.throws(()=>bindCodeBrownSource(candidate,TARGET));
  }
  assert.equal(safeBranch('feature/repair-01'),true);
  for(const b of ['../evil','a//b','x@{1}','-bad','feat/../main','a b','']){
    assert.equal(safeBranch(b),false,b);
  }
});

test('source change during history inspection is refused',()=>{
  assert.equal(confirmSameCodeBrownSource(SOURCE,pr(),TARGET),true);
  const moved=pr();moved.head.sha=SHAS[1];
  assert.throws(()=>confirmSameCodeBrownSource(SOURCE,moved,TARGET));
  const rebased=pr();rebased.head.ref='new-branch';
  assert.throws(()=>confirmSameCodeBrownSource(SOURCE,rebased,TARGET));
});

test('three consecutive failures on distinct commits trigger CODE BROWN',()=>{
  const history=page([
    run(303,9,SHAS[0]),run(302,9,SHAS[1]),run(301,9,SHAS[2])
  ]);
  const result=analyzeCodeBrown(history,SOURCE);
  assert.equal(result.outcome,'CODE_BROWN');
  assert.equal(result.repeated_workflows,1);
  assert.equal(result.workflows[0].consecutive_failed_revisions,3);
  assert.deepEqual(result.workflows[0].evidence_run_ids,[303,302,301]);
  assert.equal(result.workflows[0].current_head_has_run,true);
  assert.equal(result.causal_equivalence_proven,false);
  assert.equal(result.current_failure_proven,false);
  assert.equal(result.merge_authorization,false);
});

test('three reruns of the SAME commit do not trigger CODE BROWN',()=>{
  const result=analyzeCodeBrown(page([
    run(303,9,SHAS[0]),run(302,9,SHAS[0]),run(301,9,SHAS[0])
  ]),SOURCE);
  assert.equal(result.outcome,'INSUFFICIENT_EVIDENCE');
  assert.equal(result.workflows[0].recent_completed_revisions,1);
  assert.equal(result.workflows[0].consecutive_failed_revisions,1);
});

test('success between failures interrupts the streak',()=>{
  const result=analyzeCodeBrown(page([
    run(303,9,SHAS[0]),run(302,9,SHAS[1],'success'),run(301,9,SHAS[2]),
    run(300,9,SHAS[3])
  ]),SOURCE);
  assert.equal(result.outcome,'INSUFFICIENT_EVIDENCE');
  assert.equal(result.workflows[0].consecutive_failed_revisions,1);
});

test('two failed revisions are WATCH, not CODE BROWN',()=>{
  const result=analyzeCodeBrown(page([
    run(303,9,SHAS[0]),run(302,9,SHAS[1])
  ]),SOURCE);
  assert.equal(result.outcome,'WATCH');
  assert.equal(result.workflows[0].status,'WATCH');
  assert.equal(result.workflows[0].evidence_run_ids.length,0);
});

test('foreign PR, branch, repository, and push events are not evidence',()=>{
  const valid=run(300,9,SHAS[0]);
  const invalid=[
    run(301,9,SHAS[1],'failure',{pull_requests:[{number:12}]}),
    run(302,9,SHAS[2],'failure',{head_branch:'other/branch'}),
    run(303,9,SHAS[3],'failure',{head_repository:{full_name:'other/repo'}}),
    run(304,9,SHAS[1],'failure',{event:'push'}),
  ];
  const result=analyzeCodeBrown(page([valid,...invalid]),SOURCE);
  assert.equal(result.outcome,'INSUFFICIENT_EVIDENCE');
  assert.equal(result.bound_to_pr_runs,1);
});

test('same workflow name under different IDs is NOT the same workflow',()=>{
  const result=analyzeCodeBrown(page([
    run(301,12,SHAS[0]),run(302,13,SHAS[1]),run(303,14,SHAS[2])
  ]),SOURCE);
  assert.equal(result.outcome,'INSUFFICIENT_EVIDENCE');
  assert.equal(result.workflows.length,3);
});

test('truncated API page stays PARTIAL even with observed CODE BROWN',()=>{
  const data=page([run(303,9,SHAS[0]),run(302,9,SHAS[1]),run(301,9,SHAS[2])]);
  data.total_count=200;
  const result=analyzeCodeBrown(data,SOURCE);
  assert.equal(result.outcome,'CODE_BROWN');
  assert.equal(result.coverage,'PARTIAL');
  assert.equal(result.permissions_granted,false);
});

test('pending revisions are disclosed without manufacturing a passed result',()=>{
  const data=page([
    run(304,9,SHAS[0],null,{status:'in_progress'}),
    run(303,9,SHAS[1]),
    run(302,9,SHAS[2]),
    run(301,9,SHAS[3]),
  ]);
  const result=analyzeCodeBrown(data,SOURCE);
  assert.equal(result.workflows[0].pending_revisions,1);
  assert.equal(result.workflows[0].consecutive_failed_revisions,3);
  assert.equal(result.current_failure_proven,false);
});

test('untrusted run title and arbitrary URLs never appear in report',()=>{
  const result=analyzeCodeBrown(page([
    run(303,9,SHAS[0]),run(302,9,SHAS[1]),run(301,9,SHAS[2]),
  ]),SOURCE);
  const text=JSON.stringify(result);
  assert.equal(text.includes('<script>'),false);
  assert.equal(text.includes('UNTRUSTED NAME'),false);
  assert.equal(text.includes('http'),false);
  assert.equal(result.trust,'PUBLIC_METADATA_ONLY');
});

test('invalid/truncated/unbounded history is refused or labeled',()=>{
  assert.throws(()=>analyzeCodeBrown({workflow_runs:null,total_count:0},SOURCE));
  assert.throws(()=>analyzeCodeBrown({workflow_runs:[],total_count:-1},SOURCE));
  assert.throws(()=>analyzeCodeBrown({workflow_runs:[run(301,9,SHAS[0])],total_count:0},SOURCE));
  assert.throws(()=>analyzeCodeBrown({workflow_runs:Array.from({length:51},(_,i)=>
    run(100+i,9,SHAS[i%4])),total_count:51},SOURCE));
  const empty=analyzeCodeBrown(page([]),SOURCE);
  assert.equal(empty.outcome,'INSUFFICIENT_EVIDENCE');
  assert.equal(empty.coverage,'PARTIAL');
});
