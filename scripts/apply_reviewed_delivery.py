#!/usr/bin/env python3
"""Apply the authored learning delivery offline, retaining previous manuscripts.

This resolves bibliographic IDs and updates views, not scientific truth or release.
Run from a disposable checkout; commit only after all validators pass.
"""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH = 'learning-20260911'
INPUT = ROOT / 'research/reviewed_deliveries' / BATCH
OUTPUT = 'data/research/reviewed_deliveries/' + BATCH
DATE = '2026-09-11'

def load(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))

def save(path, value):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')

def digest(value):
    return hashlib.sha256(value).hexdigest()

def doi(value):
    return (value or '').lower().strip().removeprefix('https://doi.org/')

def run():
    source_input = json.loads((INPUT / 'sources.json').read_text(encoding='utf-8'))
    input_files = sorted(INPUT.glob('PSY-*.json'))
    specs = [(p, json.loads(p.read_text(encoding='utf-8'))['article']) for p in input_files]
    expected = {'PSY-LEA-003','PSY-LEA-005','PSY-LEA-008','PSY-CRE-001','PSY-MOT-008'}
    if {a['topic_id'] for p,a in specs} != expected or len(specs) != len(expected):
        raise ValueError('Incomplete or duplicate authored delivery')
    categories = load('data/categories.json')['categories']
    topic_docs = {c['file']: load(c['file']) for c in categories}
    topics = {t['id']: t for d in topic_docs.values() for t in d['topics']}
    category_for = {t['id']:c['id'] for c in categories for t in topic_docs[c['file']]['topics']}
    catalog = load('data/articles/catalog.json')
    rows = {r['topic_id']:r for r in catalog['articles']}
    before_identity = [(r['topic_id'],r['title_ja']) for r in catalog['articles']]
    # Resolve conflicts before making any source or article changes.
    for p,a in specs:
        row = rows[a['topic_id']]
        if row.get('reviewed_delivery_id') == BATCH:
            if not row.get('manuscript_path') or digest((ROOT/row['manuscript_path']).read_bytes()) != row['manuscript_sha256']:
                raise ValueError('Current manuscript changed outside its catalog: '+a['topic_id'])
            continue
        if row.get('manuscript_sha256') != a['expected_previous_sha256']:
            raise ValueError('Concurrent manuscript change: '+a['topic_id'])
        if row.get('claim_dossier_sha256') != a['expected_previous_claim_sha256']:
            raise ValueError('Concurrent claim dossier change: '+a['topic_id'])
    source_doc = load('data/sources.json'); sources = source_doc['sources']
    by_doi = {doi(s['doi']):s for s in sources if s.get('doi')}
    assessment_doc = load('data/source_assessments.json')
    assessments = {a['source_id']:a for a in assessment_doc['assessments']}
    review_doc = load('data/research/source_reviews.json')
    text_doc = load('data/research/source_text_checks.json')
    review_map = {r['id']:r for r in review_doc['reviews']}
    text_map = {c['id']:c for c in text_doc['checks']}
    edge_docs = {p:load(p) for p in load('data/evidence/catalog.json')['files']}
    edge_map = {(e['topic_id'],e['source_id']):e for d in edge_docs.values() for e in d['edges']}
    next_id = max(int(s['id'][3:]) for s in sources)+1
    resolutions = {}; check_ids = {}; review_ids = {}; new_source_ids = []
    for item in source_input['sources']:
        key=item['key']; meta=item['metadata']; identifier=doi(meta['doi'])
        if key in resolutions or not identifier.startswith('10.'):
            raise ValueError('Invalid source key or DOI')
        source=by_doi.get(identifier)
        if source is None:
            sid=f'SRC{next_id:03d}'; next_id+=1
            source={'id':sid,**meta,'source_type':'journal_article','record_role':'research_entry',
                    'verification_scope':'abstract_reviewed','verified_via_url':meta['url'],
                    'accessed_on':DATE,'notes_ja':'独自要約。実際の確認範囲・不一致・限界は読解記録を参照。正式な確実性評価ではない。',
                    'correction_retraction_check':'not_exhaustive'}
            sources.append(source);by_doi[identifier]=source;new_source_ids.append(sid)
        sid=source['id'];resolutions[key]=sid
        rid='RL7-'+key;cid='SL7-'+key;check_ids[key]=cid;review_ids[key]=rid
        r={'id':rid,'source_id':sid,'topic_ids':item['topic_ids'],'design':item['study_design'],
           'review_scope':'abstract','additional_reading_scope':item['reading_scope'],
           'review_method':'AI_assisted_single_review','reviewed_on':DATE,
           'key_findings_ja':item['findings_ja'],'limitations_ja':item['limitations_ja'],
           'conclusion_direction':'mixed','topic_relevance':5,'relevance_scope':'source_text_screened',
           'method_signals':item['method_signals'],'formal_evidence_certainty':'not_assessed',
           'publication_ready':False,'delivery_id':BATCH,'source_locators':item['locators']}
        c={'id':cid,'source_id':sid,'topic_ids':item['topic_ids'],'url':meta['url'],
           'checked_on':DATE,'review_scope':item['reading_scope'],'study_design':item['study_design'],
           'locators':item['locators'],'findings_ja':item['findings_ja'],'limitations_ja':item['limitations_ja'],
           'metrics':item['metrics'],'reporting_issues':item['reporting_issues'],
           'independent_review_completed':False,'formal_risk_of_bias':'not_assessed',
           'formal_evidence_certainty':'not_assessed','delivery_id':BATCH}
        for optional in ['author_reported_certainty','overlap_with_source_keys','external_method_review_url','published_on','search_end_date']:
            if optional in item:c[optional]=item[optional]
        # Existing dated checks are immutable: a new interpretation requires a new ID.
        for record,mapping,target in [(r,review_map,review_doc['reviews']),(c,text_map,text_doc['checks'])]:
            if record['id'] in mapping:
                if mapping[record['id']] != record:raise ValueError('Dated review changed: '+record['id'])
            else:target.append(record);mapping[record['id']]=record
        old=assessments.get(sid)
        if old and old.get('latest_source_check_id') != cid:
            history=OUTPUT+'/previous_assessments/'+sid+'.json'
            if not (ROOT/history).exists():save(history,{'schema_version':'1.0','assessment':old})
        if old and old.get('latest_source_check_id') == cid:
            updated=old
        else:
            updated={**(old or {}),'source_id':sid,'review_scope':item['reading_scope'],
              'method_signals':item['method_signals'],'formal_risk_of_bias':'not_assessed',
              'formal_evidence_certainty':'not_assessed','reliability_ja':'単独AI読解。著者の品質評価と当方の評価を区別。',
              'limitations_ja':[item['limitations_ja']],
              'provenance_review_ids':list(dict.fromkeys((old or {}).get('provenance_review_ids',[])+[rid])),
              'checked_on':DATE,'checked_sections':item['locators'],'integrity_status':'not_exhaustively_checked',
              'integrity_notices':(old or {}).get('integrity_notices',[]),
              'reporting_issues':(old or {}).get('reporting_issues',[])+item['reporting_issues'],
              'latest_source_check_id':cid}
        assessments[sid]=updated
        for tid in item['topic_ids']:
            topic=topics[tid]
            if sid not in topic['source_ids']:topic['source_ids'].append(sid)
            if rid not in topic.setdefault('source_review_ids',[]):topic['source_review_ids'].append(rid)
            pair=(tid,sid);edge=edge_map.get(pair)
            if edge is None:
                edge={'id':'EV-'+tid+'-'+sid,'topic_id':tid,'source_id':sid,'legacy_brief_ids':[]}
                edge_docs['data/evidence/'+category_for[tid]+'.json']['edges'].append(edge);edge_map[pair]=edge
            edge.update(relation_role=item['relation_role'],relevance_1_to_5=5,relevance_scope='source_text_screened',
              source_review_id=rid,finding_scope_ja=item['findings_ja'],conclusion_direction='mixed',
              limits_ja=item['limitations_ja'],formal_evidence_certainty='not_assessed')
    for path,d in topic_docs.items():save(path,d)
    for path,d in edge_docs.items():save(path,d)
    order=[a['source_id'] for a in assessment_doc['assessments']]
    order += [s['id'] for s in sources if s['id'] not in set(order)]
    assessment_doc['assessments']=[assessments[sid] for sid in order]
    save('data/sources.json',source_doc);save('data/source_assessments.json',assessment_doc)
    save('data/research/source_reviews.json',review_doc);save('data/research/source_text_checks.json',text_doc)
    products=[]
    for p,a in specs:
        tid=a['topic_id'];row=rows[tid];claims=[]
        source_keys=list(dict.fromkeys(k for section in a['sections'] for k in section['source_keys']))
        if not set(source_keys)<=resolutions.keys():raise ValueError('Unknown citation: '+tid)
        if not row.get('reviewed_delivery_id')==BATCH:
            for field in ['manuscript_path','claim_dossier_path']:
                if row.get(field):
                    original=ROOT/row[field]
                    backup=ROOT/'articles/history'/BATCH/original.name
                    backup.parent.mkdir(parents=True,exist_ok=True)
                    if backup.exists() and backup.read_bytes()!=original.read_bytes():raise ValueError('Archive conflict')
                    backup.write_bytes(original.read_bytes())
        lines=['---','topic_id: '+tid,'status: revised_manuscript_pending_release','publication_ready: false',
               'reviewed_delivery_id: '+BATCH,'---','','# '+a['title'],'',a['lead'],'']
        for s in a['sections']:
            keys=s['source_keys']
            if not keys or not all(tid in text_map[check_ids[k]]['topic_ids'] for k in keys):
                raise ValueError('Source/topic mismatch: '+tid)
            lines+=['## '+s['heading'],'',s['text']+' '+''.join('[^'+k+']' for k in keys),'']
            claims.append({'id':s['id'],'text_ja':s['text'],'source_ids':[resolutions[k] for k in keys],
              'source_check_ids':[check_ids[k] for k in keys], 'population_and_scope_ja':s['population_and_scope_ja'],
              'not_supported_ja':s['not_supported_ja'],'kind':s['kind'],
              'evidence_certainty':'not_formally_assessed','publication_ready':False})
        lines+=['## 日常ではどう使う？','',a['application']['text'],'',a['application']['safety'],'',
                '## まとめ','',a['conclusion'],'','## 出典と確認範囲','',
                '抄録または指定した本文箇所を確認し、研究の範囲に合わせて説明しています。生活の手順は編集上の応用例です。正式な独立査読や個別の効果保証ではありません。','']
        for key in source_keys:
            src=next(s for s in sources if s['id']==resolutions[key])
            scope=text_map[check_ids[key]]['review_scope']
            jp='抄録・指定箇所' if scope=='selected_fulltext_sections' else '抄録'
            lines += [f"[^{key}]: {src['authors_display']} ({src['year']}). {src['title']}. [{src['id']}]({src['url']})。確認範囲：{jp}。",'']
        lines += [f'[主張ごとの根拠・解釈上の限界](../../data/articles/claims/{tid}.json)','']
        manuscript='articles/manuscripts/'+tid+'.md';dossier='data/articles/claims/'+tid+'.json'
        (ROOT/manuscript).write_text('\n'.join(lines),encoding='utf-8')
        d={'schema_version':'1.0','topic_id':tid,'title':a['title'],'delivery_id':BATCH,
           'authoring_input_sha256':digest(p.read_bytes()),'claims':claims,
           'application':a['application'],'review_items':a['review_items'],
           'unresolved_source_keys':[],'independent_review_completed':False,'publication_ready':False,
           'editorial_self_check':{'completed':True,'method':'single_AI_claim_and_scope_check',
             'checks':['主張と引用の一致','反対結果と条件差の併記','数値の分母と比較条件','応用例の明示','未確認の報告不一致を推測しない']},
           'previous_manuscript_sha256':a['expected_previous_sha256']}
        save(dossier,d)
        row.update(state='manuscript_pending_article_review',manuscript_path=manuscript,claim_dossier_path=dossier,
          manuscript_sha256=digest((ROOT/manuscript).read_bytes()),claim_dossier_sha256=digest((ROOT/dossier).read_bytes()),
          source_ids=[resolutions[k] for k in source_keys],claim_count=len(claims),publication_ready=False,
          unresolved_source_keys=[],reviewed_delivery_id=BATCH,article_level_scientific_review='single_AI_claim_and_scope_check_not_independent')
        products.append({'topic_id':tid,'new_manuscript':a['expected_previous_sha256'] is None,
                         'manuscript_path':manuscript,'manuscript_sha256':row['manuscript_sha256'],
                         'claim_dossier_path':dossier,'claim_dossier_sha256':row['claim_dossier_sha256']})
    if before_identity != [(r['topic_id'],r['title_ja']) for r in catalog['articles']]:raise ValueError('Identity/order changed')
    save('data/articles/catalog.json',catalog)
    coverage=load('data/research/coverage.json');counts=Counter(r['review_scope'] for r in review_doc['reviews'])
    coverage.update(source_count=len(sources),source_review_count=len(review_doc['reviews']),abstract_review_count=counts['abstract'],
      bibliography_review_count=counts['bibliography'],selected_fulltext_checks_count=sum(a['review_scope']=='selected_fulltext_sections' for a in assessments.values()),evidence_edge_count=len(edge_map))
    save('data/research/coverage.json',coverage)
    manifest=load('data/manifest.json');manifest.update(source_count=len(sources));save('data/manifest.json',manifest)
    report={'schema_version':'1.0','delivery_id':BATCH,'date':DATE,'goal_articles':300,'goal_completed':False,
            'authored_articles':len(products),'new_manuscripts':sum(p['new_manuscript'] for p in products),
            'revised_manuscripts':sum(not p['new_manuscript'] for p in products),'source_checks':len(resolutions),
            'source_resolution':resolutions,'products':products,'publication_ready_count':0,
            'scope_ja':'本文改稿と単独AI点検。独立査読、正式な確実性評価、公開承認ではない。'}
    save(OUTPUT+'/report.json',report)
    doc=['# 学習法・創造性の原文照合と改稿','','5テーマの本文・根拠表を更新。新規2件、既存3件の改稿です。既存本文・根拠表をarticles/history/learning-20260911に保存しました。','',
         '新しい研究の肯定的結果だけでなく、条件差・無効果・本文内の報告不一致を残しています。公開承認は別です。','',
         '| テーマ | 原稿 | 根拠表 |','|---|---|---|']
    for p in products:doc.append('| '+p['topic_id']+' | [本文](../'+p['manuscript_path']+') | [根拠表](../'+p['claim_dossier_path']+') |')
    doc+=['','## 記事で採用しない精密値','',
          '学習スタイル2024年レビューの抄録と本文の統合値、歩行2026年レビューの人数・RCT数に不一致があります。どちらかを勝手に訂正せず、source_text_checksに確認箇所を残し、記事では該当する精密値を不使用としました。','',
          '## 次の作業','', '学習者が使える具体例の読みやすさを点検し、読解範囲が抄録にとどまる資料の方法・追試を補います。次の未着手テーマへも主張・研究・応用例を分けて執筆を続けます。']
    (ROOT/'docs/CONTINUATION_LEARNING_20260911.md').write_text('\n'.join(doc)+'\n',encoding='utf-8')
    subprocess.run([sys.executable,str(ROOT/'scripts/build_research_views.py')],check=True,cwd=ROOT)
    subprocess.run([sys.executable,str(ROOT/'scripts/reconcile_article_progress.py')],check=True,cwd=ROOT)
    print(json.dumps({'delivery':BATCH,'articles':len(products),'sources':len(sources),'new':report['new_manuscripts']},ensure_ascii=False))

if __name__=='__main__':run()
