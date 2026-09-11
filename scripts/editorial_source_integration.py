#!/usr/bin/env python3
"""Offline, idempotent integration of explicitly reviewed research records.

All paths are relative to this repository. No networking, credentials, or release.
"""
from __future__ import annotations
import hashlib
import json
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-11'
DELIVERY = 'editorial-2026-09-11-v1'

def load(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))

def save(path, value):
    p=ROOT/path
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def canonical_doi(value):
    return (value or '').strip().lower().removeprefix('https://doi.org/').removeprefix('http://dx.doi.org/')

def apply_sources():
    inputs=sorted((ROOT/'research/editorial_delivery').glob('sources-*.json'))
    selected=[r for p in inputs for r in json.loads(p.read_text(encoding='utf-8'))['reviews']]
    assert selected and len({canonical_doi(r['metadata']['doi']) for r in selected})==len(selected)
    categories=load('data/categories.json')['categories']
    documents={c['file']:load(c['file']) for c in categories}
    topics={t['id']:t for d in documents.values() for t in d['topics']}
    original_order=[(c['id'],[(t['id'],t['title_ja']) for t in documents[c['file']]['topics']]) for c in categories]
    topic_category={t['id']:c['id'] for c in categories for t in documents[c['file']]['topics']}
    source_doc=load('data/sources.json'); sources=source_doc['sources']
    source_by_id={s['id']:s for s in sources}
    by_doi={canonical_doi(s['doi']):s for s in sources if s.get('doi')}
    for s in sources:
        for alias in s.get('identifier_aliases',[]): by_doi[canonical_doi(alias)]=s
    assessment_doc=load('data/source_assessments.json')
    assessments={a['source_id']:a for a in assessment_doc['assessments']}
    review_doc=load('data/research/source_reviews.json')
    review_by_id={r['id']:r for r in review_doc['reviews']}
    edge_docs={p:load(p) for p in load('data/evidence/catalog.json')['files']}
    edges={(e['topic_id'],e['source_id']):e for d in edge_docs.values() for e in d['edges']}
    coverage=load('data/research/coverage.json')
    history='data/research/history/pre_editorial_delivery_coverage.json'
    snapshot='data/research/history/pre_editorial_delivery_sources.json'
    if not (ROOT/history).exists(): save(history,coverage)
    if not (ROOT/snapshot).exists(): save(snapshot,source_doc)
    original_missing=load(history)['round3_remaining_unregistered']
    original_source_ids={s['id'] for s in load(snapshot)['sources']}
    number=max(int(s['id'][3:]) for s in sources)+1
    selected_ids=[]; resolved={}
    for item in selected:
        m=item['metadata']; doi=canonical_doi(m['doi'])
        assert doi.startswith('10.') and '/' in doi
        assert all(isinstance(m[k],str) and m[k].strip() for k in ['title','authors_display','journal','url','verified_via_url'])
        assert isinstance(m['year'],int) and m['year']<=2026
        assert set(item['topic_ids'])<=set(topics)
        scope=item['review_scope']
        assert scope in ['abstract','bibliography','selected_fulltext_sections']
        assert item['publication_ready'] is False and item['evidence_certainty']=='not_assessed'
        assert item['key_findings_ja'] is None if scope=='bibliography' else bool(item['key_findings_ja'])
        source=by_doi.get(doi)
        if source is None:
            sid=f'SRC{number:03d}'; number+=1
            source={'id':sid,**m,'source_type':'journal_article','record_role':item['record_role'],
                'accessed_on':DATE,'verification_scope':'bibliography_verified' if scope=='bibliography' else 'abstract_reviewed',
                'notes_ja':'確認範囲・結果・限界は対応する読解メモを参照。資料登録は確実性評価や公開承認ではありません。',
                'indexed_related_records':item['integrity_notices'],
                'correction_retraction_check':'selected_notices_checked_not_exhaustive'}
            sources.append(source); source_by_id[sid]=source; by_doi[doi]=source
        sid=source['id']; resolved[doi]=sid; selected_ids.append(sid)
        rid='R5-'+hashlib.sha256(doi.encode()).hexdigest()[:12]
        r={'id':rid,'source_id':sid,'topic_ids':item['topic_ids'],'design':item['study_design'],
            'review_scope':'bibliography' if scope=='bibliography' else 'abstract','additional_reading_scope':scope,
            'review_method':'AI_assisted_single_review','reviewed_on':DATE,'key_findings_ja':item['key_findings_ja'],
            'limitations_ja':item['limitations_ja'],'conclusion_direction':item['conclusion_direction'],
            'topic_relevance':item['relevance_1_to_5'],
            'relevance_scope':'title_only_provisional' if scope=='bibliography' else 'source_text_screened',
            'method_signals':item['method_signals'],'formal_evidence_certainty':'not_assessed','publication_ready':False,
            'source_locators':item['locators'],'reading_source_url':m['verified_via_url'],'delivery_id':DELIVERY}
        if rid in review_by_id:
            old=review_by_id[rid]
            if old!=r:
                h=hashlib.sha256(json.dumps(old,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:12]
                save('data/research/history/reviews/'+rid+'-'+h+'.json',{'schema_version':'1.0','review':old})
                old.clear(); old.update(r)
        else:
            review_doc['reviews'].append(r); review_by_id[rid]=r
        a=assessments.get(sid,{})
        depth={'bibliography':1,'abstract':2,'legacy_abstract_review':2,'selected_fulltext_sections':3,'legacy_not_reassessed':0}
        keep=a.get('review_scope') if depth.get(a.get('review_scope'),0)>depth[scope] else scope
        assessments[sid]={**a,'source_id':sid,'review_scope':keep,'method_signals':item['method_signals'],
            'formal_risk_of_bias':'not_assessed','formal_evidence_certainty':'not_assessed',
            'reliability_ja':'研究設計・適用範囲の予備点検。点数は正しさの確率ではありません。',
            'limitations_ja':[item['limitations_ja']],'integrity_status':'selected_notices_checked_not_exhaustive',
            'integrity_notices':item['integrity_notices'],
            'provenance_review_ids':list(dict.fromkeys(a.get('provenance_review_ids',[])+[rid])),
            'checked_sections':item['locators'],'checked_on':DATE}
        if scope!='bibliography':
            if source.get('verification_scope')=='bibliography_verified': source['verification_scope']='abstract_reviewed'
            source['latest_reviewed_on']=DATE
        for tid in item['topic_ids']:
            t=topics[tid]
            if sid not in t['source_ids']: t['source_ids'].append(sid)
            if rid not in t.setdefault('source_review_ids',[]): t['source_review_ids'].append(rid)
            key=(tid,sid); e=edges.get(key)
            if e is None:
                e={'id':'EV-'+tid+'-'+sid,'topic_id':tid,'source_id':sid,'legacy_brief_ids':[]}
                edge_docs['data/evidence/'+topic_category[tid]+'.json']['edges'].append(e); edges[key]=e
            role='correction_notice' if item['record_role']=='correction_notice' else 'context_only' if scope=='bibliography' else 'direct_or_targeted_evidence'
            e.update(relation_role=role,relevance_1_to_5=item['relevance_1_to_5'],relevance_scope=r['relevance_scope'],
                source_review_id=rid,finding_scope_ja=item['key_findings_ja'] or '書誌のみ。結果は未確認。',
                conclusion_direction=item['conclusion_direction'],limits_ja=item['limitations_ja'],formal_evidence_certainty='not_assessed')
    order=[a['source_id'] for a in assessment_doc['assessments']]
    order += [sid for sid in source_by_id if sid not in set(order)]
    assessment_doc['assessments']=[assessments[sid] for sid in order]
    for d in [assessment_doc,review_doc,source_doc]: d['updated_on']=DATE
    source_doc['notes_ja']='複数回の調査を累積管理。書誌のみの資料、訂正告知、同一研究の別版を効果確認済みの独立研究として数えない。'
    for path,d in documents.items(): save(path,d)
    for path,d in edge_docs.items(): save(path,d)
    save('data/sources.json',source_doc); save('data/source_assessments.json',assessment_doc); save('data/research/source_reviews.json',review_doc)
    missing=[tid for tid,t in topics.items() if not t['source_ids']]
    counts=Counter(r['review_scope'] for r in review_doc['reviews'])
    coverage.update(source_count=len(sources),reference_linked_count=len(topics)-len(missing),search_pending_count=len(missing),
        evidence_edge_count=len(edges),correction_notice_count=sum(s.get('record_role')=='correction_notice' for s in sources),
        source_review_count=len(review_doc['reviews']),abstract_review_count=counts['abstract'],bibliography_review_count=counts['bibliography'],
        selected_fulltext_checks_count=sum(a['review_scope']=='selected_fulltext_sections' for a in assessments.values()),
        editorial_delivery_added_sources=len(set(selected_ids)-original_source_ids),editorial_delivery_review_count=len(selected),
        current_source_unregistered_topic_ids=missing,updated_on=DATE)
    for c in coverage['categories']:
        rows=[t for tid,t in topics.items() if topic_category[tid]==c['category_id']]
        c.update(reference_linked_count=sum(bool(t['source_ids']) for t in rows),source_unregistered_count=sum(not t['source_ids'] for t in rows),source_review_topic_count=sum(bool(t.get('source_review_ids')) for t in rows))
    coverage['limits_ja']=list(dict.fromkeys(coverage['limits_ja']+[
        '出典未登録ゼロと、全テーマの問いへの十分な回答・根拠評価完了は別です。部分的な資料・書誌のみを区別しています。',
        'round3_*は第3回の履歴。source_review_count等が累計です。']))
    save('data/research/coverage.json',coverage)
    manifest=load('data/manifest.json')
    manifest.update(source_count=len(sources),reference_linked_count=coverage['reference_linked_count'],search_pending_count=len(missing),updated_on=DATE,phase='claim_evidence_mapping_and_manuscript_revision',latest_delivery=DELIVERY)
    manifest['files'].update(editorial_delivery='data/research/editorial_delivery_report.json',source_reviews='data/research/source_reviews.json')
    save('data/manifest.json',manifest)
    integrations=[]
    for tid in original_missing:
        ids=[sid for sid in topics[tid]['source_ids'] if sid in selected_ids]
        integrations.append({'topic_id':tid,'title_ja':topics[tid]['title_ja'],'previous_source_count':0,'registered_source_ids':ids,
            'registry_integrated':bool(ids),'research_question_fully_resolved':False,
            'limitations_by_source':[{'source_id':sid,'limits_ja':edges[(tid,sid)]['limits_ja']} for sid in ids]})
    save('data/research/gap_integration.json',{'schema_version':'1.0','date':DATE,'topics':integrations,'note_ja':'統合の完了は参照の整合性。科学的結論の確定・記事公開の承認ではありません。'})
    report={'schema_version':'1.0','delivery_id':DELIVERY,'date':DATE,'final_goal_articles':300,'goal_completed':False,
        'selected_source_reviews':len(selected),'sources_added':len(set(selected_ids)-original_source_ids),'canonical_sources':len(sources),
        'previous_missing_topics':len(original_missing),'previous_missing_now_registered':sum(x['registry_integrated'] for x in integrations),
        'source_unregistered_topics':len(missing),'new_abstract_or_selected_text_reviews':sum(r['review_scope']!='bibliography' for r in selected),
        'new_bibliography_only_reviews':sum(r['review_scope']=='bibliography' for r in selected),'doi_to_canonical_source_id':resolved,
        'publication_ready_articles':0,'remaining_quality_gates_ja':['主張と資料の対応の点検','上位20の不足原稿を補完','訂正・反証・一般化の監査','記事単位の読みやすさ・安全性・出典点検']}
    save('data/research/editorial_delivery_report.json',report)
    assert original_order==[(c['id'],[(t['id'],t['title_ja']) for t in documents[c['file']]['topics']]) for c in categories]
    return report
