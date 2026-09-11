#!/usr/bin/env python3
"""Read-only structural checks for the learning delivery, never scientific approval."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BATCH='learning-20260911'
def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
def validate():
    report=read('data/research/reviewed_deliveries/'+BATCH+'/report.json')
    catalog={r['topic_id']:r for r in read('data/articles/catalog.json')['articles']}
    sources={s['id'] for s in read('data/sources.json')['sources']}
    checks={c['id']:c for c in read('data/research/source_text_checks.json')['checks']}
    assert len(report['products'])==5 and report['new_manuscripts']==2 and report['revised_manuscripts']==3
    for product in report['products']:
        tid=product['topic_id'];row=catalog[tid]
        input_path='research/reviewed_deliveries/'+BATCH+'/'+tid+'.json'
        a=read(input_path)['article'];d=read(row['claim_dossier_path'])
        assert d['authoring_input_sha256']==sha(input_path)
        assert sha(row['manuscript_path'])==row['manuscript_sha256']==product['manuscript_sha256']
        assert sha(row['claim_dossier_path'])==row['claim_dossier_sha256']==product['claim_dossier_sha256']
        assert len(d['claims'])==row['claim_count']==len(a['sections'])
        assert len({c['id'] for c in d['claims']})==len(d['claims'])
        for c in d['claims']:
            assert c['source_ids'] and set(c['source_ids'])<=sources
            assert set(c['source_ids'])=={checks[x]['source_id'] for x in c['source_check_ids']}
            assert all(tid in checks[x]['topic_ids'] for x in c['source_check_ids'])
            assert c['population_and_scope_ja'] and c['not_supported_ja'] and not c['publication_ready']
        body=(ROOT/row['manuscript_path']).read_text()
        used=set(re.findall(r'\[\^([^\]]+)\](?!:)',body));defined=re.findall(r'^\[\^([^\]]+)\]:',body,re.M)
        assert used==set(defined) and len(defined)==len(set(defined)),tid
        assert not d['publication_ready'] and not d['independent_review_completed'] and not row['publication_ready']
        assert d['application']['type']=='editorial_application_not_directly_validated_protocol'
        if a['expected_previous_sha256']:
            assert sha('articles/history/'+BATCH+'/'+tid+'.md')==a['expected_previous_sha256']
            assert sha('articles/history/'+BATCH+'/'+tid+'.json')==a['expected_previous_claim_sha256']
    assert report['publication_ready_count']==0 and not report['goal_completed']
    return {'status':'passed','delivery_id':BATCH,'articles':5,'new':2,'revised':3,'scope':'identifiers, claims, citations, hashes, archived originals, stage labels; not scientific truth'}
if __name__=='__main__':print(json.dumps(validate(),ensure_ascii=False))
