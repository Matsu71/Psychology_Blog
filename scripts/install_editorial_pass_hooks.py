#!/usr/bin/env python3
"""Idempotent compatibility hooks for reviewed source inputs and current views."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def replace_one(path,old,new):
    p=ROOT/path
    s=p.read_text(encoding='utf-8')
    if new in s: return
    if s.count(old)!=1: raise ValueError('Unexpected source version: '+path)
    p.write_text(s.replace(old,new),encoding='utf-8')

p=ROOT/'scripts/compile_claim_manuscripts.py'
s=p.read_text(encoding='utf-8')
s=s.replace('../../../data/articles/claims/','../../data/articles/claims/')
p.write_text(s,encoding='utf-8')
replace_one('scripts/compile_claim_manuscripts.py',
 '    print(json.dumps(report,ensure_ascii=False,indent=2))',
 "    if (ROOT/'data/research/source_text_checks.json').exists():\n        from apply_editorial_pass import apply_manuscripts\n        report = apply_manuscripts()\n    print(json.dumps(report,ensure_ascii=False,indent=2))")
replace_one('scripts/build_research_views.py',"VERSION = 'work-priority-1.0'","VERSION = 'work-priority-1.1'")
replace_one('scripts/build_research_views.py',
 "    excluded = source.get('record_role')", 
 "    open_reporting = any(x.get('status') == 'open_original_paper_check' for x in assessment.get('reporting_issues', []))\n    excluded = source.get('record_role')")
replace_one('scripts/build_research_views.py',
 "        if edge['relation_role'] == 'context_only':", 
 "        if open_reporting:\n            score = min(score, 65)\n            caps.append('unresolved_reporting_issue_max_65')\n        if edge['relation_role'] == 'context_only':")
replace_one('scripts/build_research_views.py',
 "'integrity_requires_followup': pending_correction or suspected_retraction,", 
 "'integrity_requires_followup': pending_correction or suspected_retraction or open_reporting,")
replace_one('scripts/build_research_views.py',
 '        render_delivery_docs()',
 "        render_delivery_docs()\n    if (ROOT/'data/research/source_text_checks.json').exists():\n        from apply_editorial_pass import render_docs as render_editorial_current\n        render_editorial_current()")
print('PASS: compiler retains reviewed overrides; current README and reporting-issue caps.')
