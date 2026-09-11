#!/usr/bin/env python3
"""Integrate the saved daily-life manuscripts and validate before committing.

Offline only. Existing manuscripts and bibliography records are protected.
This records structural validation, not scientific approval or publication.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BATCH = 'daily-life-20260911'
REPORT = 'data/research/push_reconciliation_20260911.json'
CHECKS = [
    ['scripts/validate.py'],
    ['scripts/validate_research.py'],
    ['scripts/validate_round3.py'],
    ['scripts/validate_editorial_pass.py'],
    ['scripts/validate_reviewed_delivery.py'],
    ['scripts/validate_daily_delivery.py'],
    ['scripts/reconcile_article_progress.py', '--check'],
]


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def run(args):
    result = subprocess.run([sys.executable, *args], cwd=ROOT, text=True, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError('Failed: ' + ' '.join(args) + '\n' + result.stdout + result.stderr)
    return {'command': args, 'returncode': 0}


def fix_official_scope():
    path = ROOT / 'scripts/validate_round3.py'
    text = path.read_text(encoding='utf-8')
    changes = [
        ("require(r['review_scope'] in ('abstract','bibliography'),'Unexpected review scope')",
         "require(r['review_scope'] in ('abstract','bibliography','official_page_reviewed'),'Unexpected review scope')\n"
         "        if r['review_scope']=='official_page_reviewed':\n"
         "            require(sources[r['source_id']]['source_type']=='official_health_information',\n"
         "                    'Official-page review must reference official health information')\n"
         "            require(r.get('additional_reading_scope')=='official_page_reviewed',\n"
         "                    'Official-page scope must be explicitly recorded')\n"
         "            require(bool(r.get('source_locators')), 'Official-page review needs checked sections')"),
        ("    require(coverage['selected_fulltext_checks_count']==",
         "    require(coverage.get('official_page_review_count',0)==sum(r['review_scope']=='official_page_reviewed' for r in reviews.values()),'Official-page review count')\n"
         "    require(coverage['selected_fulltext_checks_count']=="),
        ("'source_reviews_total':len(reviews)",
         "'official_page_reviews':coverage.get('official_page_review_count',0),'source_reviews_total':len(reviews)"),
    ]
    for old, new in changes:
        if new in text:
            continue
        if text.count(old) != 1:
            raise ValueError('Unexpected validator version; reconcile before applying.')
        text = text.replace(old, new)
    path.write_text(text, encoding='utf-8')


def product_hashes():
    result = {'README.md': sha('README.md')}
    for directory in ('articles', 'data', 'docs'):
        for path in (ROOT / directory).rglob('*'):
            if path.is_file():
                result[str(path.relative_to(ROOT))] = sha(path.relative_to(ROOT))
    return result


def main():
    before_catalog = read('data/articles/catalog.json')['articles']
    identities = [(r['topic_id'], r['title_ja']) for r in before_catalog]
    protected = {r[key]: sha(r[key]) for r in before_catalog
                 for key in ('manuscript_path', 'claim_dossier_path') if r.get(key)}
    before_sources = read('data/sources.json')['sources']
    fix_official_scope()
    run(['scripts/apply_reviewed_delivery.py', '--batch', BATCH])
    validation = [run(args) for args in CHECKS]
    first = product_hashes()
    run(['scripts/apply_reviewed_delivery.py', '--batch', BATCH])
    if first != product_hashes():
        raise ValueError('Repeated integration changed output; do not commit.')
    for path, expected in protected.items():
        if sha(path) != expected:
            raise ValueError('Existing manuscript or dossier changed: ' + path)
    current_sources = read('data/sources.json')['sources']
    if before_sources != current_sources[:len(before_sources)]:
        raise ValueError('Existing bibliography records changed.')
    after_catalog = read('data/articles/catalog.json')['articles']
    if identities != [(r['topic_id'], r['title_ja']) for r in after_catalog]:
        raise ValueError('Canonical topic identity or order changed.')
    delivery = read('data/research/reviewed_deliveries/' + BATCH + '/report.json')
    if delivery['authored_articles'] != 12 or delivery['new_manuscripts'] != 12:
        raise ValueError('Unexpected pending delivery count.')
    if delivery['publication_ready_count'] != 0 or delivery['goal_completed']:
        raise ValueError('Integration must not grant publication approval.')
    progress = read('data/articles/progress.json')
    report = {
        'schema_version': '1.0', 'date': '2026-09-11',
        'delivery_id': BATCH, 'validation_status': 'passed',
        'baseline_manuscript_count': sum(bool(r.get('manuscript_path')) for r in before_catalog),
        'preserved_manuscript_and_dossier_files': len(protected),
        'preserved_bibliography_records': len(before_sources),
        'integrated_pending_manuscripts': 12,
        'total_manuscripts': progress['manuscript_count'],
        'total_claim_dossiers': progress['claim_dossier_count'],
        'total_sources': len(current_sources),
        'publication_ready_count': progress['publication_ready_count'],
        'repeatable_integration': True, 'validation': validation,
        'products': delivery['products'],
        'scope_ja': '保存済み12原稿の統合、既存本文・出典の保持、参照・ハッシュ・再生成の一致を確認。科学的な最終評価や公開承認ではありません。'
    }
    path = ROOT / REPORT
    if not path.exists():
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    else:
        previous = read(REPORT)
        if previous['products'] != report['products']:
            raise ValueError('Previously delivered content changed; a new review is needed.')
    print(json.dumps({k: report[k] for k in ('validation_status', 'integrated_pending_manuscripts', 'total_manuscripts', 'total_claim_dossiers', 'total_sources', 'publication_ready_count')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
