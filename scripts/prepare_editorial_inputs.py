#!/usr/bin/env python3
"""One-time conversion of editorial inputs to a canonical, editable JSON file."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    target=ROOT/'data/editorial_assessments.json'
    if not target.exists():
        records=[]
        for line in (ROOT/'research/round3_editorial.psv').read_text(encoding='utf-8').splitlines():
            if not line.strip() or line.startswith('#'): continue
            tid,values,reason=line.split('|')
            daily,action,interest,breadth=map(int,values.split(','))
            records.append({'topic_id':'PSY-'+tid,'daily_relevance':daily,'actionability':action,
                'interest':interest,'audience_breadth':breadth,'reason_ja':reason,
                'assessment_type':'subjective_editorial_hypothesis','assessed_on':'2026-09-11'})
        assert len(records)==50
        target.write_text(json.dumps({'schema_version':'1.0','assessments':records},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    path=ROOT/'scripts/build_research_views.py'
    body=path.read_text(encoding='utf-8')
    start="    for line in (ROOT / 'research/round3_editorial.psv').read_text(encoding='utf-8').splitlines():\n"
    end="        assert all(1 <= x <= 5 for x in (daily, action, interest, breadth))\n"
    if start in body:
        left=body.index(start);right=body.index(end,left)
        block="    for input_row in load('data/editorial_assessments.json')['assessments']:\n        tid=input_row['topic_id']\n        assert tid in topics\n        daily=input_row['daily_relevance']\n        action=input_row['actionability']\n        interest=input_row['interest']\n        breadth=input_row['audience_breadth']\n        reason=input_row['reason_ja']\n"
        body=body[:left]+block+body[right:]
        path.write_text(body,encoding='utf-8')
    elif "load('data/editorial_assessments.json')" not in body:
        raise ValueError('Unexpected build script version')

if __name__=='__main__': main()
