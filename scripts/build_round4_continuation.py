#!/usr/bin/env python3
"""Build additive Round 4 research drafts without mutating the old canonical registry.

All new metadata is bibliography-level unless its prior review status is retained.
Search retrieval is never promoted to abstract/full-text review automatically.
No abstracts, full texts, secrets or personal data are committed.
"""
from __future__ import annotations
import collections
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/research/round4_continuation'
DOCS = ROOT / 'docs/round4_continuation'
ARTICLES = ROOT / 'articles/drafts/round4_continuation'
DATE = '2026-09-11'
API = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search'
HTTP_LOG: list[dict] = []
CACHE: dict[str, dict | None] = {}


def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def text(path: Path, value: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + '\n', encoding='utf-8')


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def normalized(value: str) -> str:
    return ' '.join(re.findall(r'[a-z0-9]+', html.unescape(re.sub('<[^>]+>', ' ', value)).lower()))


def tokens(value: str) -> set[str]:
    return set(normalized(value).split()) - {'a','an','the','of','and','in','on','to','for','with','is','as','by','at','its'}


def doi_clean(value: str | None) -> str:
    return re.sub(r'^https?://(dx\.)?doi\.org/', '', value or '', flags=re.I).strip().lower()


def get_json(url: str):
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'PsychologyBlogResearch/1.0 (bibliographic verification)', 'Accept':'application/json'})
            with urllib.request.urlopen(req, timeout=18) as response:
                raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise ValueError('Response exceeds metadata limit')
            obj = json.loads(raw)
            HTTP_LOG.append({'url':url,'status':'completed','date':DATE})
            return obj
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            last = str(exc)
            if attempt < 2:
                time.sleep(0.4 * (attempt + 1))
    HTTP_LOG.append({'url':url,'status':'failed','date':DATE,'error':last})
    return None


def acceptable_date(value: str | None) -> bool:
    return not value or value[:10] <= DATE


def epmc_metadata(row: dict, via: str) -> dict:
    pmid = row.get('pmid') or (str(row.get('id')) if row.get('source') == 'MED' else None)
    return {'title':html.unescape(re.sub('<[^>]+>','',row.get('title',''))),
            'authors_display':row.get('authorString'), 'year':int(row['pubYear']) if str(row.get('pubYear','')).isdigit() else None,
            'doi':row.get('doi'), 'pmid':pmid,
            'journal':row.get('journalInfo',{}).get('journal',{}).get('title'),
            'url':('https://pubmed.ncbi.nlm.nih.gov/'+pmid+'/') if pmid else 'https://europepmc.org/article/'+row.get('source','')+'/'+str(row.get('id','')),
            'verified_via_url':via,'first_publication_date':row.get('firstPublicationDate'),
            'verification_scope':'bibliography_verified', 'abstract_available_not_read':bool(row.get('abstractText')),
            'indexed_related_records':row.get('commentCorrectionList',{}).get('commentCorrection',[]),
            'correction_retraction_check':'metadata_links_only_not_exhaustive',
            'notes_ja':'書誌照合のみ。抄録が返っても自動で読解済みにしない。本文の正式な評価は未実施。'}


def crossref_metadata(row: dict, via: str) -> dict:
    dates = row.get('published',{}).get('date-parts', [[]])[0]
    first = '-'.join(str(x).zfill(4 if i==0 else 2) for i,x in enumerate(dates)) if dates else None
    if first and len(first)==4:
        first += '-01-01'
    elif first and len(first)==7:
        first += '-01'
    authors = '; '.join(' '.join(str(a.get(k,'')) for k in ('family','given')).strip() for a in row.get('author',[]))
    return {'title':(row.get('title') or [''])[0], 'authors_display':authors or None,
            'year':dates[0] if dates else None, 'doi':row.get('DOI'), 'pmid':None,
            'journal':(row.get('container-title') or [None])[0], 'url':'https://doi.org/'+row.get('DOI',''),
            'verified_via_url':via, 'first_publication_date':first, 'verification_scope':'bibliography_verified',
            'abstract_available_not_read':bool(row.get('abstract')), 'indexed_related_records':row.get('update-to',[]),
            'correction_retraction_check':'metadata_links_only_not_exhaustive',
            'notes_ja':'Crossrefの書誌照合のみ。論文の効果・信頼性・全文読解完了を意味しない。'}


def matches(meta: dict, selector: dict, by_identifier: bool) -> bool:
    if not acceptable_date(meta.get('first_publication_date')):
        return False
    candidate = normalized(meta.get('title',''))
    required = selector.get('required_terms') or selector.get('expected_title_words') or []
    if any(normalized(word) not in candidate for word in required):
        return False
    if selector.get('title'):
        wanted = tokens(selector['title']); found = tokens(meta.get('title',''))
        similarity = len(wanted & found) / max(1, len(wanted | found))
        if similarity < (0.55 if by_identifier else 0.78):
            return False
    return bool(meta.get('title')) and (by_identifier or bool(required) or bool(selector.get('title')))


def resolve(selector: dict, sources: list[dict]) -> dict | None:
    cache_key = json.dumps(selector, sort_keys=True)
    if cache_key in CACHE:
        return CACHE[cache_key]
    for source in sources:
        pmid = str(source.get('pmid') or '')
        if not pmid:
            hit = re.search(r'pubmed\.ncbi\.nlm\.nih\.gov/(\d+)', source.get('url',''))
            pmid = hit.group(1) if hit else ''
        found = ((selector.get('pmid') and pmid == str(selector['pmid'])) or
                 (selector.get('doi') and doi_clean(source.get('doi')) == doi_clean(selector['doi'])) or
                 (selector.get('url') and source.get('url') == selector['url']) or
                 (selector.get('title') and normalized(source.get('title','')) == normalized(selector['title'])))
        if found:
            item = dict(source)
            item['registry_origin'] = 'existing_canonical_source'
            item['canonical_source_id'] = source['id']
            item['reverified_in_this_run'] = False
            CACHE[cache_key] = item
            return item
    if selector.get('url'):
        # A URL alone is a research pointer, not a claim that the page was read.
        CACHE[cache_key] = None
        return None
    if selector.get('pmid'):
        query = 'EXT_ID:'+str(selector['pmid'])+' AND SRC:MED'
    elif selector.get('doi'):
        query = 'DOI:"'+doi_clean(selector['doi'])+'"'
    elif selector.get('title'):
        query = 'TITLE:"'+selector['title'].replace('"','')+'"'
    else:
        query = selector.get('query','')
    query = '('+query+') AND FIRST_PDATE:[1900-01-01 TO '+DATE+']'
    via = API+'?'+urllib.parse.urlencode({'query':query,'format':'json','resultType':'core','pageSize':5})
    result = get_json(via)
    identifier = bool(selector.get('pmid') or selector.get('doi'))
    if result:
        for row in result.get('resultList',{}).get('result',[]):
            item = epmc_metadata(row, via)
            if matches(item, selector, identifier):
                CACHE[cache_key] = item
                return item
    if selector.get('doi'):
        via = 'https://api.crossref.org/works/'+urllib.parse.quote(doi_clean(selector['doi']), safe='')
        result = get_json(via)
        rows = [result.get('message',{})] if result else []
    else:
        via = 'https://api.crossref.org/works?'+urllib.parse.urlencode({'query.bibliographic':selector.get('title') or selector.get('query',''),'rows':5})
        result = get_json(via)
        rows = result.get('message',{}).get('items',[]) if result else []
    for row in rows:
        item = crossref_metadata(row, via)
        if matches(item, selector, bool(selector.get('doi'))):
            CACHE[cache_key] = item
            return item
    CACHE[cache_key] = None
    return None


def source_key(source: dict) -> str:
    if source.get('canonical_source_id'):
        return source['canonical_source_id']
    ident = doi_clean(source.get('doi')) or str(source.get('pmid')) or source.get('url') or source['title']
    return 'R4SRC-'+hashlib.sha256(ident.encode()).hexdigest()[:12]


def main():
    categories = read(ROOT/'data/categories.json')['categories']
    topics = {t['id']:dict(t,category_id=c['id']) for c in categories for t in read(ROOT/c['file'])['topics']}
    canonical_sources = read(ROOT/'data/sources.json')['sources']
    assert len(topics) == 300, 'Unexpected topic snapshot: reconcile before applying.'
    specs = []
    for path in sorted((ROOT/'research').glob('round4_continuation_0[1-4].json')):
        specs.extend(read(path)['articles'])
    assert len(specs)==20 and len({s['topic_id'] for s in specs})==20, 'Missing or duplicate authored drafts.'
    assert {s['topic_id'] for s in specs} <= set(topics), 'Unknown authored topic.'
    gap_specs = read(ROOT/'research/round4_continuation_gaps.json')['topics']
    assert len(gap_specs)==29 and len({s['topic_id'] for s in gap_specs})==29
    ranking = read(ROOT/'data/rankings/editorial_topics.json')
    order = []
    for item in walk(ranking):
        tid = item.get('topic_id') or item.get('id')
        if tid in topics and tid not in order:
            order.append(tid)
    assert len(order)>=20, 'Cannot identify editorial top20 without guessing.'
    top20 = order[:20]
    register: dict[str,dict] = {}

    def add(meta):
        key = source_key(meta)
        meta = dict(meta, id=key)
        register.setdefault(key, meta)
        return key

    gap_results=[]
    for spec in gap_specs:
        refs=[]; attempts=[]
        for selector in spec['selectors']:
            meta=resolve(selector, canonical_sources)
            attempts.append({'selector':selector,'status':'bibliography_matched' if meta else 'unresolved'})
            if meta:
                sid=add(meta)
                if sid not in refs:
                    refs.append(sid)
        gap_results.append(dict(spec, source_ids=refs, resolution_attempts=attempts,
            status='bibliography_matched_needs_content_review' if refs else 'source_unresolved',
            canonical_registry_mutated=False, publication_ready=False,
            illustrative_example={'type':'illustrative_scenario','text_ja':spec['example'],'observed_in_a_study':False}))

    articles=[]; claim_documents=[]
    for spec in specs:
        tid=spec['topic_id']; refs={}; pending=[]
        for selector in spec['source_selectors']:
            meta=resolve(selector, canonical_sources)
            if meta:
                refs[selector['key']]=add(meta)
            else:
                pending.append(selector['key'])
        claims=[]
        for index, claim in enumerate(spec['claims'],1):
            keys=claim['sources']
            resolved=[refs[k] for k in keys if k in refs]
            claims.append({'id':f'CL-{tid}-{index:02d}','topic_id':tid,'statement_ja':claim['text'],
                'source_ids':resolved,'unresolved_source_keys':[k for k in keys if k not in refs],
                'scope_ja':claim['scope'],'cannot_infer_ja':claim['not_supported'],
                'status':'draft_from_existing_notes' if keys and len(resolved)==len(keys) else 'editorial_or_unresolved',
                'formal_certainty':'not_assessed','independent_fulltext_audit':False,'publication_ready':False})
        claimdoc={'schema_version':'1.0','topic_id':tid,'title':topics[tid]['title_ja'],'claims':claims,
                  'basis':'existing research notes and explicitly labelled editorial reasoning',
                  'readiness':'draft_not_final_evidence_assessment','publication_ready':False}
        claim_documents.append(claimdoc)
        write(OUT/'claims'/f'{tid}.json',claimdoc)
        lines=['# '+spec['title'],'','> 執筆段階：初稿。出典との最終照合・独立した編集確認前。公開可能な完成稿ではありません。','',spec['lead'],'']
        number={key:i+1 for i,key in enumerate(refs)}
        for section in spec['sections']:
            marks=' '.join(f"[{number[k]}]" for k in section['sources'] if k in number)
            missing=[k for k in section['sources'] if k not in number]
            lines += ['## '+section['heading'],'',section['text'] + (' '+marks if marks else ''),'']
            if missing:
                lines += ['> 編集確認：この段落の出典照合が未完了です。未確認のまま公開しないでください。','']
        lines += ['## 参考資料と確認範囲','']
        for key,sid in refs.items():
            src=register[sid]
            lines += [f"{number[key]}. {src.get('authors_display') or '著者情報はリンク先'} ({src.get('year') or '年未確認'}). {src['title']} — {src['url']}",
                      f"   資料ID: {sid}。台帳上の確認範囲: {src.get('verification_scope','未確認')}。今回、過去の確認範囲を自動で全文評価済みに変更していません。",'']
        lines += ['## 編集用・主張と限界','']
        for c in claims:
            lines += [f"### {c['id']}",c['statement_ja'],
                      '対象・範囲：'+c['scope_ja'],
                      'ここからは言えないこと：'+c['cannot_infer_ja'],
                      '出典：'+(', '.join(c['source_ids']) or '編集上の判断、または出典照合待ち'),'']
        lines += ['## 生活への応用の位置付け','',
                  '具体例は説明用の想定場面です。研究で実際に試した手順と同一とは限りません。',
                  spec['application']['safety'],'']
        if spec.get('editorial_hold'):
            lines += ['公開前の保留事項：'+spec['editorial_hold'],'']
        path=ARTICLES/f'{tid}.md'; text(path,'\n'.join(lines))
        articles.append({'topic_id':tid,'title':spec['title'],'path':str(path.relative_to(ROOT)),
                         'claim_file':str((OUT/'claims'/f'{tid}.json').relative_to(ROOT)),
                         'wording_source_audit':'pending','status':'article_draft',
                         'canonical_editorial_top20':tid in top20,'source_resolution_pending':pending,
                         'editorial_hold':spec.get('editorial_hold'), 'publication_ready':False})
        write(OUT/'applications'/f'{tid}.json',{'schema_version':'1.0','topic_id':tid,
              'application':spec['application'],'classification':'editorial_application_not_automatically_verified_intervention',
              'claim_ids':[c['id'] for c in claims],'publication_ready':False})

    supplied={d['topic_id']:d for d in claim_documents}
    top20_rows=[]
    for tid in top20:
        if tid not in supplied:
            # Do not invent an article's claims merely to achieve a count.
            doc={'schema_version':'1.0','topic_id':tid,'title':topics[tid]['title_ja'],
                 'status':'claim_extraction_pending','claims':[],
                 'existing_source_ids':topics[tid].get('source_ids',[]),
                 'next_action_ja':'当該テーマの既存読解メモから主張を抽出し、対象・比較・反証・限界を個別に確認する。',
                 'publication_ready':False}
            write(OUT/'claims'/f'{tid}.json',doc)
        top20_rows.append({'topic_id':tid,'title':topics[tid]['title_ja'],
                           'claim_file':str((OUT/'claims'/f'{tid}.json').relative_to(ROOT)),
                           'status':'claim_map_draft' if tid in supplied else 'claim_extraction_pending'})
    report={'schema_version':'1.0','date':DATE,'final_goal_articles':300,
            'goal_completed':False,'new_authored_drafts':len(articles),
            'new_publication_ready_articles':0,
            'editorial_top20_ids':top20,
            'editorial_top20_claim_map_drafts':sum(tid in supplied for tid in top20),
            'editorial_top20_claim_extraction_pending':[tid for tid in top20 if tid not in supplied],
            'authored_claim_count':sum(len(d['claims']) for d in claim_documents),
            'application_dossiers':len(articles),
            'gap_topics_requested':len(gap_results),
            'gap_topics_with_matched_bibliography':sum(bool(g['source_ids']) for g in gap_results),
            'gap_topics_unresolved':[g['topic_id'] for g in gap_results if not g['source_ids']],
            'supplemental_source_record_count':len(register),
            'canonical_registry_mutated':False,
            'canonical_registration_status':'supplement_staged_not_merged_into_legacy_sources_or_rankings',
            'new_sources_abstract_reviewed_automatically':0,
            'limits_ja':['新規検索結果は書誌の照合であり、抄録・全文の読解完了とは別。',
                         '既存台帳の情報は引き継ぐが、今回独立して全文を再評価したとは記録しない。',
                         'この補完パッケージを旧台帳へ反映する際は、重複、出典評価、テーマ対応、件数、順位を一括検証する。',
                         '20本は初稿・構成稿であり、完成記事300本に数えない。',
                         '上位20テーマと執筆済み20テーマは実データで照合し、不一致を隠さない。',
                         'ツールの結果受信が不安定な状況に備え、保存と公開完了を混同しない。']}
    write(OUT/'sources.json',{'schema_version':'1.0','sources':list(register.values())})
    write(OUT/'gap_dossiers.json',{'schema_version':'1.0','topics':gap_results})
    write(OUT/'top20_claim_index.json',{'schema_version':'1.0','topics':top20_rows})
    write(OUT/'articles.json',{'schema_version':'1.0','articles':articles})
    write(OUT/'http_log.json',{'schema_version':'1.0','requests':HTTP_LOG})
    write(OUT/'report.json',report)
    lines=['# 第4回・継続成果物の状態','',
           f"最終目標：300記事。今回追加した初稿・構成稿：{len(articles)}本。公開可能な完成稿への昇格：0本。",'',
           f"未登録29テーマのうち書誌を照合できたテーマ：{report['gap_topics_with_matched_bibliography']}件。これは内容確認済みの件数ではありません。",'',
           f"実際の編集上位20テーマに対応する主張マップの初稿：{report['editorial_top20_claim_map_drafts']}件。",'',
           '**重要：** 補完資料は独立した追記パッケージに保存し、旧台帳の出典数・未登録件数を推測で変更していません。','',
           '## 記事の初稿','']
    for a in articles:
        lines.append(f"- [{a['title']}](../../{a['path']}) — {a['topic_id']} / 初稿・最終確認前")
    lines += ['', '## 未登録テーマの資料補完', '', '| ID | テーマ | 書誌照合 | 範囲の注意 |','|---|---|---|---|']
    for g in gap_results:
        lines.append('| '+g['topic_id']+' | '+topics[g['topic_id']]['title_ja'].replace('|','／')+' | '+str(len(g['source_ids']))+' | '+g['limit'].replace('|','／')+' |')
    lines += ['', '## 完成稿へ進む前の確認',''] + report['limits_ja']
    text(DOCS/'REPORT.md','\n'.join(lines))
    text(DOCS/'REVIEW_CHECKLIST.md','''# 記事を完成稿へ進める確認

本文の各主張について、根拠が直接扱う対象・比較・結果・期間を特定します。抄録から確認したことと、本文・補足資料で確認したことを分けます。引用数や有名さで品質を置き換えません。

特にカフェインは量と時刻、習慣形成は研究全数と日数を報告した研究数、休憩は疲労と成績、通信制限は解析集団と遵守率を照合します。選択肢過多の訂正と、食事中のテレビを扱う別レビューの数値不整合は、対象論文・ページ・値を具体的に記録してから解消します。

生活への提案は、試験の手順そのものか、研究を参考にした提案か、単なる説明例かをラベルで区別します。医療や依存に関わる内容は国内の現在の適用と安全性の確認を必要とします。

主張表、本文、参考文献が一致し、未確認の数値や過剰な一般化がないことを確認します。文体・重複・読者への関連性を編集し、必要な安全確認を終えるまでpublication_readyをtrueにしません。
''')
    # Fail on internal contradictions, not on an honestly unresolved source.
    assert all(a['publication_ready'] is False for a in articles)
    assert len({a['topic_id'] for a in articles})==len(articles)
    assert all(Path(ROOT/a['path']).is_file() for a in articles)
    for d in claim_documents:
        for claim in d['claims']:
            assert set(claim['source_ids']) <= set(register)
    for path in OUT.rglob('*.json'):
        obj=read(path); assert obj['schema_version']=='1.0'
        for node in walk(obj):
            assert not ({'abstractText','full_text','fullText'} & set(node)), 'Raw source text leaked.'
    write(OUT/'validation.json',{'schema_version':'1.0','status':'passed',
          'scope':'JSON, IDs, source references, draft labels, file existence; not scientific truth or final editorial approval'})
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
