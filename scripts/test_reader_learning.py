#!/usr/bin/env python3
"""Content-integrity and browser regressions, not scientific/diagnostic validation.

READER_TEST_OFFLINE=1 permits owned-HTML rendering only. Real HTTP navigation,
URL history and delivery are checked on a normally permitted CI runner.
"""
from __future__ import annotations
import hashlib,json,os,re,threading
from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass

def main():
    offline=os.getenv('READER_TEST_OFFLINE')=='1';checks=[];errors=[];screens=[]
    def check(ok,label):
        checks.append(label)
        if not ok:errors.append(label)
    def read(p):return json.loads((ROOT/p).read_text())
    cfg=read('site/foundations.json');ed={e['topic_id']:e for e in read('site/reader_editions.json')['editions']}
    cat={a['topic_id']:a for a in read('data/articles/catalog.json')['articles']}
    sources={s['id']:s for s in read('data/sources.json')['sources']}
    items=read('site/learning_checks.json')['items'];claims=read('site/learning_claims.json')['claims']
    learning=next(s for s in cfg['series'] if s['id']=='learning')
    check(len(learning['topic_ids'])==10 and set(learning['topic_ids'])=={f'PSY-LEA-{n:03}' for n in range(1,11)},'all ten memory/learning topics connected exactly once')
    check(len({t['id'] for t in cfg['terms'] if t['group']=='memory-learning'})==12,'twelve distinct memory/learning concepts')
    check(len(items)==12 and len({i['topic_id'] for i in items})==12,'twelve original optional comprehension checks')
    for item in items:
        tid=item['topic_id'];e=ed[tid];page=(ROOT/f'read/{tid}/index.html').read_text()
        kind='rewrite' if cat[tid].get('manuscript_path') else 'new_draft'
        check(e['kind']==kind,'manuscript absence, not catalog presence determines kind: '+tid)
        check(item['publication_ready'] is False,'question not approved: '+tid)
        check(set(item['source_ids'])<=set(e['source_ids']),'question references actual article sources: '+tid)
        check(len(item['question'])<=90 and len(item['answer'])<=150,'compact question/answer: '+tid)
        check('id="learning-check"' in page and 'href="#learning-check"' in page,'TOC links real comprehension section: '+tid)
    for row in claims:
        tid=row['topic_id'];text=(ROOT/ed[tid]['path']).read_text()
        check(row['claim_ja'] in re.sub(r'\[SRC\d+\]','',text),'reviewed claim still in article: '+tid+'/'+str(row['paragraph_index']))
        check(bool(row['locator']) and set(row['source_ids'])<=sources.keys(),'claim source and read scope: '+tid+'/'+str(row['paragraph_index']))
    for tid in learning['topic_ids']:
        check((ROOT/ed[tid]['path']).is_file(),'actual learning manuscript: '+tid)
    # Prevent known overstatements from silently returning. Not a truth classifier.
    content={tid:(ROOT/e['path']).read_text() for tid,e in ed.items() if tid in {i['topic_id'] for i in items}}
    for tid,term in [('PSY-LEA-008','11件すべてに統計的に有意'),('PSY-ATT-002','開始時点'),('PSY-LEA-004','実際には誰も教えず'),('PSY-ATT-005','効果の方向'),('PSY-LEA-009','正解を見ています')]:
        check(term in content[tid],'interpretation caveat retained: '+tid)
    edges=[e for p in read('data/evidence/catalog.json')['files'] for e in read(p)['edges']]
    for tid,sid in [('PSY-LEA-002','SRC092'),('PSY-LEA-007','SRC084')]:
        check(any(e['topic_id']==tid and e['source_id']==sid and e['relation_role']=='context_only' for e in edges),'non-direct legacy source not treated as primary evidence: '+tid+'/'+sid)
    server=None
    if not offline:
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT.parent)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}/{ROOT.name}/' if server else ''
    out=ROOT/'review-screenshots';out.mkdir(exist_ok=True)
    def go(page,path,js=True):
        if offline:
            text=(ROOT/path.split('#')[0].split('?')[0]).read_text()
            text=re.sub(r'<link rel="stylesheet"[^>]*>',lambda _:'<style>'+(ROOT/'assets/site.css').read_text()+'</style>',text)
            text=re.sub(r'<script src="[^"]+" defer></script>','',text)
            if js:text=text.replace('</body>','<script>'+(ROOT/'assets/app.js').read_text()+'</script></body>')
            page.set_content(text,wait_until='load')
        else:
            target=base+path;previous=page.url;response=page.goto(target,wait_until='networkidle')
            check(response.status==200 if response else previous.split('#')[0]==target.split('#')[0] and page.url==target,'HTTP or same-document transition: '+path)
    try:
        with sync_playwright() as p:
            options={'headless':True}
            if os.getenv('CHROMIUM_EXECUTABLE'):options['executable_path']=os.environ['CHROMIUM_EXECUTABLE']
            browser=p.chromium.launch(**options)
            ctx=browser.new_context(viewport={'width':1440,'height':1050},device_scale_factor=1)
            page=ctx.new_page();page.set_default_timeout(7000);page.on('pageerror',lambda err:errors.append('JS: '+str(err)))
            for width in [320,390,768,1440]:
                page.set_viewport_size({'width':width,'height':1050})
                for label,path in [('memory-guide','learn/learning/index.html'),('attention-guide','learn/attention/index.html'),('learning-article','read/PSY-LEA-004/index.html')]:
                    go(page,path)
                    check(page.locator('h1').count()==1,f'{label}/{width}: single h1')
                    check(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),f'{label}/{width}: no horizontal overflow')
                    if width in [390,1440]:
                        name=f'learning-{label}-{width}.png';page.screenshot(path=str(out/name),full_page=True);screens.append(name)
            for item in items:
                go(page,f'read/{item["topic_id"]}/index.html')
                box=page.locator('.learning-check')
                check(box.count()==1,'one visible optional question: '+item['topic_id'])
                check(box.locator('details').get_attribute('open') is None,'answer initially closed: '+item['topic_id'])
                box.locator('summary').click()
                check(item['answer'] in box.inner_text(),'answer opens: '+item['topic_id'])
                check(box.locator('a[href^="#ref-"]').count()==len(item['source_ids']),'answer has source links: '+item['topic_id'])
            go(page,'learn/learning/index.html')
            check(page.locator('.learning-steps li').count()==10,'ten visible learning steps')
            check(page.locator('.guide-goals a').count()==3,'three compact purpose shortcuts')
            if not offline:
                page.locator('.guide-goals a').nth(1).click()
                check('/read/PSY-LEA-006/' in page.url,'purpose shortcut opens self-explanation article')
                page.locator('.reader-toc summary').click() if page.locator('.reader-toc').get_attribute('open') is None else None
                page.locator('.reader-toc a[href="#learning-check"]').click()
                check(page.url.endswith('#learning-check') and page.locator('#learning-check').is_visible(),'TOC reaches comprehension question')
                page.locator('.learning-check summary').click();page.locator('.learning-check a').first.click()
                check(page.url.endswith('#ref-SRC313'),'answer goes to real source anchor')
            go(page,'glossary/index.html')
            for query,expected in [('そうきれんしゅう','retrieval-practice'),('間隔反復','spacing'),('ＪＯＬ','judgment-of-learning'),('インターリービング','interleaving')]:
                page.locator('#glossary-query').fill(query);page.locator('#glossary-search button').click()
                check(page.locator('#'+expected).is_visible(),'memory glossary reading/alias: '+query)
            page.locator('#glossary-clear').click()
            page.locator('#group-memory-learning').scroll_into_view_if_needed()
            name='learning-memory-terms-1440.png';page.screenshot(path=str(out/name),full_page=False);screens.append(name)
            go(page,'search/index.html');page.locator('#search-query').fill('インターリービング');page.locator('#topic-search button').click()
            check(page.locator('.search-result[data-topic-id="PSY-LEA-003"]').is_visible(),'memory alias reaches actual article search')
            page.set_viewport_size({'width':320,'height':900});go(page,'read/PSY-LEA-008/index.html')
            page.locator('[data-reader-size="22"]').click();page.locator('.learning-check summary').click()
            check(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'expanded question at 320px and 22px text')
            plainctx=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':950});plain=plainctx.new_page();plain.set_default_timeout(7000)
            go(plain,'read/PSY-LEA-004/index.html',js=False)
            plain.locator('.learning-check summary').focus();plain.keyboard.press('Enter')
            check(plain.locator('.learning-check details').get_attribute('open') is not None,'no JS and keyboard: answer opens')
            plain.keyboard.press('Enter');check(plain.locator('.learning-check details').get_attribute('open') is None,'no JS and keyboard: answer closes')
            name='learning-check-mobile.png';plain.screenshot(path=str(out/name),full_page=True);screens.append(name)
            go(plain,'learn/learning/index.html',js=False);check(plain.locator('.learning-steps a').count()==10,'no JS: ten real learning links')
            go(plain,'glossary/index.html',js=False);check(plain.locator('[data-term]:visible').count()==36,'no JS: all 36 definitions readable')
            plainctx.close();ctx.close();browser.close()
    except Exception as exc:errors.append(type(exc).__name__+': '+str(exc))
    finally:
        if server:server.shutdown()
    report=dict(schema_version='1.0',passed=not errors,checks=len(checks),check_labels=checks,errors=errors,screenshots=screens,execution_mode='offline_inline_local_render' if offline else 'real_local_HTTP_browser',navigation_verified=not offline and not errors,article_count=len(items),claim_count=len(claims),article_hashes={tid:hashlib.sha256((ROOT/ed[tid]['path']).read_bytes()).hexdigest() for tid in content},scientific_validity_certified=False,independent_review_completed=False,human_usability_test_completed=False)
    (ROOT/'docs/READER_LEARNING_TESTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)
if __name__=='__main__':main()
