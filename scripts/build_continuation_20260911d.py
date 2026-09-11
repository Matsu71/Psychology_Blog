#!/usr/bin/env python3
"""Render a reviewed-input continuation and verify its references.

This performs structural checks, not scientific peer review. Existing manuscripts
are preserved; their alternatives remain explicitly labelled revisions. New topic
entries are integrated only if the existing project validators all accept them.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BATCH = 'continuation-20260911d'
BATCH_DIR = ROOT / 'data/articles/batches' / BATCH
EXPECTED_INPUTS = 3
EXPECTED_ARTICLES = 12


def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def doi(value) -> str:
    result = str(value or '').strip().lower()
    for prefix in ['https://doi.org/', 'http://doi.org/', 'https://dx.doi.org/', 'http://dx.doi.org/']:
        if result.startswith(prefix):
            result = result[len(prefix):]
    return result


def within_repo(value: str) -> Path:
    candidate = (ROOT / value).resolve()
    if not candidate.is_relative_to(ROOT):
        raise ValueError('Path escapes repository: ' + value)
    return candidate


def resolve_source(selector: dict, sources: list) -> dict:
    matches = []
    for source in sources:
        found = False
        if selector.get('doi'):
            identifiers = [source.get('doi')] + source.get('identifier_aliases', [])
            found = doi(selector['doi']) in {doi(x) for x in identifiers if x}
        if selector.get('pmid'):
            wanted = str(selector['pmid'])
            found = found or str(source.get('pmid') or '') == wanted
            for key in ['url', 'verified_via_url']:
                match = re.search(r'pubmed\.ncbi\.nlm\.nih\.gov/(\d+)', str(source.get(key) or ''))
                if match and match.group(1) == wanted:
                    found = True
        if found:
            matches.append(source)
    by_id = {s['id']: s for s in matches}
    if len(by_id) != 1:
        raise ValueError('Source selector must identify one registered record: ' + json.dumps(selector, ensure_ascii=False))
    return next(iter(by_id.values()))


def catalog_rows(document: dict):
    possibilities = []
    for key, value in document.items():
        if isinstance(value, list) and len(value) == 300 and all(isinstance(r, dict) for r in value):
            if all('topic_id' in r or ('id' in r and str(r['id']).startswith('PSY-')) for r in value):
                possibilities.append((key, value))
    if len(possibilities) != 1:
        raise ValueError('Cannot unambiguously identify the 300-topic article catalog')
    return possibilities[0]


def row_topic(row):
    return row.get('topic_id') or row.get('id')


def find_path_key(rows: list, suffix: str, token: str) -> str:
    candidates = set()
    for row in rows:
        for key, value in row.items():
            if isinstance(value, str) and value.endswith(suffix) and token in value:
                if within_repo(value).is_file():
                    candidates.add(key)
    preferred = [k for k in candidates if ('manuscript' in k if suffix == '.md' else 'claim' in k)]
    options = preferred or sorted(candidates)
    if len(options) != 1:
        raise ValueError('Ambiguous catalog file key: ' + repr(options))
    return options[0]


def render(article, topic, resolved):
    title = topic['title_ja']
    lines = ['# ' + title, '',
             '> 改稿案です。出典は既存の登録資料へ照合しています。新規の系統的検索、独立した科学的査読、公開承認の完了を意味しません。', '',
             article['lead'], '']
    claims = []
    for section in article['sections']:
        references = ''.join('[^' + resolved[key]['id'] + ']' for key in section['source_keys'])
        lines.extend(['## ' + section['heading'], '', section['text'] + references, ''])
    lines.extend(['## 出典', ''])
    seen = set()
    for selector in article['sources']:
        source = resolved[selector['key']]
        if source['id'] in seen:
            continue
        seen.add(source['id'])
        label = '訂正告知。独立した効果研究としては数えません。 ' if selector.get('role') == 'correction_notice' else ''
        ref = f"{label}{source.get('authors_display', '')} ({source.get('year') or '年未確認'}). {source['title']}."
        lines.append('[^' + source['id'] + ']: ' + ref + ' ' + source['url'])
    lines += ['', '## 公開前に残る確認', '']
    lines += ['- ' + check for check in article['remaining_checks']]
    for index, claim in enumerate(article['claims'], 1):
        ids = list(dict.fromkeys(resolved[key]['id'] for key in claim['source_keys']))
        claims.append({'id': topic['id'] + '-D' + str(index).zfill(2),
            'text': claim['text'], 'claim_ja': claim['text'],
            'source_ids': ids, 'scope': claim['scope'], 'scope_ja': claim['scope'],
            'not_supported': claim['not_supported'], 'limitations_ja': claim['not_supported'],
            'claim_type': 'research_interpretation' if ids else 'editorial_reasoning',
            'review_scope': 'previously_registered_source_review',
            'independent_review_completed': False,
            'formal_evidence_certainty': 'not_assessed'})
    dossier = {'schema_version': '1.0', 'topic_id': topic['id'], 'title_ja': title,
        'authoring_batch': BATCH, 'state': 'manuscript_pending_article_review',
        'publication_ready': False, 'independent_review_completed': False,
        'evidence_basis': article.get('evidence_basis', 'previously_registered_source_reviews_not_a_new_systematic_search'),
        'source_ids': sorted(seen), 'claims': claims,
        'source_key_map': {key: value['id'] for key, value in resolved.items()},
        'remaining_checks': article['remaining_checks'],
        'application_status': 'illustrative_and_editorial_not_independently_tested',
        'updated_on': '2026-09-11'}
    return '\n'.join(lines) + '\n', dossier


def main():
    inputs = sorted((ROOT / 'research/continuation_20260911d').glob('articles_*.json'))
    if len(inputs) != EXPECTED_INPUTS:
        raise ValueError(f'Expected {EXPECTED_INPUTS} authored input files, found {len(inputs)}')
    articles = [a for p in inputs for a in read(p)['articles']]
    if len(articles) != EXPECTED_ARTICLES or len({a['topic_id'] for a in articles}) != EXPECTED_ARTICLES:
        raise ValueError('Authored article count or unique topic count is inconsistent')
    categories = read(ROOT / 'data/categories.json')['categories']
    topic_files = [within_repo(c['file']) for c in categories]
    topics = {t['id']: t for p in topic_files for t in read(p)['topics']}
    sources = read(ROOT / 'data/sources.json')['sources']
    protected = [ROOT / 'data/sources.json', ROOT / 'data/categories.json'] + topic_files
    protected_before = {str(p): digest(p) for p in protected}
    products = []
    for article in articles:
        tid = article['topic_id']
        if tid not in topics or article['publication_ready'] is not False:
            raise ValueError('Unknown topic or unsupported release flag: ' + tid)
        if not article['remaining_checks']:
            raise ValueError('The authoring input must retain its concrete remaining checks')
        resolved = {s['key']: resolve_source(s, sources) for s in article['sources']}
        if len(resolved) != len(article['sources']):
            raise ValueError('Duplicate local source key: ' + tid)
        for section in article['sections']:
            if not set(section['source_keys']) <= set(resolved):
                raise ValueError('Unresolved section citation: ' + tid)
            if section['kind'] == 'research' and not section['source_keys']:
                raise ValueError('Research section without a registered citation: ' + tid)
            if not section['text'].strip():
                raise ValueError('Empty section: ' + tid)
        for claim in article['claims']:
            if not set(claim['source_keys']) <= set(resolved):
                raise ValueError('Unresolved claim citation: ' + tid)
        if not any(s['kind'] == 'limitations' for s in article['sections']):
            raise ValueError('Missing limitations section: ' + tid)
        manuscript, dossier = render(article, topics[tid], resolved)
        path = ROOT / 'articles/manuscripts' / BATCH / (tid + '.md')
        claim_path = ROOT / 'data/articles/revisions' / BATCH / (tid + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(manuscript, encoding='utf-8')
        write_json(claim_path, dossier)
        products.append({'topic_id': tid, 'title_ja': topics[tid]['title_ja'],
            'manuscript_path': str(path.relative_to(ROOT)), 'claim_path': str(claim_path.relative_to(ROOT)),
            'manuscript_sha256': digest(path), 'claim_sha256': digest(claim_path),
            'source_ids': dossier['source_ids'], 'claim_count': len(dossier['claims']),
            'body_characters': len(article['lead']) + sum(len(s['text']) for s in article['sections']),
            'publication_ready': False, 'catalog_disposition': 'separate_revision_pending_catalog_review'})
    catalog_path = ROOT / 'data/articles/catalog.json'
    progress_path = ROOT / 'data/articles/progress.json'
    saved_catalog = catalog_path.read_bytes()
    saved_progress = progress_path.read_bytes()
    integration_error = None
    validation = []
    new_ids = []
    try:
        catalog = read(catalog_path)
        _, rows = catalog_rows(catalog)
        row_map = {row_topic(r): r for r in rows}
        manuscript_key = find_path_key(rows, '.md', 'articles/')
        claim_key = find_path_key(rows, '.json', 'claims')
        for product in products:
            row = row_map[product['topic_id']]
            if row.get('authoring_batch') == BATCH:
                product['catalog_disposition'] = 'canonical_new_manuscript'
                new_ids.append(product['topic_id'])
                continue
            existing = row.get(manuscript_key)
            if existing and within_repo(existing).is_file():
                product['catalog_disposition'] = 'revision_of_existing_manuscript_original_preserved'
                product['existing_manuscript_path'] = existing
                continue
            row[manuscript_key] = product['manuscript_path']
            row[claim_key] = product['claim_path']
            row['state'] = 'manuscript_pending_article_review'
            row['publication_ready'] = False
            row['unresolved_source_keys'] = []
            row['source_ids'] = product['source_ids']
            row['claim_count'] = product['claim_count']
            row['manuscript_sha256'] = product['manuscript_sha256']
            row['claim_sha256'] = product['claim_sha256']
            row['authoring_batch'] = BATCH
            row['updated_on'] = '2026-09-11'
            product['catalog_disposition'] = 'canonical_new_manuscript'
            new_ids.append(product['topic_id'])
        progress = read(progress_path)
        progress['manuscript_count'] = sum(bool(r.get(manuscript_key)) and within_repo(r[manuscript_key]).is_file() for r in rows)
        progress['claim_dossier_count'] = sum(bool(r.get(claim_key)) and within_repo(r[claim_key]).is_file() for r in rows)
        if 'claim_and_caution_count' in progress:
            progress['claim_and_caution_count'] = sum(r.get('claim_count', 0) for r in rows if r.get(claim_key) and within_repo(r[claim_key]).is_file())
        write_json(catalog_path, catalog)
        write_json(progress_path, progress)
        for script in ['validate.py', 'validate_research.py', 'validate_round3.py', 'validate_editorial_pass.py']:
            p = ROOT / 'scripts' / script
            if not p.is_file():
                raise ValueError('Expected validator is missing: ' + script)
            result = subprocess.run([sys.executable, str(p)], cwd=ROOT, text=True, capture_output=True)
            validation.append({'script': script, 'returncode': result.returncode})
            if result.returncode:
                integration_error = script + ': ' + result.stderr[-6000:] + result.stdout[-3000:]
                raise ValueError(integration_error)
    except (OSError, ValueError, KeyError, TypeError) as error:
        integration_error = integration_error or str(error)
        catalog_path.write_bytes(saved_catalog)
        progress_path.write_bytes(saved_progress)
        for product in products:
            if product['catalog_disposition'] == 'canonical_new_manuscript':
                product['catalog_disposition'] = 'catalog_integration_rolled_back_pending_schema_review'
        new_ids = []
    for p in protected:
        if digest(p) != protected_before[str(p)]:
            raise ValueError('Protected source or topic file changed: ' + str(p))
    for product in products:
        if digest(ROOT / product['manuscript_path']) != product['manuscript_sha256']:
            raise ValueError('Manuscript hash mismatch')
        if digest(ROOT / product['claim_path']) != product['claim_sha256']:
            raise ValueError('Claim dossier hash mismatch')
    report = {'schema_version': '1.0', 'batch_id': BATCH, 'date': '2026-09-11',
        'final_goal_articles': 300, 'goal_completed': False,
        'authored_manuscripts': len(products), 'claim_dossiers': len(products),
        'claim_and_reasoning_items': sum(p['claim_count'] for p in products),
        'new_canonical_manuscripts': len(new_ids), 'canonical_topic_ids_added': new_ids,
        'canonical_catalog_integrated': integration_error is None,
        'catalog_integration_error': integration_error,
        'publication_ready_count': 0, 'existing_manuscripts_preserved': True,
        'sources_and_topic_ids_unchanged': True,
        'verification_scope': 'registered identifier resolution, references, file hashes, existing project validators; not scientific truth or independent peer review',
        'evidence_basis': 'existing source reviews; no new literature search claimed for this batch',
        'validation': validation, 'articles': products}
    write_json(BATCH_DIR / 'manifest.json', report)
    lines = ['# 第D回の追加原稿と改稿案', '',
        '最終目標は科学的根拠をたどれる一般向け300記事です。今回の原稿を公開承認済みの完成数へは加算していません。', '',
        f"本文と根拠表：{len(products)}テーマ。新たに正本へ統合した本文：{len(new_ids)}。既存本文は保持しました。", '',
        '今回の出典照合は、登録済み資料の識別子と既存の読解記録に基づきます。新しい文献検索や独立した再査読を実施したという表示ではありません。', '',
        '| テーマ | 原稿 | 根拠表 | 状態 |', '|---|---|---|---|']
    for p in products:
        lines.append('| ' + p['title_ja'] + ' | [本文](../' + p['manuscript_path'] + ') | [根拠表](../' + p['claim_path'] + ') | ' + p['catalog_disposition'] + ' |')
    lines += ['', '## 次の作業', '',
        '今回の原稿の具体的な残課題を原文・追試と照合します。改稿案は既存原稿と比較し、根拠が増えていない箇所を完成扱いにしません。新旧の学習法・創造性研究を比較する作業も引き継ぎます。', '',
        '## 構造検証と内容点検の区別', '',
        '識別子、参照、ハッシュの一致は、論文の解釈の正しさの保証ではありません。各本文に「公開前に残る確認」を明記しています。']
    if integration_error:
        lines += ['', '## 統合保留', '', '既存の検証条件を満たさなかったため、正本カタログと集計値を元に戻しています。原稿と根拠表は保管し、検証条件を緩めずに差分を照合します。', '', '```text', integration_error, '```']
    (ROOT / 'docs/CONTINUATION_20260911D.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    readme = ROOT / 'README.md'
    text = readme.read_text(encoding='utf-8')
    link = '[追加原稿・改稿案と確認事項](docs/CONTINUATION_20260911D.md)'
    if link not in text:
        text += '\n' + link + '\n'
    if integration_error is None:
        progress = read(progress_path)
        text = re.sub(r'本文\d+件', '本文' + str(progress['manuscript_count']) + '件', text)
        text = re.sub(r'主張対応表\d+件', '主張対応表' + str(progress['claim_dossier_count']) + '件', text)
    readme.write_text(text, encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'articles'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
