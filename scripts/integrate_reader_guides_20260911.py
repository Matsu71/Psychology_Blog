#!/usr/bin/env python3
"""Integrate two original reader guides, preserving earlier manuscripts.

This is editorial integration, not scientific approval. Every canonical change
is rolled back if an existing validator fails. Versioned drafts remain saved.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BATCH = 'research-literacy-20260911'


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def write(path, value):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    catalog = read('data/articles/catalog.json')
    rows = {row['topic_id']: row for row in catalog['articles']}
    sources = {row['id']: row for row in read('data/sources.json')['sources']}
    identities = [(row['topic_id'], row['title_ja']) for row in catalog['articles']]
    specifications = {
        'PSY-RES-001': [
            ('research_finding', '2013年のFacebook研究は若年成人の繰り返し測定を用いた観察研究である。', ['SRC012'], '当時のサービス・対象・追跡期間に限定。', 'SNSを減らせば全員の幸福が改善するという介入の結論にはしない。'),
            ('methodological_reasoning', '関連には順方向、逆方向、別要因という複数の説明が考えられる。', [], '本文の場面は説明用の仮定。', '特定の人にどの説明が当てはまるかを診断しない。'),
            ('methodological_reasoning', '単純な前後比較だけでは、介入以外の変化と切り分けにくい。', [], '比較の考え方の解説。', '個人が生活の工夫を試すこと自体が無意味とはしない。'),
            ('methodological_context', '研究設計と報告上の偏りも結論を読む際に考慮する。', ['SRC015'], '方法論的な論考を背景として使用。', '全心理学の誤りの割合を実測した資料として扱わない。'),
        ],
        'PSY-RES-003': [
            ('methodological_reasoning', '統計的な検出と生活上の有用性は別の評価である。', [], '費用・負担と便益を考える解説。', '有意なら必ず有用、小さい差なら必ず無意味、のどちらも主張しない。'),
            ('mathematical_example', '標準化効果量0.5は、そのまま得点が50％増える意味ではない。', [], '5点と標準偏差10点は架空の計算例。', '架空の値を特定の学習法の効果量として引用しない。'),
            ('mathematical_example', '相対的な割合と絶対的な人数の差は異なる量である。', [], '100人中2人と1人は説明用の仮定。', '実際の薬や治療の効果へ当てはめない。'),
            ('research_finding', '2018年の社会科学追試プロジェクトは効果の大きさも検討した。', ['SRC016'], '選ばれた雑誌・時期・実験群。', '全心理学の再現性を網羅した結果として使わない。'),
        ],
    }
    doi_expectations = {'SRC012': '10.1371/journal.pone.0069841',
                        'SRC015': '10.1371/journal.pmed.0020124',
                        'SRC016': '10.1038/s41562-018-0399-z'}
    for sid, doi in doi_expectations.items():
        if sources[sid].get('doi', '').lower() != doi:
            raise ValueError('Source identifier needs reconciliation: ' + sid)
    backup_paths = ['data/articles/catalog.json', 'data/articles/progress.json',
                    'docs/ARTICLE_PROGRESS.md', 'docs/NEXT_STEPS.md', 'README.md']
    backups = {p: (ROOT / p).read_bytes() if (ROOT / p).exists() else None for p in backup_paths}
    report = {'schema_version': '1.0', 'batch_id': BATCH, 'goal_articles': 300,
              'goal_completed': False, 'publication_ready_count': 0,
              'new_canonical_manuscripts': 0, 'retained_as_revisions': 0,
              'canonical_integrated': False, 'validation': [], 'products': []}
    for tid, definitions in specifications.items():
        row = rows[tid]
        manuscript = 'articles/manuscripts/' + BATCH + '/' + tid + '.md'
        body = (ROOT / manuscript).read_text(encoding='utf-8')
        if len(body) < 1400 or '## 出典' not in body:
            raise ValueError('Manuscript is absent or incomplete: ' + tid)
        claims = []
        for number, (kind, text, ids, scope, limits) in enumerate(definitions, 1):
            claims.append({'id': tid + '-C' + str(number).zfill(2),
                           'text': text, 'claim_ja': text, 'kind': kind,
                           'source_ids': ids, 'scope': scope, 'not_supported': limits,
                           'formal_evidence_certainty': 'not_assessed'})
        dossier = {'schema_version': '1.0', 'topic_id': tid, 'title_ja': row['title_ja'],
                   'publication_ready': False, 'claims': claims,
                   'source_ids': list(dict.fromkeys(sid for c in claims for sid in c['source_ids'])),
                   'unresolved_source_keys': [], 'independent_review_completed': False,
                   'review_basis': 'Previously registered reading notes and explicit methodological reasoning.',
                   'remaining_checks': ['Independent editorial review', 'Publication decision'],
                   'authoring_batch': BATCH}
        versioned = 'data/articles/revisions/' + BATCH + '/' + tid + '.json'
        write(versioned, dossier)
        if row.get('manuscript_path') and row['manuscript_path'] != manuscript:
            report['retained_as_revisions'] += 1
            report['products'].append({'topic_id': tid, 'manuscript_path': manuscript,
                                       'claim_dossier_path': versioned, 'canonical_replaced': False})
            continue
        canonical = 'data/articles/claims/' + tid + '.json'
        backups[canonical] = (ROOT / canonical).read_bytes() if (ROOT / canonical).exists() else None
        write(canonical, dossier)
        was_new = not row.get('manuscript_path')
        row.update(manuscript_path=manuscript, manuscript_sha256=hashlib.sha256(body.encode('utf-8')).hexdigest(),
                   claim_dossier_path=canonical, claim_count=len(claims),
                   state='manuscript_pending_article_review', publication_ready=False,
                   unresolved_source_keys=[], authoring_batch=BATCH)
        report['new_canonical_manuscripts'] += int(was_new)
        report['products'].append({'topic_id': tid, 'manuscript_path': manuscript,
                                   'claim_dossier_path': canonical, 'canonical_replaced': was_new})
    if identities != [(r['topic_id'], r['title_ja']) for r in catalog['articles']]:
        raise ValueError('Canonical identities or ordering changed.')
    write('data/articles/catalog.json', catalog)
    commands = [
        ['python3', 'scripts/reconcile_article_progress.py'],
        ['python3', 'scripts/validate.py'],
        ['python3', 'scripts/validate_research.py'],
        ['python3', 'scripts/validate_round3.py'],
        ['python3', 'scripts/validate_editorial_pass.py'],
        ['python3', 'scripts/validate_reviewed_delivery.py'],
        ['python3', 'scripts/reconcile_article_progress.py', '--check'],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=120)
        report['validation'].append({'command': command, 'returncode': result.returncode,
                                      'stdout': result.stdout[-12000:], 'stderr': result.stderr[-12000:]})
        if result.returncode:
            for path, payload in backups.items():
                target = ROOT / path
                if payload is None:
                    target.unlink(missing_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(payload)
            report['new_canonical_manuscripts'] = 0
            report['note_ja'] = '既存検証に失敗したため正本への変更を戻しました。原稿と根拠表は別の改稿案として保持しています。'
            break
    else:
        report['canonical_integrated'] = True
        report['article_progress'] = read('data/articles/progress.json')
    write('data/research/reader_guides_20260911_report.json', report)
    document = ['# 研究を読むための一般向け原稿', '',
                'この一覧は記事の公開承認を意味しません。', '',
                '正本への統合：' + str(report['canonical_integrated']), '']
    for p in report['products']:
        document += ['- ' + p['topic_id'] + ': [本文](../' + p['manuscript_path'] + ') / [根拠表](../' + p['claim_dossier_path'] + ')']
    document += ['', '次の作業：原稿と根拠表の独立した点検、既存稿がある場合の比較、公開判断。']
    (ROOT / 'docs/READER_GUIDES_20260911.md').write_text('\n'.join(document) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('canonical_integrated', 'new_canonical_manuscripts', 'retained_as_revisions')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
