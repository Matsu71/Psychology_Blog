"""Small, source-linked learning paths and glossary. No external dependencies."""
from __future__ import annotations
import html
import json
from pathlib import Path


def esc(value):
    return html.escape(str(value), quote=True)


class Foundations:
    def __init__(self, root: Path):
        self.data = json.loads((root / 'site/foundations.json').read_text())
        self.series = self.data['series']
        self.terms = self.data['terms']
        self.groups = self.data['groups']

    def keywords(self, tid):
        terms = [t for t in self.terms if tid in t['topic_ids']]
        return ' '.join(w for t in terms for w in [t['title'], t['reading'], *t['aliases']])

    def home_links(self, current, rel):
        return f'''<nav class="learning-entry" aria-label="読み始める"><a href="{esc(rel(current,'learn/index.html'))}"><strong>基礎から学ぶ</strong><span>4つの学習ガイド</span></a><a href="{esc(rel(current,'glossary/index.html'))}"><strong>用語を調べる</strong><span>研究を読むための24語</span></a></nav>'''

    def reader_links(self, tid, current, rel, title):
        terms = [t for t in self.terms if tid in t['topic_ids']]
        output = ''
        if terms:
            output += '<section class="reader-terms"><h2>この記事の用語</h2><ul>'
            for term in terms[:5]:
                url = rel(current, 'glossary/index.html')+'#'+term['id']
                output += f'<li><a href="{esc(url)}">{esc(term["title"])}</a></li>'
            output += '</ul></section>'
        for series in self.series:
            ids = series['topic_ids']
            if tid not in ids:
                continue
            n = ids.index(tid)
            url = rel(current, f'learn/{series["id"]}/index.html')
            output += f'<nav class="reading-path" aria-label="学習ガイド"><p><a href="{esc(url)}">{esc(series["title"])}</a><span>{n+1} / {len(ids)}</span></p><div>'
            if n:
                prev = ids[n-1]
                output += f'<a href="{esc(rel(current,"read/"+prev+"/index.html"))}"><small>前の解説</small>{esc(title(prev))}</a>'
            if n+1 < len(ids):
                nxt = ids[n+1]
                output += f'<a href="{esc(rel(current,"read/"+nxt+"/index.html"))}"><small>次の解説</small>{esc(title(nxt))}</a>'
            output += '</div></nav>'
        return output

    def search_help(self, current, rel):
        out = '<section id="glossary-hits" class="glossary-hits" hidden><h2>関連する用語</h2><ul>'
        for term in self.terms:
            words = ' '.join([term['title'],term['reading'],*term['aliases']])
            out += f'<li data-glossary-hit="{esc(words)}" hidden><a href="{esc(rel(current,"glossary/index.html")+"#"+term["id"])}">{esc(term["title"])}</a></li>'
        return out+'</ul></section>'

    def validate(self, site):
        for key in ['terms','series','groups']:
            ids = [x['id'] for x in self.data[key]]
            if len(ids)!=len(set(ids)):
                raise ValueError('Duplicate foundations IDs: '+key)
            import re
            if any(not re.fullmatch(r'[a-z0-9-]+',i) for i in ids):
                raise ValueError('Unsafe foundations identifier')
        for series in self.series:
            if not series['topic_ids'] or not set(series['topic_ids']) <= set(site.READERS):
                raise ValueError('Learning paths may link only to actual manuscripts')
        for term in self.terms:
            if not set(term['source_ids']) <= set(site.SOURCES):
                raise ValueError('Unknown glossary source: '+term['id'])
            if not set(term['topic_ids']) <= set(site.READERS):
                raise ValueError('Unknown glossary article: '+term['id'])
            if term['group'] not in {g['id'] for g in self.groups}:
                raise ValueError('Unknown glossary group')

    def build(self, site):
        self.validate(site)
        p='learn/index.html'
        body = site.breadcrumbs(p,[('基礎から学ぶ',None)])
        body += '<div class="page-heading"><h1>基礎から学ぶ</h1><p>知りたいことに合わせて、短い解説を順に読めます。</p></div><div class="learning-grid">'
        for series in self.series:
            url=site.rel(p,f'learn/{series["id"]}/index.html')
            mins=sum(site.minutes(t) for t in series['topic_ids'])
            body += f'<section class="learning-card"><span class="eyebrow">{len(series["topic_ids"])}本 · 合計約{mins}分</span><h2><a href="{esc(url)}">{esc(series["title"])}</a></h2><p>{esc(series["description"])}</p><a class="learning-start" href="{esc(url)}">読む順番を見る →</a></section>'
        body += f'</div><p class="guide-note">用語だけ確かめるときは、<a href="{esc(site.rel(p,"glossary/index.html"))}">研究用語集</a>へ。所要時間は文字数による目安です。</p>'
        site.write(p,site.shell(p,'基礎から学ぶ','研究、学習、習慣、判断を順に読む学習ガイド。',body))
        for series in self.series:
            p=f'learn/{series["id"]}/index.html'
            body=site.breadcrumbs(p,[('基礎から学ぶ','learn/index.html'),(series['title'],None)])
            body+=f'<div class="page-heading"><h1>{esc(series["title"])}</h1><p>{esc(series["description"])}</p></div><ol class="learning-steps">'
            for n,tid in enumerate(series['topic_ids'],1):
                body+=f'<li><span class="step-number" aria-hidden="true">{n:02d}</span><div><h2><a href="{esc(site.reader_link(p,tid))}">{esc(site.title(tid))}</a></h2><p>{esc(site.summary(tid))}</p><small>編集稿 · 約{site.minutes(tid)}分</small></div></li>'
            body+='</ol><p class="guide-note">上から順に読むほか、必要な解説だけ選んでも構いません。記事は編集・確認中です。</p>'
            site.write(p,site.shell(p,series['title'],series['description'],body))
        p='glossary/index.html'
        body=site.breadcrumbs(p,[('研究用語集',None)])
        body+='<div class="page-heading"><h1>研究用語集</h1><p>論文や解説に出てくる24語。意味から、例・原資料・記事へ進めます。</p></div>'
        body+='<form id="glossary-search" class="search-form" role="search"><label for="glossary-query">用語を検索</label><input id="glossary-query" type="search" name="q" placeholder="例：こうかりょう、追試、CI" maxlength="150"><button type="submit">検索</button></form><div id="glossary-tools" hidden><p id="glossary-count" role="status" aria-live="polite"></p><button type="button" id="glossary-clear">検索をクリア</button></div><noscript><p class="notice">全用語を表示しています。ブラウザのページ内検索も利用できます。</p></noscript>'
        body+='<nav class="index-links" aria-label="用語の分類">'+''.join(f'<a href="#group-{esc(g["id"])}" data-glossary-group-link="{esc(g["id"])}">{esc(g["name"])}</a>' for g in self.groups)+'</nav><p id="glossary-empty" class="notice" hidden>一致する用語はありません。短い言葉や別の表記で検索してください。</p>'
        for group in self.groups:
            body+=f'<section class="glossary-group" id="group-{esc(group["id"])}" data-glossary-group="{esc(group["id"])}"><h2>{esc(group["name"])}</h2><dl class="glossary-list">'
            for term in [t for t in self.terms if t['group']==group['id']]:
                words=' '.join([term['title'],term['reading'],*term['aliases']])
                body+=f'<div class="glossary-term" id="{esc(term["id"])}" data-term="{esc(words)}"><dt>{esc(term["title"])}</dt><dd><p>{esc(term["definition"])}</p><details><summary>例と注意点</summary><p>{esc(term["example"])}</p><p class="source-hint">出典：'+ ' · '.join(f'<a href="#glossary-ref-{esc(s)}">{esc(s)}</a>' for s in term['source_ids'])+f' · {esc(term["locator"])}</p></details><ul class="term-articles">'
                body+=''.join(f'<li><a href="{esc(site.reader_link(p,t))}">{esc(site.title(t))}</a></li>' for t in term['topic_ids'])+'</ul></dd></div>'
            body+='</dl></section>'
        body+='<section class="glossary-sources"><h2>参考文献</h2><p>指定箇所のAI支援点検に基づく編集稿です。専門家確認・公開承認は未完了です。</p><details><summary>出典一覧と確認範囲</summary><ul>'
        for sid in sorted({s for t in self.terms for s in t['source_ids']}):
            s=site.SOURCES[sid]
            locators=' / '.join(dict.fromkeys(t['locator'] for t in self.terms if sid in t['source_ids']))
            body+=f'<li id="glossary-ref-{esc(sid)}">{esc(sid)} · <a href="{esc(s["url"])}">{esc(s["title"])}</a><p>{esc(locators)}。全文の網羅的な点検ではありません。</p></li>'
        body+='</ul></details></section>'
        site.write(p,site.shell(p,'研究用語集','相関、効果量、メタ分析、追試など24語を例と出典で確認。',body))
