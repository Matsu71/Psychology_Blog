"""Render optional editorial comprehension questions using native HTML only."""
from __future__ import annotations
import html,json,re
from pathlib import Path

def inject_check(root: Path, tid: str, rendered: str, toc: list, edition: dict):
    data=json.loads((root/'site/learning_checks.json').read_text())
    items=[x for x in data['items'] if x['topic_id']==tid]
    if not items:
        return rendered,toc
    if len(items)!=1:
        raise ValueError('One comprehension question per article: '+tid)
    item=items[0]
    if item['publication_ready'] is not False or not set(item['source_ids'])<=set(edition['source_ids']):
        raise ValueError('Invalid learning-check provenance: '+tid)
    e=lambda value:html.escape(str(value),quote=True)
    refs=' · '.join(f'<a href="#ref-{e(s)}">{e(s)}</a>' for s in item['source_ids'])
    block=f'<section class="learning-check" aria-labelledby="learning-check"><h2 id="learning-check">1問で確認</h2><p>{e(item["question"])}</p><details><summary>答えを見る</summary><p>{e(item["answer"])}</p><p class="source-hint">根拠：{refs}</p></details><small>採点・診断ではなく、本文の理解を確かめるための問題です。</small></section>'
    match=re.search(r'<h2 id="[^"]+">参考文献</h2>',rendered)
    if match:
        rendered=rendered[:match.start()]+block+rendered[match.start():]
        pos=next((i for i,(_,label) in enumerate(toc) if label=='参考文献'),len(toc))
    else:
        rendered+=block;pos=len(toc)
    toc=list(toc);toc.insert(pos,('learning-check','1問で確認'))
    return rendered,toc
