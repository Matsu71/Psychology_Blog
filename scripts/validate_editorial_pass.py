#!/usr/bin/env python3
"""Check references, hashes and review boundaries; not scientific truth."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path): return json.loads((ROOT/path).read_text(encoding='utf-8'))
def require(test,msg):
    if not test: raise ValueError(msg)
def validate():
    inp=ROOT/'research/editorial_pass_20260911'
    specs=[json.loads(p.read_text())['article'] for p in sorted(inp.glob('PSY-*.json'))]
    checks=load('data/research/source_text_checks.json')['checks']; cm={c['id']:c for c in checks}
    sources={s['id']:s for s in load('data/sources.json')['sources']}
    catalog=load('data/articles/catalog.json')['articles']; rows={r['topic_id']:r for r in catalog}
    require(len(rows)==len(catalog)==300,'All 300 unique themes must be retained')
    require(len(cm)==len(checks),'Duplicate source check')
    count=0
    for a in specs:
        tid=a['topic_id']; row=rows[tid]; d=load(row['claim_dossier_path'])
        p=ROOT/row['manuscript_path']; body=p.read_text()
        require(hashlib.sha256(p.read_bytes()).hexdigest()==row['manuscript_sha256'],'Article hash '+tid)
        require(d['authoring_input_sha256']==hashlib.sha256((inp/(tid+'.json')).read_bytes()).hexdigest(),'Stale input '+tid)
        require(not d['unresolved_source_keys'] and not row['unresolved_source_keys'],'Unresolved bibliography '+tid)
        require(row['state']=='source_checked_manuscript' and not row['publication_ready'],'Wrong status '+tid)
        require(len(d['claims'])==len(a['claims']),'Lost claims')
        require(len({c['id'] for c in d['claims']})==len(d['claims']),'Duplicate claim ID')
        for c in d['claims']:
            count+=1
            require(c['source_ids'] and set(c['source_ids'])<=sources.keys(),'Missing source')
            require(set(c['source_check_ids'])<=cm.keys(),'Unknown check')
            require(all(tid in cm[x]['topic_ids'] for x in c['source_check_ids']),'Source/theme mismatch')
            require(set(c['source_ids'])=={cm[x]['source_id'] for x in c['source_check_ids']},'Source/check mismatch')
            require(c['population_and_scope_ja'] and c['not_supported_ja'],'Missing scope')
            require(not c['publication_ready'] and c['evidence_certainty']=='not_formally_assessed','Inflated certainty')
        require(len(a['sections'])>=3 and all(s['text'].strip() for s in a['sections']),'Incomplete body')
        require('台帳との一意な照合が未完了' not in body and '結果は未確認' not in body,'Unresolved result placeholder')
        require('../../data/articles/claims/'+tid+'.json' in body,'Broken link')
        require(a['application']['type']=='editorial_application_not_directly_validated_protocol','Mislabelled advice')
        require(a['application']['safety'] and not d['independent_review_completed'],'Missing boundary')
    progress=load('data/articles/progress.json')
    checked={r['topic_id'] for r in catalog if r.get('state')=='source_checked_manuscript'}
    require(progress['source_checked_manuscript_count']==len(checked)==len(specs),'Progress mismatch')
    require(progress['top20_source_checked_count']==len(checked&set(progress['top20_topic_ids'])),'Top20 mismatch')
    require(not progress['goal_completed'] and progress['publication_ready_count']==0,'Premature release')
    require(not progress['dossiers_with_unresolved_sources'],'Identifier gap remains')
    for c in checks:
        require(c['source_id'] in sources and c['locators'] and c['findings_ja'] and c['limitations_ja'],'Incomplete check')
        require(not c['independent_review_completed'] and c['formal_risk_of_bias']=='not_assessed','Inflated scope')
        for m in c['metrics']:
            if 'ci95' in m: require(len(m['ci95'])==2 and m['ci95'][0]<=m['ci95'][1],'Invalid CI')
            if 'denominator' in m: require(0<=m['n']<=m['denominator'],'Invalid fraction')
    for d in load('research/editorial_pass_20260911/audit_resolutions.json')['resolutions']:
        require(d['topic_id'] in checked and set(d['source_check_ids'])<=cm.keys(),'Invalid audit resolution')
        require(d['action_ja'] and d['remaining_scope_ja'],'Missing audit boundary')
    return {'schema_version':'1.0','status':'passed','pass_id':'source-editorial-pass-20260911',
            'topic_count':len(rows),'source_count':len(sources),'manuscript_count':progress['manuscript_count'],
            'source_checked_manuscripts':len(specs),'checked_claims':count,'source_checks':len(checks),
            'top20_source_checked':progress['top20_source_checked_count'],'unresolved_source_dossiers':0,
            'publication_ready_count':0,'goal_articles':300,'goal_completed':False,
            'scope_ja':'ID・参照・ハッシュ・状態を検証。科学的真偽、独立査読、医療監修の自動認定ではない。'}
if __name__=='__main__': print(json.dumps(validate(),ensure_ascii=False,indent=2))
