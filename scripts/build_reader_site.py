#!/usr/bin/env python3
"""Build a dependency-free static reader site without changing research originals.

Python 3.9+. The site is an explicitly labelled editorial preview. Publication
approval is never inferred from source counts, generated pages, or a passing test.
"""
from __future__ import annotations
import csv
import io
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
from urllib.parse import urlparse, quote

ROOT = Path(__file__).resolve().parents[1]
GENERATED: list[str] = []

def load(path: str):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))

def esc(value) -> str:
    return html.escape(str(value), quote=True)

def write(path: str, text: str):
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')
    GENERATED.append(path)

def rel(current: str, target: str) -> str:
    """Explicit index.html also works in a downloaded preview opened locally."""
    return os.path.relpath(target, str(Path(current).parent)).replace(os.sep, '/')

CONFIG = load('site/editorial.json')
CATEGORIES = {x['id']: x for x in load('data/categories.json')['categories']}
GROUPS = {x['id']: x for x in CONFIG['groups']}
GROUP_OF = {category: group['id'] for group in CONFIG['groups'] for category in group['categories']}
SOURCES = {x['id']: x for x in load('data/sources.json')['sources']}
TOPICS = {}
for category in CATEGORIES.values():
    for record in load(category['file'])['topics']:
        TOPICS[record['id']] = dict(record, category_id=category['id'])
CATALOG = {x['topic_id']: x for x in load('data/articles/catalog.json')['articles']}
EDITIONS_PATH = ROOT / 'site/reader_editions.json'
EDITIONS = {x['topic_id']: x for x in load('site/reader_editions.json')['editions']} if EDITIONS_PATH.exists() else {}
HEADINGS = load('site/heading_labels.json').get('labels', {}) if (ROOT / 'site/heading_labels.json').exists() else {}
READERS = {}
for tid, topic in TOPICS.items():
    entry = EDITIONS.get(tid, CATALOG.get(tid, {}))
    manuscript = entry.get('path') or entry.get('manuscript_path')
    if manuscript:
        file = (ROOT / manuscript).resolve()
        if not file.is_relative_to((ROOT / 'articles').resolve()):
            raise ValueError(f'Unsafe manuscript path: {manuscript}')
        if not file.exists():
            raise ValueError(f'Missing manuscript: {manuscript}')
        READERS[tid] = dict(entry, path=manuscript, text=file.read_text(encoding='utf-8'))

SEARCH_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/></svg>'

def title(tid: str) -> str:
    return CONFIG['display_titles'][tid]

def category_label(cid: str) -> str:
    return CONFIG['category_labels'][cid]

def summary(tid: str) -> str:
    if tid in EDITIONS:
        return EDITIONS[tid]['summary']
    if tid in CONFIG.get('descriptions', {}):
        return CONFIG['descriptions'][tid]
    # Pending topics are not presented as researched conclusions.
    original = TOPICS[tid].get('angle_ja', '').strip()
    if len(original) > 72:
        parts = re.split(r'[。；]', original)
        short = parts[0]
        if len(short) <= 72:
            return short + ('。' if not short.endswith(('？','?','。')) else '')
        return '研究で分かっていることと、その限界を整理します。'
    return original

def minutes(tid: str) -> int:
    plain = re.sub(r'https?://\S+|\[[^\]]+\]|[#*`>]', '', READERS[tid]['text'])
    return max(1, math.ceil(len(plain) / 550))

def reader_link(current: str, tid: str) -> str:
    return rel(current, f'read/{tid}/index.html')

def breadcrumbs(current: str, items: list[tuple[str,str | None]]) -> str:
    nodes = []
    for label, target in [('ホーム','index.html')] + items:
        content = f'<a href="{esc(rel(current,target))}">{esc(label)}</a>' if target else esc(label)
        nodes.append(f'<li>{content}</li>')
    return '<nav aria-label="現在地"><ol class="breadcrumbs">' + ''.join(nodes) + '</ol></nav>'

def shell(current: str, page_title: str, description: str, body: str, active: str = '', main_class: str = '', noindex: bool = True) -> str:
    nav = ''.join(f'<a href="{esc(rel(current,"topics/"+g["id"]+"/index.html"))}"'+(' aria-current="page"' if g['id']==active else '')+f'>{esc(g["name"])}</a>' for g in CONFIG['groups'])
    site = CONFIG['site_name']
    full_title = f'{page_title} | {site}' if page_title != site else site
    canonical = CONFIG['canonical_base'] + ('' if current == 'index.html' else current.removesuffix('index.html'))
    return f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(full_title)}</title><meta name="description" content="{esc(description)}"><meta name="robots" content="{'noindex,follow' if noindex else 'index,follow'}"><meta name="theme-color" content="#245c54"><link rel="canonical" href="{esc(canonical)}"><link rel="stylesheet" href="{esc(rel(current,'assets/site.css'))}"><script src="{esc(rel(current,'assets/app.js'))}" defer></script></head>
<body><a href="#main" class="skip">本文へ移動</a>
<div class="preview-strip"><div class="wrap"><span>制作プレビュー<span class="preview-detail"> · 記事は編集・確認中です</span></span><a href="{esc(rel(current,'about/index.html'))}">編集方針</a></div></div>
<header class="masthead"><div class="wrap header-row"><a class="brand" href="{esc(rel(current,'index.html'))}"><span class="brand-mark" aria-hidden="true">ψ</span>{esc(site)}</a><form class="header-search" role="search" aria-label="サイト内検索" method="get" action="{esc(rel(current,'search/index.html'))}"><label class="sr-only" for="header-query">キーワード</label><input id="header-query" name="q" type="search" placeholder="気になるテーマを検索" maxlength="150"><button type="submit" aria-label="検索ページへ">{SEARCH_ICON}</button></form></div><nav class="topic-nav" aria-label="テーマ別"><div class="wrap nav-row">{nav}</div></nav></header>
<main id="main" class="{esc(main_class)}" tabindex="-1"><div class="wrap">{body}</div></main>
<footer class="footer"><div class="wrap"><div class="footer-top"><span class="footer-brand">{esc(site)}</span><nav class="footer-links" aria-label="フッター"><a href="{esc(rel(current,'topics/index.html'))}">テーマ一覧</a><a href="{esc(rel(current,'search/index.html'))}">検索</a><a href="{esc(rel(current,'about/index.html'))}">このサイトについて</a></nav></div><div class="footer-bottom"><p>一般向けの心理学・行動科学の情報を扱います。個別の診断・治療に代わるものではありません。AI支援による制作。独立した専門家確認と公開承認は未完了です。</p></div></div></footer></body></html>'''

def card(current: str, tid: str) -> str:
    cat = category_label(TOPICS[tid]['category_id'])
    return f'<article class="article-card"><span class="eyebrow">{esc(cat)}</span><h3><a href="{esc(reader_link(current,tid))}">{esc(title(tid))}</a></h3><p>{esc(summary(tid))}</p><div class="card-foot"><span>約{minutes(tid)}分</span><span class="draft-label">編集稿</span></div></article>'

def group_card(current: str, gid: str) -> str:
    g = GROUPS[gid]
    labels = ' / '.join(category_label(c) for c in g['categories'])
    return f'<div class="group-card"><h3><a href="{esc(rel(current,"topics/"+gid+"/index.html"))}">{esc(g["name"])}</a></h3><p>{esc(labels)}</p></div>'

def rows(current: str, tids: list[str]) -> str:
    output = []
    for tid in tids:
        if tid in READERS:
            line = f'<a href="{esc(reader_link(current,tid))}">{esc(title(tid))}</a><small>編集稿 · 約{minutes(tid)}分</small>'
        else:
            line = f'<span class="pending-title">{esc(title(tid))}</span><small>準備中</small>'
        output.append(f'<li class="topic-row" data-topic-id="{esc(tid)}">{line}</li>')
    return '<ul class="topic-list">' + ''.join(output) + '</ul>'

def topic_ids(cid: str) -> list[str]:
    return [tid for tid,t in TOPICS.items() if t['category_id']==cid]

def flow() -> str:
    return '''<figure class="mini-flow"><div class="flow-track"><div class="flow-step"><b>気が重い</b><span>課題に向き合う</span></div><span class="flow-arrow" aria-hidden="true">→</span><div class="flow-step"><b>後回し</b><span>いったん避ける</span></div><span class="flow-arrow" aria-hidden="true">→</span><div class="flow-step"><b>一時的に楽</b><span>負担は後に残る</span></div></div><figcaption>短期的な気分の調整という説明モデルの概念図。全員に当てはまる原因ではありません。</figcaption></figure>'''

def build_home():
    p='index.html'; lead='PSY-MOT-001'
    chosen=[tid for tid in CONFIG['featured'] if tid in READERS and tid!=lead][:4]
    picks=''.join(f'<article class="pick"><span class="eyebrow">{esc(category_label(TOPICS[t]["category_id"]))}</span><h3><a href="{esc(reader_link(p,t))}">{esc(title(t))}</a></h3><p>{esc(summary(t))}</p></article>' for t in chosen)
    selections=['PSY-GEN-002','PSY-ATT-004','PSY-REL-002','PSY-RES-005','PSY-PER-002','PSY-CRE-001']
    selections=[t for t in selections if t in READERS]
    body=f'''<div class="home-intro"><h1>心理学を読む</h1><span>睡眠、習慣、人間関係。気になるテーマから。</span></div>
<div class="feature-grid"><article class="feature"><span class="eyebrow">習慣・行動</span><h2 class="feature-title"><a href="{esc(reader_link(p,lead))}">{esc(title(lead))}</a></h2><p class="feature-summary">{esc(summary(lead))}</p>{flow()}<div class="feature-foot"><a href="{esc(reader_link(p,lead))}">解説を読む →</a><span class="draft-label">編集稿</span></div></article><section class="picks" aria-labelledby="picks-heading"><h2 id="picks-heading">まず読む</h2>{picks}</section></div>
<section class="section"><div class="section-heading"><h2>テーマから探す</h2><a href="{esc(rel(p,'topics/index.html'))}">すべてのテーマ →</a></div><div class="group-grid">{''.join(group_card(p,g) for g in GROUPS)}</div></section>
<section class="section"><div class="section-heading"><h2>日常の疑問</h2><a href="{esc(rel(p,'search/index.html'))}?status=draft">解説一覧 →</a></div><div class="article-grid">{''.join(card(p,t) for t in selections)}</div></section>
<section class="section editor-note"><h2>根拠と限界を読む</h2><div><p>結論だけでなく、研究の対象と、まだ分からないことを載せます。本文の出典から元の論文や公的資料へ進めます。</p><a href="{esc(rel(p,'about/index.html'))}">編集方針を見る →</a></div></section>'''
    write(p,shell(p,CONFIG['site_name'],'心理学・行動科学のテーマを、睡眠、習慣、学習、人間関係などから探す情報サイト。',body))

def build_topics():
    p='topics/index.html'
    body=breadcrumbs(p,[('テーマ一覧',None)])+f'<div class="page-heading"><h1>テーマ一覧</h1><p>{len(CATEGORIES)}分野・{len(TOPICS)}テーマ。編集稿のあるテーマと、準備中のテーマを分けて表示しています。</p></div>'
    for gid,g in GROUPS.items():
        body+=f'<section class="section"><div class="section-heading"><h2>{esc(g["name"])}</h2><a href="{esc(rel(p,"topics/"+gid+"/index.html"))}">この分野を見る →</a></div><div class="group-grid">'
        for cid in g['categories']:
            ids=topic_ids(cid); ready=sum(t in READERS for t in ids)
            body+=f'<div class="group-card"><h3><a href="{esc(rel(p,"topics/category/"+cid+"/index.html"))}">{esc(category_label(cid))}</a></h3><p>{len(ids)}テーマ · 編集稿{ready}本</p></div>'
        body+='</div></section>'
    write(p,shell(p,'テーマ一覧','28分野の心理学・行動科学のテーマ索引。',body))
    for gid,g in GROUPS.items():
        p=f'topics/{gid}/index.html'
        body=breadcrumbs(p,[('テーマ一覧','topics/index.html'),(g['name'],None)])
        body+=f'<div class="page-heading"><h1>{esc(g["name"])}</h1><p>短い解説から入り、参考文献までたどれます。準備中のテーマには、まだ本文がありません。</p></div><nav class="index-links" aria-label="この分野の分類">'
        body+=''.join(f'<a href="#category-{esc(cid)}">{esc(category_label(cid))}</a>' for cid in g['categories'])+'</nav>'
        for cid in g['categories']:
            body+=f'<section class="category-block" id="category-{esc(cid)}"><h2><a href="{esc(rel(p,"topics/category/"+cid+"/index.html"))}">{esc(category_label(cid))}</a><span class="count">{len(topic_ids(cid))}テーマ</span></h2>{rows(p,topic_ids(cid))}</section>'
        write(p,shell(p,g['name'],f'{g["name"]}の心理学・行動科学のテーマ一覧。',body,active=gid))
    for cid,category in CATEGORIES.items():
        p=f'topics/category/{cid}/index.html'; gid=GROUP_OF[cid]
        body=breadcrumbs(p,[('テーマ一覧','topics/index.html'),(GROUPS[gid]['name'],f'topics/{gid}/index.html'),(category_label(cid),None)])
        body+=f'<div class="page-heading"><h1>{esc(category_label(cid))}</h1><p>{esc(category["scope_ja"])}</p></div>{rows(p,topic_ids(cid))}'
        write(p,shell(p,category_label(cid),f'{category_label(cid)}のテーマと参考文献付き解説。',body,active=gid))

def safe_link(url: str, current: str, origin: str) -> str | None:
    parsed=urlparse(html.unescape(url))
    if parsed.scheme in ('https','http') and parsed.netloc:
        return url
    if parsed.scheme or parsed.netloc:
        return None
    if url.startswith('#'):
        return url
    target=(ROOT/Path(origin).parent/parsed.path).resolve()
    if not target.is_relative_to(ROOT):
        return None
    matched=re.search(r'(PSY-[A-Z]+-\d+)\.md$',target.name)
    if matched and matched.group(1) in READERS:
        return reader_link(current,matched.group(1))
    path=target.relative_to(ROOT).as_posix()
    return 'https://github.com/Matsu71/Psychology_Blog/blob/main/'+quote(path,safe='/')+('#'+parsed.fragment if parsed.fragment else '')

def normalized_manuscript(text: str) -> str:
    """Normalize the citation styles actually used by legacy manuscripts.

    Front matter and internal workflow links are not reader content. References
    stay visible and clickable; unresolved aliases abort the build rather than
    silently dropping evidence. No scientific claim is inferred from metadata.
    """
    text = re.sub(r'\A---\s*\n.*?\n---\s*\n', '', text, count=1, flags=re.S)
    text = re.split(r'\n---\n\s*(?:確認日|編集|作成|調査)', text, maxsplit=1)[0]
    aliases = {}
    definitions = {}
    for match in re.finditer(r'^\[(\^?[^\]\n]+)\](?::\s*|\s+)(.+)$', text, re.M):
        key, value = match.group(1), match.group(2)
        sid = key.removeprefix('^') if re.fullmatch(r'\^?SRC\d+', key) else None
        if sid is None:
            explicit = re.findall(r'\[(SRC\d+)\]\(', value)
            if len(set(explicit)) == 1:
                sid = explicit[0]
        if sid is None:
            urls = re.findall(r'https?://[^\s)\]。]+', value)
            for candidate in SOURCES.values():
                if candidate.get('doi') and candidate['doi'].lower() in value.lower():
                    sid = candidate['id']; break
                for field in ('url', 'verified_via_url'):
                    u = candidate.get(field, '').rstrip('/')
                    if u and any(x.rstrip('/.,') == u for x in urls):
                        sid = candidate['id']; break
                if sid: break
        if sid is None:
            raise ValueError('Unresolved manuscript reference alias: '+key+' '+value[:90])
        aliases[key] = sid
        definitions[match.group(0)] = '['+sid+'] '+value
    for original, replacement in definitions.items():
        text = text.replace(original, replacement)
    for key, sid in sorted(aliases.items(), key=lambda x: -len(x[0])):
        text = re.sub(r'\['+re.escape(key)+r'\](?!\()', '['+sid+']', text)
    text = re.sub(r'^> (?:原稿です。|改稿案です。).*\n?', '', text, flags=re.M)
    text = re.sub(r'^(?:根拠表：|\[主張ごとの根拠).*\n?', '', text, flags=re.M)
    return text.strip()+'\n'


def inline(text: str, current: str, origin: str) -> str:
    # No raw HTML or script URLs are rendered. Link plain legacy URLs as well.
    pattern = re.compile(r'\[([^\]\n]+)\]\(([^\s)]+)\)|\*\*([^*\n]+)\*\*|`([^`\n]+)`|\[(SRC\d+)\]|(https?://[^\s<>]+)')
    result=[]; end=0
    for match in pattern.finditer(text):
        result.append(esc(text[end:match.start()]))
        if match.group(1) is not None:
            target=safe_link(match.group(2),current,origin)
            result.append(f'<a href="{esc(target)}">{esc(match.group(1))}</a>' if target else esc(match.group(1)))
        elif match.group(3) is not None:
            result.append('<strong>'+esc(match.group(3))+'</strong>')
        elif match.group(4) is not None:
            result.append('<code>'+esc(match.group(4))+'</code>')
        elif match.group(5) is not None:
            sid=match.group(5)
            result.append(f'<a href="#ref-{esc(sid)}">[{esc(sid)}]</a>')
        else:
            raw=match.group(6); u=raw.rstrip('。,.;）)')
            target=safe_link(u,current,origin)
            result.append((f'<a href="{esc(target)}">{esc(u)}</a>' if target else esc(u))+esc(raw[len(u):]))
        end=match.end()
    result.append(esc(text[end:]))
    return ''.join(result)

def render_markdown(text: str,current: str,origin: str) -> tuple[str,list[tuple[str,str]]]:
    out=[]; toc=[]; para=[]; listing=None; code=None
    def flush():
        if para:
            value=' '.join(para); para.clear()
            ref=re.match(r'^\[(SRC\d+)\]\s',value)
            cls=' class="source-line"' if value.startswith(('出典：','根拠：','確認範囲：')) else ''
            if ref:
                out.append(f'<p class="reference-item" id="ref-{esc(ref.group(1))}">{inline(value,current,origin)}</p>')
            else:
                out.append(f'<p{cls}>{inline(value,current,origin)}</p>')
    def end_list():
        nonlocal listing
        if listing:
            out.append(f'</{listing}>');listing=None
    for line in text.splitlines():
        stripped=line.strip()
        if stripped.startswith('```'):
            flush();end_list()
            if code is None:code=[]
            else:out.append('<pre><code>'+esc('\n'.join(code))+'</code></pre>');code=None
            continue
        if code is not None:code.append(line);continue
        if not stripped:flush();end_list();continue
        if stripped.startswith('# '):flush();end_list();continue
        head=re.match(r'^(#{2,4})\s+(.+)$',stripped)
        if head:
            flush();end_list();level=len(head.group(1));label=HEADINGS.get(head.group(2),head.group(2))
            anchor='section-'+str(len(toc)+1)
            toc.append((anchor,label))
            out.append(f'<h{level} id="{anchor}">{esc(label)}</h{level}>');continue
        if stripped=='---':flush();end_list();out.append('<hr>');continue
        if stripped.startswith('> '):
            flush();end_list();out.append('<blockquote><p>'+inline(stripped[2:],current,origin)+'</p></blockquote>');continue
        item=re.match(r'^(?:([-*])\s+|(\d+)\.\s+)(.+)',stripped)
        if item:
            flush();tag='ul' if item.group(1) else 'ol'
            if listing!=tag:end_list();listing=tag;out.append(f'<{tag}>')
            out.append('<li>'+inline(item.group(3),current,origin)+'</li>');continue
        if re.match(r'^\[SRC\d+\]\s',stripped):flush()
        end_list();para.append(stripped)
    flush();end_list()
    if code is not None:out.append('<pre><code>'+esc('\n'.join(code))+'</code></pre>')
    return ''.join(out),toc

def build_readers():
    for tid,entry in READERS.items():
        p=f'read/{tid}/index.html';cid=TOPICS[tid]['category_id'];gid=GROUP_OF[cid]
        text=entry['text']
        # Legacy footer is internal operational metadata, preserved in GitHub.
        # Reader-facing provenance is rendered separately rather than repeated.
        text=normalized_manuscript(text)
        rendered,toc=render_markdown(text,p,entry['path'])
        toc_html=''.join(f'<li><a href="#{esc(anchor)}">{esc(label)}</a></li>' for anchor,label in toc)
        reader_summary=EDITIONS.get(tid,{}).get('answer')
        if reader_summary:
            refs=EDITIONS[tid]['source_ids']
            hint=' · '.join(f'<a href="#ref-{esc(sid)}">{esc(sid)}</a>' for sid in refs[:3])
            answer=f'<div class="answer"><span class="answer-label">この記事の結論</span><p>{esc(reader_summary)}</p><span class="source-hint">根拠：{hint}</span></div>'
        else:
            answer=''
        reviewed=EDITIONS.get(tid,{}).get('reviewed_on')
        date_text=f'編集更新 {reviewed}' if reviewed else '原稿版 2026-09-11'
        basis=EDITIONS.get(tid,{}).get('review_scope','既存の原稿と出典・主張対応表を引き継いでいます。この画面への変換は、科学的内容の再点検を意味しません。')
        canonical_record=CATALOG.get(tid,{})
        claim_path=canonical_record.get('claim_dossier_path')
        links=f'<a href="https://github.com/Matsu71/Psychology_Blog/blob/main/{quote(entry["path"],safe="/")}">この編集稿の原文</a>'
        if claim_path:
            links+=f' · <a href="https://github.com/Matsu71/Psychology_Blog/blob/main/{quote(claim_path,safe="/")}">従来稿の主張対応表</a>'
        if tid in EDITIONS:
            links+=' · <a href="https://github.com/Matsu71/Psychology_Blog/blob/main/site/reader_editions.json">今回の主張確認記録</a>'
        related=EDITIONS.get(tid,{}).get('related_ids',[])
        related=[r for r in related if r in READERS and r!=tid]
        if len(related)<3:
            candidates=[r for r in READERS if GROUP_OF[TOPICS[r]['category_id']]==gid and r!=tid and r not in related]
            related+=candidates[:3-len(related)]
        related=related[:3]
        related_html='<section class="related"><h2>あわせて読む</h2><ul>'+''.join(f'<li><a href="{esc(reader_link(p,r))}">{esc(title(r))}</a></li>' for r in related)+'</ul></section>' if related else ''
        body=breadcrumbs(p,[('テーマ一覧','topics/index.html'),(category_label(cid),f'topics/category/{cid}/index.html'),(title(tid),None)])
        body+=f'''<div class="reader-shell"><aside><details class="reader-toc" open><summary>この記事の目次</summary><ol>{toc_html}</ol><p class="toc-meta">編集稿 · 約{minutes(tid)}分</p></details></aside><article class="reader" data-topic-id="{esc(tid)}"><span class="eyebrow">{esc(category_label(cid))}</span><h1>{esc(title(tid))}</h1><div class="reader-meta"><span class="draft-label">編集稿</span><span>{esc(date_text)}</span><span>約{minutes(tid)}分</span><div class="font-controls" role="group" aria-label="本文の文字サイズ"><button data-reader-size="18" aria-pressed="true" aria-label="文字サイズ 標準18ピクセル">標準</button><button data-reader-size="20" aria-pressed="false" aria-label="文字サイズ 大20ピクセル">大</button><button data-reader-size="22" aria-pressed="false" aria-label="文字サイズ 特大22ピクセル">特大</button></div></div>{answer}<div class="prose">{rendered}</div><details class="review-panel"><summary>出典の確認状況</summary><p>{esc(basis)}</p><p>AI支援による編集です。独立した専門家確認・公開承認・網羅的な撤回調査は未完了です。正式なエビデンス確実性評価は行っていません。掲載論文の査読と、この編集稿の点検は別です。</p><p>{links}</p></details>{related_html}</article></div>'''
        write(p,shell(p,title(tid),summary(tid),body,active=gid,noindex=True))

def build_search():
    p='search/index.html'
    body=breadcrumbs(p,[('検索',None)])+'<div class="page-heading"><h1>テーマを探す</h1><p>短い言葉でも、元の題名や関連用語でも検索できます。</p></div>'
    body+='<form id="topic-search" class="search-form" role="search" method="get"><label for="search-query">キーワード</label><input type="search" name="q" id="search-query" placeholder="例：睡眠、先延ばし、記憶" maxlength="150"><button type="submit">検索</button></form>'
    options=''.join(f'<option value="{esc(gid)}">{esc(g["name"])}</option>' for gid,g in GROUPS.items())
    body+=f'<div id="search-enhancements" hidden><div class="filters"><label for="search-group">分野<select id="search-group"><option value="">すべての分野</option>{options}</select></label><label for="search-status">本文<select id="search-status"><option value="">すべて</option><option value="draft">編集稿あり</option><option value="pending">準備中</option></select></label><button type="button" data-reset-search>条件をクリア</button></div></div>'
    body+='<noscript><p class="notice">JavaScriptが無効のため、全テーマを表示しています。ブラウザのページ内検索、またはテーマ一覧をご利用ください。</p></noscript>'
    body+=f'<p id="result-summary" class="result-summary" role="status" aria-live="polite" tabindex="-1">{len(TOPICS)}件のテーマ</p><div id="no-results" class="empty" hidden><h2>見つかりませんでした</h2><p>短い言葉に変えるか、絞り込みを解除してください。</p><button type="button" data-reset-search>条件をクリア</button></div><ul class="search-results">'
    for tid,t in TOPICS.items():
        corpus=' '.join([title(tid),t['title_ja'],category_label(t['category_id']),*t.get('concepts_en',[])])
        ready=tid in READERS
        heading=f'<a href="{esc(reader_link(p,tid))}">{esc(title(tid))}</a>' if ready else f'<span class="pending-title">{esc(title(tid))}</span>'
        desc=summary(tid) if ready else '本文は準備中です。'
        body+=f'<li class="search-result" data-topic-id="{esc(tid)}" data-search="{esc(corpus)}" data-group="{esc(GROUP_OF[t["category_id"]])}" data-status="{"draft" if ready else "pending"}"><span class="eyebrow">{esc(category_label(t["category_id"]))} · {"編集稿" if ready else "準備中"}</span><h2>{heading}</h2><p>{esc(desc)}</p></li>'
    body+='</ul><nav id="pagination" class="pagination" aria-label="検索結果のページ" hidden><button id="previous" type="button">前へ</button><span id="page-info"></span><button id="next" type="button">次へ</button></nav>'
    write(p,shell(p,'テーマを探す','300の心理学・行動科学テーマをキーワードと分野で検索。',body))

def build_about():
    p='about/index.html'
    body=breadcrumbs(p,[('このサイトについて',None)])+f'''<article class="about-prose"><h1>このサイトについて</h1><p>心理学と、その周辺にある行動科学の研究を、日常の疑問から読める形に整理するサイトです。睡眠、学習、性格、人間関係などを扱います。</p><h2>いまの掲載状況</h2><p>{len(TOPICS)}テーマの索引と、{len(READERS)}テーマの編集稿を掲載した制作プレビューです。編集稿は公開承認済みの記事ではありません。テーマ数、原稿数、確認済みの主張数を混同しません。</p><h2>記事の読み方</h2><p>新しい編集稿は、短い結論、本文、研究の限界、参考文献の順に読めます。実際の研究結果と、編集上の生活への応用例を分けています。</p><p>「関連がある」と「原因である」、「平均では差がある」と「自分にも効く」は別の主張です。効果量を、そのまま改善率のパーセントとして表しません。</p><h2>出典と確認</h2><p>研究の出典は論文と公的な資料を優先し、本文からたどれるようにしています。既存の研究台帳の題名とIDを保持し、読者向けの短い表示タイトルだけを別に管理しています。</p><p>確認できた範囲を各記事の末尾に記載します。抄録だけを確認した研究を「全文確認済み」とせず、AIによる点検を独立した専門家確認と呼びません。論文の正式なリスク・オブ・バイアス評価やGRADE評価は未実施です。</p><h2>編集と更新</h2><p>AI支援による編集・構造点検を行っています。医師、公認心理師、臨床心理士などが監修したという表示は、実際の確認と本人の了承が得られるまで使いません。編集日の更新だけで、全出典を再確認したようには表示しません。</p><p>記事の誤りは、該当箇所と根拠を確認して修正します。変更履歴と未解決の論点はGitHubに残します。閲覧数を計測していない段階で「人気ランキング」は設けません。</p><h2>健康情報の扱い</h2><p>個別の診断、治療方針、薬の使用量は案内しません。体調や生活上の支障が続く場合は、記事だけで判断せず、医療機関などの専門窓口に相談してください。</p><h2>参考にした構造</h2><p>Psychology Todayのテーマ索引、Greater Goodの分野別導線、NHSの短い見出しと読みやすい色の役割、Simply Psychologyの解説と出典への導線を参考にしています。文章・写真・ロゴ・固有の画面を複製したものではありません。</p><p><a href="https://github.com/Matsu71/Psychology_Blog/blob/main/docs/redesign/REFERENCE_REVIEW.md">参考サイトの比較</a> · <a href="https://github.com/Matsu71/Psychology_Blog/blob/main/docs/redesign/EDITORIAL_STANDARD.md">編集基準と課題</a> · <a href="https://github.com/Matsu71/Psychology_Blog/issues">訂正の連絡</a></p><h2>プライバシー</h2><p>この版には広告、アクセス解析、外部フォント、外部埋め込みを追加していません。検索はこのページ内で処理します。本文の文字サイズ設定だけを、このブラウザのローカルストレージに保存します。配信事業者の通常のアクセス記録は、この説明とは別です。</p></article>'''
    write(p,shell(p,'このサイトについて','出典、記事の確認状況、編集方針と訂正方法。',body))

def main():
    if set(CONFIG['display_titles']) != set(TOPICS):
        raise ValueError('Display title coverage must match the canonical topic IDs')
    if len(GROUP_OF)!=len(CATEGORIES) or set(GROUP_OF)!=set(CATEGORIES):
        raise ValueError('Each category needs exactly one parent group')
    for tid, edition in EDITIONS.items():
        if tid not in TOPICS:raise ValueError(f'Unknown edition topic: {tid}')
        if edition.get('publication_ready') is not False:raise ValueError('Reader editions are unapproved previews')
        if not set(edition['source_ids']).issubset(SOURCES):raise ValueError(f'Unknown source: {tid}')
    # Delete only files in our previous generated-file manifest. Never remove
    # unrelated user files or research material under similarly named folders.
    old_report=ROOT/'docs/READER_SITE_BUILD.json'
    if old_report.exists():
        for path in json.loads(old_report.read_text()).get('generated_files',[]):
            target=(ROOT/path).resolve()
            if target.is_relative_to(ROOT) and target.is_file() and path not in ('README.md','AGENTS.md'):
                target.unlink()
    audit=io.StringIO();writer=csv.writer(audit)
    writer.writerow(['topic_id','original_title','display_title','original_chars','display_chars'])
    for tid,t in TOPICS.items():writer.writerow([tid,t['title_ja'],title(tid),len(t['title_ja']),len(title(tid))])
    write('docs/redesign/TITLE_AUDIT.csv',audit.getvalue())
    write('assets/site.css',(ROOT/'site/style.css').read_text())
    write('assets/app.js',(ROOT/'site/app.js').read_text())
    write('.nojekyll','')
    build_home();build_topics();build_readers();build_search();build_about()
    original=[len(x['title_ja']) for x in TOPICS.values()]
    shortened=[len(x) for x in CONFIG['display_titles'].values()]
    report={'schema_version':'1.0','built_from_editorial_date':CONFIG['updated_on'],'site_status':'editorial_preview','topic_count':len(TOPICS),'category_count':len(CATEGORIES),'navigation_group_count':len(GROUPS),'canonical_manuscript_count':sum(bool(x.get('manuscript_path')) for x in CATALOG.values()),'reader_topic_count':len(READERS),'reader_rewrites':sum(x['kind']=='rewrite' for x in EDITIONS.values()),'new_reader_drafts':sum(x['kind']=='new_draft' for x in EDITIONS.values()),'approved_article_count':sum(x.get('publication_ready') is True for x in CATALOG.values()),'display_title_chars':{'original_median':statistics.median(original),'new_median':statistics.median(shortened),'original_max':max(original),'new_max':max(shortened)},'html_page_count':sum(p.endswith('.html') for p in GENERATED),'generated_files':list(GENERATED),'research_truth_validated':False}
    write('docs/READER_SITE_BUILD.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='generated_files'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
