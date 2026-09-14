"""Compact category entrances and reader scope disclosures. No tracking or diagnosis."""
from __future__ import annotations
import html
import json
from pathlib import Path

def esc(value: str) -> str:
    return html.escape(str(value), quote=True)

class ReaderNavigation:
    def __init__(self, root: Path):
        self.categories=json.loads((root/'site/category_guides.json').read_text())['categories']
        items=json.loads((root/'site/reader_scope_notes.json').read_text())['notes']
        self.notes={x['topic_id']:x for x in items}
        if len(items)!=len(self.notes):
            raise ValueError('Duplicate reader scope notes')

    def validate(self, site):
        series={s['id']:s for s in site.FOUNDATIONS.series}
        for cid,entry in self.categories.items():
            if cid not in site.CATEGORIES or entry['guide_id'] not in series:
                raise ValueError('Unknown category guide')
            if len(entry['goals'])>3:
                raise ValueError('Category entrance exceeds three choices')
            for goal in entry['goals']:
                tid=goal['topic_id']
                if tid not in site.READERS or tid not in series[entry['guide_id']]['topic_ids'] or site.TOPICS[tid]['category_id']!=cid:
                    raise ValueError('Category goal must have a real, relevant article')
        for tid,note in self.notes.items():
            if tid not in site.EDITIONS or not set(note['source_ids'])<=set(site.EDITIONS[tid]['source_ids']):
                raise ValueError('Scope note must use the article sources')
            if len(note['outcome'])>50 or len(note['limit'])>80:
                raise ValueError('Scope note exceeds reader-facing text budget')

    def category(self, cid, current, site):
        entry=self.categories.get(cid)
        if not entry:
            return ''
        series=next(s for s in site.FOUNDATIONS.series if s['id']==entry['guide_id'])
        choices=''.join(f'<a href="{esc(site.reader_link(current,g["topic_id"]))}">{esc(g["label"])}</a>' for g in entry['goals'])
        guide=site.rel(current,f'learn/{series["id"]}/index.html')
        return f'<div class="category-entrance"><nav class="guide-goals" aria-label="気になることから"><span>気になることから</span>{choices}</nav><p><a href="{esc(guide)}">{esc(series["title"])}を順に読む →</a></p></div>'

    def scope(self, tid):
        note=self.notes.get(tid)
        if not note:
            return ''
        refs=' · '.join(f'<a href="#ref-{esc(s)}">{esc(s)}</a>' for s in note['source_ids'])
        # Evidence design is descriptive; it is not a quality/efficacy ranking.
        return f'<details class="study-scope"><summary>研究の対象と限界</summary><dl><div><dt>資料</dt><dd>{esc(note["design"])}</dd></div><div><dt>調べたこと</dt><dd>{esc(note["outcome"])}</dd></div><div><dt>読めないこと</dt><dd>{esc(note["limit"])}</dd></div></dl><p class="source-hint">出典：{refs}</p></details>'
