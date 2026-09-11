#!/usr/bin/env python3
"""Import this reviewed snapshot once, offline. Temporary papers never enter data/.

Inputs: _round3/reader_bundle.json and _resolved/resolved.json from completed
Actions runs. For normal subsequent updates edit the canonical JSON, not this
historical importer. Fail rather than silently reapply over later work.
"""
from __future__ import annotations
import copy
import hashlib
import html
import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-11'
ROUND = 'round3-ranked-evidence-v1'
PICKS = {1:[0],2:[0,1,2],3:[0,1],4:[0,1],5:[0,1],6:[0],8:[0],9:[0,1,2],10:[0],11:[1],13:[0],14:[1],15:[0],16:[0],18:[0,1],19:[1],20:[0],21:[0],23:[2],24:[1],26:[0],27:[0],28:[0],29:[0],32:[0],33:[0],34:[0],35:[0],36:[2],37:[0],38:[1],39:[2],40:[2],41:[0],42:[0,2],43:[1],44:[0,2],45:[0,1],46:[0],47:[1],48:[0],49:[0],50:[2],51:[0],52:[0],53:[0],54:[1],55:[0],56:[0],57:[0],58:[0],59:[0],60:[0],61:[0],64:[0],65:[0],67:[0,2],68:[0],70:[0],71:[0],72:[0],73:[0],74:[0],75:[1],76:[0],77:[2],78:[1],79:[0],80:[0],81:[0],82:[0],83:[0,1],84:[0],85:[0],86:[0],87:[0],88:[1],89:[0],91:[0],93:[0],94:[0],95:[1],96:[0],97:[1],98:[0],100:[0,1],101:[0],102:[0]}
SUPP = {104:0,108:1,110:2,112:0,114:0,115:0,116:2,117:2,119:4,120:0,121:4,122:4,123:1,124:0,125:0,130:0,132:1,134:0,136:0,138:0,139:4,145:0}


def load(path: str) -> Any:
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def save(path: str, obj: Any) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def clean(value: str) -> str:
    # Do not treat statistical inequalities such as p < .05 as XML tags.
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'</?[A-Za-z][^>]*>', ' ', value or ''))).strip()


def candidate_id(row: dict, provider: str) -> str:
    if provider == 'crossref':
        return 'DOI:' + row['DOI'].lower()
    return row.get('source', 'UNKNOWN') + ':' + str(row['id'])


def normalize(row: dict, provider: str) -> dict:
    if provider == 'crossref':
        parts = row.get('issued', {}).get('date-parts', [[]])[0]
        return {'id': candidate_id(row, provider), 'title': clean((row.get('title') or [''])[0]),
                'doi': row['DOI'].lower(), 'year': parts[0] if parts else None,
                'authors': '; '.join(' '.join(filter(None, [a.get('given'), a.get('family')])) or a.get('name', '') for a in row.get('author', [])),
                'journal': '; '.join(row.get('container-title', [])) or None,
                'url': 'https://doi.org/' + row['DOI'], 'publication_types': [row.get('type')],
                'abstract_available': bool(row.get('abstract')), 'provider': 'crossref',
                'candidate_status': 'machine_retrieved_not_screened'}
    return {'id': candidate_id(row, provider), 'title': clean(row.get('title', '')),
            'doi': row.get('doi'), 'year': row.get('pubYear'), 'authors': row.get('authorString'),
            'journal': row.get('journalInfo', {}).get('journal', {}).get('title'),
            'pmid': row.get('pmid'), 'pmcid': row.get('pmcid'),
            'url': 'https://europepmc.org/article/' + candidate_id(row, provider).replace(':', '/'),
            'publication_types': row.get('pubTypeList', {}).get('pubType', []),
            'abstract_available': bool(row.get('abstractText')), 'provider': 'europepmc',
            'candidate_status': 'machine_retrieved_not_screened'}


def selected_records(bundle: dict, resolved: list) -> dict:
    selections = {}
    for query in bundle['searches']:
        if query['provider'] != 'crossref':
            continue
        number = int(query['id'].split('-')[-1])
        for index in PICKS.get(number, []):
            cr = query['records'][index]
            doi = cr['DOI'].lower()
            matches = [(q, r) for q in resolved for r in q['records'] if r.get('doi', '').lower() == doi and r.get('pmid')]
            q, ep = matches[0] if matches else (None, None)
            key = f'C{len(selections):03d}'
            selections[key] = {'doi': doi, 'crossref': cr, 'epmc': ep,
                'query_ids': [query['id']] + ([f'R3-X-{resolved.index(q):03d}'] if q else []),
                'verified_via_url': q['api_url'] if q else query['api_url'],
                'read_text': clean(ep.get('abstractText', '') if ep else cr.get('abstract', ''))}
    assert len(selections) == 102
    for index, rank in SUPP.items():
        q = resolved[index]
        ep = q['records'][rank]
        selections[f'S{index:03d}'] = {'doi': ep.get('doi'), 'crossref': None, 'epmc': ep,
            'query_ids': [f'R3-X-{index:03d}'], 'verified_via_url': q['api_url'],
            'read_text': clean(ep.get('abstractText', ''))}
    assert len(selections) == 124
    return selections


def create_source(sid: str, selection: dict, design: str) -> dict:
    ep, cr = selection['epmc'], selection['crossref']
    normalized = normalize(ep, 'europepmc') if ep else normalize(cr, 'crossref')
    year = normalized.get('year')
    refs = (ep or {}).get('commentCorrectionList', {}).get('commentCorrection', [])
    return {'id': sid, 'title': normalized['title'],
            'authors_display': normalized.get('authors') or '書誌に著者記載なし',
            'year': int(year) if year else None, 'journal': normalized.get('journal'),
            'source_type': 'book_chapter' if (cr or {}).get('type') == 'book-chapter' else 'journal_article',
            'doi': selection['doi'], 'pmid': (ep or {}).get('pmid'),
            'url': normalized['url'], 'verified_via_url': selection['verified_via_url'],
            'verification_scope': 'abstract_reviewed' if selection['read_text'] else 'bibliography_verified',
            'notes_ja': 'テーマとの関連性を予備選別。確認範囲・結論・限界はsource_reviewsとevidenceの対応表を参照。正式な確実性評価ではない。',
            'accessed_on': DATE, 'record_role': 'correction_notice' if design == 'correction_notice' else 'research_entry',
            'provenance_query_ids': selection['query_ids'], 'indexed_related_records': refs,
            'correction_retraction_check': 'indexed_links_checked_not_exhaustive' if ep else 'not_completed'}


def candidate_searches(bundle: dict, resolved: list, doi_to_source: dict) -> tuple[list, list]:
    legacy = load('data/literature/candidates.json')['papers']
    legacy_ids = {p['id'] for p in legacy}
    new_records, logs = {}, []
    for query in bundle['searches']:
        provider = query['provider']
        ids = []
        for row in query['records']:
            item = normalize(row, provider)
            ids.append(item['id'])
            if item['id'] not in legacy_ids:
                new_records.setdefault(item['id'], item)
        logs.append({'task_id': query['id'], 'topic_id': query['topic_id'], 'provider': provider,
            'query': query['query'], 'api_url': query['api_url'], 'status': query['status'],
            'searched_at_utc': query['searched_at_utc'], 'collection_run_id': 34548795256,
            'candidate_ids': list(dict.fromkeys(ids)), 'error': query.get('error')})
    for index, query in enumerate(resolved):
        ids = []
        for row in query['records']:
            item = normalize(row, 'europepmc')
            ids.append(item['id'])
            if item['id'] not in legacy_ids:
                new_records.setdefault(item['id'], item)
        logs.append({'task_id': f'R3-X-{index:03d}', 'topic_id': query['topic_id'], 'provider': 'europepmc',
            'query': query['query'], 'api_url': query['api_url'], 'status': query['status'],
            'searched_at_utc': None, 'collection_date': DATE, 'collection_run_id': 34549481613,
            'candidate_ids': list(dict.fromkeys(ids)), 'error': query.get('error')})
    for item in new_records.values():
        sid = doi_to_source.get((item.get('doi') or '').lower())
        if sid:
            item['source_id'] = sid
            item['candidate_status'] = 'bibliographic_record_has_registered_source'
    paths = ['data/literature/candidates.json']
    rows = list(new_records.values())
    for start in range(0, len(rows), 100):
        path = f'data/literature/round3/candidates-{start // 100 + 1:03d}.json'
        save(path, {'schema_version': '1.0', 'collection_date': DATE, 'papers': rows[start:start + 100]})
        paths.append(path)
    log_paths = ['data/literature/search_log.json']
    for start in range(0, len(logs), 100):
        path = f'data/literature/round3/searches-{start // 100 + 1:03d}.json'
        save(path, {'schema_version': '1.0', 'cutoff': DATE, 'searches': logs[start:start + 100]})
        log_paths.append(path)
    save('data/literature/catalog.json', {'schema_version': '1.0', 'candidate_files': paths,
        'search_files': log_paths, 'identity_rule': 'provider record ID; not deduplicated independent studies',
        'notes_ja': '旧ファイルは保持。新規台帳は100レコードずつ分割。候補・書誌の登録は効果確認を意味しない。'})
    return legacy + rows, load('data/literature/search_log.json')['searches'] + logs


def main() -> None:
    manifest = load('data/manifest.json')
    if manifest.get('research_round') == ROUND:
        raise SystemExit('Already imported. Refusing to overwrite canonical updates.')
    assert manifest['topic_count'] == 300 and manifest['source_count'] == 106
    categories = load('data/categories.json')['categories']
    documents = {c['file']: load(c['file']) for c in categories}
    topics = {t['id']: t for d in documents.values() for t in d['topics']}
    original_topics = copy.deepcopy(topics)
    missing_before = {tid for tid, t in topics.items() if not t['source_ids']}
    source_doc = load('data/sources.json')
    sources = source_doc['sources']
    original_sources = copy.deepcopy(sources)
    save('data/research/history/round2_coverage.json', load('data/research/coverage.json'))
    selections = selected_records(load('_round3/reader_bundle.json'), load('_resolved/resolved.json'))
    doi_to_source = {(s.get('doi') or '').lower(): s['id'] for s in sources if s.get('doi')}
    bindings, reviews, assessments = {}, [], {}
    for line in (ROOT / 'research/round3_source_reviews.psv').read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        key, tids, relevance, design, methods, direction, finding, limits = line.split('|')
        selected = selections[key]
        if finding != '-':
            assert selected['read_text'], f'No abstract for claimed findings: {key}'
        tids = ['PSY-' + tid for tid in tids.split(',')]
        assert set(tids) <= topics.keys()
        doi = (selected['doi'] or '').lower()
        sid = doi_to_source.get(doi)
        if not sid:
            sid = f'SRC{max(int(s["id"][3:]) for s in sources) + 1:03d}'
            sources.append(create_source(sid, selected, design))
            if doi:
                doi_to_source[doi] = sid
        bindings[key] = sid
        rid = 'R3-' + key
        reviewed = bool(selected['read_text'])
        review = {'id': rid, 'source_id': sid, 'topic_ids': tids, 'design': design,
            'review_scope': 'abstract' if reviewed else 'bibliography',
            'review_method': 'AI_assisted_single_review', 'reviewed_on': DATE,
            'key_findings_ja': None if finding == '-' else finding, 'limitations_ja': limits,
            'conclusion_direction': direction, 'topic_relevance': int(relevance),
            'relevance_scope': 'abstract_screened' if reviewed else 'title_only_provisional',
            'method_signals': int(methods), 'formal_evidence_certainty': 'not_assessed',
            'publication_ready': False}
        reviews.append(review)
        for tid in tids:
            if sid not in topics[tid]['source_ids']:
                topics[tid]['source_ids'].append(sid)
            topics[tid].setdefault('source_review_ids', []).append(rid)
        assessments[sid] = {'source_id': sid, 'review_scope': review['review_scope'],
            'method_signals': int(methods), 'formal_risk_of_bias': 'not_assessed',
            'formal_evidence_certainty': 'not_assessed', 'reliability_ja': '書誌のみ・信頼性未評価' if not reviewed else '抄録による予備点検・正式評価未実施',
            'provenance_review_ids': [rid], 'limitations_ja': [limits],
            'integrity_status': 'indexed_links_checked_not_exhaustive' if selected['epmc'] else 'not_completed',
            'integrity_notices': (selected['epmc'] or {}).get('commentCorrectionList', {}).get('commentCorrection', [])}
    assert len(reviews) == len(selections) == 124
    for source in original_sources:
        assessments.setdefault(source['id'], {'source_id': source['id'], 'review_scope': 'legacy_not_reassessed',
            'method_signals': None, 'formal_risk_of_bias': 'not_assessed', 'formal_evidence_certainty': 'not_assessed',
            'reliability_ja': '既存資料・今回は未再評価', 'integrity_status': 'not_completed',
            'integrity_notices': source.get('indexed_related_records', [])})
    checks = load('research/round3_fulltext_checks.json')['checks']
    for check in checks:
        sid = bindings.get(check['key'], check['key'])
        assert sid in assessments
        item = assessments[sid]
        item.update(review_scope='selected_fulltext_sections', method_signals=check['method_signals'],
            reliability_ja='本文の指定箇所を確認・正式なバイアス評価と確実性評価は未実施',
            selected_fulltext_check={k: v for k, v in check.items() if k not in ('key', 'method_signals')})
        item['limitations_ja'] = check['limitations_ja']
    # Relevant existing anchor papers without a new full-text pass remain abstract-level.
    anchor_fits = {'SRC036': {'PSY-GEN-001': 5, 'PSY-GEN-002': 4},
                  'SRC038': {'PSY-SLP-004': 5}, 'SRC039': {'PSY-HAB-001': 5, 'PSY-HAB-002': 4, 'PSY-HAB-003': 4, 'PSY-HAB-004': 4},
                  'SRC040': {'PSY-SLP-008': 5}, 'SRC041': {'PSY-SLP-002': 5},
                  'SRC043': {'PSY-ADD-006': 5}, 'SRC050': {'PSY-LEA-001': 5},
                  'SRC054': {'PSY-ATT-004': 5, 'PSY-ATT-007': 4}, 'SRC099': {'PSY-WRK-001': 5}}
    for sid in anchor_fits:
        if assessments[sid]['review_scope'] == 'legacy_not_reassessed':
            assessments[sid].update(review_scope='legacy_abstract_review', method_signals=3,
                reliability_ja='前回の抄録読解から調査順を付与・今回本文未確認')
    edges = []
    review_by_pair = {(tid, r['source_id']): r for r in reviews for tid in r['topic_ids']}
    old_briefs = load('data/research/briefs.json')['briefs']
    for tid, topic in topics.items():
        for sid in topic['source_ids']:
            r = review_by_pair.get((tid, sid))
            fit = r['topic_relevance'] if r else anchor_fits.get(sid, {}).get(tid)
            assessment = assessments[sid]
            existing = [b['id'] for b in old_briefs if tid in b['topic_ids'] and sid in b['source_ids']]
            role = ('correction_notice' if r and r['design'] == 'correction_notice' else
                    'unassessed_legacy_link' if fit is None else
                    'direct_or_targeted_evidence' if fit >= 4 else 'context_only')
            edges.append({'id': f'EV-{tid}-{sid}', 'topic_id': tid, 'source_id': sid,
                'relation_role': role, 'relevance_1_to_5': fit,
                'relevance_scope': r['relevance_scope'] if r else ('anchor_question_checked' if fit else 'not_reassessed'),
                'source_review_id': r['id'] if r else None, 'legacy_brief_ids': existing,
                'finding_scope_ja': r['key_findings_ja'] if r else None,
                'conclusion_direction': r['conclusion_direction'] if r else 'not_classified',
                'limits_ja': r['limitations_ja'] if r else '既存読解メモを参照。テーマ全体への主張単位の適用は未評価。',
                'formal_evidence_certainty': 'not_assessed'})
    evidence_paths = []
    for cat in categories:
        ids = {t['id'] for t in documents[cat['file']]['topics']}
        path = 'data/evidence/' + cat['id'] + '.json'
        save(path, {'schema_version': '1.0', 'category_id': cat['id'], 'edges': [e for e in edges if e['topic_id'] in ids]})
        evidence_paths.append(path)
    save('data/evidence/catalog.json', {'schema_version': '1.0', 'files': evidence_paths})
    save('data/source_assessments.json', {'schema_version': '1.0', 'assessed_on': DATE,
        'not_a_probability_or_formal_grade': True, 'assessments': list(assessments.values())})
    save('data/research/source_reviews.json', {'schema_version': '1.0', 'round': ROUND, 'reviews': reviews})
    save('data/research/round3_bindings.json', {'schema_version': '1.0', 'bindings': bindings})
    candidates, searches = candidate_searches(load('_round3/reader_bundle.json'), load('_resolved/resolved.json'), doi_to_source)
    assert sources[:106] == original_sources
    for tid, old in original_topics.items():
        assert topics[tid]['id'] == old['id'] and topics[tid]['title_ja'] == old['title_ja']
        assert set(old['source_ids']) <= set(topics[tid]['source_ids'])
    for path, doc in documents.items():
        save(path, doc)
    source_doc['sources'] = sources
    source_doc['updated_on'] = DATE
    source_doc['notes_ja'] = '旧106資料を保持し追加。書誌のみ、抄録、本文指定箇所の確認を分離。信頼性と確実性の正式評価は未実施。'
    save('data/sources.json', source_doc)
    coverage = load('data/research/coverage.json')
    no_source = [tid for tid, topic in topics.items() if not topic['source_ids']]
    new_abstract_topics = {tid for r in reviews if r['review_scope'] == 'abstract' and r['topic_relevance'] >= 4 for tid in r['topic_ids']}
    coverage.update(source_count=len(sources), reference_linked_count=300-len(no_source), search_pending_count=len(no_source),
        correction_notice_count=sum(s.get('record_role') == 'correction_notice' for s in sources),
        candidate_record_count=len(candidates), search_request_count=len(searches),
        successful_searches=sum(s['status'] == 'completed' for s in searches), failed_searches=sum(s['status'] != 'completed' for s in searches),
        zero_hit_searches=sum(s['status'] == 'completed' and not s['candidate_ids'] for s in searches),
        round3_added_source_count=len(sources)-106, round3_source_review_count=len(reviews),
        round3_abstract_review_count=sum(r['review_scope'] == 'abstract' for r in reviews),
        round3_bibliography_only_count=sum(r['review_scope'] == 'bibliography' for r in reviews),
        round3_original_missing_count=len(missing_before),
        round3_missing_now_registered=len(missing_before-set(no_source)),
        round3_missing_with_targeted_abstract=len(missing_before & new_abstract_topics),
        round3_existing_with_targeted_abstract=len(new_abstract_topics-missing_before),
        round3_new_search_request_count=510, selected_fulltext_checks_count=len(checks),
        evidence_edge_count=len(edges), editorial_scored_topic_count=50,
        round3_remaining_unregistered=no_source)
    for cat, progress in zip(categories, coverage['categories']):
        rows = documents[cat['file']]['topics']
        progress.update(reference_linked_count=sum(bool(t['source_ids']) for t in rows),
            round3_source_review_topic_count=sum(bool(t.get('source_review_ids')) for t in rows),
            source_unregistered_count=sum(not t['source_ids'] for t in rows))
    coverage['limits_ja'] = ['資料の登録は確実性や公開準備完了を意味しない。書誌のみ・背景資料を含む。',
        '旧68件の読解メモと今回のsource_reviewsは別管理。本文指定箇所の確認は正式なバイアス評価ではない。',
        '候補数はデータベースのレコード数。同一研究の別版やDOIとPMIDの重複を含み得る。',
        '探索検索であり系統的レビューではない。出典未登録テーマを無関係な資料で埋めない。',
        '今回の510検索は507成功・3失敗。0件も研究不存在の証明ではない。',
        '編集ランキングは50テーマの仮説的評価。閲覧数・検索数・市場調査は用いていない。',
        '出典の点数は調査の優先順。正しさの確率、GRADE、AMSTAR 2の合計点ではない。']
    save('data/research/coverage.json', coverage)
    manifest.update(research_round=ROUND, updated_on=DATE, source_count=len(sources),
        reference_linked_count=300-len(no_source), search_pending_count=len(no_source),
        candidate_record_count=len(candidates), search_request_count=len(searches),
        coverage_notes_ja=coverage['limits_ja'])
    manifest['files'].update(source_reviews='data/research/source_reviews.json',
        source_assessments='data/source_assessments.json', evidence_catalog='data/evidence/catalog.json',
        literature_catalog='data/literature/catalog.json', rankings='data/rankings/')
    save('data/manifest.json', manifest)
    save('data/research/round3_report.json', {'schema_version': '1.0', 'round': ROUND,
        'coverage': {k:v for k,v in coverage.items() if k not in ('categories','limits_ja')},
        'preservation': {'topic_ids_titles_and_order': 'passed', 'original_106_sources_unchanged': 'passed'},
        'fulltext_retrieval_requests': 5, 'fulltext_retrieval_successes': 3,
        'additional_web_fulltext_section_reviews': 4})
    print(json.dumps({k:v for k,v in coverage.items() if k not in ('categories','limits_ja')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
