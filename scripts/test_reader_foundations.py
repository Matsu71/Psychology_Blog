#!/usr/bin/env python3
"""Validate actual learning/glossary source and browser interactions.

CI uses real local HTTP navigation. READER_TEST_OFFLINE=1 renders owned local
HTML directly when network navigation is unavailable; it never claims that
navigation, status codes, history, or server delivery were tested in that mode.
"""
from __future__ import annotations
import hashlib,json,os,re,threading
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass

def main():
    checks=[];errors=[];offline=os.getenv('READER_TEST_OFFLINE')=='1'
    def check(ok,label):
        checks.append(label)
        if not ok:errors.append(label)
    data=json.loads((ROOT/'site/foundations.json').read_text())
    ed={x['topic_id']:x for x in json.loads((ROOT/'site/reader_editions.json').read_text())['editions']}
    traces=json.loads((ROOT/'site/foundation_claims.json').read_text())['claims']
    sources={x['id'] for x in json.loads((ROOT/'data/sources.json').read_text())['sources']}
    for row in traces:
        text=(ROOT/ed[row['topic_id']]['path']).read_text()
        plain=re.sub(r'\[SRC\d+\]','',text)
        check(row['claim_ja'] in plain,'claim text still present: '+row['topic_id']+'/'+str(row['paragraph_index']))
        check(set(row['source_ids'])<=sources,'claim sources registered: '+row['topic_id']+'/'+str(row['paragraph_index']))
    for term in data['terms']:
        check(bool(term['definition'] and term['locator'] and term['source_ids']),'term provenance: '+term['id'])
        check(len(term['definition'])<=120,'term concise definition: '+term['id'])
    check(len({x['id'] for x in data['terms']})==24,'24 distinct terms')
    check(len(data['series'])==4,'four learning paths')
    research=next(x for x in data['series'] if x['id']=='research')['topic_ids']
    check(set(research)=={f'PSY-RES-{n:03d}' for n in range(1,11)},'research path covers all ten research topics')
    for series in data['series']:
        check(len(series['topic_ids'])==len(set(series['topic_ids'])),'no duplicate step: '+series['id'])
        check(all((ROOT/f'read/{t}/index.html').exists() for t in series['topic_ids']),'real article endpoints: '+series['id'])
    server=None;screens=[]
    if not offline:
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}/' if server else ''
    out=ROOT/'review-screenshots';out.mkdir(exist_ok=True)
    def go(page,path,js=True):
        if offline:
            text=(ROOT/path.split('#')[0]).read_text()
            text=re.sub(r'<link rel="stylesheet"[^>]*>',lambda _: '<style>'+(ROOT/'assets/site.css').read_text()+'</style>',text)
            text=re.sub(r'<script src="[^"]+" defer></script>','',text)
            if js:text=text.replace('</body>','<script>'+(ROOT/'assets/app.js').read_text()+'</script></body>')
            page.set_content(text,wait_until='load')
        else:
            previous=page.url
            target=base+path
            response=page.goto(target,wait_until='networkidle')
            if response is None:
                # A same-document fragment navigation has no HTTP response.
                check(previous.split('#')[0]==target.split('#')[0] and page.url==target,'same-document anchor '+path)
            else:
                check(response.status==200,'HTTP200 '+path)
    try:
        with sync_playwright() as p:
            opt={'headless':True}
            if os.getenv('CHROMIUM_EXECUTABLE'):opt['executable_path']=os.environ['CHROMIUM_EXECUTABLE']
            browser=p.chromium.launch(**opt)
            context=browser.new_context(viewport={'width':1440,'height':1000},device_scale_factor=1)
            page=context.new_page();page.on('pageerror',lambda err:errors.append('JS: '+str(err)))
            for width in [320,390,768,1440]:
                page.set_viewport_size({'width':width,'height':1000})
                for name,path in [('learn','learn/index.html'),('research-guide','learn/research/index.html'),('glossary','glossary/index.html'),('research-article','read/PSY-RES-003/index.html')]:
                    go(page,path)
                    check(page.locator('h1').count()==1,f'{name}/{width}: one main heading')
                    check(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),f'{name}/{width}: no horizontal page overflow')
                    if width in [390,1440]:
                        image=f'foundations-{name}-{width}.png';page.screenshot(path=str(out/image),full_page=True);screens.append(image)
            go(page,'index.html');check(page.locator('.learning-entry a').count()==2,'home: two compact learning entries')
            page.screenshot(path=str(out/'foundations-home-1440.png'),full_page=True);screens.append('foundations-home-1440.png')
            go(page,'glossary/index.html')
            visible=page.locator('[data-term]:visible')
            check(visible.count()==24,'glossary: all24 initially visible')
            for query,expected in [('こうかりょう','effect-size'),('ＣＩ','confidence-interval'),('メタアナリシス','meta-analysis'),('ｐｒｅｒｅｇｉｓｔｒａｔｉｏｎ','preregistration')]:
                page.locator('#glossary-query').fill(query)
                page.locator('#glossary-search button').click()
                check(page.locator('#'+expected).is_visible(),'glossary: alias '+query)
                check(visible.count()>0,'glossary: results '+query)
            page.locator('#glossary-query').fill('zznonexistentzz');page.locator('#glossary-search button').click()
            check(visible.count()==0 and page.locator('#glossary-empty').is_visible(),'glossary: empty state')
            page.locator('#glossary-clear').click();check(visible.count()==24,'glossary: clear restores all groups')
            page.locator('#effect-size details summary').click();check(page.locator('#effect-size details').get_attribute('open') is not None,'glossary: example disclosure')
            page.locator('#glossary-query').fill('<script>alert(1)</script>');page.locator('#glossary-search button').click()
            check(visible.count()==0,'glossary: markup query treated as text')
            go(page,'search/index.html')
            for query,tid in [('こうかりょう','PSY-RES-003'),('平均回帰','PSY-RES-010'),('サンクコストとは','PSY-DEC-004')]:
                page.locator('#search-query').fill(query);page.locator('#topic-search button').click()
                check(page.locator('.search-result[data-topic-id="'+tid+'"]').is_visible(),'search: targeted synonym '+query)
            check(page.locator('.search-result:visible').first.get_attribute('data-topic-id')=='PSY-DEC-004','search: exact title ranks first')
            page.locator('#search-query').fill('こうかりょう');page.locator('#topic-search button').click()
            check(page.locator('#glossary-hits').is_visible(),'search: matching glossary entry offered')
            check(page.locator('[data-glossary-hit]:visible').count()<=5,'search: glossary matches capped')
            go(page,'read/PSY-RES-003/index.html');check(page.locator('.reader-terms a').count()>0,'article: linked terms')
            check(page.locator('.reading-path').count()==1,'article: learning path navigation')
            check(page.locator('.reading-path small').count()==2,'article: previous and next')
            page.locator('[data-reader-size="22"]').click()
            page.set_viewport_size({'width':320,'height':900})
            check(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'article: 320px with largest font')
            # Browser zoom/reflow equivalent: halve a 640-CSS-pixel viewport.
            page.set_viewport_size({'width':640,'height':900})
            go(page,'glossary/index.html')
            page.locator('body').evaluate('(e)=>e.style.zoom="2"')
            check(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'glossary: 200% zoom at320px')
            if not offline:
                page.set_viewport_size({'width':390,'height':900})
                go(page,'learn/index.html');page.locator('.learning-card a').first.click();page.locator('.learning-steps a').first.click()
                check('/read/PSY-RES-001/' in page.url,'navigation: hub to guide to first article')
                page.locator('.reader-terms a').first.click();check('/glossary/' in page.url,'navigation: article to glossary')
                target=page.url.split('#')[-1]
                check(page.locator('#'+target).is_visible(),'navigation: glossary anchor visible')
                go(page,'glossary/index.html#glossary-ref-SRC302')
                check(page.locator('.glossary-sources details').get_attribute('open') is not None,'navigation: deep source link opens disclosure')
                go(page,'glossary/index.html?q=こうかりょう')
                check(page.locator('#effect-size').is_visible() and page.locator('[data-term]:visible').count()<24,'navigation: glossary query survives URL load')
                page.reload(wait_until='networkidle')
                check(page.locator('#glossary-query').input_value()=='こうかりょう','navigation: glossary query survives reload')
            plainctx=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':900})
            plain=plainctx.new_page();go(plain,'glossary/index.html',js=False)
            check(plain.locator('[data-term]:visible').count()==24,'noJS: all glossary definitions available')
            plain.locator('#effect-size details summary').click();check(plain.locator('#effect-size details').get_attribute('open') is not None,'noJS: native disclosure works')
            go(plain,'learn/research/index.html',js=False);check(plain.locator('.learning-steps a').count()==10,'noJS: learning links available')
            plain.keyboard.press('Tab');check(plain.locator('.skip').evaluate('(e)=>e===document.activeElement'),'keyboard: first focus is skip link')
            plainctx.close();context.close();browser.close()
    except Exception as exc:errors.append(type(exc).__name__+': '+str(exc))
    finally:
        if server:server.shutdown()
    report=dict(schema_version='1.0',passed=not errors,checks=len(checks),check_labels=checks,errors=errors,screenshots=screens,execution_mode='offline_inline_local_render' if offline else 'real_local_HTTP_browser',navigation_verified=not offline and not errors,publication_ready=False,scientific_validity_certified=False,human_usability_test_completed=False)
    (ROOT/'docs/READER_FOUNDATIONS_TESTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)
if __name__=='__main__':main()
