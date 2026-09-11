#!/usr/bin/env python3
"""One-time compatibility upgrade; narrow, checked replacements only."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def replace_once(path, old, new):
    p=ROOT/path
    body=p.read_text(encoding='utf-8')
    if new in body:
        return
    if body.count(old)!=1:
        raise ValueError('Unexpected source version; reconcile before patching: '+path)
    p.write_text(body.replace(old,new),encoding='utf-8')


def main():
    replace_once('scripts/validate.py',
        "source_types = {'journal_article', 'official_health_information', 'official_bibliography'}",
        "source_types = {'journal_article', 'book_chapter', 'official_health_information', 'official_bibliography'}")
    replace_once('scripts/validate_research.py',
        "candidates = read('data/literature/candidates.json')['papers']",
        "catalog_path = ROOT / 'data/literature/catalog.json'\n    catalog = read('data/literature/catalog.json') if catalog_path.exists() else {'candidate_files':['data/literature/candidates.json'], 'search_files':['data/literature/search_log.json']}\n    candidates = [p for path in catalog['candidate_files'] for p in read(path)['papers']]")
    replace_once('scripts/validate_research.py',
        "searches = read('data/literature/search_log.json')['searches']",
        "searches = [s for path in catalog['search_files'] for s in read(path)['searches']]")
    replace_once('.github/workflows/validate.yml',
        '            python3 scripts/validate_research.py --export build\n          fi',
        '            python3 scripts/validate_research.py --export build\n          fi\n          if [ -f data/research/source_reviews.json ]; then\n            python3 scripts/validate_round3.py --export build\n          fi')
    # Historical actions contained destructive resets to an earlier snapshot.
    # They are no longer valid entry points once new source IDs have been added.
    for name in ['materialize-research','refine-relevance']:
        path=ROOT/('.github/workflows/'+name+'.yml')
        path.write_text('name: Archived '+name+' snapshot action\non:\n  workflow_dispatch:\npermissions:\n  contents: read\njobs:\n  notice:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo "This historical importer is archived. Edit canonical JSON and run the read-only validators instead."\n',encoding='utf-8')
    p=ROOT/'.gitignore'
    body=p.read_text()
    for item in ['_round3/','_resolved/','round3_output/','resolved_output/']:
        if item not in body.splitlines(): body+=item+'\n'
    p.write_text(body)

if __name__=='__main__':
    main()
