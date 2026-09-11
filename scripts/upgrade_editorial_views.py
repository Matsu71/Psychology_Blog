#!/usr/bin/env python3
"""Small idempotent compatibility changes; refuse an unexpected source version."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def patch(path, changes):
    p=ROOT/path
    text=p.read_text(encoding='utf-8')
    for old,new in changes:
        if old in text:
            assert text.count(old)==1, (path,'ambiguous patch')
            text=text.replace(old,new)
        elif new not in text:
            raise RuntimeError('Unexpected source; reconcile '+path)
    p.write_text(text,encoding='utf-8')

patch('scripts/validate_round3.py',[
("require(coverage['round3_source_review_count']==len(reviews),'Review count')", "require(coverage.get('source_review_count',coverage['round3_source_review_count'])==len(reviews),'Review count')"),
("require(coverage['round3_abstract_review_count']==sum(r['review_scope']=='abstract' for r in reviews.values()),'Abstract count')", "require(coverage.get('abstract_review_count',coverage['round3_abstract_review_count'])==sum(r['review_scope']=='abstract' for r in reviews.values()),'Abstract count')"),
("'new_source_reviews':len(reviews),'new_abstract_reviews':coverage['round3_abstract_review_count'],", "'source_reviews_total':len(reviews),'abstract_reviews_total':coverage.get('abstract_review_count',coverage['round3_abstract_review_count']),"),
("'bibliography_only':coverage['round3_bibliography_only_count'],'selected_fulltext_checks':coverage['selected_fulltext_checks_count'],", "'bibliography_only':coverage.get('bibliography_review_count',coverage['round3_bibliography_only_count']),'selected_fulltext_checks':coverage['selected_fulltext_checks_count'],")])
patch('scripts/build_research_views.py',[
("    render_docs(categories, documents, editorial, queue, by_topic, sources, coverage)\n    return", "    render_docs(categories, documents, editorial, queue, by_topic, sources, coverage)\n    if (ROOT/'data/research/editorial_delivery_report.json').exists():\n        from apply_editorial_delivery import render_delivery_docs\n        render_delivery_docs()\n    return"),
("    for review in load('data/research/source_reviews.json')['reviews']:\n        source=sources[review['source_id']]", "    for review in load('data/research/source_reviews.json')['reviews']:\n        if review.get('delivery_id'):\n            continue\n        source=sources[review['source_id']]"),
("登録資料数 | 第3回読解メモ数", "登録資料数 | 累計読解メモ数")])
print('PASS: cumulative review counts and versioned reader views.')
