#!/usr/bin/env python3
"""Integrate reviewed top-20 source checks offline without changing topic order.

The batch is versioned, readable research data, not an executable instruction.
No networking or publication is performed by this installer.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'research/editorial_pass_20260911'
DATE = '2026-09-11'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def patch(path, old, new):
    original = path.read_text(encoding='utf-8')
    if old in original:
        if original.count(old) != 1:
            raise ValueError('Ambiguous compatibility change: ' + str(path))
        path.write_text(original.replace(old, new), encoding='utf-8')
    elif new not in original:
        raise ValueError('Unexpected source version: ' + str(path))


def merge_rows(path, field, rows, identity, compare_keys):
    document = read(path)
    current = {identity(row): row for row in document[field]}
    assert len(current) == len(document[field]), 'Duplicate input identities'
    for row in rows:
        key = identity(row)
        if key in current:
            assert all(current[key].get(k) == row.get(k) for k in compare_keys), 'Input identity conflict: ' + str(key)
        else:
            document[field].append(row)
            current[key] = row
    write(path, document)


def main():
    batch = read(INPUT / 'continuation_checks.json')
    assert batch['schema_version'] == '1.0'
    sources = []
    for record in batch['sources']:
        source = {
            'source_type': 'journal_article', 'record_role': 'research_entry',
            'verified_via_url': record['url'], 'verification_scope': 'abstract_reviewed',
            'accessed_on': DATE,
            'notes_ja': '確認した抄録・本文箇所と限界はsource_checksを参照。独立査読や正式な確実性評価ではありません。',
            'correction_retraction_check': 'selected_primary_text_checked_not_exhaustive',
            **record,
        }
        sources.append(source)
    merge_rows(INPUT / 'new_sources.json', 'sources', sources, lambda r: r['id'], ['doi', 'url', 'title'])
    merge_rows(INPUT / 'source_checks.json', 'checks', batch['checks'], lambda r: r['id'], ['source_id', 'topic_ids', 'url'])
    merge_rows(INPUT / 'audit_resolutions.json', 'resolutions', batch['resolutions'],
               lambda r: (r['audit_id'], r['topic_id']), ['source_check_ids'])
    script = ROOT / 'scripts/apply_editorial_pass.py'
    helper = "def source_identity(s):\n    if s.get('doi'): return ('doi',s['doi'].strip().lower())\n    if s.get('pmid'): return ('pmid',str(s['pmid']))\n    assert s.get('url'),'Source lacks resolvable identity'\n    return ('url',s['url'].rstrip('/'))\n\n"
    if 'def source_identity(s):' not in script.read_text():
        patch(script, 'def integrate_sources():', helper + 'def integrate_sources():')
    patch(script, "assert sources[new['id']]['doi'].lower()==new['doi'].lower(),'Source ID conflict'",
          "assert source_identity(sources[new['id']])==source_identity(new),'Source ID conflict'")
    patch(script, "assert new['doi'].lower() not in {s['doi'].lower() for s in sources.values() if s.get('doi')},'Duplicate DOI'",
          "assert source_identity(new) not in {source_identity(s) for s in sources.values()},'Duplicate source identity'")
    patch(script, "'category_id':old.get('category_id'),", "'category_id':old.get('category_id') or rows[tid].get('category_id'),")
    validator = ROOT / 'scripts/validate.py'
    patch(validator,
          "source_types = {'journal_article', 'book_chapter', 'official_health_information', 'official_bibliography'}",
          "source_types = {'journal_article', 'book_chapter', 'working_paper', 'official_health_information', 'official_bibliography'}")
    registry_path = ROOT / 'data/sources.json'
    registry = read(registry_path)
    source = next(s for s in registry['sources'] if s['id'] == 'SRC245')
    assert source['doi'].lower() == '10.1093/jcmc/zmad055'
    assert source['year'] in (2023, 2024)
    if source['year'] == 2023:
        write(ROOT / 'data/research/history/SRC245-publication-year-correction.json', {
            'schema_version': '1.0', 'source_id': 'SRC245', 'checked_on': DATE,
            'previous_record': source,
            'correction_ja': '出版社の公開日2024-01-31と巻号29(1)2024を確認。2023は掲載年ではない。',
            'verified_via_url': 'https://academic.oup.com/jcmc/article/29/1/zmad055/7595758',
        })
        source['year'] = 2024
        source['metadata_correction_note_ja'] = '2024-01-31公開。以前の2023表記を出版社の掲載日に基づき修正。'
        write(registry_path, registry)
    print(json.dumps({'status': 'integrated', 'batch_id': batch['batch_id'],
                      'batch_source_records': len(sources), 'batch_source_checks': len(batch['checks']),
                      'batch_audit_actions': len(batch['resolutions']),
                      'scientific_or_publication_approval': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
