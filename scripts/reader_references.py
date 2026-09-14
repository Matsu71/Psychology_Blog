"""Readable numbered references and truthful update records for generated pages.

This transforms the builder's own HTML, not arbitrary or untrusted HTML. Stable
source anchors and full bibliography are retained; no scientific review is inferred.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.parse import quote


def esc(value):
    return html.escape(str(value), quote=True)


class ReaderReferences:
    def __init__(self, root: Path):
        self.root = root
        self.labels = json.loads((root/'site/source_labels.json').read_text())['labels']
        doc = json.loads((root/'site/article_updates.json').read_text())
        entries = doc['entries']
        self.updates = {e['topic_id']: e for e in entries}
        if len(self.updates) != len(entries) or doc.get('schedule_is_automated') is not False:
            raise ValueError('Update records must be unique and not claim automatic review')

    def validate(self, site):
        for sid, label in self.labels.items():
            if sid not in site.SOURCES or not label.get('name') or len(label['name']) > 36 or len(label.get('topic','')) > 36:
                raise ValueError('Invalid reader-facing source label: '+sid)
        for tid, item in self.updates.items():
            if tid not in site.EDITIONS or item.get('publication_ready') is not False or item.get('independent_review') != 'pending':
                raise ValueError('Update does not establish publication approval: '+tid)
            if dt.date.fromisoformat(item['next_review_on']) <= dt.date.fromisoformat(item['updated_on']):
                raise ValueError('Review target must follow this recorded edit')
            if not item['changes'] or any(not isinstance(c,str) or len(c)>95 for c in item['changes']):
                raise ValueError('Update description must be concise and specific')
            current = self.root/site.EDITIONS[tid]['path']
            if hashlib.sha256(current.read_bytes()).hexdigest() != item['reader_sha256']:
                raise ValueError('Update record is stale for reader edition: '+tid)
            if not set(item['source_ids']) <= set(site.EDITIONS[tid]['source_ids']):
                raise ValueError('Update sources differ from actual edition: '+tid)
            checked = (self.root/item['source_checks_path']).resolve()
            if not checked.is_relative_to(self.root) or not checked.is_file():
                raise ValueError('Missing check record: '+tid)
            old = item.get('previous_reader_or_manuscript_path')
            if old:
                previous = (self.root/old).resolve()
                if not previous.is_relative_to(self.root) or not previous.is_file():
                    raise ValueError('Missing archived previous edition')
                if hashlib.sha256(previous.read_bytes()).hexdigest() != item['previous_sha256']:
                    raise ValueError('Previous edition changed unexpectedly: '+tid)
            elif item.get('previous_sha256') is not None:
                raise ValueError('No previous edition must have no invented hash')

    def history(self, tid: str) -> str:
        item = self.updates.get(tid)
        if not item:
            return ''
        changes = ''.join('<li>'+esc(c)+'</li>' for c in item['changes'])
        checked = quote(item['source_checks_path'],safe='/')
        return (f'<details class="update-history"><summary>更新履歴</summary>'
                f'<p><time datetime="{esc(item["updated_on"])}">{esc(item["updated_on"])}</time>'
                f' · {esc(item["review_kind"])}</p><ul>{changes}</ul>'
                f'<p><a href="https://github.com/Matsu71/Psychology_Blog/blob/main/{checked}">確認した資料と範囲</a></p>'
                f'<p class="review-target">次回点検の目安：<time datetime="{esc(item["next_review_on"])}">{esc(item["next_review_on"])}</time>'
                '。編集計画上の日付です。自動点検や専門家確認の予約ではありません。</p></details>')

    def label(self, sid: str, sources: dict) -> str:
        if sid in self.labels:
            return self.labels[sid]['name']
        s = sources[sid]
        # Keep the stored first author/organization literally. Do not guess which
        # token is a surname; source metadata uses several name conventions.
        authors = s.get('authors_display', '').strip()
        first = authors.split(';')[0].strip()
        if len(first)>48 or not first:
            first='文献'
        suffix='ほか' if ';' in authors else ''
        return first+suffix+(f'（{s["year"]}）' if s.get('year') is not None else '')

    def enhance(self, body: str, sources: dict) -> str:
        pattern = re.compile(r'<p class="reference-item" id="ref-(SRC\d+)">(.*?)</p>',re.S)
        records = list(pattern.finditer(body))
        sids = [m.group(1) for m in records]
        if len(sids) != len(set(sids)) or any(s not in sources for s in sids):
            raise ValueError('References must have unique registered source anchors')
        number = {sid:n+1 for n,sid in enumerate(sids)}
        original = {m.group(1):m.group(2) for m in records}
        # Protect bibliography paragraphs while assigning citation IDs.
        body = pattern.sub(lambda m:'<!--reader-reference:'+m.group(1)+'-->', body)
        # Some legacy Markdown links use an external URL with only an internal
        # source ID as their label. Route those through the corresponding local
        # bibliography entry; the original bibliography URL is kept below.
        def old_citation(m):
            sid=m.group(2)
            return '<a href="#ref-'+sid+'">['+sid+']</a>' if sid in number else m.group(0)
        body=re.sub(r'<a href="(https?://[^"]+)">\[?(SRC\d+)\]?</a>',old_citation,body)
        anchors = {sid:[] for sid in sids}
        prose_start=body.find('<div class="prose">')
        prose_end=body.find('<details class="review-panel">',prose_start)
        prose_refs={sid:[] for sid in sids}
        def citation(m):
            sid, text=m.group(1),m.group(2)
            if sid not in number:
                raise ValueError('Citation has no bibliography entry: '+sid)
            n=number[sid];ident=f'cite-{sid}-{len(anchors[sid])+1}'
            anchors[sid].append(ident)
            if prose_start<=m.start()<prose_end:
                prose_refs[sid].append(ident)
            plain=html.unescape(re.sub(r'<[^>]+>','',text)).strip()
            # A bare source in a hint becomes a short name; a bracketed inline
            # source becomes a normal numeric citation. Descriptive labels stay.
            visible=f'[{n}]' if plain==f'[{sid}]' else (f'{n}. {self.label(sid,sources)}' if plain==sid else plain)
            return f'<a class="citation-link" id="{ident}" href="#ref-{sid}" aria-label="参考文献{n}：{esc(self.label(sid,sources))}">{esc(visible)}</a>'
        body=re.sub(r'<a href="#ref-(SRC\d+)">(.*?)</a>',citation,body,flags=re.S)
        # Shorten source IDs in the folded scope prose too. Only text nodes are
        # changed: IDs, anchor URLs, original source records, and protected full
        # bibliography remain intact.
        def plain_source(m):
            sid=m.group(0)
            return esc(self.label(sid,sources)) if sid in sources else sid
        body=''.join(part if part.startswith('<') else re.sub(r'(?<![A-Za-z0-9])SRC\d+(?!\d)',plain_source,part) for part in re.split(r'(<[^>]+>)',body))
        for sid in sids:
            n=number[sid]
            # The original leading ID is metadata, not the bibliography itself.
            full=re.sub(r'^<a href="#ref-'+sid+r'">\['+sid+r'\]</a>\s*','',original[sid],count=1)
            # Preserve all original bibliography words/URLs except a technical
            # source-ID-only link label, which becomes an ordinary link label.
            full=re.sub(r'(<a href="[^"]+">)\[?SRC\d+\]?(</a>)',r'\1資料を開く\2',full)
            short=self.label(sid,sources)
            topic=self.labels.get(sid,{}).get('topic')
            topic_html=f'<p class="reference-topic">{esc(topic)}</p>' if topic else ''
            initial=(prose_refs[sid] or anchors[sid])
            back=(f'<a class="reference-return" href="#{initial[0]}">引用箇所へ戻る</a>' if initial else '')
            item=(f'<div class="reference-item" id="ref-{sid}" tabindex="-1" data-reference-number="{n}">'
                  f'<div class="reference-heading"><span class="reference-number">{n}.</span>'
                  f'<span>{esc(short)}</span><a class="reference-primary" href="{esc(sources[sid]["url"])}" aria-label="参考文献{n}の原資料を開く">原資料</a></div>'
                  f'{topic_html}<details class="reference-bibliography"><summary>書誌情報</summary><p>{full}</p></details>{back}</div>')
            body=body.replace('<!--reader-reference:'+sid+'-->', item,1)
        return body
