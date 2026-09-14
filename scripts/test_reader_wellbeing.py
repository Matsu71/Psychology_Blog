#!/usr/bin/env python3
"""Verify recorded edits, source navigation, and readable tables.

Browser success is not a scientific, clinical, or human-usability certification.
Offline mode renders owned files only and never claims HTTP navigation coverage.
"""
from __future__ import annotations
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import hashlib, json, os, re, threading
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import build_reader_site as site
from reader_references import ReaderReferences
ROOT=Path(__file__).resolve().parents[1]

class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*args): pass

def main():
    checks=[];errors=[];screens=[];offline=os.getenv('READER_TEST_OFFLINE')=='1'
    def check(ok,label):
        checks.append(label)
        if not ok:errors.append(label)
    def read(path):return json.loads((ROOT/path).read_text())
    all_updates=read('site/article_updates.json')['entries']
    batch={'PSY-WEL-001','PSY-WEL-002','PSY-WEL-003','PSY-WEL-005','PSY-WEL-007','PSY-WEL-009','PSY-WRK-001','PSY-WRK-002','PSY-WRK-011'}
    updates=[e for e in all_updates if e['topic_id'] in batch]
    check(len(all_updates)==len({e['topic_id'] for e in all_updates}),'all update records are unique')
    baseline=read('site/emotion_baseline.json')
    canonical=[(t['id'],t['title_ja']) for c in read('data/categories.json')['categories'] for t in read(c['file'])['topics']]
    check(hashlib.sha256(json.dumps(canonical,ensure_ascii=False).encode()).hexdigest()==baseline['topic_id_title_order_sha256'],'original topic IDs, titles and order retained')
    for path,sha in baseline['canonical_manuscripts'].items():
        check(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==sha,'original manuscript retained: '+path)
    check(len(batch)==9 and len(updates)==9,'nine distinct actual edit records')
    check(sum(site.EDITIONS[t]['kind']=='rewrite' for t in batch)==6,'six legacy rewrites, not new articles')
    check(sum(site.EDITIONS[t]['kind']=='new_draft' for t in batch)==3,'three genuinely new themes')
    check(read('site/article_updates.json')['schedule_is_automated'] is False,'review targets do not imply an automation')
    checked={e['source_id'] for e in read('site/wellbeing_source_checks.json')['checks']}
    for u in updates:
        tid=u['topic_id'];raw=site.READERS[tid]['text']
        check(hashlib.sha256(raw.encode()).hexdigest()==u['reader_sha256'],'record bound to actual article: '+tid)
        check(u['publication_ready'] is False and site.EDITIONS[tid]['publication_ready'] is False,'no publication approval invented: '+tid)
        check(set(u['source_ids'])<=checked,'sources have specified verification scope: '+tid)
        p=BeautifulSoup((ROOT/f'read/{tid}/index.html').read_text(),'html.parser')
        check(len(p.select('.update-history'))==1 and not p.select_one('.update-history').has_attr('open'),'actual update history initially folded: '+tid)
        check('幸福・仕事記事の段落別出典' in p.get_text() and '感情・対話記事の段落別出典' not in p.get_text(),'article links its own claim record: '+tid)
    claims=read('site/wellbeing_claims.json')['claims']
    check(len(claims)==36,'36 recorded claim paragraphs')
    for c in claims:
        tid=c['topic_id']
        check(c['claim_ja'] in re.sub(r'\[SRC\d+\]','',site.READERS[tid]['text']),'claim paragraph not stale: '+tid+'/'+str(c['paragraph_index']))
        check(bool(c['locator']) and set(c['source_ids'])<=set(site.EDITIONS[tid]['source_ids']),'claim source and locator present: '+tid+'/'+str(c['paragraph_index']))
    for tid,phrase in [('PSY-WEL-002','19％'),('PSY-WEL-005','未査読'),('PSY-WEL-009','想像'),('PSY-WRK-001','同等性検定'),('PSY-WRK-002','すべてが無作為化試験だったとも扱えません'),('PSY-WRK-011','2026年')]:
        check(phrase in site.READERS[tid]['text'],'authored interpretation distinction retained: '+tid)
    for path in ROOT.glob('read/*/index.html'):
        tid=path.parent.name;p=BeautifulSoup(path.read_text(),'html.parser')
        refs=p.select('.reference-item');ns=[int(x['data-reference-number']) for x in refs]
        check(ns==list(range(1,len(refs)+1)),'local source numbering sequential: '+tid)
        check(not re.search(r'(?<![A-Za-z0-9])SRC\d+(?!\d)',p.select_one('.reader').get_text()),'internal source IDs not shown: '+tid)
        check(not p.select('.reference-bibliography[open]'),'full metadata folded by default: '+tid)
        # Compare against the same normalized, rendered bibliography before UI
        # enhancement, not against a second hand-maintained source list.
        original,_=site.render_markdown(site.normalized_manuscript(site.READERS[tid]['text']),str(path.relative_to(ROOT)),site.READERS[tid]['path'])
        old=BeautifulSoup(original,'html.parser')
        for ref in refs:
            sid=ref['id'].removeprefix('ref-');num=int(ref['data-reference-number'])
            check(ref.select_one('.reference-primary')['href']==site.SOURCES[sid]['url'],'canonical source URL retained: '+tid+'/'+sid)
            prior=old.find(id=ref['id']);lead=prior.find('a',href='#ref-'+sid)
            if lead:lead.decompose()
            old_urls=[a['href'] for a in prior.find_all('a',href=True)]
            for a in prior.find_all('a'):
                if re.fullmatch(r'\[?SRC\d+\]?',a.get_text()):a.string='資料を開く'
            check(old_urls==[a['href'] for a in ref.select('.reference-bibliography a[href]')],'original bibliography links preserved: '+tid+'/'+sid)
            check(prior.get_text().strip()==ref.select_one('.reference-bibliography p').get_text().strip(),'complete original bibliography retained: '+tid+'/'+sid)
            for a in p.select(f'a.citation-link[href="#{ref["id"]}"]'):
                check(a.has_attr('id') and str(num) in a['aria-label'],'numbered citation has accessible name: '+tid+'/'+a.get('id','missing'))
            back=ref.select_one('.reference-return')
            check(back is None or p.find(id=back['href'][1:]) is not None,'native source return target exists: '+tid+'/'+sid)
    p=BeautifulSoup((ROOT/'read/PSY-WEL-001/index.html').read_text(),'html.parser')
    check(len(p.select('.table-wrap table thead th[scope="col"]'))==3 and len(p.select('.table-wrap tbody tr'))==3,'comparison is a real three-column, three-row table')
    check('|---|' not in p.get_text(),'table delimiter is not reader text')
    for sid,count in [('wellbeing',6),('work-rest',3)]:
        seq=next(x for x in site.FOUNDATIONS.series if x['id']==sid)['topic_ids']
        check(len(seq)==count and len(set(seq))==count and set(seq)<=site.READERS.keys(),'purpose guide has only real distinct articles: '+sid)
    # Escape authored text; never turn the source label into markup.
    fake=ReaderReferences(ROOT);fake.labels=dict(fake.labels,SRC331={'name':'<bad & "label">','topic':'<script>'})
    f=fake.enhance('<div class="prose"><p><a href="#ref-SRC331">[SRC331]</a></p><p class="reference-item" id="ref-SRC331"><a href="#ref-SRC331">[SRC331]</a> Full book.</p></div><details class="review-panel"></details>',site.SOURCES)
    check('<bad' not in f and '<script>' not in f and '&lt;bad' in f,'reference labels escaped as text')
    try:
        fake.enhance('<a href="#ref-SRC9999">[SRC9999]</a>',site.SOURCES)
        check(False,'unresolved reference must stop build')
    except ValueError:check(True,'unresolved reference must stop build')
    server=None
    if not offline:
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT.parent)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}/{ROOT.name}/' if server else ''
    out=ROOT/'review-screenshots';out.mkdir(exist_ok=True)
    def go(page,path,js=True):
        if offline:
            text=(ROOT/path.split('#')[0].split('?')[0]).read_text()
            text=re.sub(r'<link rel="stylesheet"[^>]*>',lambda _: '<style>'+(ROOT/'assets/site.css').read_text()+'</style>',text)
            text=re.sub(r'<script src="[^"]+" defer></script>','',text)
            if js:text=text.replace('</body>','<script>'+(ROOT/'assets/app.js').read_text()+'</script></body>')
            page.set_content(text,wait_until='load')
        else:
            before=page.url;target=base+path;res=page.goto(target,wait_until='networkidle')
            check(res.status==200 if res else before.split('#')[0]==target.split('#')[0] and page.url==target,'real HTTP or fragment transition: '+path)
    try:
        with sync_playwright() as pw:
            args={'headless':True}
            if os.getenv('CHROMIUM_EXECUTABLE'):args['executable_path']=os.environ['CHROMIUM_EXECUTABLE']
            browser=pw.chromium.launch(**args)
            ctx=browser.new_context(viewport={'width':1440,'height':1000})
            page=ctx.new_page();page.set_default_timeout(7000)
            page.on('pageerror',lambda e:errors.append('JavaScript: '+str(e)))
            for w in [320,390,768,1440]:
                page.set_viewport_size({'width':w,'height':1000})
                for name,path in [('guide','learn/wellbeing/index.html'),('work','learn/work-rest/index.html'),('article','read/PSY-WEL-001/index.html'),('income','read/PSY-WEL-005/index.html')]:
                    go(page,path)
                    check(page.locator('h1').count()==1,f'{name}/{w}: single main heading')
                    check(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),f'{name}/{w}: no horizontal page overflow')
                    if w in [390,1440]:
                        fn=f'wellbeing-{name}-{w}.png';page.screenshot(path=str(out/fn),full_page=True);screens.append(fn)
            go(page,'read/PSY-WEL-002/index.html')
            citation=page.locator('.prose p .citation-link').last;ident=citation.get_attribute('id');refid=citation.get_attribute('href')[1:]
            if not offline:
                citation.click();check(page.url.endswith('#'+refid),'numeric citation opens correct stable reference anchor')
            else:
                # Run only the delegated handler; this does not emulate a network navigation.
                citation.dispatch_event('click')
            back=page.locator('#'+refid+' .reference-return')
            check(back.get_attribute('href')=='#'+ident,'return updates to the exact clicked citation without storage')
            if not offline:
                back.click();check(page.url.endswith('#'+ident),'return link reaches exact citation')
            for tid in sorted(batch):
                go(page,f'read/{tid}/index.html')
                history=page.locator('.update-history')
                check(history.get_attribute('open') is None,'history initially closed: '+tid)
                history.locator('summary').focus();page.keyboard.press('Enter')
                check(history.get_attribute('open') is not None and history.locator('time').count()==2,'keyboard opens dated update history: '+tid)
                check('自動点検' in history.inner_text(),'review target has an explicit planning qualification: '+tid)
            go(page,'read/PSY-WEL-001/index.html');page.set_viewport_size({'width':320,'height':1000})
            page.locator('[data-reader-size="22"]').click()
            page.locator('.reference-bibliography summary').first.click();page.locator('.update-history summary').click()
            check(page.locator('table').is_visible() and page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'table and expanded sources fit 320px with largest body type')
            page.set_viewport_size({'width':390,'height':1000})
            page.locator('#ref-SRC331').scroll_into_view_if_needed()
            fn='wellbeing-references-mobile.png';page.screenshot(path=str(out/fn),full_page=False);screens.append(fn)
            page.set_viewport_size({'width':640,'height':1000});page.evaluate('document.documentElement.style.zoom="2"')
            check(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'200 percent reflow without page overflow')
            plainctx=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':1000})
            plain=plainctx.new_page();go(plain,'read/PSY-WEL-001/index.html',False)
            target=plain.locator('.reference-return').get_attribute('href')[1:]
            check(plain.locator('#'+target).count()==1,'noJS: native return points to actual prose citation')
            plain.locator('.reference-bibliography summary').focus();plain.keyboard.press('Enter')
            check(plain.locator('.reference-bibliography').get_attribute('open') is not None,'noJS: keyboard opens full bibliography')
            if not offline:
                plain.locator('.reference-return').click();check(plain.url.endswith('#'+target),'noJS: native reference return navigation works')
            go(plain,'learn/work-rest/index.html',False)
            check(plain.locator('.learning-steps a').count()==3,'noJS: three work articles remain available')
            plainctx.close();ctx.close();browser.close()
    except Exception as e:errors.append(type(e).__name__+': '+str(e))
    finally:
        if server:server.shutdown();server.server_close()
    result={'schema_version':'1.0','passed':not errors,'checks':len(checks),'check_labels':checks,'errors':errors,'reader_pages_checked':len(site.READERS),'edited_articles':len(batch),'new_articles':3,'rewritten_legacy_articles':6,'claim_count':len(claims),'screenshots':screens,'execution_mode':'offline_inline_local_render' if offline else 'real_local_HTTP_browser','navigation_verified':not offline and not errors,'scientific_validity_certified':False,'independent_review_completed':False,'human_usability_test_completed':False}
    (ROOT/'docs/READER_WELLBEING_TESTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='check_labels'},ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)
if __name__=='__main__':main()
