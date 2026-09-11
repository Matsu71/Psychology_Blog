#!/usr/bin/env python3
"""Validate research links, counts and example labels; never scientific truth."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read(path: str) -> dict:
    value = json.loads((ROOT / path).read_text(encoding='utf-8'))
    require(isinstance(value, dict) and value.get('schema_version') == '1.0', 'Invalid document: ' + path)
    return value


def no_raw_text(value: object, path: str = '') -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            require(key.lower() not in {'abstracttext', 'abstract', 'fulltext', 'full_text'}, 'Raw paper text: ' + path + '/' + key)
            no_raw_text(child, path + '/' + key)
    elif isinstance(value, list):
        for child in value:
            no_raw_text(child, path)


def validate() -> dict:
    for path in (ROOT / 'data').rglob('*.json'):
        no_raw_text(read(str(path.relative_to(ROOT))))
    manifest = read('data/manifest.json')
    coverage = read('data/research/coverage.json')
    categories = read('data/categories.json')['categories']
    sources = {s['id']: s for s in read('data/sources.json')['sources']}
    topics = {t['id']: t for c in categories for t in read(c['file'])['topics']}
    briefs_list = read('data/research/briefs.json')['briefs']
    briefs = {b['id']: b for b in briefs_list}
    require(len(briefs) == len(briefs_list), 'Duplicate research brief ID')
    require(len({b['primary_source_id'] for b in briefs_list}) == len(briefs), 'Duplicate primary source brief')
    linked_topics = set()
    for bid, b in briefs.items():
        require(b['primary_source_id'] in sources and set(b['source_ids']) <= set(sources), 'Unknown source in ' + bid)
        require(set(b['topic_ids']) <= set(topics), 'Unknown topic in ' + bid)
        require(b['primary_source_id'] in b['source_ids'], 'Primary source absent from references')
        require(b['review_scope'] == 'abstract', 'Unexpected review scope')
        require(b['formal_evidence_certainty'] == 'not_assessed' and b['publication_ready'] is False, 'Overstated review status')
        require(b['study_context']['type'] == 'study_context' and b['study_context']['source_id'] == b['primary_source_id'], 'Study context source mismatch')
        example = b['daily_life_example']
        require(example['type'] == 'illustrative_scenario' and example['observed_in_a_study'] is False, 'Mislabelled example')
        for key in ['key_findings_ja', 'limitations_ja']:
            require(bool(b[key].strip()), 'Empty review field')
        for tid in b['topic_ids']:
            require(bid in topics[tid].get('research_brief_ids', []), 'Missing backlink: ' + tid)
            require(set(b['source_ids']) <= set(topics[tid]['source_ids']), 'Missing topic source links')
        linked_topics.update(b['topic_ids'])
    examples = len(briefs)
    for tid, topic in topics.items():
        for bid in topic.get('research_brief_ids', []):
            require(bid in briefs and tid in briefs[bid]['topic_ids'], 'Invalid brief backlink: ' + tid)
        for key in ['related_topic_ids', 'parent_topic_ids']:
            require(set(topic.get(key, [])) <= set(topics), 'Unknown related topic')
            require(tid not in topic.get(key, []), 'Self relation')
        if 'daily_life_example' in topic:
            ex = topic['daily_life_example']
            require(ex['type'] == 'illustrative_scenario' and ex['observed_in_a_study'] is False, 'Mislabelled topic example')
            examples += 1
    relations = read('data/topic_relations.json')['relations']
    keys = set()
    for rel in relations:
        key = (rel['from_topic_id'], rel['to_topic_id'], rel['relation'])
        require(key not in keys, 'Duplicate relation')
        keys.add(key)
        require(key[0] in topics and key[1] in topics and key[0] != key[1], 'Invalid relation IDs')
        require(key[2] in {'related_question', 'application_of'}, 'Unknown relation type')
    catalog_path = ROOT / 'data/literature/catalog.json'
    catalog = read('data/literature/catalog.json') if catalog_path.exists() else {'candidate_files':['data/literature/candidates.json'], 'search_files':['data/literature/search_log.json']}
    candidates = [p for path in catalog['candidate_files'] for p in read(path)['papers']]
    cids = {p['id'] for p in candidates}
    require(len(cids) == len(candidates), 'Duplicate candidate database ID')
    searches = [s for path in catalog['search_files'] for s in read(path)['searches']]
    require(len({s['task_id'] for s in searches}) == len(searches), 'Duplicate search ID')
    for search in searches:
        require(set(search['candidate_ids']) <= cids, 'Search references unknown candidate')
        require(search['topic_id'] is None or search['topic_id'] in topics, 'Unknown searched topic')
    for p in candidates:
        if p.get('source_id'):
            require(p['source_id'] in sources, 'Unknown candidate source')
    counters = {'category_count': len(categories), 'topic_count': len(topics),
                'source_count': len(sources), 'reviewed_research_count': len(briefs),
                'brief_linked_topic_count': len(linked_topics),
                'reference_linked_count': sum(bool(t['source_ids']) for t in topics.values()),
                'search_pending_count': sum(not t['source_ids'] for t in topics.values()),
                'illustrative_scenario_count': examples, 'study_context_count': len(briefs),
                'search_request_count': len(searches), 'candidate_record_count': len(candidates),
                'correction_notice_count': sum(s.get('record_role') == 'correction_notice' for s in sources.values())}
    for key, count in counters.items():
        require(coverage.get(key) == count, f'Coverage mismatch: {key}')
        if key in manifest:
            require(manifest[key] == count, f'Manifest mismatch: {key}')
    require(manifest['research_brief_count'] == len(briefs), 'Brief total mismatch')
    require(manifest['topic_defaults']['publication_ready'] is False, 'Candidates must remain unpublished')
    for cat, progress in zip(categories, coverage['categories']):
        rows = read(cat['file'])['topics']
        require(cat['id'] == progress['category_id'], 'Category order mismatch')
        require(len(rows) == progress['topic_count'] == cat['topic_count'], 'Category count mismatch')
        require(sum(t['id'] in linked_topics for t in rows) == progress['brief_linked_count'], 'Category review count mismatch')
    return {'schema_version': '1.0', 'status': 'passed', **counters,
            'scope_ja': 'ID・参照・件数・状態・例のラベル・論文原文の非収録を構造検証。科学的真偽、意味の重複、全リンクの到達性を保証しない。'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', type=Path)
    args = parser.parse_args()
    try:
        result = validate()
        if args.export is not None:
            out = args.export.resolve()
            require(not out.is_relative_to((ROOT / 'data').resolve()), 'Cannot export over canonical data')
            out.mkdir(parents=True, exist_ok=True)
            for src, dest in [('data/research/briefs.json', 'research_briefs.json'),
                              ('data/research/coverage.json', 'research_coverage.json'),
                              ('data/literature/candidates.json', 'literature_candidates.json'),
                              ('data/literature/search_log.json', 'search_log.json'),
                              ('data/topic_relations.json', 'topic_relations.json'),
                              ('docs/RESEARCH_NOTES.md', 'research_notes.md'),
                              ('docs/TOPICS_INDEX.md', 'topics_index.md'),
                              ('docs/THEME_ARCHITECTURE.md', 'theme_architecture.md')]:
                if (ROOT / src).is_file():
                    shutil.copyfile(ROOT / src, out / dest)
            (out / 'research_validation_report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('RESEARCH VALIDATION FAILED: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
