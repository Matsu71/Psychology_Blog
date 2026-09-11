#!/usr/bin/env python3
"""Render human-authored continuation articles and verify their references.

No external calls, scientific auto-approval, source-registry edits or force push.
A failed catalog integration is rolled back; the authored draft package is kept
with an explicit pending status instead of claiming it is integrated.
"""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH = 'continuation-20260911b'
DATA = ROOT / 'data/articles/batches' / BATCH
DRAFTS = ROOT / 'articles/drafts' / BATCH


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def write(path, value):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(encode(value))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def doi(value):
    return (value or '').strip().lower().removeprefix('https://doi.org/')


def pmid(source):
    value = str(source.get('pmid') or '')
    if value:
        return value
    for key in ['url', 'verified_via_url']:
        hit = re.search(r'(?:pubmed\.ncbi\.nlm\.nih\.gov/|europepmc\.org/article/MED/)(\d+)', source.get(key) or '')
        if hit:
            return hit.group(1)
    return ''


def resolve(selector, sources):
    matches = [s for s in sources if
        selector.get('pmid') and pmid(s) == str(selector['pmid']) or
        selector.get('doi') and doi(s.get('doi')) == doi(selector['doi'])]
    if len(matches) != 1:
        raise ValueError('Source selector must resolve uniquely: ' + json.dumps(selector))
    return matches[0]


def run_validators(names):
    results = []
    for name in names:
        p = ROOT / 'scripts' / name
        if not p.is_file():
            continue
        run = subprocess.run([sys.executable, str(p)], cwd=ROOT, text=True, capture_output=True, timeout=90)
        results.append({'script': name, 'returncode': run.returncode,
                        'stdout_tail': run.stdout[-5000:], 'stderr_tail': run.stderr[-3000:]})
    return results


def render(article, resolved):
    tid = article['topic_id']
    number = {s['key']: str(i) for i, s in enumerate(article['source_selectors'], 1)}
    lines = ['---', 'topic_id: ' + tid, 'status: manuscript_pending_article_review',
             'publication_ready: false', 'authoring_batch: ' + BATCH, '---', '',
             '# ' + article['title'], '', article['lead'], '']
    claims = []
    examples = []
    for index, section in enumerate(article['sections'], 1):
        refs = section['sources']
        assert set(refs) <= set(resolved), tid + ': unknown citation key'
        if section['kind'] == 'research_finding':
            assert refs, tid + ': uncited research finding'
        citation = ''.join('[^' + number[k] + ']' for k in refs)
        lines += ['## ' + section['heading'], '', section['text'] + citation, '']
        if refs:
            claims.append({'id': tid + '-C' + f'{index:02d}', 'claim_id': tid + '-C' + f'{index:02d}',
                'text': section['text'], 'claim_type': section['kind'],
                'source_ids': [resolved[k]['id'] for k in refs],
                'support_assessment': 'existing_source_review_reused_article_check_pending',
                'causal_scope': 'limited_to_cited_study_design_not_general_life_effect',
                'formal_evidence_certainty': 'not_assessed', 'publication_ready': False})
        if section['kind'] in ('illustrative_scenario', 'editorial_application'):
            examples.append({'section': index, 'text': section['text'],
                'type': 'editorial_application_or_illustrative_scenario', 'observed_in_a_study': False})
    lines += ['## この記事の要点', '', article['takeaway'], '', '## 出典', '']
    for key, source in resolved.items():
        label = source['title'].replace('\n', ' ')
        lines += ['[^' + number[key] + ']: ' + (source.get('authors_display') or '') +
                  ' (' + str(source.get('year') or '年未確認') + '). ' + label +
                  '. [' + source['id'] + '](' + source['url'] + ')', '']
    source_ids = list(dict.fromkeys(s['id'] for s in resolved.values()))
    dossier = {'schema_version': '1.0', 'topic_id': tid, 'title': article['title'],
        'batch_id': BATCH, 'source_ids': source_ids, 'claims': claims, 'applications': examples,
        'publication_ready': False, 'review_method': 'new_manuscript_using_prior_source_reviews',
        'article_level_scientific_review': 'pending', 'independent_review_completed': False,
        'limits_ja': '出典の一意な照合は科学的主張の妥当性の自動認定ではありません。既存読解を再利用し、この処理で全文を新たに読んだとは記録しません。'}
    return ('\n'.join(lines) + '\n').encode('utf-8'), dossier


def integrate_catalog(products, baseline_progress):
    catalog_path = ROOT / 'data/articles/catalog.json'
    progress_path = ROOT / 'data/articles/progress.json'
    original = {catalog_path: catalog_path.read_bytes(), progress_path: progress_path.read_bytes()}
    created = []
    result = {'completed': False, 'reason': None, 'validation': []}
    try:
        catalog = json.loads(original[catalog_path])
        candidates = [(k, v) for k, v in catalog.items() if isinstance(v, list) and v and
                      all(isinstance(r, dict) and 'topic_id' in r for r in v)]
        assert len(candidates) == 1, 'Cannot identify one canonical article array'
        key, rows = candidates[0]
        by_id = {r['topic_id']: r for r in rows}
        assert len(by_id) == len(rows), 'Duplicate catalog topic IDs'
        samples = [r for r in rows if any(isinstance(v, str) and v.startswith('articles/') and
                   v.endswith('.md') and (ROOT/v).is_file() for v in r.values())]
        assert samples, 'No existing manuscript layout to reuse'
        path_keys = {k for r in samples for k, v in r.items() if isinstance(v, str) and
                     v.startswith('articles/') and v.endswith('.md')}
        claim_keys = {k for r in samples for k, v in r.items() if isinstance(v, str) and
                      v.startswith('data/articles/claims/') and v.endswith('.json')}
        assert len(path_keys) == 1 and len(claim_keys) == 1, 'Unrecognized catalog file fields'
        manuscript_key, claim_key = next(iter(path_keys)), next(iter(claim_keys))
        statuses = [r.get('status') for r in samples if isinstance(r.get('status'), str) and
                    'draft' in r['status'].lower() and 'approved' not in r['status'].lower() and
                    'checked' not in r['status'].lower()]
        draft_status = statuses[0] if statuses else 'manuscript_pending_review'
        added = 0
        for product in products:
            tid = product['topic_id']
            assert tid in by_id, 'Topic absent from canonical catalog: ' + tid
            row = by_id[tid]
            old_path = row.get(manuscript_key)
            if old_path and (ROOT / old_path).exists():
                if row.get('authoring_batch') == BATCH:
                    continue
                product['catalog_disposition'] = 'existing_manuscript_preserved_review_alternative_draft'
                continue
            manuscript = 'articles/manuscripts/' + tid + '.md'
            claim = 'data/articles/claims/' + tid + '.json'
            for relative, data in [(manuscript, product['_markdown']), (claim, encode(product['_dossier']))]:
                target = ROOT / relative
                assert not target.exists(), 'Refusing to overwrite existing output: ' + relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                created.append(target)
            row[manuscript_key] = manuscript
            row[claim_key] = claim
            row['status'] = draft_status
            row['authoring_batch'] = BATCH
            row['publication_ready'] = False
            row['manuscript_sha256'] = digest(product['_markdown'])
            row['claim_dossier_sha256'] = digest(encode(product['_dossier']))
            row['source_ids'] = product['source_ids']
            row['claim_count'] = product['claim_count']
            row['article_level_scientific_review'] = 'pending'
            if 'has_manuscript' in row: row['has_manuscript'] = True
            if 'has_claim_dossier' in row: row['has_claim_dossier'] = True
            if 'source_checked' in row: row['source_checked'] = False
            added += 1
            product['catalog_disposition'] = 'canonical_manuscript_and_claim_dossier_added'
        catalog['latest_authoring_batch'] = BATCH
        write('data/articles/catalog.json', catalog)
        progress = json.loads(original[progress_path])
        progress['manuscript_count'] = baseline_progress['manuscript_count'] + added
        progress['claim_dossier_count'] = baseline_progress['claim_dossier_count'] + added
        progress['claim_and_caution_count'] = baseline_progress.get('claim_and_caution_count', 0) + sum(
            p['claim_count'] for p in products if p.get('catalog_disposition') == 'canonical_manuscript_and_claim_dossier_added')
        progress['latest_authoring_batch'] = BATCH
        progress['goal_completed'] = False
        write('data/articles/progress.json', progress)
        validation = run_validators(['validate.py', 'validate_research.py', 'validate_round3.py',
                                     'validate_editorial_pass.py'])
        result['validation'] = validation
        assert all(r['returncode'] == 0 for r in validation), 'Existing validator rejected catalog integration'
        result.update(completed=True, canonical_manuscripts_added=added,
                      manuscript_count=progress['manuscript_count'], claim_dossier_count=progress['claim_dossier_count'])
    except Exception as exc:
        for p, data in original.items(): p.write_bytes(data)
        for p in created: p.unlink()
        for product in products:
            product['catalog_disposition'] = 'additive_draft_retained_catalog_integration_pending'
        result['reason'] = str(exc)
    return result


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    DRAFTS.mkdir(parents=True, exist_ok=True)
    inputs = sorted((ROOT/'research/continuation_20260911b').glob('articles_*.json'))
    articles = [a for p in inputs for a in json.loads(p.read_text(encoding='utf-8'))['articles']]
    assert articles and len({a['topic_id'] for a in articles}) == len(articles), 'Missing or duplicate article inputs'
    sources = read('data/sources.json')['sources']
    categories = read('data/categories.json')['categories']
    topics = {t['id']: t for c in categories for t in read(c['file'])['topics']}
    protected = {p: digest(p.read_bytes()) for p in [ROOT/'data/sources.json', ROOT/'data/categories.json']}
    protected.update({p: digest(p.read_bytes()) for p in (ROOT/'data/topics').glob('*.json')})
    baseline_path = DATA/'baseline_progress.json'
    if not baseline_path.exists(): baseline_path.write_bytes((ROOT/'data/articles/progress.json').read_bytes())
    baseline = json.loads(baseline_path.read_text())
    products = []
    for a in articles:
        tid = a['topic_id']; assert tid in topics
        assert a['publication_ready'] is False
        assert len(a['sections']) >= 4
        chars = len(a['lead']) + sum(len(s['text']) for s in a['sections']) + len(a['takeaway'])
        assert chars >= 900, tid + ': body is too short for this authored package'
        assert any(s['kind'] == 'research_finding' for s in a['sections']), tid
        assert any(s['kind'] == 'limitations' for s in a['sections']), tid
        assert any(s['kind'] == 'illustrative_scenario' for s in a['sections']), tid
        selectors = a['source_selectors']
        assert len({s['key'] for s in selectors}) == len(selectors), tid
        resolved = {s['key']: resolve(s, sources) for s in selectors}
        markdown, dossier = render(a, resolved)
        md_path = DRAFTS/(tid+'.md'); md_path.write_bytes(markdown)
        claim_path = DATA/'claims'/(tid+'.json'); claim_path.parent.mkdir(exist_ok=True); claim_path.write_bytes(encode(dossier))
        products.append({'topic_id': tid, 'title': a['title'], 'canonical_theme_title': topics[tid]['title_ja'],
            'draft_path': str(md_path.relative_to(ROOT)), 'claim_path': str(claim_path.relative_to(ROOT)),
            'body_characters': chars, 'source_ids': dossier['source_ids'], 'claim_count': len(dossier['claims']),
            'manuscript_sha256': digest(markdown), 'claim_sha256': digest(encode(dossier)),
            'publication_ready': False, 'review_status': a['review_status'],
            '_markdown': markdown, '_dossier': dossier})
    integration = integrate_catalog(products, baseline)
    for p, expected in protected.items(): assert digest(p.read_bytes()) == expected, 'Protected source changed: '+str(p)
    manifest = {'schema_version': '1.0', 'batch_id': BATCH, 'final_goal_articles': 300, 'goal_completed': False,
        'authored_manuscripts': len(products), 'claim_dossiers': len(products),
        'publication_ready_count': 0, 'body_characters': sum(p['body_characters'] for p in products),
        'structural_reference_validation': 'passed', 'canonical_integration': integration,
        'scientific_review': 'article_level_check_pending_prior_source_reviews_reused',
        'articles': [{k:v for k,v in p.items() if not k.startswith('_')} for p in products],
        'notes_ja': ['本文は個別に執筆した原稿です。テンプレートから研究結果を推測生成していません。',
                     '根拠表の主張は研究結果・概念の説明・限界を区別しています。応用例を実証された事例に数えません。',
                     '参照と構造の検証は、全文の独立点検や公開承認ではありません。']}
    write(str((DATA/'manifest.json').relative_to(ROOT)), manifest)
    lines = ['# 継続執筆：研究から生活への説明を加えた原稿', '',
        '最終目標は300記事。今回の原稿は公開前の記事単位の点検を残しています。', '',
        '本文：'+str(len(products))+'件。主張対応表：'+str(len(products))+'件。公開承認：0件。', '',
        '既存の出典台帳・テーマID・題名・順序は変更していません。', '',
        '正本カタログへの統合：'+('検証通過' if integration['completed'] else '保留。原稿と根拠表は下の別管理領域に保存。'), '',
        '| テーマ | 原稿 | 根拠表 |', '|---|---|---|']
    for p in products:
        lines.append('| '+p['title']+' | ['+p['topic_id']+'](../'+p['draft_path']+') | [主張・限界](../'+p['claim_path']+') |')
    lines += ['', '## 次の作業', '',
        '各主張を原典の該当箇所と比較し、数字・対象・比較条件・訂正の扱いを記事単位で点検します。既存の上位20テーマの改稿は保持し、未着手テーマへ同じ工程を続けます。', '',
        'カタログ統合が保留の場合は、manifest.jsonの検証結果を解消してから件数を統合します。下書きを完成記事数に加算しません。']
    (ROOT/'docs/CONTINUATION_20260911B.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k!='articles'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
