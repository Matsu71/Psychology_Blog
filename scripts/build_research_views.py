#!/usr/bin/env python3
"""Deterministic, offline derived views. Does not reorder canonical records."""
from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'work-priority-1.1'
DATE = json.loads((ROOT / 'data/manifest.json').read_text(encoding='utf-8')).get('updated_on', '2026-09-11')


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def save(path: str, obj) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def text(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.rstrip() + '\n', encoding='utf-8')


def priority(edge: dict, assessment: dict, source: dict) -> dict:
    fit = edge['relevance_1_to_5']
    method = assessment['method_signals']
    scope = assessment['review_scope']
    depth = {'bibliography': 1, 'abstract': 2, 'legacy_abstract_review': 2,
             'selected_fulltext_sections': 3}.get(scope)
    notes = assessment.get('integrity_notices', [])
    pending_correction = any('erratum in' in x.get('type', '').lower() for x in notes)
    suspected_retraction = any('retract' in x.get('type', '').lower() and 'preprint' not in x.get('type', '').lower() for x in notes)
    open_reporting = any(x.get('status') == 'open_original_paper_check' for x in assessment.get('reporting_issues', []))
    excluded = source.get('record_role') == 'correction_notice' or suspected_retraction
    score = None
    caps = []
    if fit is not None and method is not None and depth is not None and not excluded:
        score = fit * 10 + method * 7.5 + depth * 5
        if edge['relevance_scope'] == 'title_only_provisional' or scope == 'bibliography':
            score = min(score, 49)
            caps.append('bibliography_only_max_49')
        if pending_correction:
            score = min(score, 65)
            caps.append('unresolved_indexed_correction_max_65')
        if open_reporting:
            score = min(score, 65)
            caps.append('unresolved_reporting_issue_max_65')
        if edge['relation_role'] == 'context_only':
            score = min(score, 55)
            caps.append('background_only_max_55')
    return {'priority_score': score, 'components': {'theme_relevance_1_to_5': fit,
            'method_signals_0_to_4': method, 'reading_depth_0_to_4': depth},
            'caps': caps, 'excluded_from_evidence_priority': excluded,
            'integrity_requires_followup': pending_correction or suspected_retraction or open_reporting,
            'score_interpretation': 'reading_and_research_priority_not_probability_of_truth'}


def sort_sources(rows: list) -> list:
    rows = sorted(rows, key=lambda x: (x['priority_score'] is None, -(x['priority_score'] or 0), x['source_id']))
    previous, rank = object(), None
    for position, row in enumerate(rows, 1):
        score = row['priority_score']
        if score is not None:
            if score != previous:
                rank = position
            row['priority_rank'] = rank
        else:
            row['priority_rank'] = None
        previous = score
        row['display_position'] = position
    return rows


def build() -> dict:
    categories = load('data/categories.json')['categories']
    documents = {c['id']: load(c['file']) for c in categories}
    topics = {t['id']: t for d in documents.values() for t in d['topics']}
    sources = {s['id']: s for s in load('data/sources.json')['sources']}
    assessments = {a['source_id']: a for a in load('data/source_assessments.json')['assessments']}
    edges = [e for path in load('data/evidence/catalog.json')['files'] for e in load(path)['edges']]
    by_topic = defaultdict(list)
    for edge in edges:
        sid = edge['source_id']
        row = {'edge_id': edge['id'], 'source_id': sid, 'title': sources[sid]['title'],
               'review_scope': assessments[sid]['review_scope'], 'relation_role': edge['relation_role'],
               'conclusion_direction': edge['conclusion_direction'],
               'limits_ja': edge['limits_ja'], **priority(edge, assessments[sid], sources[sid])}
        by_topic[edge['topic_id']].append(row)
    global_rows = {}
    for tid in topics:
        by_topic[tid] = sort_sources(by_topic[tid])
        for row in by_topic[tid]:
            sid = row['source_id']
            item = global_rows.setdefault(sid, {'source_id': sid, 'title': row['title'],
                'priority_score': None, 'best_matched_topic_ids': [], 'review_scope': row['review_scope'],
                'formal_evidence_certainty': 'not_assessed'})
            score = row['priority_score']
            if score is not None:
                if item['priority_score'] is None or score > item['priority_score']:
                    item['priority_score'], item['best_matched_topic_ids'] = score, [tid]
                elif score == item['priority_score']:
                    item['best_matched_topic_ids'].append(tid)
    for sid, source in sources.items():
        global_rows.setdefault(sid, {'source_id': sid, 'title': source['title'], 'priority_score': None,
            'best_matched_topic_ids': [], 'review_scope': assessments[sid]['review_scope'],
            'formal_evidence_certainty': 'not_assessed'})
    catalog = []
    for category in categories:
        tids = [t['id'] for t in documents[category['id']]['topics']]
        path = 'data/rankings/sources_by_topic/' + category['id'] + '.json'
        save(path, {'schema_version': '1.0', 'scoring_version': VERSION,
            'category_id': category['id'], 'topics': [{'topic_id': tid, 'sources': by_topic[tid]} for tid in tids]})
        catalog.append(path)
    save('data/rankings/source_catalog.json', {'schema_version': '1.0', 'files': catalog})
    save('data/rankings/sources_global.json', {'schema_version': '1.0', 'scoring_version': VERSION,
        'definition_ja': 'テーマ別の最大調査優先度で表示。リンク数・引用数では加点しない。未評価は順位なし。',
        'sources': sort_sources(list(global_rows.values()))})
    editorial = []
    for input_row in load('data/editorial_assessments.json')['assessments']:
        tid=input_row['topic_id']
        assert tid in topics
        daily=input_row['daily_relevance']
        action=input_row['actionability']
        interest=input_row['interest']
        breadth=input_row['audience_breadth']
        reason=input_row['reason_ja']
        assert all(1 <= x <= 5 for x in (daily, action, interest, breadth))
        score = daily*8 + action*5 + interest*4 + breadth*3
        editorial.append({'topic_id': tid, 'title_ja': topics[tid]['title_ja'], 'editorial_score': score,
            'components': {'daily_relevance': daily, 'actionability': action, 'interest': interest, 'audience_breadth': breadth},
            'reason_ja': reason, 'assessment_type': 'subjective_editorial_hypothesis',
            'audience_analytics_measured': False, 'publication_ready': False})
    assert editorial and len({r['topic_id'] for r in editorial}) == len(editorial)
    editorial.sort(key=lambda x: (-x['editorial_score'], x['topic_id']))
    previous, rank = None, 0
    for pos, row in enumerate(editorial, 1):
        if row['editorial_score'] != previous:
            rank = pos
        row['rank'] = rank
        row['display_position'] = pos
        previous = row['editorial_score']
    editorial_by_id = {r['topic_id']: r for r in editorial}
    save('data/rankings/editorial_topics.json', {'schema_version': '1.0', 'scoring_version': VERSION,
        'assessed_count': len(editorial), 'not_assessed_count': len(topics)-len(editorial),
        'warning_ja': '50テーマの編集上の仮説。実際の人気・検索数・収益性のランキングではない。未評価250件は下位と判定したものではない。',
        'topics': editorial})
    queue = []
    for tid, topic in topics.items():
        reviewed_direct = [r for r in by_topic[tid] if r['components']['theme_relevance_1_to_5'] is not None
            and r['components']['theme_relevance_1_to_5'] >= 4
            and r['review_scope'] not in ('bibliography', 'legacy_not_reassessed')
            and not r['excluded_from_evidence_priority']]
        body = [r for r in reviewed_direct if r['review_scope'] == 'selected_fulltext_sections']
        state = 'source_unregistered' if not topic['source_ids'] else ('legacy_review_needs_relevance_recheck' if topic.get('research_brief_ids') else 'no_targeted_review') if not reviewed_direct else 'abstract_evidence_available' if not body else 'selected_methods_checked'
        gap = {'source_unregistered': 100, 'no_targeted_review': 90, 'legacy_review_needs_relevance_recheck': 75, 'abstract_evidence_available': 65, 'selected_methods_checked': 45}[state]
        e = editorial_by_id.get(tid)
        appeal = e['editorial_score'] if e else 50
        task = {'legacy_review_needs_relevance_recheck': '既存の読解メモはある。テーマとの適合性を再点検し、全文・反証・更新資料を確認する。', 'source_unregistered': '原著・統合研究を検索し、問いとの直接の関連を確認する。',
                'no_targeted_review': '書誌・背景資料から、対象と結果が対応する抄録・全文を確認する。',
                'abstract_evidence_available': '優先資料の全文・独立追試・反証・訂正を照合する。',
                'selected_methods_checked': '補足資料・登録計画・独立した裏付けを確認し主張単位で評価する。'}[state]
        queue.append({'topic_id': tid, 'title_ja': topic['title_ja'], 'work_priority_score': round(0.55*appeal+0.45*gap,2),
            'editorial_score': e['editorial_score'] if e else None,
            'editorial_fallback_for_queue': None if e else 50,
            'gap_score': gap, 'evidence_state': state, 'next_action_ja': task,
            'legacy_brief_count': len(topic.get('research_brief_ids',[])), 'source_review_count': len(topic.get('source_review_ids',[])), 'targeted_review_source_count': len(reviewed_direct), 'selected_fulltext_source_count': len(body),
            'publication_ready': False})
    queue.sort(key=lambda x: (-x['work_priority_score'], x['topic_id']))
    for position, row in enumerate(queue, 1):
        row['queue_position'] = position
    save('data/rankings/research_queue.json', {'schema_version': '1.0', 'scoring_version': VERSION,
        'definition_ja': '55％編集優先度＋45％調査不足。編集未評価は作業配分用に50を仮置きし、人気点数はnullのまま。',
        'topics': queue})
    save('data/research/next_queue.json', {'schema_version': '1.0', 'not_an_automatic_schedule': True,
        'ranked_queue': 'data/rankings/research_queue.json',
        'topic_ids_without_registered_sources': [r['topic_id'] for r in queue if r['evidence_state']=='source_unregistered'],
        'topic_ids_without_targeted_review': [r['topic_id'] for r in queue if r['evidence_state'] in ('source_unregistered','no_targeted_review')],
        'next_actions_ja': ['未登録の残りを直接資料で補う。','編集上位20テーマの全文と独立した比較研究を読む。',
            '主張・対象・結果ごとに支持と反証を整理する。','公開候補を選ぶ前に安全性・日本への適用・出典状態を確認する。']})
    index = []
    for cat in categories:
        for topic in documents[cat['id']]['topics']:
            index.append({'topic_id': topic['id'], 'title_ja': topic['title_ja'], 'category_id':cat['id'],
                'topic_file': cat['file'], 'evidence_file':'data/evidence/'+cat['id']+'.json',
                'ranked_sources_file':'data/rankings/sources_by_topic/'+cat['id']+'.json',
                'source_count':len(topic['source_ids']), 'editorial_score':editorial_by_id.get(topic['id'],{}).get('editorial_score')})
    save('data/index/topics.json', {'schema_version':'1.0','topics':index})
    limits = {'schema_version':'1.0','policy_version':VERSION,
        'normal_json_warning_bytes':1024*1024,'candidate_shard_target_records':100,
        'repo_data_warning_bytes':100*1024*1024,'units_note':'Internal operating thresholds; not GitHub hard limits.'}
    save('data/storage_policy.json', limits)
    files = [(str(p.relative_to(ROOT)),p.stat().st_size) for p in (ROOT/'data').rglob('*.json') if p.name!='storage_report.json']
    save('data/storage_report.json', {'schema_version':'1.0','excludes':'Git history, working caches, generated build/, and this report',
        'canonical_and_derived_data_bytes':sum(n for _,n in files),'data_json_file_count':len(files),
        'largest_files':[{'path':p,'bytes':n} for p,n in sorted(files,key=lambda x:-x[1])[:10]],
        'files_above_internal_1MiB':[p for p,n in files if n>1024*1024]})
    coverage = load('data/research/coverage.json')
    coverage.update(editorial_scored_topic_count=len(editorial),research_queue_count=len(queue),
        current_targeted_review_topic_count=sum(r['targeted_review_source_count']>0 for r in queue),
        current_selected_fulltext_topic_count=sum(r['selected_fulltext_source_count']>0 for r in queue))
    save('data/research/coverage.json',coverage)
    render_docs(categories, documents, editorial, queue, by_topic, sources, coverage)
    if (ROOT/'data/research/editorial_delivery_report.json').exists():
        from apply_editorial_delivery import render_delivery_docs
        render_delivery_docs()
    if (ROOT/'data/research/source_text_checks.json').exists():
        from apply_editorial_pass import render_docs as render_editorial_current
        render_editorial_current()
    return {'topic_count':len(topics),'source_count':len(sources),'edge_count':len(edges),
        'editorial_count':len(editorial),'queue_count':len(queue),'source_unregistered_count':coverage['search_pending_count']}


def render_docs(categories, documents, editorial, queue, by_topic, sources, coverage):
    lines=['# テーマの有力度と次の調査順', '',
        '編集上の有力度は50テーマの主観的な仮説です。市場調査や閲覧数ではありません。未評価の250テーマが面白くないという意味ではありません。', '',
        '## 編集上の有力度', '', '| 同点順位 | ID | テーマ | 編集点 | 判断理由 |','|---:|---|---|---:|---|']
    for row in editorial:
        lines.append(f"| {row['rank']} | {row['topic_id']} | {row['title_ja']} | {row['editorial_score']} | {row['reason_ja']} |")
    lines += ['', '## 次の調査順（上位30件）', '',
        'この順位は資料の不足を含む作業配分です。公開記事の優先順位や人気順位とは異なります。', '',
        '| 作業順 | ID | テーマ | 状態 | 次の作業 |','|---:|---|---|---|---|']
    for row in queue[:30]:
        lines.append(f"| {row['queue_position']} | {row['topic_id']} | {row['title_ja']} | {row['evidence_state']} | {row['next_action_ja']} |")
    text('docs/RANKINGS.md','\n'.join(lines))
    notes=['# 第3回：追加出典の確認メモ', '',
        '書誌のみと抄録を分離しています。点数は調査の優先順であり、真である確率ではありません。全文の指定箇所の確認はdata/source_assessments.jsonを参照してください。', '']
    for review in load('data/research/source_reviews.json')['reviews']:
        if review.get('delivery_id'):
            continue
        source=sources[review['source_id']]
        notes += [f"## {review['id']} / {review['source_id']} — {source['title']}", '',
            f"{source['authors_display']} / {source['year']} / {source['journal']}", '',
            f"[書誌・原論文]({source['url']}) / 確認範囲: `{review['review_scope']}` / 関連性: {review['topic_relevance']}/5", '',
            '**対応テーマ：** '+', '.join(review['topic_ids']), '',
            '**結果：** '+(review['key_findings_ja'] or '書誌のみ。結果は未確認。'), '',
            '**限界・注意：** '+review['limitations_ja'], '']
    text('docs/ROUND3_SOURCE_NOTES.md','\n'.join(notes))
    index=['# 全300テーマの索引', '', '正本のID・並び順を維持。新しい資料は書誌だけの場合もあります。', '']
    for category in categories:
        index += ['## '+category['name_ja'], '', '| ID | テーマ | 登録資料数 | 累計読解メモ数 |','|---|---|---:|---:|']
        for t in documents[category['id']]['topics']:
            index.append(f"| {t['id']} | {t['title_ja']} | {len(t['source_ids'])} | {len(t.get('source_review_ids',[]))} |")
        index.append('')
    text('docs/TOPICS_INDEX.md','\n'.join(index))
    c=coverage
    readme=['# Psychology Blog — 人間の科学・調査用データベース', '',
        '**28分野・300テーマ。記事本文・サイトの制作前の調査段階です。**', '',
        '## 第3回の更新（2026-09-11）', '',
        f"出典台帳は{c['source_count']}件。今回{c['round3_added_source_count']}件を追加し、出典未登録は131テーマから{c['search_pending_count']}テーマになりました。登録だけで科学的結論を確認したことにはなりません。", '',
        f"今回の124件の確認メモは抄録{c['round3_abstract_review_count']}件、書誌のみ{c['round3_bibliography_only_count']}件です。旧68件の読解メモを保持し、重要資料7件について本文の指定箇所も確認しました。正式なバイアス・確実性評価や独立した二重選別は未実施です。", '',
        f"今回の検索は510回。累計{c['search_request_count']}回、候補レコード{c['candidate_record_count']}件です。候補は未選別を含み、レコード数と独立した研究数は異なります。", '',
        '## 最初に開くファイル', '',
        '- [テーマの有力度・次の調査順](docs/RANKINGS.md)',
        '- [追加124件の書誌・結果・限界](docs/ROUND3_SOURCE_NOTES.md)',
        '- [全300テーマ一覧](docs/TOPICS_INDEX.md)',
        '- [データ設計](docs/DATABASE_ARCHITECTURE.md) / [採点方法](docs/RANKING_METHOD.md) / [次の作業](docs/NEXT_STEPS.md)', '',
        '## 使い方', '', '```bash',
        'python scripts/validate.py --export build',
        'python scripts/validate_research.py --export build',
        'python scripts/validate_round3.py --export build',
        'python scripts/query_database.py topic PSY-SLP-004 --limit 5',
        'python scripts/build_research_views.py', '```', '',
        'テーマ正本はdata/topics、出典正本はdata/sources.json、関連性と使える範囲はdata/evidence、資料評価はdata/source_assessments.json、ランキングはdata/rankingsです。候補台帳はdata/literature/catalog.jsonから必要な分割ファイルだけ読みます。', '',
        '順位は正本の配列を並べ替えず別ファイルに生成します。出典の優先度はテーマとの対応・方法上の情報・確認範囲を区別した調査用指標で、科学的に正しい確率やGRADE評価ではありません。編集ランキングは50テーマの仮説的な評価であり、実際の人気を測定していません。', '',
        '## 未完了の確認', '',
        f"出典未登録{c['search_pending_count']}テーマを引き続き直接資料で補います。登録済みでも書誌・背景だけの場合があり、全文・独立追試・反証・訂正・日本への適用を確認してから記事化します。全テーマのpublication_readyはfalseです。", '',
        '生活例は説明用の想定場面と研究で実際に調べた場面を区別します。薬・治療・依存・トラウマ等は専門家の安全性確認を必要とします。全論文の原文・図表は公開データに転載していません。', '',
        '旧データを巻き戻す一回限りのワークフローは廃止しています。通常は正本を編集し、読取専用の検証と派生ビュー生成を行います。定期実行は設定していません。']
    text('README.md','\n'.join(readme))


if __name__ == '__main__':
    print(json.dumps(build(),ensure_ascii=False,indent=2))
