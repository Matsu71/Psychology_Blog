#!/usr/bin/env python3
"""Structural checks only. Passing does not certify scientific truth."""
from __future__ import annotations
from collections import Counter
from html.parser import HTMLParser
import hashlib,json,re
from pathlib import Path
from urllib.parse import urlsplit,unquote
ROOT=Path(__file__).resolve().parents[1]
class Page(HTMLParser):
    def __init__(self,text):
        super().__init__(convert_charrefs=True);self.ids=[];self.links=[];self.h1=0;self.lang=None;self.robots=None;self.text=[];self.rows=[];self.labels=[];self.heading=None;self.headings=[]
        self.feed(text)
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='html':self.lang=a.get('lang')
        if tag=='meta' and a.get('name')=='robots':self.robots=a.get('content')
        if tag=='h1':self.h1+=1
        if tag=='h2':self.heading=[]
        if tag in ('a','link','script','img'):
            k='src' if tag in ('script','img') else 'href'
            if a.get(k):self.links.append(a[k])
        if a.get('class')=='search-result':self.rows.append(a)
        if tag=='label' and a.get('for'):self.labels.append(a['for'])
    def handle_data(self,text):
        self.text.append(text)
        if self.heading is not None:self.heading.append(text)
    def handle_endtag(self,tag):
        if tag=='h2' and self.heading is not None:self.headings.append(''.join(self.heading));self.heading=None

def main():
    report=json.loads((ROOT/'docs/READER_SITE_BUILD.json').read_text())
    files=[p for p in report['generated_files'] if p.endswith('.html')]
    pages={p:Page((ROOT/p).read_text()) for p in files}
    errors=[];checks=0
    def check(ok,msg):
        nonlocal checks
        checks+=1
        if not ok:errors.append(msg)
    for path,page in pages.items():
        check(page.h1==1,f'{path}: h1 count {page.h1}')
        check(page.lang=='ja',f'{path}: lang')
        check(page.robots=='noindex,follow',f'{path}: preview must be noindex')
        check(len(page.ids)==len(set(page.ids)),f'{path}: duplicate ids')
        check(set(page.labels)<=set(page.ids),f'{path}: label target')
        text=''.join(page.text)
        check(not re.search(r'\[\^[\w-]+\]|\[S\d+\]|publication_ready:|topic_id:',text),f'{path}: leaked manuscript markup')
        if path.startswith('read/'):
            check(all(len(h)<=18 for h in page.headings),f'{path}: long h2 {[(h,len(h)) for h in page.headings if len(h)>18]}')
        for link in page.links:
            u=urlsplit(link)
            if u.scheme or u.netloc:
                check(u.scheme in ('https','http','mailto'),f'{path}: unsafe URL {link}')
                continue
            target=(ROOT/path).parent/unquote(u.path) if u.path else ROOT/path
            target=target.resolve()
            check(target.is_relative_to(ROOT),f'{path}: path escapes project {link}')
            check(target.exists(),f'{path}: missing {link}')
            if u.fragment and target.suffix=='.html' and target.exists():
                key=target.relative_to(ROOT).as_posix()
                q=pages.get(key) or Page(target.read_text())
                check(unquote(u.fragment) in q.ids,f'{path}: missing anchor {link}')
    cfg=json.loads((ROOT/'site/editorial.json').read_text())
    cats=json.loads((ROOT/'data/categories.json').read_text())['categories']
    topics=[t for c in cats for t in json.loads((ROOT/c['file']).read_text())['topics']]
    tids={t['id'] for t in topics}
    check(set(cfg['display_titles'])==tids,'300 display titles cover canonical IDs')
    check(all(len(t)<=34 for t in cfg['display_titles'].values()),'Display-title character budget')
    grouped=[c for g in cfg['groups'] for c in g['categories']]
    check(len(grouped)==len(set(grouped))==len(cats),'Every category belongs to exactly one group')
    rows=pages['search/index.html'].rows
    check({r['data-topic-id'] for r in rows}==tids and len(rows)==len(tids),'Search covers every topic once')
    states=Counter(r['data-status'] for r in rows)
    check(states['draft']==report['reader_topic_count'],'Search ready count')
    check(states['pending']==len(tids)-report['reader_topic_count'],'Search pending count')
    for tid in tids:
        check((ROOT/f'read/{tid}/index.html').exists()==any(r['data-topic-id']==tid and r['data-status']=='draft' for r in rows),f'{tid}: no fake empty article')
    sources=json.loads((ROOT/'data/sources.json').read_text())['sources'];sids={x['id'] for x in sources}
    ed=json.loads((ROOT/'site/reader_editions.json').read_text())['editions']
    for x in ed:
        check(x['publication_ready'] is False,f'{x["topic_id"]}: approval unchanged')
        check(set(x['source_ids'])<=sids,f'{x["topic_id"]}: source register coverage')
        p=pages[f'read/{x["topic_id"]}/index.html']
        check(all('ref-'+s in p.ids for s in x['source_ids']),f'{x["topic_id"]}: edition source anchors')
    check(report['approved_article_count']==0,'Preview does not invent publication approvals')
    check(len(files)==104,'Expected 104 HTML pages')
    check((ROOT/'assets/site.css').stat().st_size<30000,'CSS budget 30 kB')
    check((ROOT/'assets/app.js').stat().st_size<10000,'JS budget 10 kB')
    result={'schema_version':'1.0','passed':not errors,'checks':checks,'html_pages':len(files),'source_count':len(sources),'search_states':dict(states),'errors':errors,'scientific_validity_certified':False,'browser_test':'separate test_reader_browser.py','asset_bytes':{x:(ROOT/x).stat().st_size for x in ['index.html','assets/site.css','assets/app.js']}}
    (ROOT/'docs/READER_SITE_TESTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)
if __name__=='__main__':main()
