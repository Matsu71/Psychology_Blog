#!/usr/bin/env python3
"""Exercise the built site in Chromium; run on a normal permitted CI runner."""
from __future__ import annotations
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
import json,threading,os
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass

def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT.parent)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}/{ROOT.name}/'
    out=ROOT/'review-screenshots';out.mkdir(exist_ok=True)
    checks=[];errors=[];screens=[]
    def check(ok,label):
        checks.append(label)
        if not ok:errors.append(label)
    try:
        with sync_playwright() as p:
            options={'headless':True}
            if os.getenv('CHROMIUM_EXECUTABLE'):options['executable_path']=os.environ['CHROMIUM_EXECUTABLE']
            browser=p.chromium.launch(**options)
            page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
            page.on('pageerror',lambda e: errors.append('JavaScript: '+str(e)))
            for width in (320,390,768,1440):
                page.set_viewport_size({'width':width,'height':1000})
                for name,url in [('home','index.html'),('article','read/PSY-SLP-004/index.html'),('search','search/index.html')]:
                    response=page.goto(base+url,wait_until='networkidle')
                    check(response.status==200,f'{name}/{width}: HTTP 200')
                    check(page.locator('h1').count()==1,f'{name}/{width}: h1')
                    width_ok=page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                    check(width_ok,f'{name}/{width}: no document horizontal overflow')
                    if width in (390,1440):
                        f=f'{name}-{width}.png';page.screenshot(path=str(out/f),full_page=True);screens.append(f)
            page.set_viewport_size({'width':1440,'height':1000})
            page.goto(base+'search/index.html',wait_until='networkidle')
            visible=page.locator('.search-result:visible')
            check(visible.count()==24,'search: initial pagination 24')
            page.locator('#next').click();check('page=2' in page.url,'search: page reflected in URL')
            page.locator('#search-query').fill('先延ばし');page.locator('#topic-search button').click()
            check(visible.count()>0,'search: Japanese query')
            check('先延ばし' in page.locator('#search-query').input_value(),'search: query preserved')
            page.locator('#search-query').fill('ｓｌｅｅｐ');page.locator('#topic-search button').click()
            check(visible.count()>0,'search: NFKC full-width English matching')
            page.locator('#search-query').fill('カフェイン');page.locator('#topic-search button').click();katakana=visible.count()
            page.locator('#search-query').fill('かふぇいん');page.locator('#topic-search button').click()
            check(visible.count()==katakana and katakana>0,'search: kana equivalence')
            page.locator('[data-reset-search]').first.click()
            page.locator('#search-group').select_option('research');page.locator('#search-status').select_option('draft')
            check(visible.count()>0 and all(x=='research' for x in visible.evaluate_all('(els)=>els.map(e=>e.dataset.group)')),'search: group filter')
            check(all(x=='draft' for x in visible.evaluate_all('(els)=>els.map(e=>e.dataset.status)')),'search: manuscript filter')
            page.locator('#search-query').fill('zznotfoundzz');page.locator('#topic-search button').click()
            check(page.locator('#no-results').is_visible(),'search: empty state')
            page.locator('#no-results [data-reset-search]').click();check(visible.count()==24,'search: clear all filters')
            page.goto(base+'search/index.html?group=unknown&status=bad&page=9999',wait_until='networkidle')
            check(page.locator('#search-group').input_value()=='','search: invalid group reset')
            check(visible.count()>0,'search: invalid page clamped')
            page.goto(base+'index.html',wait_until='networkidle');page.locator('.feature-title a').click()
            check('/read/' in page.url,'home: feature navigates to article')
            page.locator('[data-reader-size="22"]').click()
            check(page.locator('[data-reader-size="22"]').get_attribute('aria-pressed')=='true','reader: size selected')
            page.reload(wait_until='networkidle')
            check(page.locator('[data-reader-size="22"]').get_attribute('aria-pressed')=='true','reader: size survives reload')
            page.locator('.reader-toc a').first.click();check('#section-' in page.url,'reader: table of contents navigation')
            source=page.locator('.prose a[href^="#ref-"]').first
            if source.count():
                source.click();check('#ref-' in page.url,'reader: reference anchor navigation')
            page.set_viewport_size({'width':390,'height':900});page.reload(wait_until='networkidle')
            check(page.locator('.reader-toc').get_attribute('open') is None,'reader: mobile TOC initially collapsed')
            page.locator('.reader-toc summary').click();check(page.locator('.reader-toc').get_attribute('open') is not None,'reader: mobile TOC expands')
            context=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':900})
            plain=context.new_page();plain.goto(base+'search/index.html')
            check(plain.locator('.search-result:visible').count()==300,'no JavaScript: all 300 themes readable')
            plain.goto(base+'read/PSY-ATT-001/index.html');check(plain.locator('.prose').inner_text().strip()!='','no JavaScript: full article readable')
            plain.goto(base+'index.html');plain.keyboard.press('Tab');check(plain.locator('.skip').evaluate('(e)=>e===document.activeElement'),'keyboard: first focus is skip link')
            context.close();browser.close()
    except Exception as exc:errors.append(type(exc).__name__+': '+str(exc))
    finally:server.shutdown()
    result={'schema_version':'1.0','passed':not errors,'checks':len(checks),'check_labels':checks,'viewports':[320,390,768,1440],'screenshots':screens,'errors':errors,'automated_accessibility_audit':False,'human_usability_test_completed':False,'scientific_validity_certified':False}
    (ROOT/'docs/READER_BROWSER_TESTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)
if __name__=='__main__':main()
