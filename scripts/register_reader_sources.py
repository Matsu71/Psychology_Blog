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
    if (ROOT/'site/learning_sources.json').exists():packs.append(read('site/learning_sources.json'))
    if (ROOT/'site/emotion_sources.json').exists():packs.append(read('site/emotion_sources.json'))
    if (ROOT/'site/wellbeing_sources.json').exists():packs.append(read('site/wellbeing_sources.json'))
    if (ROOT/'site/motivation_sources.json').exists():packs.append(read('site/motivation_sources.json'))
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
            if (edge['topic_id'],edge['source_id']) in [('PSY-LEA-002','SRC092'),('PSY-LEA-007','SRC084')]:
                edge['relation_role']='context_only'
                edge['limits_ja']='第二言語の習得年齢／好奇心の研究。分散学習／学習判断の主張を直接支える根拠として読者版で使用しない。既存ID・書誌・確認記録は保持。'
    # Non-direct seed links are retained as background, not silently deleted.
    context_pairs={('PSY-EMO-001','SRC096'),('PSY-EMO-004','SRC105'),('PSY-EMO-005','SRC056'),('PSY-EMO-007','SRC028'),('PSY-EMO-009','SRC086'),('PSY-REL-004','SRC093'),('PSY-REL-004','SRC094')}
    for doc in edgedocs.values():
        for edge in doc['edges']:
            if (edge['topic_id'],edge['source_id']) in context_pairs:
                edge['relation_role']='context_only'
                edge['limits_ja']='個別疾患の指針、別の介入、概説、レジリエンス、質問と好意等の背景資料。今回の読者稿の直接根拠に使用しない。旧ID・訂正記録・主張対応を保持。'
    wellbeing_context={('PSY-WEL-001','SRC068'),('PSY-WEL-005','SRC069'),('PSY-WEL-009','SRC069'),('PSY-WEL-009','SRC100'),('PSY-WRK-002','SRC100')}
    for doc in edgedocs.values():
        for edge in doc['edges']:
            if (edge['topic_id'],edge['source_id']) in wellbeing_context:
                edge['relation_role']='context_only'
                edge['limits_ja']='所得と感情、時間を買う行動、労働時間短縮の背景資料。幸福の一般定義、自由時間の最適量、心理的切り離し介入の直接の証明として読者版では使用しない。元の書誌・確認記録は保持。'
    motivation_context={
        ('PSY-MOT-003','SRC047'):'性格への介入の資料であり、目標と本人の価値の一致を直接検証した資料ではない。',
        ('PSY-MOT-003','SRC084'):'好奇心の資料であり、目標の自己選択や自己一致の直接根拠ではない。',
        ('PSY-MOT-004','SRC045'):'進捗確認への介入であり、目標の難度や学習目標との比較の直接根拠ではない。',
        ('PSY-MOT-004','SRC098'):'障害の検討と行動計画の組合せであり、目標の難度そのものの比較ではない。',
        ('PSY-MOT-006','SRC104'):'先延ばしへの介入の資料であり、完璧主義の二側面と先延ばしの相関の直接根拠ではない。',
    }
    for doc in edgedocs.values():
        for edge in doc['edges']:
            pair=(edge['topic_id'],edge['source_id'])
            if pair in motivation_context:
                edge['relation_role']='context_only'
                edge['limits_ja']=motivation_context[pair]+'旧書誌と照合記録は保持。'
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
