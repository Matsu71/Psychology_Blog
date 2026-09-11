#!/usr/bin/env python3
"""Read a small topic dossier or one source; no network or side effects."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('kind',choices=['topic','source','queue'])
    p.add_argument('id',nargs='?')
    p.add_argument('--limit',type=int,default=5)
    a=p.parse_args()
    if not 1<=a.limit<=30:
        p.error('--limit must be from 1 to 30')
    try:
        if a.kind=='queue':
            result=read('data/rankings/research_queue.json')['topics'][:a.limit]
        elif a.kind=='source':
            source=next(s for s in read('data/sources.json')['sources'] if s['id']==a.id)
            assessment=next(s for s in read('data/source_assessments.json')['assessments'] if s['source_id']==a.id)
            result={'source':source,'assessment':assessment}
        else:
            entry=next(t for t in read('data/index/topics.json')['topics'] if t['topic_id']==a.id)
            topic=next(t for t in read(entry['topic_file'])['topics'] if t['id']==a.id)
            ranking=next(t for t in read(entry['ranked_sources_file'])['topics'] if t['topic_id']==a.id)
            rows=ranking['sources'][:a.limit]
            ids={r['source_id'] for r in rows}
            result={'topic':topic,'source_priority':rows,
                'evidence_edges':[e for e in read(entry['evidence_file'])['edges'] if e['topic_id']==a.id and e['source_id'] in ids],
                'sources':[s for s in read('data/sources.json')['sources'] if s['id'] in ids],
                'assessments':[s for s in read('data/source_assessments.json')['assessments'] if s['source_id'] in ids]}
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError,KeyError,StopIteration) as e:
        print('LOOKUP FAILED: unknown ID or invalid database: '+str(e),file=sys.stderr)
        return 1
if __name__=='__main__':
    raise SystemExit(main())
