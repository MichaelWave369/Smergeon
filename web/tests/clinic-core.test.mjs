import test from 'node:test';
import assert from 'node:assert/strict';

import {
  LABELS, analyzeResults, classify, isSha, parseTarget,
  toDownloadReport, validateFreshPR, validatePR,
} from '../clinic-core.mjs';

const SHA = 'a'.repeat(40);
const MERGE = 'b'.repeat(40);
const TARGET = {repo:'MichaelWave369/Smergeon',number:9};
const openPR = () => ({
  number:9, state:'open',
  base:{repo:{full_name:'MichaelWave369/Smergeon',private:false}},
  head:{sha:SHA}, merge_commit_sha:MERGE, mergeable:true,
});
const context = (items, {sha = SHA,kind = 'check',total = items.length} = {}) =>
  ({items,sha,kind,total});
const check = (id,name,conclusion,status='completed') =>
  ({id,name,conclusion,status});

test('repository input is strict, public GitHub URL permitted', () => {
  assert.deepEqual(parseTarget(' MichaelWave369/Smergeon ','9'),TARGET);
  assert.deepEqual(parseTarget('https://github.com/MichaelWave369/Smergeon/','9'),TARGET);
  for(const value of ('../bad','owner/..','owner/.','bad','owner/repo/tree/main',
                        'https://evil.example/owner/repo','owner/<script>')){
    assert.throws(()=>parseTarget(value,'9'));
  }
  for(const value of ('0','-1','1.4','abc','1<script>','0009','1234567890')){
    assert.throws(()=>parseTarget('owner/repo',value));
  }
});

test('open public PR validated; private/closed/mismatched/fork bases rejected', () => {
  const result=validatePR(openPR(),TARGET);
  assert.equal(result.headSha,SHA);
  assert.equal(result.mergeSha,MERGE);
  const variants=[
    p=>{p.state='closed';},p=>{p.base.repo.private=true;},
    p=>{p.base.repo.full_name='another/repo';},
    p=>{p.number=10;},p=>{p.head.sha='no';}
  ];
  for(const mutate of variants){
    const changed=openPR();mutate(changed);
    assert.throws(()=>validatePR(changed,TARGET));
  }
});

test('a changed PR cannot be described as a stable examination', () => {
  const original=validatePR(openPR(),TARGET);
  assert.equal(validateFreshPR(original,openPR(),TARGET),true);
  const moved=openPR();moved.head.sha='c'.repeat(40);
  assert.throws(()=>validateFreshPR(original,moved,TARGET));
  const movedMerge=openPR();movedMerge.merge_commit_sha='d'.repeat(40);
  assert.throws(()=>validateFreshPR(original,movedMerge,TARGET));
});

test('metadata failure on test-merge SHA beats head success', () => {
  const contexts=[
    context([check(1,'smoke','success')]),
    context([check(2,'TypeScript Build','failure')],{sha:MERGE}),
  ];
  const report=analyzeResults(contexts,{mergeInspected:true,mergeable:true});
  assert.equal(report.state,'code_blue');
  assert.equal(report.failureCount,1);
  assert.equal(report.categories.build,1);
  assert.equal(report.coverage,'HEAD + TEST-MERGE');
  assert.equal(report.authorization.mergeApproval,false);
});

test('pending checks remain RECOVERY and do not certify passed CI', () => {
  const report=analyzeResults([context([
    check(1,'smoke',null,'in_progress')
  ])],{mergeInspected:true,mergeable:true});
  assert.equal(report.state,'recovery');
  assert.equal(report.pendingCount,1);
});

test('incomplete pagination or missing merge SHA never means CLEAR', () => {
  const items=[check(1,'test','success')];
  const partial=analyzeResults([context(items,{total:101})],
    {mergeInspected:true,mergeable:true});
  assert.equal(partial.state,'unknown');
  assert.equal(partial.coverage,'PARTIAL');
  const missing=analyzeResults([context(items)],
    {expectMerge:true,mergeInspected:false,mergeable:true});
  assert.equal(missing.state,'unknown');
  assert.equal(missing.missingMerge,true);
});

test('mergeability null or conflict with green checks remains uncertain', () => {
  const items=[check(1,'smoke','success')];
  for(const mergeable of (null,false)){
    const value=analyzeResults([context(items)],{mergeable});
    assert.equal(value.state,'unknown');
  }
  const clear=analyzeResults([context(items)],{mergeable:true,mergeInspected:true});
  assert.equal(clear.state,'clear');
  assert.equal(clear.authorization.writes,false);
});

test('cancelled checks never establish clean state', () => {
  const result=analyzeResults([context([check(1,'job','cancelled')])],
    {mergeable:true,mergeInspected:true});
  assert.equal(result.state,'unknown');
  assert.equal(result.cancelledCount,1);
});

test('untrusted check name converted into allowlisted categories only', () => {
  const record=analyzeResults([context([
    check(4,'<script>alert(1)</script>','failure')
  ])],{mergeable:true,mergeInspected:true});
  assert.equal(record.categories.unknown,1);
  assert.equal(JSON.stringify(record).includes('<script>'),false);
  assert.equal(classify('vite build'),'build');
  assert.equal(classify('pytest test suite'),'tests');
});

test('report export never contains log text, credentials or permission grants', () => {
  const result=analyzeResults([context([check(1,'npm install','failure')])],
    {mergeable:true,mergeInspected:true});
  const report=toDownloadReport(TARGET,
    {headSha:SHA,mergeSha:MERGE,mergeable:true},result);
  assert.equal(report.schema,'smergeon.pages-clinic.v1');
  assert.equal(report.merge_authorization,false);
  assert.equal(report.observations.authorization.drafts,false);
  assert.equal(report.source.inspected_head_sha,SHA);
  assert.equal(report.source.inspected_test_merge_sha,MERGE);
  assert.equal(JSON.stringify(report).includes('npm install'),false);
});

test('state labels and SHA validation fixed',()=>{
  assert.equal(LABELS.code_blue,'CODE BLUE');
  assert.equal(isSha('f'.repeat(40)),true);
  assert.equal(isSha('f'.repeat(39)),false);
});
