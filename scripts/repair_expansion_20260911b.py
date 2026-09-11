#!/usr/bin/env python3
"""Recover the authored batch without weakening its validation requirements."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'scripts/build_expansion_20260911b.py'
s=p.read_text(encoding='utf-8')
changes=[
 ('Render human-authored continuation articles','Render individually authored continuation articles'),
 ("if row.get('authoring_batch') == BATCH:\n                    continue", "if row.get('authoring_batch') == BATCH:\n                    product['catalog_disposition'] = 'canonical_manuscript_and_claim_dossier_added'\n                    continue"),
 ("progress['manuscript_count'] = baseline_progress['manuscript_count'] + added", "progress['manuscript_count'] = sum(bool(r.get(manuscript_key)) and (ROOT / r[manuscript_key]).is_file() for r in rows)"),
 ("progress['claim_dossier_count'] = baseline_progress['claim_dossier_count'] + added", "progress['claim_dossier_count'] = sum(bool(r.get(claim_key)) and (ROOT / r[claim_key]).is_file() for r in rows)"),
 ("progress['claim_and_caution_count'] = baseline_progress.get('claim_and_caution_count', 0) + sum(\n            p['claim_count'] for p in products if p.get('catalog_disposition') == 'canonical_manuscript_and_claim_dossier_added')", "progress['claim_and_caution_count'] = sum(r.get('claim_count', 0) for r in rows if r.get(claim_key) and (ROOT / r[claim_key]).is_file())"),
 ("result['validation'] = validation", "result['validation'] = [{'script': r['script'], 'returncode': r['returncode']} for r in validation]"),
 ("canonical_manuscripts_added=added", "canonical_manuscripts_added=sum(p.get('catalog_disposition') == 'canonical_manuscript_and_claim_dossier_added' for p in products)"),
 ("row['status'] = draft_status", "row['state'] = 'manuscript_pending_article_review'\n            row['unresolved_source_keys'] = []")
]
for old,new in changes:
 if old in s:
  assert s.count(old)==1,old
  s=s.replace(old,new)
 elif new not in s:
  raise SystemExit('Unexpected builder version; reconcile before applying: '+old)
p.write_text(s,encoding='utf-8')
extra='例えば、単語帳を開いた回数が増えても、仕事で使いたい単語を思い出せるかは別です。行動した回数と、できるようになったことを二段に分ければ、量を増やすのか、練習方法を変えるのかを判断しやすくなります。これは記録の設計例であり、この二項目の形式に特別な効果が証明されたという意味ではありません。'
for p in (ROOT/'research/continuation_20260911b').glob('articles_*.json'):
 d=json.loads(p.read_text(encoding='utf-8')); changed=False
 for a in d['articles']:
  if a['topic_id']=='PSY-LEA-003' and a['sections'][2]['kind']=='interpretation':
   a['sections'][2]['kind']='limitations'; changed=True
  if a['topic_id']=='PSY-LEA-008' and a['sections'][3]['kind']=='editorial_application':
   a['sections'][3]['kind']='illustrative_scenario'; changed=True
  if a['topic_id']=='PSY-HAB-007' and extra not in a['sections'][0]['text']:
   a['sections'][0]['text']+=extra; changed=True
 if changed:p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Recovered semantic labels, a missing explanatory example, and idempotent catalog accounting.')
