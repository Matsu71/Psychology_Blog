#!/usr/bin/env python3
"""Validate the topic database; optionally export a portable JSON and Markdown index.

Python 3.9+; standard library only. This validates structure, not scientific truth
or URL reachability. The checked-in data/topics files are the source of truth.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import quote_plus, urlparse

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def invalid_constant(value: str) -> None:
    raise ValueError(f'Non-finite JSON constant: {value}')


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'),
                       object_pairs_hook=unique_object,
                       parse_constant=invalid_constant)
    require(isinstance(value, dict), f'{path}: expected an object')
    require(value.get('schema_version') == '1.0', f'{path}: unsupported schema')
    return value


def nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def valid_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == 'https' and bool(parsed.netloc)


def load_and_validate() -> tuple[dict[str, Any], dict[str, Any]]:
    # Parse all checked-in JSON, including future additional data files.
    for path in (ROOT / 'data').rglob('*.json'):
        read_json(path)
    manifest = read_json(ROOT / 'data/manifest.json')
    categories = read_json(ROOT / 'data/categories.json')['categories']
    source_document = read_json(ROOT / 'data/sources.json')
    sources = source_document['sources']
    require(isinstance(categories, list) and isinstance(sources, list), 'Invalid catalog arrays')
    scopes = {'official_page_reviewed', 'bibliography_verified', 'abstract_reviewed', 'article_text_reviewed'}
    source_types = {'journal_article', 'official_health_information', 'official_bibliography'}
    source_ids: set[str] = set()
    doi_ids: set[str] = set()
    for source in sources:
        require(isinstance(source, dict), 'Invalid source record')
        sid = source.get('id')
        require(isinstance(sid, str) and re.fullmatch(r'SRC\d{3,}', sid) is not None, 'Invalid source ID')
        require(sid not in source_ids, f'Duplicate source ID: {sid}')
        source_ids.add(sid)
        for key in ('title', 'authors_display', 'notes_ja'):
            require(nonempty_text(source.get(key)), f'{sid}: missing {key}')
        require(source.get('verification_scope') in scopes, f'{sid}: invalid verification scope')
        require(source.get('source_type') in source_types, f'{sid}: invalid source type')
        require(valid_url(source.get('url')) and valid_url(source.get('verified_via_url')), f'{sid}: invalid URL')
        year = source.get('year')
        require(year is None or type(year) is int, f'{sid}: invalid year')
        doi = source.get('doi')
        if doi is not None:
            require(isinstance(doi, str) and re.fullmatch(r'10\.\d{4,9}/\S+', doi) is not None, f'{sid}: invalid DOI')
            require(doi.lower() not in doi_ids, f'Duplicate DOI: {doi}')
            doi_ids.add(doi.lower())
    category_ids: set[str] = set()
    topic_ids: set[str] = set()
    titles: set[str] = set()
    catalog_paths: set[Path] = set()
    topics: list[dict[str, Any]] = []
    defaults = manifest['topic_defaults']
    require(defaults.get('record_status') == 'theme_candidate', 'Unexpected publication stage')
    require(defaults.get('evidence_appraisal') == 'not_assessed', 'Unexpected evidence appraisal')
    require(defaults.get('publication_ready') is False, 'Candidates must not be publication-ready')
    for category in categories:
        cid = category['id']
        require(cid not in category_ids, f'Duplicate category: {cid}')
        category_ids.add(cid)
        require(nonempty_text(category.get('name_ja')), f'{cid}: missing name')
        path = (ROOT / category['file']).resolve()
        require(path.is_relative_to((ROOT / 'data/topics').resolve()), f'{cid}: invalid path')
        require(path not in catalog_paths, f'Duplicate category file: {path}')
        catalog_paths.add(path)
        document = read_json(path)
        require(document.get('category_id') == cid, f'{path}: category mismatch')
        records = document.get('topics')
        require(isinstance(records, list), f'{cid}: topics must be an array')
        require(len(records) == category['topic_count'], f'{cid}: count mismatch')
        for record in records:
            require(isinstance(record, dict), f'{cid}: invalid topic record')
            tid = record.get('id')
            pattern = r'PSY-' + re.escape(category['id_prefix']) + r'-\d{3,}'
            require(isinstance(tid, str) and re.fullmatch(pattern, tid) is not None, f'{cid}: invalid topic ID')
            require(tid not in topic_ids, f'Duplicate topic ID: {tid}')
            topic_ids.add(tid)
            for key in ('title_ja', 'angle_ja', 'search_query', 'caution_ja'):
                require(nonempty_text(record.get(key)), f'{tid}: missing {key}')
            title = record['title_ja'].strip()
            require(title not in titles, f'Duplicate title: {title}')
            titles.add(title)
            concepts = record.get('concepts_en')
            require(isinstance(concepts, list) and len(concepts) > 0 and all(nonempty_text(x) for x in concepts), f'{tid}: invalid concepts')
            require(type(record.get('priority')) is int and record['priority'] in (1, 2), f'{tid}: invalid priority')
            refs = record.get('source_ids')
            require(isinstance(refs, list) and all(isinstance(x, str) for x in refs), f'{tid}: invalid source list')
            require(len(refs) == len(set(refs)), f'{tid}: duplicate references')
            require(set(refs).issubset(source_ids), f'{tid}: unknown source reference')
            merged = dict(record)
            merged.update(defaults)
            merged.update(category_id=cid, category_name_ja=category['name_ja'],
                          research_status='reference_linked' if refs else 'search_pending',
                          pubmed_search_url='https://pubmed.ncbi.nlm.nih.gov/?term=' + quote_plus(record['search_query']))
            topics.append(merged)
    actual_paths = {path.resolve() for path in (ROOT / 'data/topics').glob('*.json')}
    require(catalog_paths == actual_paths, 'Catalog and topic files differ')
    linked = sum(bool(t['source_ids']) for t in topics)
    expected = {'category_count': len(categories), 'topic_count': len(topics),
                'source_count': len(sources), 'reference_linked_count': linked,
                'search_pending_count': len(topics) - linked}
    for key, value in expected.items():
        require(manifest.get(key) == value, f'Manifest {key}: expected {value}, found {manifest.get(key)}')
    shortlist = manifest['initial_shortlist']
    require(len(shortlist) == len(set(shortlist)) and set(shortlist).issubset(topic_ids), 'Invalid shortlist')
    referenced = {sid for topic in topics for sid in topic['source_ids']}
    report = {'status': 'passed', **expected,
              'priority_counts': dict(Counter(str(t['priority']) for t in topics)),
              'source_verification_counts': dict(Counter(s['verification_scope'] for s in sources)),
              'unassigned_source_ids': sorted(source_ids - referenced),
              'scope': 'JSON structure, stable-ID uniqueness, exact-title uniqueness, counts, reference integrity; not scientific or semantic validation'}
    portable = {'schema_version': '1.0', 'manifest': manifest, 'categories': categories,
                'source_metadata': {k: v for k, v in source_document.items() if k != 'sources'},
                'sources': sources, 'topics': topics}
    return portable, report


def export_files(directory: Path, portable: dict[str, Any], report: dict[str, Any]) -> None:
    directory = directory.resolve()
    require(not directory.is_relative_to((ROOT / 'data').resolve()), 'Export must not modify source data')
    directory.mkdir(parents=True, exist_ok=True)
    for name, obj in [('topics.json', portable), ('validation_report.json', report)]:
        (directory / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    lines = ['# ブログテーマ一覧', '', 'テーマ候補であり、効果の確実性や公開可能性を示す一覧ではありません。', '']
    for category in portable['categories']:
        lines += ['## ' + category['name_ja'], '', '| ID | テーマ | 調査優先度 | 資料の入口 |', '|---|---|---|---|']
        for topic in portable['topics']:
            if topic['category_id'] == category['id']:
                refs = ', '.join(topic['source_ids']) or '出典調査待ち'
                title = topic['title_ja'].replace('|', '\\|')
                lines.append(f"| {topic['id']} | {title} | {topic['priority']} | {refs} |")
        lines.append('')
    (directory / 'topics.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', type=Path, help='Directory for consolidated JSON, index, and validation report')
    args = parser.parse_args()
    try:
        portable, report = load_and_validate()
        if args.export is not None:
            export_files(args.export, portable, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'VALIDATION FAILED: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
