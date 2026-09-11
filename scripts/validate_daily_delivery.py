#!/usr/bin/env python3
"""Read-only verification of the daily-life delivery; no scientific approval."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BATCH='daily-life-20260911'

def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))

def sha(path):
    return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()

def require(condition,message):
    if not condition: raise ValueError(message)

def validate():
    config=read('research/reviewed_deliveries/'+BATCH+'/manifest.json')
    report=read('data/research/reviewed_deliveries/'+BATCH+'/report.json')
    entries={r['topic_id']:r for r in read('data/articles/catalog.json')['articles']}
    sources={s['id']:s for s in read('data/sources.json')['sources']}
    checks={c['id']:c for c in read('data/research/source_text_checks.json')['checks']}
    require(set(p['topic_id'] for p in report['products'])==set(config['topic_ids']), 'Delivery coverage')
    require(len(report['products'])==report['new_manuscripts']==12 and report['revised_manuscripts']==0,'Delivery counts')
    all_claims=set()
    for item in report['products']:
        tid=item['topic_id'];row=entries[tid]
        path='research/reviewed_deliveries/'+BATCH+'/'+tid+'.json'
        a=read(path)['article'];d=read(row['claim_dossier_path'])
        require(a['expected_previous_sha256'] is None and a['expected_previous_claim_sha256'] is None,'New manuscripts only')
        require(row['reviewed_delivery_id']==BATCH and d['delivery_id']==BATCH,'Wrong active delivery')
        require(d['authoring_input_sha256']==sha(path),'Stale input '+tid)
        require(row['manuscript_sha256']==item['manuscript_sha256']==sha(row['manuscript_path']),'Manuscript bytes '+tid)
        require(row['claim_dossier_sha256']==item['claim_dossier_sha256']==sha(row['claim_dossier_path']),'Dossier bytes '+tid)
        require(d['topic_id']==tid and len(d['claims'])==len(a['sections'])==row['claim_count'],'Claim identity')
        require(len(a['sections'])>=3 and a['lead'] and a['application']['text'] and a['conclusion'],'Incomplete article')
        for claim in d['claims']:
            require(claim['id'] not in all_claims,'Duplicate claim');all_claims.add(claim['id'])
            require(claim['source_ids'] and set(claim['source_ids'])<=sources.keys(),'Unknown source')
            require(set(claim['source_ids'])=={checks[x]['source_id'] for x in claim['source_check_ids']},'Check/source mismatch')
            require(all(tid in checks[x]['topic_ids'] for x in claim['source_check_ids']),'Wrong source scope')
            require(claim['population_and_scope_ja'] and claim['not_supported_ja'],'Missing boundary')
        require(a['application']['type']=='editorial_application_not_directly_validated_protocol','Mislabelled application')
        require(not row['publication_ready'] and not d['publication_ready'] and not d['independent_review_completed'],'Inflated approval')
        body=(ROOT/row['manuscript_path']).read_text(encoding='utf-8')
        used=set(re.findall(r'\[\^([^\]]+)\](?!:)',body))
        defined=re.findall(r'^\[\^([^\]]+)\]:',body,re.M)
        require(used==set(defined) and len(defined)==len(set(defined)),'Broken footnotes')
        require('None' not in body and 'TODO' not in body,'Unresolved placeholder')
        require('../../data/articles/claims/'+tid+'.json' in body,'Missing dossier link')
    official=[c for c in checks.values() if c.get('delivery_id')==BATCH and c['review_scope']=='official_page_reviewed']
    require(len(official)==1 and sources[official[0]['source_id']]['source_type']=='official_health_information','Official source distinction')
    require(report['source_checks']==21 and not report['goal_completed'] and report['publication_ready_count']==0,'Report mismatch')
    return dict(schema_version='1.0',status='passed',delivery_id=BATCH,articles=12,claim_groups=len(all_claims),source_checks=21,
                official_page_checks=1,publication_ready=0,scope_ja='識別子、本文・根拠表のハッシュ、引用と確認記録、旧原稿との区別、確認範囲を検証。科学的真偽の自動認定ではない。')

if __name__=='__main__': print(json.dumps(validate(),ensure_ascii=False,indent=2))
