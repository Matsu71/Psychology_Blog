#!/usr/bin/env python3
"""Compile existing authoring work into auditable dossiers, without publication.

Uses local repository files only. Missing source matches remain explicit. Original
themes, source records and authoring files are never rewritten by this compiler.
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/articles'
DOCS = ROOT / 'docs/articles'
DRAFTS = ROOT / 'articles/manuscripts'
DATE = '2026-09-11'

def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))

def write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')

def doi(value: Any) -> str:
    s = str(value or '').strip().lower()
    return re.sub(r'^https?://(?:dx\.)?doi\.org/', '', s)

def entries(value: Any) -> list[dict]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ('rankings', 'topics', 'items', 'ranking', 'assessments'):
            if isinstance(value.get(key), list):
                return value[key]
    raise ValueError('Cannot identify editorial ranking records')

def main() -> None:
    categories = read(ROOT/'data/categories.json')['categories']
    topics = {t['id']: {**t, 'category_id': c['id']} for c in categories for t in read(ROOT/c['file'])['topics']}
    assert len(topics) == 300, 'Unexpected theme count; reconcile instead of dropping records'
    source_list = read(ROOT/'data/sources.json')['sources']
    sources = {s['id']:s for s in source_list}
    doi_index: dict[str,list[str]] = {}
    pmid_index: dict[str,list[str]] = {}
    title_index: dict[str,list[str]] = {}
    for s in source_list:
        for d in [s.get('doi'), *s.get('identifier_aliases',[])]:
            if d: doi_index.setdefault(doi(d), []).append(s['id'])
        p = s.get('pmid')
        if not p:
            match = re.search(r'pubmed\.ncbi\.nlm\.nih\.gov/(\d+)', s.get('url',''))
            p = match.group(1) if match else None
        if p: pmid_index.setdefault(str(p), []).append(s['id'])
        title_index.setdefault(s.get('title','').strip().casefold(), []).append(s['id'])
    authoring_paths = sorted((ROOT/'research').glob('round4_continuation_0[1-5].json'))
    specs = [a for path in authoring_paths for a in read(path)['articles']]
    extra_paths = sorted((ROOT/'research/manuscript_revision_20260911').glob('*.json'))
    revisions = [a for path in extra_paths for a in read(path).get('articles', [])]
    spec_map = {a['topic_id']:a for a in specs}
    assert len(spec_map) == len(specs), 'Duplicate original authoring topic'
    revision_ids = set()
    for revision in revisions:
        tid = revision['topic_id']
        assert tid in topics and tid not in revision_ids, 'Duplicate or unknown revision'
        revision_ids.add(tid)
        # The original raw files stay unchanged and remain available as history.
        spec_map[tid] = revision
    audit_file = ROOT/'research/round4_continuation_editorial_audit.json'
    audits = read(audit_file)['checks'] if audit_file.exists() else []
    ranking_rows = entries(read(ROOT/'data/rankings/editorial_topics.json'))
    top20 = []
    for row in ranking_rows:
        tid = row.get('topic_id') or row.get('id')
        if tid in topics and tid not in top20:
            top20.append(tid)
        if len(top20) == 20: break
    assert len(top20) == 20, 'Editorial top 20 could not be resolved'
    dossiers = []
    records = []
    for tid, topic in topics.items():
        spec = spec_map.get(tid)
        if spec is None:
            records.append({'topic_id':tid,'title_ja':topic['title_ja'],'state':'research_pending','manuscript_path':None,'claim_dossier_path':None,'publication_ready':False})
            continue
        selector_map = {s['key']:s for s in spec['source_selectors']}
        assert len(selector_map) == len(spec['source_selectors'])
        resolved = {}
        for key, sel in selector_map.items():
            matches = set()
            if sel.get('doi'): matches.update(doi_index.get(doi(sel['doi']),[]))
            if sel.get('pmid'): matches.update(pmid_index.get(str(sel['pmid']),[]))
            method = 'exact_identifier'
            if not matches and sel.get('title'):
                matches.update(title_index.get(sel['title'].strip().casefold(),[]))
                method = 'exact_title_requires_identifier_check'
            resolved[key] = {'selector':sel,'source_ids':sorted(matches),'resolution_method':method if len(matches)==1 else 'unresolved' if not matches else 'ambiguous','claim_support_verified_by_compiler':False}
        claims=[]
        for i, claim in enumerate(spec['claims'],1):
            keys = claim.get('sources',[])
            assert set(keys) <= set(selector_map), (tid, 'unknown claim reference')
            ref_ids = list(dict.fromkeys(sid for key in keys for sid in resolved[key]['source_ids']))
            claims.append({'id':tid+f'-C{i:02d}','claim_ja':claim['text'],'population_and_scope_ja':claim['scope'],
                'not_supported_ja':claim['not_supported'],'source_keys':keys,'source_ids':ref_ids,
                'source_resolution_complete':bool(keys) and all(resolved[k]['resolution_method']=='exact_identifier' for k in keys),
                'evidence_certainty':'not_formally_assessed','claim_review_status':'authoring_claim_pending_source_text_check',
                'application_type':'research_claim_or_interpretation_caution','publication_ready':False})
        applicable=[{'audit_id':a['id'],'severity':a.get('severity'),'finding_ja':a.get('finding_ja'),
                     'next_action_ja':a.get('required_action_ja'),'status':'requires_recheck_after_revision'}
                    for a in audits if not a.get('topic_ids') or tid in a['topic_ids']]
        unresolved=[key for key,value in resolved.items() if value['resolution_method']!='exact_identifier']
        dossier={'schema_version':'1.0','topic_id':tid,'title_ja':spec['title'],'category_id':topic['category_id'],
                 'created_on':DATE,'authoring_revision':'editorial_revision' if tid in revision_ids else 'preserved_round4_draft',
                 'source_resolution':resolved,'claims':claims,'unresolved_source_keys':unresolved,
                 'application':{'type':'editorial_application_not_directly_validated_protocol',**spec['application']},
                 'outstanding_audit_items':applicable,'editorial_hold':spec.get('editorial_hold'),
                 'publication_ready':False,'independent_review_completed':False}
        write(OUT/'claims'/f'{tid}.json',dossier)
        lines=['# '+spec['title'],'', '> 原稿です。未確認事項と公開判定は対応する根拠表で管理しています。','',spec['lead'],'']
        for sec in spec['sections']:
            assert set(sec.get('sources',[])) <= set(selector_map)
            lines += ['## '+sec['heading'],'',sec['text'],'']
            if sec.get('sources'): lines += ['出典：'+'、'.join('['+k+']' for k in sec['sources']),'']
        lines+=['## 日常へのつなげ方','', '以下は研究を参考にした編集上の応用例です。研究でそのまま検証された手順とは限りません。','']
        for step in spec['application']['steps']: lines += [step,'']
        lines += [spec['application']['safety'],'','## 出典','']
        for key, value in resolved.items():
            if value['resolution_method']=='exact_identifier':
                s=sources[value['source_ids'][0]]
                lines += [f"[{key}] {s.get('authors_display','')} ({s.get('year','年未確認')}). {s['title']}. {s.get('url','')}",'']
            else:
                sel=value['selector']
                identity=sel.get('doi') or sel.get('pmid') or sel.get('title') or sel.get('url') or key
                lines += [f'[{key}] 台帳との一意な照合が未完了：{identity}。','']
        if spec.get('editorial_hold'): lines += ['編集上の保留事項：'+spec['editorial_hold'],'']
        lines += [f'根拠表：../../../data/articles/claims/{tid}.json','']
        DRAFTS.mkdir(parents=True,exist_ok=True)
        path=DRAFTS/f'{tid}.md'
        path.write_text('\n'.join(lines),encoding='utf-8')
        records.append({'topic_id':tid,'title_ja':topic['title_ja'],'state':'revised_manuscript_pending_review' if tid in revision_ids else 'manuscript_pending_review',
                        'manuscript_path':str(path.relative_to(ROOT)),'claim_dossier_path':f'data/articles/claims/{tid}.json',
                        'claim_count':len(claims),'unresolved_source_keys':unresolved,
                        'manuscript_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'publication_ready':False})
        dossiers.append(dossier)
    report={'schema_version':'1.0','date':DATE,'goal_articles':300,'goal_completed':False,
            'theme_count':len(topics),'manuscript_count':len(dossiers),'claim_dossier_count':len(dossiers),
            'claim_and_caution_count':sum(len(d['claims']) for d in dossiers),
            'revised_manuscript_count':len(revision_ids),'publication_ready_count':0,
            'top20_topic_ids':top20,'top20_dossiers_present':sum(t in spec_map for t in top20),
            'missing_top20_topic_ids':[t for t in top20 if t not in spec_map],
            'dossiers_with_unresolved_sources':[d['topic_id'] for d in dossiers if d['unresolved_source_keys']],
            'notes_ja':['出典の一意な照合は、出典がその主張を支持することの自動認定ではありません。',
                        '原稿の再編集と独立した科学的査読、医療上の安全確認、公開承認を分離しています。',
                        '300テーマの状態をすべて記録し、未着手の記事を完成数へ加算しません。']}
    write(OUT/'progress.json',report)
    write(OUT/'catalog.json',{'schema_version':'1.0','articles':records})
    DOCS.mkdir(parents=True,exist_ok=True)
    lines=['# 記事制作の現在地','',f"目標300記事。原稿{report['manuscript_count']}件、根拠表{report['claim_dossier_count']}件。公開承認済み0件。",'',
           f"上位20テーマの根拠表：{report['top20_dossiers_present']}/20。",'',
           '原稿があることと、監査事項が解決したことを区別しています。','',
           '| テーマID | テーマ | 状態 |','|---|---|---|']
    for r in records: lines.append(f"| {r['topic_id']} | {r['title_ja']} | {r['state']} |")
    (ROOT/'docs/ARTICLE_PROGRESS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
