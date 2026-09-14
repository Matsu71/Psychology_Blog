#!/usr/bin/env python3
"""Check editorial integrity and navigation; never certify clinical/scientific claims.

Offline mode only renders owned HTML. Real HTTP tests run in authorized CI.
"""
from __future__ import annotations
import hashlib, json, os, re, threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*args): pass

def main():
    checks=[];errors=[];screens=[];offline=os.getenv('READER_TEST_OFFLINE')=='1'
    def check(ok,label):
        checks.append(label)
        if not ok: errors.append(label)
    def read(p):return json.loads((ROOT/p).read_text())
    cfg=read('site/foundations.json');ed={e['topic_id']:e for e in read('site/reader_editions.json')['editions']}
    batch={f'PSY-EMO-{n:03}' for n in range(1,11)}|{'PSY-REL-004','PSY-REL-010'}
    cat={e['topic_id']:e for e in read('data/articles/catalog.json')['articles']}
    notes=read('site/reader_scope_notes.json')['notes']; claims=read('site/emotion_claims.json')['claims']
    sources={s['id']:s for s in read('data/sources.json')['sources']}
    raw={tid:(ROOT/ed[tid]['path']).read_text() for tid in batch}
    baseline=read('site/emotion_baseline.json')
    def digest(value):return hashlib.sha256(value).hexdigest()
    topic_files=[c['file'] for c in read('data/categories.json')['categories']]
    canonical=[(t['id'],t['title_ja']) for p in topic_files for t in read(p)['topics']]
    check(digest(json.dumps(canonical,ensure_ascii=False).encode())==baseline['topic_id_title_order_sha256'],'all canonical topic IDs, titles and order retained')
    for path,sha in baseline['canonical_manuscripts'].items():
        check(digest((ROOT/path).read_bytes())==sha,'original manuscript unchanged: '+path)
    check(batch <= set(n['topic_id'] for n in notes) and len(notes)==len({n['topic_id'] for n in notes}),'each original emotion edition retains one distinct scope note')
    for tid in sorted(batch):
        check(ed[tid]['publication_ready'] is False and ed[tid]['independent_review']=='pending','no invented approval: '+tid)
        check(ed[tid]['kind']==('rewrite' if cat[tid].get('manuscript_path') else 'new_draft'),'correct new/rewrite classification: '+tid)
        check(set(ed[tid]['source_ids'])<=sources.keys(),'registered article sources: '+tid)
        check(all(x in ed for x in ed[tid]['related_ids']) or all((ROOT/f'read/{x}/index.html').exists() for x in ed[tid]['related_ids']),'related articles exist: '+tid)
        check('study-scope' in (ROOT/f'read/{tid}/index.html').read_text(),'scope disclosure rendered: '+tid)
    for c in claims:
        check(c['claim_ja'] in re.sub(r'\[SRC\d+\]','',raw[c['topic_id']]),f'checked paragraph retained: {c["topic_id"]}/{c["paragraph_index"]}')
        check(bool(c['locator']) and set(c['source_ids'])<=set(ed[c['topic_id']]['source_ids']),'claim source/locator matches edition: '+c['topic_id'])
    for tid,phrase in [('PSY-EMO-006','両群の改善と、群間の差は別'),('PSY-EMO-003','2026年'),('PSY-EMO-005','脳活動を測った結果'),('PSY-EMO-007','即効性'),('PSY-EMO-008','元論文の全解析'),('PSY-EMO-010','ペンを保持する条件'),('PSY-REL-004','想像や場面提示'),('PSY-REL-010','正確さ')]:
        # Checks preserve explicitly authored caveats; they do not establish truth.
        check(phrase in raw[tid] or phrase in ed[tid]['answer'],'specific interpretation caveat: '+tid)
    for series_id in ['emotions','dialogue']:
        seq=next(s for s in cfg['series'] if s['id']==series_id)['topic_ids']
        check(len(seq)==len(set(seq)),'no duplicated guide steps: '+series_id)
        check(all((ROOT/f'read/{tid}/index.html').exists() for tid in seq),'no empty guide destinations: '+series_id)
    all_rows=[]
    for c in read('data/categories.json')['categories']:
        soup=BeautifulSoup((ROOT/f'topics/category/{c["id"]}/index.html').read_text(),'html.parser')
        expected=[t['id'] for t in read(c['file'])['topics']]
        rows=[li['data-topic-id'] for li in soup.select('li.topic-row')]
        all_rows+=rows
        check(len(rows)==len(set(rows)) and set(rows)==set(expected),'all category topics retained once: '+c['id'])
        ready=[li['data-topic-id'] for li in soup.select('.ready-topics li')]
        check(ready==[tid for tid in expected if (ROOT/f'read/{tid}/index.html').is_file()],'ready articles retain relative order: '+c['id'])
        pending=soup.select('.planned-topics li')
        check(all(not li.find('a') for li in pending),'no empty pending article links: '+c['id'])
        check(not any(d.has_attr('open') for d in soup.select('.planned-topics')),'planned topics initially collapsed: '+c['id'])
    check(len(all_rows)==len(canonical),'category pages retain all original themes')
    check(len([t for t in cfg['terms'] if t['group']=='emotion-dialogue'])==12,'twelve distinct emotional/dialogue definitions')
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
            check(res.status==200 if res else before.split('#')[0]==target.split('#')[0] and page.url==target,'real page transition: '+path)
    try:
        with sync_playwright() as p:
            options={'headless':True}
            if os.getenv('CHROMIUM_EXECUTABLE'): options['executable_path']=os.environ['CHROMIUM_EXECUTABLE']
            browser=p.chromium.launch(**options)
            ctx=browser.new_context(viewport={'width':1440,'height':1000})
            page=ctx.new_page();page.set_default_timeout(7000)
            page.on('pageerror',lambda e:errors.append('JS: '+str(e)))
            for w in [320,390,768,1440]:
                page.set_viewport_size({'width':w,'height':1000})
                for name,path in [('emotion-category','topics/category/emotions/index.html'),('relationship-category','topics/category/relationships/index.html'),('emotion-guide','learn/emotions/index.html'),('breathing-article','read/PSY-EMO-006/index.html')]:
                    go(page,path)
                    check(page.locator('h1').count()==1,f'{name}/{w}: one h1')
                    check(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),f'{name}/{w}: no horizontal overflow')
                    if w in [390,1440]:
                        fn=f'emotions-{name}-{w}.png';page.screenshot(path=str(out/fn),full_page=True);screens.append(fn)
            for tid in sorted(batch):
                go(page,f'read/{tid}/index.html')
                box=page.locator('.study-scope')
                check(box.count()==1 and box.get_attribute('open') is None,'scope initially collapsed: '+tid)
                box.locator('summary').focus();page.keyboard.press('Enter')
                check(box.get_attribute('open') is not None,'keyboard expands scope: '+tid)
                check(box.locator('dl dd').count()==3 and box.locator('a[href^="#ref-"]').count()>0,'three readable scope fields with sources: '+tid)
            go(page,'topics/category/relationships/index.html')
            ready_count=page.locator('.ready-topics .topic-row').count();pending_count=page.locator('.planned-topics .topic-row').count()
            check(ready_count==3 and pending_count==7,'relationships: three real articles and seven planned')
            check(page.locator('.planned-topics .topic-row:visible').count()==0,'planned titles do not dominate the initial view')
            page.locator('.planned-topics summary').click()
            check(page.locator('.planned-topics .topic-row:visible').count()==pending_count,'planned topics can be opened')
            if not offline:
                page.locator('.category-entrance .guide-goals a').first.click()
                check('/read/PSY-REL-004/' in page.url,'category shortcut reaches listening article')
                go(page,'learn/emotions/index.html');page.locator('.guide-goals a').first.click()
                check('/read/PSY-EMO-006/' in page.url,'guide shortcut reaches breathing article')
                page.locator('.study-scope summary').click();page.locator('.study-scope a').last.click()
                check(page.url.endswith('#ref-SRC324'),'scope link reaches null-comparator trial source')
                page.locator('.reading-path p a').first.click();check('/learn/emotions/' in page.url,'article returns to guide')
            go(page,'glossary/index.html')
            for q,term in [('けいちょう','high-quality-listening'),('感情抑制','expressive-suppression'),('ａｆｆｅｃｔ ｌａｂｅｌｉｎｇ','affect-labeling')]:
                page.locator('#glossary-query').fill(q);page.locator('#glossary-search button').click()
                check(page.locator('#'+term).is_visible(),'glossary alias: '+q)
            go(page,'search/index.html');page.locator('#search-query').fill('反芻');page.locator('#topic-search button').click()
            check(page.locator('.search-result[data-topic-id="PSY-EMO-004"]').is_visible(),'glossary synonym finds the actual article')
            page.set_viewport_size({'width':320,'height':1000});go(page,'read/PSY-EMO-003/index.html')
            page.locator('[data-reader-size="22"]').click();page.locator('.study-scope summary').click()
            check(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'largest body font and scope at 320px')
            plainctx=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':1000});plain=plainctx.new_page()
            go(plain,'topics/category/relationships/index.html',js=False);plain.locator('.planned-topics summary').focus();plain.keyboard.press('Enter')
            check(plain.locator('.planned-topics .topic-row:visible').count()==7,'no JS: keyboard reveals planned topics')
            go(plain,'read/PSY-EMO-006/index.html',js=False);plain.locator('.study-scope summary').focus();plain.keyboard.press('Enter')
            check('比較条件' in plain.locator('.study-scope').inner_text(),'no JS: scope content readable')
            fn='emotions-breathing-scope-mobile.png';plain.screenshot(path=str(out/fn),full_page=True);screens.append(fn)
            go(plain,'glossary/index.html',js=False);check(plain.locator('[data-term]:visible').count()==len(cfg['terms']),'no JS: all current glossary definitions readable')
            go(plain,'learn/dialogue/index.html',js=False);check(plain.locator('.learning-steps a').count()==3,'no JS: three real dialogue links')
            plainctx.close();ctx.close();browser.close()
    except Exception as exc:errors.append(type(exc).__name__+': '+str(exc))
    finally:
        if server:server.shutdown()
    report=dict(schema_version='1.0',passed=not errors,checks=len(checks),check_labels=checks,errors=errors,article_count=len(batch),claim_count=len(claims),article_hashes={t:digest(raw[t].encode()) for t in sorted(batch)},screenshots=screens,execution_mode='offline_inline_local_render' if offline else 'real_local_HTTP_browser',navigation_verified=not offline and not errors,scientific_validity_certified=False,independent_review_completed=False,human_usability_test_completed=False)
    (ROOT/'docs/READER_EMOTIONS_TESTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)
if __name__=='__main__':main()
