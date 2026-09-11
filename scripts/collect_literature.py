#!/usr/bin/env python3
"""One-shot literature discovery using public Europe PMC metadata.

Search hits are CANDIDATES, never evidence endorsements. Abstracts are kept only
in the temporary review artifact, not in the repository or public database.
No credentials are sent to external literature services. Standard library only.
"""
from __future__ import annotations
import concurrent.futures
import datetime as dt
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
API = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search'
CUTOFF = '2026-09-11'
OUT = ROOT / 'research_output'


def search(query: str) -> tuple[list[dict], str]:
    full_query = '(' + query + ') AND FIRST_PDATE:[1900-01-01 TO ' + CUTOFF + ']'
    params = urllib.parse.urlencode({'query': full_query, 'format': 'json', 'resultType': 'core', 'pageSize': 5})
    url = API + '?' + params
    error = ''
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'PsychologyBlogLiteratureDiscovery/1.0', 'Accept': 'application/json'})
            with urllib.request.urlopen(request, timeout=25) as response:
                body = json.load(response)
            records = body.get('resultList', {}).get('result', [])
            if not isinstance(records, list):
                raise ValueError('Unexpected API response')
            return records, url
        except Exception as exc:
            error = type(exc).__name__ + ': ' + str(exc)
            time.sleep(1 + attempt)
    raise RuntimeError(error)


def process(task: dict) -> dict:
    result = {'task_id': task['id'], 'topic_id': task.get('topic_id'), 'requested_title': task.get('title'), 'kind': task['kind'], 'query': task['query'], 'searched_at_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
    try:
        rows, url = search(task['query'])
        result.update(status='completed', api_url=url, records=rows)
    except Exception as exc:
        result.update(status='failed', error=str(exc), records=[])
    print(json.dumps({'task_id': task['id'], 'status': result['status'], 'hits': len(result['records'])}, ensure_ascii=False), flush=True)
    return result


def main() -> None:
    OUT.mkdir(exist_ok=True)
    tasks = json.loads((ROOT / 'scripts/research_queries.json').read_text())['queries']
    for path in sorted((ROOT / 'data/topics').glob('*.json')):
        for topic in json.loads(path.read_text())['topics']:
            concept = topic['concepts_en'][0].replace('"', '')
            tasks.append({'id': 'DISC-' + topic['id'], 'topic_id': topic['id'], 'kind': 'topic_discovery', 'query': 'TITLE_ABS:"' + concept + '" AND SRC:MED'})
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(process, tasks))
    # Normalized bibliography and transient abstract bundle are intentionally separate.
    papers = {}
    links = []
    for result in results:
        ids = []
        for row in result['records']:
            pid = row.get('source', 'UNKNOWN') + ':' + str(row.get('id', ''))
            ids.append(pid)
            papers[pid] = row
        links.append({k: v for k, v in result.items() if k != 'records'} | {'candidate_ids': ids})
    normalized = []
    for pid, row in papers.items():
        info = row.get('journalInfo', {})
        normalized.append({'id': pid, 'title': row.get('title'), 'authors': row.get('authorString'), 'year': row.get('pubYear'), 'first_publication_date': row.get('firstPublicationDate'), 'journal': info.get('journal', {}).get('title'), 'doi': row.get('doi'), 'pmid': row.get('pmid'), 'pmcid': row.get('pmcid'), 'url': 'https://europepmc.org/article/' + pid.replace(':', '/'), 'publication_types': row.get('pubTypeList', {}).get('pubType', []), 'abstract_available': bool(row.get('abstractText')), 'is_open_access': row.get('isOpenAccess'), 'cited_by_count_at_collection': row.get('citedByCount'), 'candidate_status': 'machine_retrieved_not_screened', 'correction_retraction_check': 'not_completed'})
    summary = {'schema_version': '1.0', 'cutoff': CUTOFF, 'task_count': len(tasks), 'successful_searches': sum(x['status'] == 'completed' for x in results), 'failed_searches': sum(x['status'] == 'failed' for x in results), 'unique_candidate_count': len(papers), 'warning_ja': '検索結果は未選別の候補です。題名の類似や引用数は研究の妥当性を保証しません。抄録と全文精査・撤回確認は別工程です。'}
    for name, obj in [('metadata.json', {'schema_version': '1.0', 'summary': summary, 'papers': normalized, 'searches': links}), ('reader_bundle.json', {'summary': summary, 'papers': papers, 'searches': links})]:
        (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('COLLECTION_SUMMARY ' + json.dumps(summary, ensure_ascii=False), flush=True)
    if not papers:
        raise SystemExit('No papers retrieved; inspect API errors before retrying.')

if __name__ == '__main__':
    main()
