#!/usr/bin/env python3
"""Test motivation editions and precise search; not scientific certification.

Offline mode exercises owned HTML/CSS/JS without claiming HTTP navigation.
Run without READER_TEST_OFFLINE on an authorized runner for URL/reload tests.
"""
from __future__ import annotations
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from urllib.parse import parse_qs, urlsplit
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import build_reader_site as site

ROOT = Path(__file__).resolve().parents[1]
BATCH = {f'PSY-MOT-{i:03d}' for i in range(2, 11)} | {'PSY-HAB-007', 'PSY-ATT-003'}
NEW = {f'PSY-MOT-{i:03d}' for i in (2, 3, 4, 5, 7, 10)}
CONTEXT = {('PSY-MOT-003','SRC047'), ('PSY-MOT-003','SRC084'), ('PSY-MOT-004','SRC045'), ('PSY-MOT-004','SRC098'), ('PSY-MOT-006','SRC104')}

class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

def main():
    checks, errors, screenshots = [], [], []
    offline = os.getenv('READER_TEST_OFFLINE') == '1'
    def check(ok, label):
        checks.append(label)
        if not ok:
            errors.append(label)
    def read(path):
        return json.loads((ROOT/path).read_text())
    baseline = read('site/emotion_baseline.json')
    canonical = [(t['id'],t['title_ja']) for c in read('data/categories.json')['categories'] for t in read(c['file'])['topics']]
    check(hashlib.sha256(json.dumps(canonical,ensure_ascii=False).encode()).hexdigest() == baseline['topic_id_title_order_sha256'], 'canonical IDs, titles, order unchanged')
    for path, digest in baseline['canonical_manuscripts'].items():
        check(hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == digest, 'original manuscript unchanged: '+path)
    claims = read('site/motivation_claims.json')['claims']
    source_checks = read('site/motivation_source_checks.json')['checks']
    source_ids = {c['source_id'] for c in source_checks}
    check(len(claims) == 38 and {c['topic_id'] for c in claims} == BATCH, '38 mapped paragraphs across eleven editions')
    check(len(source_checks) == len(source_ids), 'source checks have unique IDs')
    check(all(c['independent_review_completed'] is False for c in source_checks), 'no invented independent source review')
    for tid in sorted(BATCH):
        ed = site.EDITIONS[tid]
        text = (ROOT/ed['path']).read_text()
        check(ed['kind'] == ('new_draft' if tid in NEW else 'rewrite'), 'correct new/rewrite classification: '+tid)
        check(bool(site.CATALOG[tid].get('manuscript_path')) == (tid not in NEW), 'new means no previous canonical manuscript: '+tid)
        check(ed['publication_ready'] is False and ed['independent_review'] == 'pending', 'no fabricated approval: '+tid)
        check(set(ed['source_ids']) <= site.SOURCES.keys() and set(ed['source_ids']) <= source_ids, 'registered and scoped article references: '+tid)
        check(len(text.split('## 参考文献')[0]) >= 650, 'substantive body rather than an empty title: '+tid)
        check('旧稿の抄録照合を' not in text, 'internal editing process not placed in body: '+tid)
        update = site.REFERENCES.updates[tid]
        check(update['reader_sha256'] == hashlib.sha256(text.encode()).hexdigest(), 'dated edit matches real manuscript hash: '+tid)
        soup = BeautifulSoup((ROOT/f'read/{tid}/index.html').read_text(), 'html.parser')
        check(soup.select_one('.study-scope') and soup.select_one('.update-history'), 'scope and true edit history rendered: '+tid)
        check(len(soup.select('.reader h1')) == 1, 'one reader heading: '+tid)
    for c in claims:
        text = (ROOT/site.EDITIONS[c['topic_id']]['path']).read_text()
        p = text.split('\n\n')[c['paragraph_index']]
        check(c['claim_ja'] == re.sub(r'\[SRC\d+\]','',p).strip(), 'exact checked paragraph: '+c['topic_id']+'/'+str(c['paragraph_index']))
        check(set(c['source_ids']) <= set(site.EDITIONS[c['topic_id']]['source_ids']) and bool(c['locator']), 'claim source and locator: '+c['topic_id']+'/'+str(c['paragraph_index']))
    edges = {(e['topic_id'],e['source_id']):e for e in read('data/evidence/motivation.json')['edges']}
    for pair in sorted(CONTEXT):
        check(edges[pair]['relation_role'] == 'context_only', 'non-direct legacy link labelled as context: '+str(pair))
    seq = next(s for s in site.FOUNDATIONS.series if s['id'] == 'motivation')['topic_ids']
    check(seq == [f'PSY-MOT-{i:03d}' for i in range(1,11)] and set(seq) <= site.READERS.keys(), 'all ten motivation topics connected exactly once')
    for tid, phrases in {
        'PSY-MOT-006':['r=0.23','r=-0.22','原因'],
        'PSY-MOT-007':['128研究','183研究','質','量','因果'],
        'PSY-MOT-008':['d=0.05','d=0.14','-0.08〜0.35','0.10点','新しい介入試験ではありません'],
        'PSY-MOT-010':['既存の行動記録','年末まで'],
        'PSY-HAB-007':['d=0.40','40％','公開'],
        'PSY-ATT-003':['割り込み先の仕事','一律の回復時間']
    }.items():
        check(all(p in site.READERS[tid]['text'] for p in phrases), 'comparison and applicability caveats preserved: '+tid)
    soup = BeautifulSoup((ROOT/'search/index.html').read_text(),'html.parser')
    check(len(soup.select('#search-category option[value]')) == 29, 'all 28 categories plus unrestricted option')
    for li in soup.select('.search-result'):
        tid = li['data-topic-id']
        check(li['data-category'] == site.TOPICS[tid]['category_id'], 'search item assigned to canonical category: '+tid)
        expected = site.REFERENCES.updates.get(tid, {}).get('updated_on','')
        check(li['data-updated'] == expected and bool(li.select('time.search-update')) == bool(expected), 'only real update dates exposed: '+tid)
    for cid in site.CATEGORIES:
        p = BeautifulSoup((ROOT/f'topics/category/{cid}/index.html').read_text(),'html.parser')
        link = p.select_one('.category-search a')
        params = parse_qs(urlsplit(link['href']).query) if link else {}
        check(params == {'category':[cid],'status':['draft']}, 'category search link has exact category and readable status: '+cid)
    server = None
    if not offline:
        server = ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT.parent)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}/{ROOT.name}/' if server else ''
    def go(page, path, js=True):
        if offline:
            text = (ROOT/path.split('#')[0].split('?')[0]).read_text()
            text = re.sub(r'<link rel="stylesheet"[^>]*>',lambda _: '<style>'+(ROOT/'assets/site.css').read_text()+'</style>',text)
            text = re.sub(r'<script src="[^"]+" defer></script>','',text)
            if js:
                text = text.replace('</body>','<script>'+(ROOT/'assets/app.js').read_text()+'</script></body>')
            page.set_content(text,wait_until='load')
        else:
            before=page.url; target=base+path; response=page.goto(target,wait_until='networkidle')
            check(response.status==200 if response else before.split('#')[0]==target.split('#')[0] and page.url==target, 'HTTP or fragment navigation: '+path)
    def ids(page):
        return page.locator('.search-result:visible').evaluate_all('(items)=>items.map(i=>i.dataset.topicId)')
    out = ROOT/'review-screenshots';out.mkdir(exist_ok=True)
    try:
        with sync_playwright() as pw:
            launch={'headless':True}
            if os.getenv('CHROMIUM_EXECUTABLE'):
                launch['executable_path']=os.environ['CHROMIUM_EXECUTABLE']
            browser=pw.chromium.launch(**launch)
            ctx=browser.new_context(viewport={'width':1440,'height':1000})
            page=ctx.new_page();page.set_default_timeout(8000)
            page.on('pageerror',lambda e: errors.append('JavaScript: '+str(e)))
            for width in (320,390,768,1440):
                page.set_viewport_size({'width':width,'height':1000})
                for name,path in [('search','search/index.html'),('guide','learn/motivation/index.html'),('goals','read/PSY-MOT-004/index.html'),('rewards','read/PSY-MOT-007/index.html')]:
                    go(page,path)
                    check(page.locator('h1').count()==1,f'{name}/{width}: one h1')
                    check(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),f'{name}/{width}: no horizontal page overflow')
                    if width in (390,1440):
                        fn=f'motivation-{name}-{width}.png';page.screenshot(path=str(out/fn),full_page=True);screenshots.append(fn)
            go(page,'search/index.html')
            check(len(ids(page))==24,'default pagination remains 24')
            check(all(t in site.READERS for t in ids(page)), 'unfiltered relevance view prioritizes actual articles, not placeholders')
            page.select_option('#search-category','motivation')
            check(ids(page)==seq and page.input_value('#search-group')=='habits','specific category selects all ten real motivation topics and parent')
            page.select_option('#search-status','pending')
            check(not ids(page) and page.locator('#no-results').is_visible(),'fully written category has honest zero pending result')
            page.select_option('#search-status','draft')
            page.fill('#search-query','ご褒美');page.locator('#topic-search').evaluate('(f)=>f.requestSubmit()')
            check(ids(page)==['PSY-MOT-007'],'keyword + specific category + article status intersect')
            page.fill('#search-query','');page.locator('#topic-search').evaluate('(f)=>f.requestSubmit()')
            page.select_option('#search-group','research')
            check(page.input_value('#search-category')=='' and page.locator('#search-category option').count()==2,'group change clears incompatible category and rebuilds options')
            page.locator('[data-reset-search]').first.click()
            check(page.locator('#search-category option').count()==29 and page.input_value('#search-sort')=='relevance' and len(ids(page))==24,'reset restores all groups, categories and default order')
            page.select_option('#search-sort','updated')
            got=ids(page)
            expected=sorted(site.TOPICS,key=lambda t:site.REFERENCES.updates.get(t,{}).get('updated_on',''),reverse=True)[:24]
            check(got==expected,'update order uses actual dates with stable canonical tie order')
            check(page.locator('#sort-note').is_visible(),'update order explains unknown dates')
            page.locator('[data-reset-search]').first.click()
            page.fill('#search-query','<script>');page.locator('#topic-search').evaluate('(f)=>f.requestSubmit()')
            check(not ids(page),'markup input is treated as plain text')
            if not offline:
                go(page,'search/index.html?category=motivation&status=draft&sort=updated&q=%E7%9B%AE%E6%A8%99')
                initial=ids(page);page.reload(wait_until='networkidle')
                check(initial==ids(page) and bool(initial) and page.input_value('#search-category')=='motivation' and page.input_value('#search-sort')=='updated','precise URL survives reload with query/status/sort')
                go(page,'search/index.html?group=health&category=motivation&page=999')
                check(page.input_value('#search-group')=='habits' and ids(page)==seq,'specific URL category takes precedence over conflicting group and page clamps')
                go(page,'search/index.html?category=missing&group=missing&sort=missing&page=-2')
                check(page.input_value('#search-group')=='' and page.input_value('#search-category')=='' and page.input_value('#search-sort')=='relevance' and len(ids(page))==24,'invalid URL filters reset safely')
                for cid in site.CATEGORIES:
                    go(page,'search/index.html?category='+cid+'&status=draft')
                    expected_ids=[t for t in site.TOPICS if site.TOPICS[t]['category_id']==cid and t in site.READERS]
                    check(ids(page)==expected_ids,'real category URL results: '+cid)
                go(page,'topics/category/motivation/index.html');page.locator('.category-search a').click();page.wait_for_load_state('networkidle')
                check(ids(page)==seq and page.input_value('#search-status')=='draft','category link lands in exact filtered search')
                page.select_option('#search-category','decisions')
                params=parse_qs(urlsplit(page.url).query)
                check(params.get('category')==['decisions'],'interactive filter is serialized to shareable URL')
                page.go_back(wait_until='networkidle')
                check('/topics/category/motivation/' in page.url,'browser back returns to originating category')
                go(page,'learn/motivation/index.html');page.locator('.learning-steps a').first.click();page.wait_for_load_state('networkidle')
                check('PSY-MOT-001' in page.url,'guide first link reaches actual article')
            page.set_viewport_size({'width':320,'height':1000});go(page,'read/PSY-MOT-004/index.html')
            page.locator('[data-reader-size="22"]').click();page.locator('.study-scope summary').click()
            check(page.locator('table').is_visible() and page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'goal table and expanded scope fit largest text at 320px')
            go(page,'search/index.html');page.set_viewport_size({'width':640,'height':1000});page.evaluate('document.documentElement.style.zoom="2"')
            check(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'search reflows at 200 percent')
            plainctx=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':1000})
            plain=plainctx.new_page();go(plain,'search/index.html',False)
            check(plain.locator('.search-result:visible').count()==len(site.TOPICS),'noJS: every topic remains available')
            check(plain.locator('#search-enhancements').is_hidden(),'noJS: inactive filter controls are not shown')
            go(plain,'learn/motivation/index.html',False)
            check(plain.locator('.learning-steps a').count()==10,'noJS: all ten guide steps are real links')
            go(plain,'read/PSY-MOT-007/index.html',False)
            plain.locator('.study-scope summary').focus();plain.keyboard.press('Enter')
            check(plain.locator('.study-scope').get_attribute('open') is not None,'noJS: scope disclosure opens by keyboard')
            plainctx.close();ctx.close();browser.close()
    except Exception as exc:
        errors.append(type(exc).__name__+': '+str(exc))
    finally:
        if server:
            server.shutdown();server.server_close()
    result=dict(schema_version='1.0',passed=not errors,checks=len(checks),check_labels=checks,errors=errors,edited_articles=len(BATCH),new_articles=len(NEW),rewritten_legacy_articles=len(BATCH-NEW),claim_count=len(claims),search_categories=len(site.CATEGORIES),recorded_updates=len(site.REFERENCES.updates),screenshots=screenshots,execution_mode='offline_inline_local_render' if offline else 'real_local_HTTP_browser',navigation_verified=not offline and not errors,scientific_validity_certified=False,independent_review_completed=False,human_usability_test_completed=False)
    (ROOT/'docs/READER_MOTIVATION_TESTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='check_labels'},ensure_ascii=False,indent=2))
    if errors:
        raise SystemExit(1)

if __name__=='__main__':
    main()
