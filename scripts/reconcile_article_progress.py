#!/usr/bin/env python3
"""Derive progress from canonical files. --check is read-only; no approval changes."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))

def local_file(path):
    p=(ROOT/path).resolve()
    if not p.is_relative_to(ROOT) or not p.is_file():
        raise ValueError('Missing or unsafe repository file: '+path)
    return p

def products():
    rows=read('data/articles/catalog.json')['articles']
    categories=read('data/categories.json')['categories']
    topics=[t for c in categories for t in read(c['file'])['topics']]
    if [t['id'] for t in topics] != [r['topic_id'] for r in rows]:
        raise ValueError('Article catalog must preserve all canonical topic IDs and order')
    sources={s['id'] for s in read('data/sources.json')['sources']}
    manuscripts,dossiers,checked,unresolved=[],[],[],[]
    claims=0
    for r in rows:
        tid=r['topic_id']
        if r.get('manuscript_path'):
            f=local_file(r['manuscript_path'])
            if hashlib.sha256(f.read_bytes()).hexdigest()!=r['manuscript_sha256']:
                raise ValueError('Manuscript hash mismatch: '+tid)
            manuscripts.append(tid)
        if r.get('claim_dossier_path'):
            d=json.loads(local_file(r['claim_dossier_path']).read_text(encoding='utf-8'))
            if d['topic_id']!=tid or len(d['claims'])!=r['claim_count']:
                raise ValueError('Claim count or topic mismatch: '+tid)
            for c in d['claims']:
                if not set(c.get('source_ids',[]))<=sources:
                    raise ValueError('Unknown claim source: '+tid)
            dossiers.append(tid);claims+=len(d['claims'])
            if d.get('unresolved_source_keys') or r.get('unresolved_source_keys'):unresolved.append(tid)
        if r.get('state')=='source_checked_manuscript':checked.append(tid)
    p=read('data/articles/progress.json');top=p['top20_topic_ids']
    ready=sum(r.get('publication_ready') is True for r in rows)
    p.update(theme_count=len(topics),manuscript_count=len(manuscripts),claim_dossier_count=len(dossiers),
        claim_and_caution_count=claims,publication_ready_count=ready,goal_completed=ready==p['goal_articles'],
        top20_dossiers_present=len(set(top)&set(dossiers)),missing_top20_topic_ids=[t for t in top if t not in dossiers],
        dossiers_with_unresolved_sources=unresolved,source_checked_manuscript_count=len(checked),
        source_checked_manuscript_ids=checked,top20_source_checked_count=len(set(top)&set(checked)))
    count=f'本文{len(manuscripts)}件、主張対応表{len(dossiers)}件。'
    boundary='原稿の存在、限定した主張の照合、独立した点検、公開承認は別の状態です。構造検証は科学的正しさを自動認定しません。'
    lines=['# 記事制作の現在地','',f"目標{p['goal_articles']}記事。"+count,'',
        f'限定した原文照合の記録がある原稿：{len(checked)}件。公開承認済み：{ready}件。','',boundary,'',
        '| テーマ | 本文 | 状態 |','|---|---|---|']
    for r in rows:
        link='[原稿](../'+r['manuscript_path']+')' if r.get('manuscript_path') else '未着手'
        lines.append(f"| {r['topic_id']} {r['title_ja']} | {link} | {r['state']} |")
    if (ROOT/'data/articles/audit_status.json').is_file():
        lines+=['','## 既存監査の記録','','| ID | 状態 |','|---|---|']
        lines += [f"| {a['audit_id']} | {a['status']} |" for a in read('data/articles/audit_status.json')['items']]
    extras=sorted((ROOT/'docs').glob('CONTINUATION_*.md'))
    if extras:
        lines+=['','## 追加原稿・別の改稿案','','同じテーマの改稿案は別記事として数えません。','']
        lines += [f'- [{x.stem}]({x.name})' for x in extras]
    missing=sum(not t['source_ids'] for t in topics)
    nxt=['# 次の作業','',f"最終目標：根拠をたどれる一般向け{p['goal_articles']}記事。",'',
        f'出典{len(sources)}件、出典未登録{missing}テーマ。'+count,'',
        f'本文未作成は{len(topics)-len(manuscripts)}テーマ。公開承認済みは{ready}件。','',
        '## 実行順','',
        '1. main上の原稿・根拠表・カタログ・ハッシュと、この件数を照合する。未反映を回収し、既存原稿を黙って上書きしない。',
        '2. 原稿に残る具体的な主張を原文・近年の統合研究・反証・訂正で確認する。調べた範囲と未確認を分ける。',
        '3. 読みやすさ、対象・期間の一般化、生活例と検証済み手順の区別を記事単位で点検する。',
        '4. 医療的な記事では安全性と国内への適用を確認する。非臨床記事も公開判断を記録し、原稿数と承認数を分離する。',
        '5. 未着手テーマにも同じ工程を続ける。研究結果を題名から推測した量産はしない。','',
        '## 継続する比較','',
        '学習スタイル、マーカー学習、混合練習、歩行と創造性、成長マインドセットについて、古典的な説明と新しい研究を比較する。','',
        '## 更新コマンド','','```bash','python scripts/build_research_views.py','python scripts/reconcile_article_progress.py',
        'python scripts/reconcile_article_progress.py --check','```','',boundary,'','会話終了後の自動執筆や定期公開は設定していません。']
    readme=['# Psychology Blog — 人間の科学・記事制作データベース','',
        '**最終目標：一般向けに面白く、科学的根拠をたどれる300記事。**','',
        f'{len(categories)}分野・{len(topics)}テーマ。出典{len(sources)}件。出典未登録{missing}テーマ。','',
        count+f' 限定した原文照合記録あり{len(checked)}件。公開承認済み{ready}件。','',
        '- [記事の現在地](docs/ARTICLE_PROGRESS.md)','- [次の作業](docs/NEXT_STEPS.md)',
        '- [原文照合と注意点](docs/SOURCE_CHECKS.md)','- [順位](docs/RANKINGS.md) / [データ設計](docs/DATABASE_ARCHITECTURE.md)','',
        boundary,'',
        'テーマはdata/topics、書誌はdata/sources.json、記事の参照先はdata/articles/catalog.jsonが正本です。題名・ID・テーマの順序を維持し、改稿案を独立記事として水増ししません。','',
        '```bash','python scripts/build_research_views.py','python scripts/reconcile_article_progress.py','python scripts/validate.py',
        'python scripts/validate_research.py','python scripts/validate_round3.py','python scripts/validate_editorial_pass.py',
        'python scripts/reconcile_article_progress.py --check','```','',
        '全文・抄録の原文は公開データに転載しません。想定例と実際の研究場面を分けます。定期執筆・自動サイト公開は設定していません。']
    if extras:
        readme+=['','## 追加原稿・改稿案','']+[f'- [{x.stem}](docs/{x.name})' for x in extras]
    out={'data/articles/progress.json':json.dumps(p,ensure_ascii=False,indent=2)+'\n',
         'docs/ARTICLE_PROGRESS.md':'\n'.join(lines)+'\n','docs/NEXT_STEPS.md':'\n'.join(nxt)+'\n','README.md':'\n'.join(readme)+'\n'}
    return out,p

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    output,p=products()
    stale=[path for path,body in output.items() if not (ROOT/path).is_file() or (ROOT/path).read_text(encoding='utf-8')!=body]
    if args.check and stale:raise SystemExit('Stale progress views: '+', '.join(stale))
    if not args.check:
        for path,body in output.items():(ROOT/path).write_text(body,encoding='utf-8')
    print(json.dumps({'status':'passed','manuscripts':p['manuscript_count'],'claims':p['claim_and_caution_count'],'publication_ready':p['publication_ready_count']},ensure_ascii=False))

if __name__=='__main__':main()
