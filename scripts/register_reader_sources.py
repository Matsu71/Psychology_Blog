#!/usr/bin/env python3
"""Apply a reviewed, idempotent source migration; canonical data stays in data/.

No title/order/state or existing review score is replaced. A source-ID/DOI
collision stops the migration. Rerun build_research_views.py afterwards.
"""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
def read(path):return json.loads((ROOT/path).read_text())
def save(path,value):(ROOT/path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def main():
    packs=[read('site/research_additions.json')]
    if (ROOT/'site/foundation_sources.json').exists():packs.append(read('site/foundation_sources.json'))
    pack={'entries':[e for p in packs for e in p['entries']], 'updated_on':max(p['updated_on'] for p in packs)}
    sources=read('data/sources.json'); assessments=read('data/source_assessments.json')
    cats=read('data/categories.json')['categories']
    docs={c['file']:read(c['file']) for c in cats}
    loc={t['id']:(path,t) for path,d in docs.items() for t in d['topics']}
    edgefiles=read('data/evidence/catalog.json')['files']
    edgedocs={p:read(p) for p in edgefiles}
    added=[]
    for item in pack['entries']:
        tid=item['topic_id']; source=item['source']; sid=source['id']
        old=next((s for s in sources['sources'] if s['id']==sid),None)
        if old:
            if old.get('doi')!=source.get('doi') or old['title']!=source['title']:
                raise ValueError('Source-ID collision: '+sid)
        else:
            if source.get('doi') and any((s.get('doi') or '').lower()==source['doi'].lower() for s in sources['sources']):
                raise ValueError('DOI already registered: '+sid)
            sources['sources'].append(source); assessments['assessments'].append(item['assessment']);added.append(sid)
        path,topic=loc[tid]
        if sid not in topic['source_ids']:topic['source_ids'].append(sid)
        candidates=[d for d in edgedocs.values() if any(e['topic_id']==tid for e in d['edges'])]
        if len(candidates)!=1:raise ValueError('Ambiguous edge file: '+tid)
        edges=candidates[0]['edges']
        if not any(e['topic_id']==tid and e['source_id']==sid for e in edges):
            edges.append({'id':'EV-'+tid+'-'+sid,'topic_id':tid,'source_id':sid,'relation_role':'reader_definition_or_result','relevance_1_to_5':None,'relevance_scope':'selected_claim_scope_not_scored','source_review_id':None,'legacy_brief_ids':[],'finding_scope_ja':source['notes_ja'],'conclusion_direction':'not_classified','limits_ja':'読者版の指定主張に使用。サイト全体の内容確認や効果保証ではない。正式な採点は未実施。','formal_evidence_certainty':'not_assessed'})
    # Keep older research links, but identify two non-direct links explicitly.
    for doc in edgedocs.values():
        for edge in doc['edges']:
            if (edge['topic_id'],edge['source_id']) in [('PSY-ATT-001','SRC055'),('PSY-DEC-001','SRC067')]:
                edge['relation_role']='context_only'
                edge['limits_ja']='通知の中断／誤情報への注意喚起を扱う背景資料。今回の課題切り替え／確証バイアスの定義に直接対応する資料としては使わない。従来の書誌・主張記録は保持。'
    save('data/sources.json',sources);save('data/source_assessments.json',assessments)
    for p,d in docs.items():save(p,d)
    for p,d in edgedocs.items():save(p,d)
    m=read('data/manifest.json');m['source_count']=len(sources['sources']);m['updated_on']=pack['updated_on'];save('data/manifest.json',m)
    coverage=read('data/research/coverage.json')
    coverage['source_count']=len(sources['sources'])
    coverage['updated_on']=pack['updated_on']
    coverage['evidence_edge_count']=sum(len(d['edges']) for d in edgedocs.values())
    coverage['selected_fulltext_checks_count']=sum(a['review_scope']=='selected_fulltext_sections' for a in assessments['assessments'])
    save('data/research/coverage.json',coverage)
    print('Reader-source migration:',', '.join(added) if added else 'already applied')
if __name__=='__main__':main()
