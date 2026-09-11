#!/usr/bin/env python3
"""Materialize the 2026-09-11 research snapshot. No external calls or credentials.

Canonical data is independent of temporary reading artifacts once committed.
This importer deliberately refuses to overwrite an already imported snapshot.
"""
from __future__ import annotations
import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-11'
SNAPSHOT = '2026-09-11-expanded-300'
NOTICE_MAP = {'38355154': '38806193', '30646029': '30646107', '28447835': '40111841'}


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def save(path: str, value: dict) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def text(path: str, value: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value.rstrip() + '\n', encoding='utf-8')


def normalize(row: dict) -> dict:
    key = row['source'] + ':' + str(row['id'])
    return {'id': key, 'title': row.get('title'), 'authors': row.get('authorString'),
            'year': row.get('pubYear'), 'first_publication_date': row.get('firstPublicationDate'),
            'journal': row.get('journalInfo', {}).get('journal', {}).get('title'),
            'doi': row.get('doi'), 'pmid': row.get('pmid'), 'pmcid': row.get('pmcid'),
            'url': 'https://europepmc.org/article/' + key.replace(':', '/'),
            'publication_types': row.get('pubTypeList', {}).get('pubType', []),
            'abstract_available': bool(row.get('abstractText')),
            'is_open_access': row.get('isOpenAccess'),
            'cited_by_count_at_collection': row.get('citedByCount'),
            'candidate_status': 'machine_retrieved_not_screened',
            'correction_retraction_check': 'not_completed'}


def main() -> None:
    manifest = load('data/manifest.json')
    if manifest.get('research_snapshot') == SNAPSHOT:
        raise SystemExit('Snapshot already imported. Edit canonical JSON rather than overwriting it.')
    categories = load('data/categories.json')['categories']
    sources_doc = load('data/sources.json')
    sources = sources_doc['sources']
    documents = {c['file']: load(c['file']) for c in categories}
    original = {t['id']: t for d in documents.values() for t in d['topics']}
    assert len(original) == 200 and len(categories) == 20 and len(sources) == 35, 'Unexpected base; reconcile first.'
    original_refs = {tid: set(t['source_ids']) for tid, t in original.items()}

    bundle = load('_inputs/literature/reader_bundle.json')
    supplement = load('_inputs/supplement/supplement.json')
    raw = dict(bundle['papers'])
    searches = [dict(s, collection_run_id=34545106140) for s in bundle['searches']]
    for index, result in enumerate(supplement, 1):
        ids = []
        for row in result['records']:
            key = row['source'] + ':' + str(row['id'])
            raw[key] = row
            ids.append(key)
        searches.append({'task_id': f'SUP-{index:03d}', 'topic_id': None,
                         'kind': 'key_paper_supplement', 'query': result['query'],
                         'api_url': result.get('url'), 'status': result['status'],
                         'searched_at_utc': None, 'collection_date': DATE,
                         'collection_run_id': 34545908849, 'candidate_ids': ids,
                         'error': result.get('error')})
    provenance = {}
    for item in searches:
        for pid in item['candidate_ids']:
            provenance.setdefault(pid, []).append(item['task_id'])
    api_urls = {s['task_id']: s.get('api_url') for s in searches}

    new_ids = []
    new_categories = []
    current = None
    for line in (ROOT / 'research/new_topics.psv').read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        if line.startswith('@'):
            cid, name, prefix = line[1:].split('|')
            path = f'data/topics/{21 + len(new_categories):02d}_{cid}.json'
            current = {'id': cid, 'name_ja': name, 'id_prefix': prefix, 'file': path,
                       'topic_count': 0, 'scope_ja': name + 'に関する独立した生活上の問いと、既存テーマの応用。'}
            new_categories.append(current)
            documents[path] = {'schema_version': '1.0', 'category_id': cid, 'topics': []}
            continue
        assert current is not None
        title, concepts, scenario, related, caution = line.split('|')
        current['topic_count'] += 1
        tid = f"PSY-{current['id_prefix']}-{current['topic_count']:03d}"
        new_ids.append(tid)
        documents[current['file']]['topics'].append({
            'id': tid, 'title_ja': title, 'concepts_en': concepts.split(';'),
            'angle_ja': scenario, 'search_query': concepts.replace(';', ' ') + ' systematic review human study',
            'priority': 1 if current['topic_count'] <= 8 else 2, 'source_ids': [],
            'caution_ja': caution, 'related_topic_ids': ['PSY-' + x for x in related.split(',')],
            'daily_life_example': {'type': 'illustrative_scenario', 'description_ja': scenario,
                                  'observed_in_a_study': False}})
    assert len(new_ids) == 100 and len(new_categories) == 8
    categories.extend(new_categories)
    topics = {t['id']: t for d in documents.values() for t in d['topics']}
    assert len(topics) == 300 and len({t['title_ja'] for t in topics.values()}) == 300

    next_number = max(int(s['id'][3:]) for s in sources) + 1
    by_doi = {s['doi'].lower(): s['id'] for s in sources if s.get('doi')}
    added_sources = []
    resolved = {}

    def add_source(pmid: str, notice: bool = False) -> str:
        nonlocal next_number
        if pmid in resolved:
            return resolved[pmid]
        pid = 'MED:' + pmid
        row = raw[pid]
        doi = row.get('doi')
        if doi and doi.lower() in by_doi:
            sid = by_doi[doi.lower()]
        else:
            sid = f'SRC{next_number:03d}'
            next_number += 1
            has_abstract = bool(row.get('abstractText'))
            assert has_abstract or notice, f'No reviewed abstract: {pmid}'
            year = row.get('pubYear')
            source = {'id': sid, 'title': row['title'],
                      'authors_display': row.get('authorString') or '書誌に著者記載なし',
                      'year': int(year) if year else None,
                      'journal': row.get('journalInfo', {}).get('journal', {}).get('title'),
                      'source_type': 'journal_article', 'doi': doi,
                      'pmid': pmid, 'url': f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/',
                      'verified_via_url': api_urls[provenance[pid][0]],
                      'verification_scope': 'abstract_reviewed' if has_abstract else 'bibliography_verified',
                      'notes_ja': 'Europe PMC収載の書誌・抄録をAI支援で確認。全文の批判的評価、独立した二重選別、解析の再現は未実施。' if not notice else '関連する訂正告知。独立した効果検証研究の件数には含めない。',
                      'accessed_on': DATE, 'record_role': 'correction_notice' if notice else 'reviewed_research',
                      'first_publication_date': row.get('firstPublicationDate'),
                      'provenance_query_ids': provenance[pid],
                      'indexed_related_records': row.get('commentCorrectionList', {}).get('commentCorrection', []),
                      'correction_retraction_check': 'indexed_links_checked_not_exhaustive'}
            if notice:
                source['notes_ja'] += (' 抄録で訂正説明を確認。著者らは結論維持と記載するが、元データの独立再監査はしていない。' if pmid == '40111841' else ' 書誌のみ確認。訂正の内容と結論への影響は未精査。')
            sources.append(source)
            added_sources.append(sid)
            if doi:
                by_doi[doi.lower()] = sid
        resolved[pmid] = sid
        return sid

    briefs = []
    for path in ['research/reviews_01.psv', 'research/reviews_02.psv']:
        for line in (ROOT / path).read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            pmid, refs, design, context, findings, limitations, example = line.split('|')
            sid = add_source(pmid)
            source_ids = [sid]
            if pmid in NOTICE_MAP:
                source_ids.append(add_source(NOTICE_MAP[pmid], notice=True))
            tids = ['PSY-' + x for x in refs.split(',')]
            assert set(tids) <= set(topics), f'Unknown topics: {set(tids) - set(topics)}'
            bid = 'RB-' + pmid
            briefs.append({'id': bid, 'primary_source_id': sid, 'source_ids': source_ids,
                           'topic_ids': tids, 'study_design': design,
                           'study_context': {'type': 'study_context', 'description_ja': context, 'source_id': sid},
                           'key_findings_ja': findings, 'limitations_ja': limitations,
                           'daily_life_example': {'type': 'illustrative_scenario', 'description_ja': example, 'observed_in_a_study': False},
                           'review_scope': 'abstract', 'review_method': 'AI_assisted_single_review',
                           'formal_evidence_certainty': 'not_assessed', 'publication_ready': False,
                           'reviewed_on': DATE, 'relation_role': 'relevant_research_not_whole_theme_verification'})
            for tid in tids:
                topic = topics[tid]
                for item in source_ids:
                    if item not in topic['source_ids']:
                        topic['source_ids'].append(item)
                topic.setdefault('research_brief_ids', []).append(bid)
    assert len(briefs) == 68 and len({b['id'] for b in briefs}) == 68

    relations = []
    for tid in new_ids:
        for related in topics[tid]['related_topic_ids']:
            assert related in topics, related
            relations.append({'from_topic_id': tid, 'to_topic_id': related, 'relation': 'related_question'})
    for child, parents in {'PSY-MON-008': ['PSY-DEC-010', 'PSY-DEC-004'],
                           'PSY-HPS-012': ['PSY-DEC-005', 'PSY-RES-003'],
                           'PSY-CRE-005': ['PSY-ATT-006']}.items():
        topics[child]['parent_topic_ids'] = parents
        for parent in parents:
            relations.append({'from_topic_id': child, 'to_topic_id': parent, 'relation': 'application_of'})

    candidates = []
    for pid, row in raw.items():
        item = normalize(row)
        pmid = row.get('pmid')
        if pmid in resolved:
            item.update(candidate_status='selected_correction_notice' if pmid in NOTICE_MAP.values() else 'selected_abstract_reviewed',
                        source_id=resolved[pmid], correction_retraction_check='indexed_links_checked_not_exhaustive')
        candidates.append(item)
    reviewed_ids = {tid for b in briefs for tid in b['topic_ids']}
    old_reviewed = reviewed_ids & set(original)
    newly_referenced = {tid for tid in original if not original_refs[tid] and topics[tid]['source_ids']}
    linked = sum(bool(t['source_ids']) for t in topics.values())
    category_coverage = []
    for cat in categories:
        rows = documents[cat['file']]['topics']
        category_coverage.append({'category_id': cat['id'], 'name_ja': cat['name_ja'],
                                 'topic_count': len(rows),
                                 'reference_linked_count': sum(bool(t['source_ids']) for t in rows),
                                 'brief_linked_count': sum(t['id'] in reviewed_ids for t in rows)})
    coverage = {'schema_version': '1.0', 'as_of': DATE,
                'category_count': len(categories), 'topic_count': len(topics), 'new_topic_count': len(new_ids),
                'source_count': len(sources), 'legacy_source_count': 35,
                'added_source_count': len(added_sources), 'reviewed_research_count': len(briefs),
                'correction_notice_count': len(NOTICE_MAP), 'brief_linked_topic_count': len(reviewed_ids),
                'original_topics_with_new_briefs': len(old_reviewed),
                'new_topics_with_briefs': len(reviewed_ids - set(original)),
                'previously_unreferenced_original_topics_now_linked': len(newly_referenced),
                'reference_linked_count': linked, 'search_pending_count': len(topics) - linked,
                'illustrative_scenario_count': len(new_ids) + len(briefs), 'study_context_count': len(briefs),
                'search_request_count': len(searches),
                'successful_searches': sum(s['status'] == 'completed' for s in searches),
                'failed_searches': sum(s['status'] != 'completed' for s in searches),
                'zero_hit_searches': sum(s['status'] == 'completed' and not s['candidate_ids'] for s in searches),
                'candidate_record_count': len(candidates),
                'original_topic_search_count': sum(s['kind'] == 'topic_discovery' for s in searches),
                'categories': category_coverage,
                'limits_ja': ['重要論文68件は抄録中心の予備読解で、全テーマの正式なエビデンス評価ではない。',
                              '候補件数はデータベースのレコード数。プレプリントと刊行版など同一研究の別版を含み得る。',
                              '既存200テーマは概念検索済み。新規100テーマすべての個別検索は未実施。',
                              'Europe PMC中心の検索には収載分野の偏りがある。各検索の上位5件であり網羅的検索ではない。',
                              '検索の成功は関連文献が存在することや十分な根拠を得たことを意味しない。',
                              '索引上の訂正・関連論文は確認したが、全文・全追試・撤回情報の網羅的精査は未実施。',
                              '生活例は説明用の想定場面であり、実在人物の事例やその方法を直接検証した結果ではない。']}
    manifest.update(research_snapshot=SNAPSHOT, updated_on=DATE, phase='topic_discovery_and_preliminary_evidence_mapping',
                    category_count=len(categories), topic_count=len(topics), source_count=len(sources),
                    reference_linked_count=linked, search_pending_count=len(topics)-linked,
                    research_brief_count=len(briefs), brief_linked_topic_count=len(reviewed_ids),
                    candidate_record_count=len(candidates), search_request_count=len(searches),
                    coverage_notes_ja=coverage['limits_ja'])
    manifest['files'].update(research_briefs='data/research/briefs.json', coverage='data/research/coverage.json',
                             candidate_records='data/literature/candidates.json', search_log='data/literature/search_log.json',
                             topic_relations='data/topic_relations.json')
    sources_doc.update(updated_on=DATE, notes_ja='旧35資料の確認状態は保持。追加資料は抄録中心の予備読解68件と訂正告知3件。掲載・確認の状態は各レコードを参照。全文査読相当の評価ではない。')
    for path, document in documents.items():
        save(path, document)
    save('data/categories.json', {'schema_version': '1.0', 'categories': categories})
    save('data/sources.json', sources_doc)
    save('data/manifest.json', manifest)
    save('data/research/briefs.json', {'schema_version': '1.0', 'reviewed_on': DATE, 'briefs': briefs})
    save('data/research/coverage.json', coverage)
    save('data/topic_relations.json', {'schema_version': '1.0', 'relations': relations})
    save('data/literature/candidates.json', {'schema_version': '1.0', 'collection_date': DATE,
         'warning_ja': '未選別候補を含むレコード台帳。候補数は独立研究数や実証済み効果数ではない。', 'papers': candidates})
    save('data/literature/search_log.json', {'schema_version': '1.0', 'cutoff': DATE,
         'result_limit_per_query': 5, 'searches': searches})
    save('data/research/next_queue.json', {'schema_version': '1.0', 'not_an_automatic_schedule': True,
         'topic_ids_without_briefs': [tid for tid in topics if tid not in reviewed_ids],
         'priority_tasks_ja': ['既存の意思決定・発達・デジタル生活など読解メモの少ない分野を補う。',
                              '新規100テーマのうち未検索・未読解のテーマを個別に調査する。',
                              '重要論文の全文・独立追試・近年レビュー・訂正内容を照合する。',
                              '日本の対象者・制度・言語尺度への適用と医療上の安全性を確認する。']})
    generate_docs(categories, documents, sources, briefs, coverage)
    print(json.dumps({k:v for k,v in coverage.items() if k not in ('categories','limits_ja')}, ensure_ascii=False, indent=2))


def generate_docs(categories: list, documents: dict, sources: list, briefs: list, c: dict) -> None:
    source_map = {s['id']: s for s in sources}
    readme = ['# Psychology Blog — 人間の科学・テーマと研究データベース', '',
              f"**更新：{DATE}。28分野・300テーマ。追加100テーマ、重要論文・指針の読解メモ68件。**", '',
              '一般の読者が自分の生活と結びつけて読める、日本語ブログの調査用データです。完成記事や医療上の推奨ではありません。', '',
              '## 今回の成果と確認範囲', '',
              f"出典台帳は{c['source_count']}件（旧35資料＋今回の研究・指針68件＋訂正告知3件）。読解メモは{c['brief_linked_topic_count']}テーマに対応し、うち既存テーマ{c['original_topics_with_new_briefs']}件、新規テーマ{c['new_topics_with_briefs']}件です。", '',
              f"関連資料付きは{c['reference_linked_count']}テーマ、個別の出典未登録は{c['search_pending_count']}テーマです。資料付きでも背景解説だけの場合があります。全300テーマの正式な確実性評価は未実施で、公開可能状態にはしていません。", '',
              f"検索は{c['search_request_count']}回実行し、候補レコード{c['candidate_record_count']}件を保存しました。候補は未選別を含み、同一研究の別版もあり得ます。重要資料の読解は抄録中心で、全文の品質評価・解析再現とは異なります。", '',
              '## 読みやすい入口', '',
              '- [300テーマ一覧](docs/TOPICS_INDEX.md)',
              '- [68件の重要論文・指針と生活へのつながり](docs/RESEARCH_NOTES.md)',
              '- [分類・基本テーマ・派生記事の設計](docs/THEME_ARCHITECTURE.md)',
              '- [調査件数・分野別の進捗](data/research/coverage.json)', '',
              '## 分野別JSON', '', '| 分野 | テーマ数 | 読解メモ付き |', '|---|---:|---:|']
    for cat, progress in zip(categories, c['categories']):
        readme.append(f"| [{cat['name_ja']}]({cat['file']}) | {cat['topic_count']} | {progress['brief_linked_count']} |")
    readme += ['', '## データ構成', '',
               '`data/topics/` がテーマの正本です。出典は `data/sources.json`、主張と限界の予備整理は `data/research/briefs.json`、関連・派生関係は `data/topic_relations.json` に分離しています。候補と検索履歴は `data/literature/` にあります。', '',
               '研究で実際に調べた対象・条件は `study_context`、説明のための生活場面は `daily_life_example` です。後者は実在人物の体験談や、直接検証済みの介入ではありません。', '',
               '## 検証と統合出力', '', '```bash', 'python scripts/validate.py --export build',
               'python scripts/validate_research.py --export build', '```', '',
               'Python 3.9以降の標準ライブラリを使用。テーマ統合JSON、論文読解メモ、候補台帳、検索ログ、構造検証レポートを出力します。構造検証は科学的正しさの保証ではありません。', '',
               '`research/` のPSVは今回の編集用原稿で、通常の更新対象は正本JSONです。一度限りの取り込みは一時的な読解用Artifactを入力にしましたが、保存後の正本・検証・統合出力にはそのArtifactは不要です。定期実行は設定していません。', '',
               '## 未確認事項', ''] + c['limits_ja'] + ['',
               '出典の優先度と証拠の強さは別管理です。相関と因果、個人と集団、人と動物、短期と長期を分けます。遺伝率を個人の遺伝割合と解釈しません。治療・薬・依存症・睡眠制限などの記事は専門家の安全確認を必要とします。', '',
               '[データ辞書](docs/DATA_DICTIONARY.md) / [収集方針](docs/METHODOLOGY.md)']
    text('README.md', '\n'.join(readme))
    notes = ['# 重要論文・指針の予備読解メモ', '',
             '68件。書誌と抄録をAI支援で確認した一次整理です。全文の批判的評価、独立した二重選別、論文の解析再現は未実施です。生活例はすべて説明用の想定場面です。', '']
    for b in briefs:
        s = source_map[b['primary_source_id']]
        notes += [f"## {b['id']} — {s['title']}", '',
                  f"{s['authors_display']} / {s['year']} / {s['journal']}", '',
                  f"[原論文の書誌・抄録]({s['url']}) — DOI: `{s.get('doi') or '未確認'}`", '',
                  '**対応テーマ：** ' + ', '.join(b['topic_ids']), '',
                  '**実際に研究した対象・条件：** ' + b['study_context']['description_ja'], '',
                  '**主な結果：** ' + b['key_findings_ja'], '',
                  '**限界・注意：** ' + b['limitations_ja'], '',
                  '**生活へのつなげ方（説明用の例・実証済み事例ではない）：** ' + b['daily_life_example']['description_ja'], '']
        for sid in b['source_ids'][1:]:
            notice = source_map[sid]
            notes += [f"**関連する訂正：** [{notice['title']}]({notice['url']}) — {notice['notes_ja']}", '']
    text('docs/RESEARCH_NOTES.md', '\n'.join(notes))
    index = ['# 全300テーマ', '', '題名は記事の問いであり、結論ではありません。並び順と安定IDを維持しています。', '']
    for cat in categories:
        index += ['## ' + cat['name_ja'], '', '| ID | テーマ | 読解メモ |', '|---|---|---|']
        for t in documents[cat['file']]['topics']:
            index.append(f"| {t['id']} | {t['title_ja']} | {', '.join(t.get('research_brief_ids', [])) or '未作成'} |")
        index.append('')
    text('docs/TOPICS_INDEX.md', '\n'.join(index))


if __name__ == '__main__':
    main()
