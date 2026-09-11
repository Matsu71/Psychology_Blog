#!/usr/bin/env python3
"""Render the authored continuation without overwriting canonical manuscripts.

No network calls, no automatic scientific approval, no alteration of source IDs.
The public input contains original prose and citations, not copied paper text.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'research/continuation_delivery_20260911'
OUTPUT = ROOT / 'data/articles/continuation_20260911'
MANUSCRIPTS = ROOT / 'articles/continuation_20260911'
EXPECTED = {
    'PSY-DEC-006', 'PSY-SLP-007', 'PSY-SLP-001', 'PSY-LEA-001',
    'PSY-WRK-002', 'PSY-DIG-001', 'PSY-WEL-005', 'PSY-HAB-005',
    'PSY-LAN-008', 'PSY-MON-001',
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=object_pairs)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def doi(value: str | None) -> str:
    return (value or '').strip().lower().removeprefix('https://doi.org/')


def build() -> dict:
    sources = load(ROOT / 'data/sources.json')['sources']
    source_by_id = {s['id']: s for s in sources}
    categories = load(ROOT / 'data/categories.json')['categories']
    topics = {t['id']: t for category in categories for t in load(ROOT / category['file'])['topics']}
    protected = [ROOT / 'data/sources.json', ROOT / 'data/categories.json', ROOT / 'data/manifest.json']
    protected += sorted((ROOT / 'data/topics').glob('*.json'))
    protected += [p for p in [ROOT / 'data/articles/catalog.json', ROOT / 'data/articles/progress.json'] if p.exists()]
    before = {str(p.relative_to(ROOT)): digest(p) for p in protected}
    inputs = sorted(INPUT.glob('articles_*.json'))
    articles = []
    for path in inputs:
        document = load(path)
        require(document['schema_version'] == '1.0', 'Unknown input schema')
        require(document['publication_ready'] is False, 'Input must not assert publication approval')
        articles.extend(document['articles'])
    require(len(articles) == len(EXPECTED), 'Expected exactly the ten continuation manuscripts')
    require({a['topic_id'] for a in articles} == EXPECTED, 'Unexpected or duplicate continuation topics')
    require(EXPECTED <= set(topics), 'Unknown topic ID')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    MANUSCRIPTS.mkdir(parents=True, exist_ok=True)
    index = []
    missing_bindings = []
    claim_total = 0
    for article in articles:
        tid = article['topic_id']
        references = {s['key']: s for s in article['sources']}
        require(len(references) == len(article['sources']), 'Duplicate source key: ' + tid)
        require(len(article['sections']) >= 3, 'Too few substantive sections: ' + tid)
        require(len(article['lead']) >= 40, 'Missing introduction: ' + tid)
        require(sum(len(s['text']) for s in article['sections']) >= 650, 'Insufficient manuscript body: ' + tid)
        require(len(article['claims']) >= 2, 'Missing scoped claims: ' + tid)
        require(len({c['id'] for c in article['claims']}) == len(article['claims']), 'Duplicate claim ID: ' + tid)
        bindings = {}
        for key, reference in references.items():
            require(urlparse(reference['url']).scheme == 'https', 'Invalid citation URL: ' + key)
            requested_doi = doi(reference.get('doi'))
            requested_pmid = str(reference.get('pmid') or '')
            requested_id = reference.get('canonical_source_id')
            matches = []
            for source in sources:
                match_doi = bool(requested_doi and requested_doi == doi(source.get('doi')))
                match_pmid = bool(requested_pmid and requested_pmid == str(source.get('pmid') or ''))
                match_url = source.get('url') == reference['url']
                match_id = requested_id == source['id']
                if match_doi or match_pmid or match_url or match_id:
                    matches.append(source['id'])
            matches = list(dict.fromkeys(matches))
            if len(matches) == 1:
                sid = matches[0]
                if requested_doi and source_by_id[sid].get('doi'):
                    require(doi(source_by_id[sid]['doi']) == requested_doi, 'Conflicting DOI binding: ' + tid + '/' + key)
                bindings[key] = {'canonical_source_id': sid, 'binding_status': 'unique_identifier_match'}
            else:
                bindings[key] = {'canonical_source_id': None, 'binding_status': 'not_found' if not matches else 'ambiguous', 'candidate_source_ids': matches}
                missing_bindings.append({'topic_id': tid, 'reference_key': key, 'selector': reference, 'binding': bindings[key]})
        claims = []
        for claim in article['claims']:
            require(bool(claim['text']) and bool(claim['scope']) and bool(claim['not_supported']), 'Unscoped claim: ' + tid)
            require(claim['source_keys'] and set(claim['source_keys']) <= set(references), 'Unknown claim reference: ' + tid)
            claims.append({
                'claim_id': tid + '-' + claim['id'], 'text_ja': claim['text'],
                'scope_ja': claim['scope'], 'not_supported_ja': claim['not_supported'],
                'source_keys': claim['source_keys'],
                'canonical_source_ids': [bindings[k]['canonical_source_id'] for k in claim['source_keys'] if bindings[k]['canonical_source_id']],
                'unresolved_source_keys': [k for k in claim['source_keys'] if not bindings[k]['canonical_source_id']],
                'formal_evidence_certainty': 'not_assessed',
                'independent_review_completed': False,
                'publication_ready': False,
            })
        claim_total += len(claims)
        text = ['# ' + article['title'], '',
                '> 出典と適用範囲を整理した編集原稿です。公開承認済みの完成稿ではありません。', '', article['lead'], '']
        for section in article['sections']:
            require(set(section['source_keys']) <= set(references), 'Unknown section reference: ' + tid)
            refs = ''.join('[^' + key + ']' for key in section['source_keys'])
            text += ['## ' + section['heading'], '', section['text'] + refs, '']
        application = article['application']
        require(application['classification'] == 'editorial_application_not_directly_validated_protocol', 'Application status is overstated')
        text += ['## 日常で考えるための例', '', '以下は編集上の応用例で、この手順全体の有効性を直接検証した実験の紹介ではありません。', '']
        text += [str(i) + '. ' + step for i, step in enumerate(application['steps'], 1)]
        text += ['', application['caution'], '', '## 出典と確認範囲', '']
        for key, reference in references.items():
            identity = reference.get('doi') or reference.get('title') or reference.get('canonical_source_id') or key
            text += ['[^' + key + ']: [' + identity + '](' + reference['url'] + ')。確認範囲：`' + reference['reading_scope'] + '`。']
            if reference.get('publication_status') == 'working_paper_not_peer_reviewed':
                text.append('    査読前ワーキングペーパー。査読済みの決着や独立した再現としては扱いません。')
            for note in ['independence_note', 'reporting_note', 'method_note']:
                if reference.get(note):
                    text.append('    ' + reference[note])
        text += ['', '確認範囲は引き継いだ原資料の読解記録に基づきます。ファイルの生成や書誌IDの一致だけで科学的な主張の正しさを認定していません。', '']
        manuscript = MANUSCRIPTS / (tid + '.md')
        manuscript.write_text('\n'.join(text), encoding='utf-8')
        dossier = OUTPUT / 'claims' / (tid + '.json')
        write_json(dossier, {
            'schema_version': '1.0', 'topic_id': tid,
            'title_ja': article['title'], 'canonical_topic_title_ja': topics[tid]['title_ja'],
            'claims': claims, 'references': article['sources'], 'source_bindings': bindings,
            'application': application, 'publication_ready': False,
            'status': 'source_scoped_manuscript_pending_final_review',
            'manuscript_path': str(manuscript.relative_to(ROOT)), 'manuscript_sha256': digest(manuscript),
        })
        index.append({'topic_id': tid, 'title_ja': article['title'],
                      'manuscript_path': str(manuscript.relative_to(ROOT)), 'manuscript_sha256': digest(manuscript),
                      'claim_dossier_path': str(dossier.relative_to(ROOT)), 'claim_count': len(claims),
                      'publication_ready': False})
    for name, checksum in before.items():
        require(digest(ROOT / name) == checksum, 'Protected canonical data changed: ' + name)
    progress_path = ROOT / 'data/articles/progress.json'
    canonical_progress = load(progress_path) if progress_path.exists() else {}
    top20 = canonical_progress.get('top20_topic_ids', [])
    report = {
        'schema_version': '1.0', 'delivery_id': 'continuation-20260911', 'date': '2026-09-11',
        'final_goal_articles': 300, 'goal_completed': False,
        'manuscript_count_this_delivery': len(index), 'claim_count_this_delivery': claim_total,
        'publication_ready_count_this_delivery': 0,
        'unresolved_canonical_binding_count': len(missing_bindings),
        'unresolved_canonical_bindings': missing_bindings,
        'delivery_topic_ids_in_current_top20': [a['topic_id'] for a in index if a['topic_id'] in top20],
        'canonical_registry_mutated': False, 'canonical_article_catalog_mutated': False,
        'verification_scope': 'JSON, identifiers, citation keys, manuscript lengths, hashes and preservation; not independent scientific review',
        'input_sha256': {str(p.relative_to(ROOT)): digest(p) for p in inputs},
        'articles': index,
        'next_steps_ja': [
            '原稿・主張表の保存結果を再取得して確認する。',
            '未結合の出典識別子は正本への照合・追加を行い、内容を確認してから採用する。',
            '既存の原稿・原文照合記録と差分を比較し、正本への統合と記事別の完成判定へ進める。',
            '未着手テーマにも研究確認、主張の限定、読者向けの本文、点検の工程を続ける。',
        ],
    }
    write_json(OUTPUT / 'report.json', report)
    document = ['# 継続編集：原稿と主張表', '',
                '最終目標は300記事です。以下の原稿保存を、記事の公開承認や全工程の完了とは扱いません。', '',
                f"今回の原稿は{len(index)}件、主張表は{claim_total}項目です。既存の正本と記事カタログは変更していません。", '',
                f"正本の書誌への未結合・曖昧な対応は{len(missing_bindings)}件です。識別子の一致は科学的な支持の認定ではありません。", '',
                '| テーマID | 原稿 | 主張数 |', '|---|---|---:|']
    for row in index:
        document.append('| ' + row['topic_id'] + ' | [' + row['title_ja'] + '](../' + row['manuscript_path'] + ') | ' + str(row['claim_count']) + ' |')
    document += ['', '## 次の作業', ''] + report['next_steps_ja']
    (ROOT / 'docs/CONTINUATION_DELIVERY.md').write_text('\n'.join(document) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ['articles', 'unresolved_canonical_bindings', 'input_sha256']}, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    build()
