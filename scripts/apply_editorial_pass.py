#!/usr/bin/env python3
"""Integrate explicitly authored source checks and manuscripts, offline.

This materializes human-readable decisions; it does not search or approve science.
"""
from __future__ import annotations
import hashlib
import json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'research/editorial_pass_20260911'
DATE='2026-09-11'
REVISION='source-editorial-pass-20260911'

def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))

def save(path,obj):
    p=ROOT/path
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def text(path,value):
    p=ROOT/path
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(value.rstrip()+'\n',encoding='utf-8')

def digest(path):
    return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()

def specs():
    return [json.loads(p.read_text(encoding='utf-8'))['article'] for p in sorted(INPUT.glob('PSY-*.json'))]

def source_identity(s):
    if s.get('doi'): return ('doi',s['doi'].strip().lower())
    if s.get('pmid'): return ('pmid',str(s['pmid']))
    assert s.get('url'),'Source lacks resolvable identity'
    return ('url',s['url'].rstrip('/'))

def integrate_sources():
    check_doc=read('research/editorial_pass_20260911/source_checks.json')
    checks=[{**check_doc.get('defaults',{}),**c} for c in check_doc['checks']]
    check_doc['checks']=checks
    assert len({c['id'] for c in checks})==len(checks)
    cats=read('data/categories.json')['categories']
    docs={c['file']:read(c['file']) for c in cats}
    topics={t['id']:t for d in docs.values() for t in d['topics']}
    original=[(t['id'],t['title_ja']) for t in topics.values()]
    source_doc=read('data/sources.json')
    sources={s['id']:s for s in source_doc['sources']}
    for new in read('research/editorial_pass_20260911/new_sources.json')['sources']:
        if new['id'] in sources:
            assert source_identity(sources[new['id']])==source_identity(new),'Source ID conflict'
        else:
            assert source_identity(new) not in {source_identity(s) for s in sources.values()},'Duplicate source identity'
            sources[new['id']]=dict(new)
            source_doc['sources'].append(sources[new['id']])
    adoc=read('data/source_assessments.json')
    assessments={a['source_id']:a for a in adoc['assessments']}
    rdoc=read('data/research/source_reviews.json')
    reviews={r['id']:r for r in rdoc['reviews']}
    edocs={p:read(p) for p in read('data/evidence/catalog.json')['files']}
    edges={(e['topic_id'],e['source_id']):e for d in edocs.values() for e in d['edges']}
    tcat={t['id']:c['id'] for c in cats for t in docs[c['file']]['topics']}
    depths={'bibliography':1,'legacy_not_reassessed':0,'legacy_abstract_review':2,'abstract':2,'selected_fulltext_sections':3}
    for c in checks:
        sid,rid=c['source_id'],c['id']
        assert sid in sources and set(c['topic_ids'])<=set(topics)
        assert c['formal_evidence_certainty']=='not_assessed' and not c['independent_review_completed']
        scope=c['review_scope']
        assert scope in ('abstract','selected_fulltext_sections')
        s=sources[sid]
        if s.get('verification_scope')=='bibliography_verified': s['verification_scope']='abstract_reviewed'
        s['latest_source_check_id']=rid
        s['latest_source_checked_on']=DATE
        r={'id':rid,'source_id':sid,'topic_ids':c['topic_ids'],'design':c['study_design'],
           'review_scope':'abstract','additional_reading_scope':scope,'review_method':c['review_method'],
           'reviewed_on':DATE,'key_findings_ja':c['findings_ja'],'limitations_ja':c['limitations_ja'],
           'conclusion_direction':'mixed','topic_relevance':c.get('relevance_1_to_5',5),
           'relevance_scope':'source_text_screened','method_signals':c['method_signals'],
           'formal_evidence_certainty':'not_assessed','publication_ready':False,
           'source_locators':c['locators'],'reading_source_url':c['url'],'delivery_id':REVISION,
           'structured_source_check':'data/research/source_text_checks.json#'+rid}
        if rid in reviews: reviews[rid].update(r)
        else:
            rdoc['reviews'].append(r); reviews[rid]=r
        a=assessments.get(sid)
        if a is None:
            a={'source_id':sid,'integrity_notices':[],'provenance_review_ids':[]}
            adoc['assessments'].append(a); assessments[sid]=a
        old_scope=a.get('review_scope','legacy_not_reassessed')
        a.update(review_scope=scope if depths[scope]>=depths.get(old_scope,0) else old_scope,
                 method_signals=c['method_signals'],formal_risk_of_bias='not_assessed',formal_evidence_certainty='not_assessed',
                 limitations_ja=[c['limitations_ja']],checked_on=DATE,checked_sections=c['locators'],
                 reporting_issues=c['reporting_issues'],latest_source_check_id=rid,
                 reliability_ja='確認した原文箇所に対する単独AI読解。正式な確実性評価や独立査読ではない。')
        a['provenance_review_ids']=list(dict.fromkeys(a.get('provenance_review_ids',[])+[rid]))
        for tid in c['topic_ids']:
            t=topics[tid]
            if sid not in t['source_ids']: t['source_ids'].append(sid)
            if rid not in t.setdefault('source_review_ids',[]): t['source_review_ids'].append(rid)
            e=edges.get((tid,sid))
            if e is None:
                e={'id':'EV-'+tid+'-'+sid,'topic_id':tid,'source_id':sid,'legacy_brief_ids':[]}
                edocs['data/evidence/'+tcat[tid]+'.json']['edges'].append(e); edges[(tid,sid)]=e
            e.update(relation_role='correction_notice' if s.get('record_role')=='correction_notice' else c['evidence_relation_role'],
                     relevance_1_to_5=c.get('relevance_1_to_5',5),relevance_scope='source_text_screened',
                     source_review_id=rid,finding_scope_ja=c['findings_ja'],conclusion_direction='mixed',
                     limits_ja=c['limitations_ja'],formal_evidence_certainty='not_assessed')
    for path,d in docs.items(): save(path,d)
    for path,d in edocs.items(): save(path,d)
    for d in (source_doc,adoc,rdoc): d['updated_on']=DATE
    save('data/sources.json',source_doc)
    save('data/source_assessments.json',adoc)
    save('data/research/source_reviews.json',rdoc)
    save('data/research/source_text_checks.json',check_doc)
    coverage=read('data/research/coverage.json')
    counts=Counter(r['review_scope'] for r in rdoc['reviews'])
    coverage.update(source_count=len(sources),source_review_count=len(reviews),abstract_review_count=counts['abstract'],
                    bibliography_review_count=counts['bibliography'],evidence_edge_count=len(edges),
                    selected_fulltext_checks_count=sum(a['review_scope']=='selected_fulltext_sections' for a in assessments.values()),
                    reference_linked_count=sum(bool(t['source_ids']) for t in topics.values()),
                    search_pending_count=sum(not t['source_ids'] for t in topics.values()),
                    source_check_pass=REVISION,source_check_pass_records=len(checks))
    for c in coverage['categories']:
        rows=[t for tid,t in topics.items() if tcat[tid]==c['category_id']]
        c['reference_linked_count']=sum(bool(t['source_ids']) for t in rows)
        c['source_unregistered_count']=sum(not t['source_ids'] for t in rows)
        c['source_review_topic_count']=sum(bool(t.get('source_review_ids')) for t in rows)
    save('data/research/coverage.json',coverage)
    m=read('data/manifest.json')
    m.update(source_count=len(sources),reference_linked_count=coverage['reference_linked_count'],
             search_pending_count=coverage['search_pending_count'],updated_on=DATE,latest_editorial_pass=REVISION)
    m['files']['source_text_checks']='data/research/source_text_checks.json'
    save('data/manifest.json',m)
    assert original==[(t['id'],t['title_ja']) for t in topics.values()]

def apply_audit_resolutions():
    path=INPUT/'audit_resolutions.json'
    if not path.exists(): return
    decisions=json.loads(path.read_text(encoding='utf-8'))['resolutions']
    doc=read('data/articles/audit_status.json')
    items={i['audit_id']:i for i in doc['items']}
    for d in decisions:
        assert d['audit_id'] in items and d['source_check_ids']
        item=items[d['audit_id']]
        item.setdefault('per_topic_resolution',{})[d['topic_id']]='addressed_in_current_manuscript'
        records=item.setdefault('resolution_records',[])
        new={**d,'editorial_pass':REVISION,'checked_on':DATE,'independent_review':False}
        old=next((r for r in records if r['topic_id']==d['topic_id'] and r['editorial_pass']==REVISION),None)
        if old is None: records.append(new)
        else: old.update(new)
        required=item.get('topic_ids',[])
        item['status']='addressed_in_current_manuscripts' if required and all(item['per_topic_resolution'].get(t)=='addressed_in_current_manuscript' for t in required) else 'partially_addressed'
    doc['updated_on']=DATE
    doc['resolution_scope_ja']='旧原稿の具体的な問題への修正。元研究の未解決点の修復、網羅的学術レビュー、独立査読ではない。'
    save('data/articles/audit_status.json',doc)

def apply_manuscripts():
    authored=specs()
    assert len({a['topic_id'] for a in authored})==len(authored)
    sources={s['id']:s for s in read('data/sources.json')['sources']}
    checks={c['source_id']:c for c in read('data/research/source_text_checks.json')['checks']}
    catalog=read('data/articles/catalog.json')
    rows={r['topic_id']:r for r in catalog['articles']}
    audit=read('data/articles/audit_status.json')
    for a in authored:
        tid=a['topic_id']; assert tid in rows
        srcids=[s['source_id'] for s in a['source_selectors']]
        assert len(srcids)==len(set(srcids)) and set(srcids)<=set(sources)
        assert set(srcids)<=set(checks) and all(tid in checks[s]['topic_ids'] for s in srcids)
        assert not a['publication_ready'] and a['state']=='source_checked_manuscript'
        claims=[]
        for c in a['claims']:
            assert c['sources'] and set(c['sources'])<=set(srcids)
            claims.append({'id':tid+'-R6-'+c['key'],'claim_ja':c['text'],'population_and_scope_ja':c['scope'],
               'not_supported_ja':c['not_supported'],'source_keys':c['sources'],'source_ids':c['sources'],
               'source_resolution_complete':True,'source_check_ids':[checks[s]['id'] for s in c['sources']],
               'source_locators':{s:checks[s]['locators'] for s in c['sources']},
               'claim_review_status':'AI_source_text_checked_with_stated_scope',
               'evidence_certainty':'not_formally_assessed','publication_ready':False})
        rel='data/articles/claims/'+tid+'.json'
        old=read(rel) if (ROOT/rel).exists() else {}
        d={'schema_version':'1.0','topic_id':tid,'title_ja':a['title'],'category_id':old.get('category_id') or rows[tid].get('category_id'),
           'created_on':old.get('created_on',DATE),'updated_on':DATE,'authoring_revision':REVISION,
           'authoring_input':'research/editorial_pass_20260911/'+tid+'.json',
           'authoring_input_sha256':digest('research/editorial_pass_20260911/'+tid+'.json'),
           'source_resolution':{s:{'selector':{'source_id':s,'doi':sources[s].get('doi')},'source_ids':[s],
                 'resolution_method':'exact_identifier','claim_support_verified_by_compiler':False} for s in srcids},
           'claims':claims,'unresolved_source_keys':[],'application':a['application'],'outstanding_audit_items':[],
           'editorial_hold':None,'state':a['state'],'reporting_caveats':[{'source_id':s,'issue':i} for s in srcids for i in checks[s]['reporting_issues']],
           'publication_ready':False,'independent_review_completed':False,
           'review_boundary_ja':'確認した原文箇所と限定した主張を照合し改稿。独立査読・医学的監修・公開承認とは別。'}
        for issue in audit['items']:
            if not issue.get('topic_ids') or tid in issue['topic_ids']:
                d['outstanding_audit_items'].append({'audit_id':issue['audit_id'],'status':issue.get('per_topic_resolution',{}).get(tid,issue['status'])})
        save(rel,d)
        lines=['# '+a['title'],'',a['lead'],'']
        for sec in a['sections']:
            assert set(sec['sources'])<=set(srcids)
            lines+=['## '+sec['heading'],'',sec['text'],'']
            if sec['sources']: lines+=['出典：'+'、'.join('['+s+']('+sources[s]['url']+')' for s in sec['sources']),'']
        lines+=['## 日常へのつなげ方','','以下は編集上の応用例です。研究でその手順そのものが検証されたという意味ではありません。','']
        lines += [str(i)+'. '+step for i,step in enumerate(a['application']['steps'],1)]
        lines += ['',a['application']['safety'],'','## 参考文献','']
        for sid in srcids:
            s=sources[sid]
            lines+=['['+sid+'] '+s['authors_display']+' ('+str(s.get('year') or '年未確認')+'). ['+s['title']+']('+s['url']+'). '+str(s.get('journal') or '')+'.','']
        lines+=['---','','確認日：'+DATE+'。AI支援による原文照合と編集。独立した査読・公開承認は別途管理しています。',
                '[主張ごとの根拠・適用範囲](../../data/articles/claims/'+tid+'.json)','']
        path='articles/manuscripts/'+tid+'.md'
        text(path,'\n'.join(lines))
        rows[tid].update(state=a['state'],manuscript_path=path,claim_dossier_path=rel,claim_count=len(claims),
                        unresolved_source_keys=[],manuscript_sha256=digest(path),publication_ready=False,
                        latest_editorial_pass=REVISION,source_check_ids=[checks[s]['id'] for s in srcids])
    save('data/articles/catalog.json',catalog)
    p=read('data/articles/progress.json')
    active=[r for r in catalog['articles'] if r.get('manuscript_path')]
    p.update(manuscript_count=len(active),claim_dossier_count=len(active),claim_and_caution_count=sum(r.get('claim_count',0) for r in active),
             source_checked_manuscript_count=sum(r.get('state')=='source_checked_manuscript' for r in active),
             source_checked_manuscript_ids=[r['topic_id'] for r in active if r.get('state')=='source_checked_manuscript'],
             publication_ready_count=0,goal_completed=False,dossiers_with_unresolved_sources=[r['topic_id'] for r in active if r.get('unresolved_source_keys')],latest_editorial_pass=REVISION)
    p['top20_source_checked_count']=sum(t in p['source_checked_manuscript_ids'] for t in p['top20_topic_ids'])
    save('data/articles/progress.json',p)
    render_docs()
    return p

def render_docs():
    p=read('data/articles/progress.json'); cov=read('data/research/coverage.json')
    rows=read('data/articles/catalog.json')['articles']; audits=read('data/articles/audit_status.json')['items']
    n=p.get('source_checked_manuscript_count',0)
    lines=['# 記事制作の現在地','',f"目標300記事。本文{p['manuscript_count']}件、主張対応表{p['claim_dossier_count']}件。",'',
           f"原文の確認箇所と主張を照合した改稿：{n}件。上位20のうち{p.get('top20_source_checked_count',0)}件。公開承認済み0件。",'',
           'source_checked_manuscriptは限定した主張の原文照合と単独AI編集が済んだ原稿。独立査読・全研究の確実性評価・医療監修・公開承認とは別です。','',
           '| テーマ | 本文 | 状態 |','|---|---|---|']
    for r in rows:
        link='[原稿](../'+r['manuscript_path']+')' if r.get('manuscript_path') else '未着手'
        lines.append(f"| {r['topic_id']} {r['title_ja']} | {link} | {r['state']} |")
    lines+=['','## 監査事項','','| ID | 状態 |','|---|---|']
    lines += [f"| {i['audit_id']} | {i['status']} |" for i in audits]
    text('docs/ARTICLE_PROGRESS.md','\n'.join(lines))
    remaining=[t for t in p['top20_topic_ids'] if t not in p.get('source_checked_manuscript_ids',[])]
    text('docs/NEXT_STEPS.md','\n'.join(['# 次の作業','','最終目標：読者が生活に結びつけられる、根拠の明確な300記事。','',
        f"出典{cov['source_count']}件、出典未登録{cov['search_pending_count']}テーマ、本文{p['manuscript_count']}件、原文照合後の改稿{n}件。",'',
        '上位20の未照合原稿：'+('、'.join(remaining) if remaining else '限定した主張の照合済み。独立点検・公開判断は別。'),'',
        '1. 残る監査事項を原文・訂正・反証と照合し、主張の範囲を決めて改稿する。',
        '2. 原文の報告上の不一致は推測で修正せず保留し、必要なら該当する主張を使わない。',
        '3. 読みやすさ、過剰一般化、日本への適用、医療的内容の安全性を記事単位で点検する。',
        '4. 整った非臨床原稿から公開判断へ進め、未着手テーマにも同じ工程を続ける。','',
        '原稿数や出典数を完成300本に読み替えない。会話終了後の自動実行は設定していない。']))
    text('README.md','\n'.join(['# Psychology Blog — 人間の科学・記事制作データベース','',
        '**最終目標：一般向けに面白く、科学的根拠をたどれる300記事。**','',
        f"28分野・300テーマ。出典{cov['source_count']}件。出典未登録{cov['search_pending_count']}テーマ。",'',
        f"本文{p['manuscript_count']}件、主張対応表{p['claim_dossier_count']}件。原文照合後の改稿{n}件。公開承認済み0件。",'',
        '- [記事の現在地](docs/ARTICLE_PROGRESS.md)', '- [原文照合と注意点](docs/SOURCE_CHECKS.md)',
        '- [次の作業](docs/NEXT_STEPS.md)', '- [順位](docs/RANKINGS.md) / [データ設計](docs/DATABASE_ARCHITECTURE.md)','',
        '出典登録、抄録読解、本文の確認範囲、原稿編集、公開判断を分離します。相関と因果、研究場面と応用例、同じ試験の別版を区別し、未確認情報を推測しません。','',
        'テーマはdata/topics、出典はdata/sources.json、読解はdata/research/source_text_checks.json、原稿はarticles/manuscripts、根拠表はdata/articles/claimsです。旧入力とGit履歴、テーマのID・題名・順序を維持します。','',
        '```bash','python scripts/apply_editorial_pass.py','python scripts/validate.py','python scripts/validate_research.py','python scripts/validate_round3.py','python scripts/validate_editorial_pass.py','```','',
        'スクリプトは編集入力を反映するもので、科学的な正しさを自動認定しません。公開サイトへの自動配信・定期実行は設定していません。']))
    sources={s['id']:s for s in read('data/sources.json')['sources']}
    lines=['# 原文照合の記録','','確認箇所に限定したAI支援の単独読解。全文の独立査読・解析再現・GRADE評価ではありません。','']
    for c in read('data/research/source_text_checks.json')['checks']:
        lines+=['## '+c['id']+' — '+sources[c['source_id']]['title'],'','[確認した出典]('+c['url']+')','',
                '範囲：'+c['review_scope']+' / '+'; '.join(c['locators']),'',c['findings_ja'],'','**限界：** '+c['limitations_ja'],'']
        if c['reporting_issues']: lines+=['**記載上の注意：** '+'; '.join(i['detail_ja']+' ['+i['status']+']' for i in c['reporting_issues']),'']
    text('docs/SOURCE_CHECKS.md','\n'.join(lines))

def main():
    integrate_sources()
    apply_audit_resolutions()
    apply_manuscripts()
    from build_research_views import build
    build()
    render_docs()
    from validate_editorial_pass import validate
    report=validate()
    save('data/articles/editorial_pass_report.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
