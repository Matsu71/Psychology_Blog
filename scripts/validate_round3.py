#!/usr/bin/env python3
"""Cross-record checks, scoring reproducibility and bounded-file exports.

Does not assess scientific truth, semantic completeness or audience demand.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from build_research_views import priority
ROOT=Path(__file__).resolve().parents[1]


def require(test,message):
    if not test: raise ValueError(message)


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))


def validate():
    cats=read('data/categories.json')['categories']
    topics={t['id']:t for c in cats for t in read(c['file'])['topics']}
    source_list=read('data/sources.json')['sources']
    sources={s['id']:s for s in source_list}
    review_list=read('data/research/source_reviews.json')['reviews']
    reviews={r['id']:r for r in review_list}
    assessment_list=read('data/source_assessments.json')['assessments']
    assessments={a['source_id']:a for a in assessment_list}
    edge_list=[e for p in read('data/evidence/catalog.json')['files'] for e in read(p)['edges']]
    edges={e['id']:e for e in edge_list}
    require(len(reviews)==len(review_list),'Duplicate source review ID')
    require(len(assessments)==len(assessment_list) and set(assessments)==set(sources),'Source assessment coverage')
    require(len(edges)==len(edge_list),'Duplicate edge ID')
    doi_values=[s['doi'].lower() for s in source_list if s.get('doi')]
    require(len(doi_values)==len(set(doi_values)),'Duplicate DOI')
    for r in reviews.values():
        require(r['source_id'] in sources,'Unknown source')
        require(isinstance(r['topic_relevance'],int) and 1<=r['topic_relevance']<=5,'Bad relevance')
        require(isinstance(r['method_signals'],int) and 1<=r['method_signals']<=4,'Bad method signal')
        require(r['review_scope'] in ('abstract','bibliography','official_page_reviewed'),'Unexpected review scope')
        if r['review_scope']=='official_page_reviewed':
            require(sources[r['source_id']]['source_type']=='official_health_information',
                    'Official-page review must reference official health information')
            require(r.get('additional_reading_scope')=='official_page_reviewed',
                    'Official-page scope must be explicitly recorded')
            require(bool(r.get('source_locators')), 'Official-page review needs checked sections')
        require(r['publication_ready'] is False and r['formal_evidence_certainty']=='not_assessed','Inflated readiness')
        if r['review_scope']=='bibliography':
            require(r['key_findings_ja'] is None,'Bibliography must not assert results')
        else:
            require(isinstance(r['key_findings_ja'],str) and bool(r['key_findings_ja']),'Missing reviewed finding')
        for tid in r['topic_ids']:
            require(tid in topics and r['id'] in topics[tid].get('source_review_ids',[]),'Missing review backlink')
            require(r['source_id'] in topics[tid]['source_ids'],'Missing source backlink')
    expected_pairs={(tid,sid) for tid,t in topics.items() for sid in t['source_ids']}
    actual_pairs={(e['topic_id'],e['source_id']) for e in edges.values()}
    require(expected_pairs==actual_pairs and len(expected_pairs)==len(edges),'Evidence must correspond exactly to theme-source pairs')
    for e in edges.values():
        require(e['formal_evidence_certainty']=='not_assessed','Unexpected certainty')
        if e['source_review_id']:
            require(e['source_review_id'] in reviews,'Unknown source review')
    for tid,t in topics.items():
        for rid in t.get('source_review_ids',[]):
            require(rid in reviews and tid in reviews[rid]['topic_ids'],'Invalid topic backlink')
    rankings=[t for p in read('data/rankings/source_catalog.json')['files'] for t in read(p)['topics']]
    require(len(rankings)==len(topics) and {t['topic_id'] for t in rankings}==set(topics),'Ranking theme coverage')
    computed={}
    for group in rankings:
        require({r['source_id'] for r in group['sources']}==set(topics[group['topic_id']]['source_ids']),'Ranking sources mismatch')
        scores=[]
        for row in group['sources']:
            e=edges[row['edge_id']]
            result=priority(e,assessments[row['source_id']],sources[row['source_id']])
            for key in result: require(row[key]==result[key],'Non-reproducible source score: '+row['edge_id'])
            score=row['priority_score']
            if score is not None:
                require(0<=score<=100,'Score range')
                scores.append(score)
                computed[row['source_id']]=max(score,computed.get(row['source_id'],0))
            else:
                require(row['priority_rank'] is None,'Unassessed source cannot have scientific rank')
        require(scores==sorted(scores,reverse=True),'Source order')
    global_rows=read('data/rankings/sources_global.json')['sources']
    require({r['source_id'] for r in global_rows}==set(sources),'Global source view mismatch')
    for r in global_rows: require(r['priority_score']==computed.get(r['source_id']),'Global score not max of per-theme score')
    editorial=read('data/rankings/editorial_topics.json')['topics']
    require(len(editorial)==len(read('data/editorial_assessments.json')['assessments']) and len({r['topic_id'] for r in editorial})==len(editorial),'Editorial assessment coverage')
    for r in editorial:
        c=r['components']
        expected=c['daily_relevance']*8+c['actionability']*5+c['interest']*4+c['audience_breadth']*3
        require(expected==r['editorial_score'],'Editorial formula')
        require(not r['audience_analytics_measured'] and not r['publication_ready'],'Editorial status')
    queue=read('data/rankings/research_queue.json')['topics']
    require(len(queue)==len(topics) and {r['topic_id'] for r in queue}==set(topics),'Research queue coverage')
    for r in queue:
        appeal=r['editorial_score'] if r['editorial_score'] is not None else r['editorial_fallback_for_queue']
        require(r['work_priority_score']==round(.55*appeal+.45*r['gap_score'],2),'Queue formula')
        require(r['publication_ready'] is False,'Queue is not publication approval')
    coverage=read('data/research/coverage.json')
    require(coverage.get('source_review_count',coverage['round3_source_review_count'])==len(reviews),'Review count')
    require(coverage.get('abstract_review_count',coverage['round3_abstract_review_count'])==sum(r['review_scope']=='abstract' for r in reviews.values()),'Abstract count')
    require(coverage.get('official_page_review_count',0)==sum(r['review_scope']=='official_page_reviewed' for r in reviews.values()),'Official-page review count')
    require(coverage['selected_fulltext_checks_count']==sum(a['review_scope']=='selected_fulltext_sections' for a in assessments.values()),'Fulltext scope count')
    require(coverage['search_pending_count']==sum(not t['source_ids'] for t in topics.values()),'Unregistered count')
    require(coverage['evidence_edge_count']==len(edges),'Edge count')
    sizes=[(str(p.relative_to(ROOT)),p.stat().st_size) for p in (ROOT/'data').rglob('*.json')]
    require(all(n<50*1024*1024 for p,n in sizes),'Unexpected large Git object')
    shards=[(p,n) for p,n in sizes if p.startswith('data/literature/round3/')]
    require(all(n<1024*1024 for p,n in shards),'Research shard exceeds internal 1MiB threshold')
    return {'schema_version':'1.0','status':'passed','topics':len(topics),'sources':len(sources),
        'official_page_reviews':coverage.get('official_page_review_count',0),'source_reviews_total':len(reviews),'abstract_reviews_total':coverage.get('abstract_review_count',coverage['round3_abstract_review_count']),
        'bibliography_only':coverage.get('bibliography_review_count',coverage['round3_bibliography_only_count']),'selected_fulltext_checks':coverage['selected_fulltext_checks_count'],
        'evidence_edges':len(edges),'source_unregistered':coverage['search_pending_count'],
        'editorial_topics_assessed':len(editorial),'research_queue_topics':len(queue),
        'data_json_bytes':sum(n for _,n in sizes),'largest_data_json_bytes':max(n for _,n in sizes),
        'data_files_over_1MiB':[p for p,n in sizes if n>1024*1024],
        'scope_ja':'構造・参照・件数・採点式・未確認ラベル・分割サイズの検証。科学的真偽、全文の査読相当の評価、意味重複の網羅確認ではない。'}


def export(out,report):
    out=out.resolve()
    require(not out.is_relative_to((ROOT/'data').resolve()),'Export cannot overwrite canonical data')
    out.mkdir(parents=True,exist_ok=True)
    # This tree is the complete portable database, not an incomplete legacy export.
    for name in ('data','docs','schemas'):
        if (ROOT/name).exists():
            shutil.copytree(ROOT/name,out/'database'/name,dirs_exist_ok=True)
    for name in ('README.md','AGENTS.md'):
        shutil.copyfile(ROOT/name,out/'database'/name)
    for name in ('RANKINGS.md','ROUND3_SOURCE_NOTES.md','DATABASE_ARCHITECTURE.md','NEXT_STEPS.md'):
        shutil.copyfile(ROOT/'docs'/name,out/name)
    (out/'round3_validation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--export',type=Path)
    a=p.parse_args()
    try:
        report=validate()
        if a.export: export(a.export,report)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError,KeyError,TypeError) as e:
        print('ROUND3 VALIDATION FAILED: '+str(e),file=sys.stderr)
        return 1
if __name__=='__main__':
    raise SystemExit(main())
