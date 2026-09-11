#!/usr/bin/env python3
"""Rebuild the reviewed research delivery. This never publishes the site."""
from editorial_source_integration import ROOT, DATE, DELIVERY, load, save, apply_sources
import json


def render_delivery_docs():
    report_path = ROOT / 'data/research/editorial_delivery_report.json'
    if not report_path.exists():
        return
    report = load('data/research/editorial_delivery_report.json')
    sources = {s['id']: s for s in load('data/sources.json')['sources']}
    lines = ['# Research delivery', '', 'Date: ' + DATE, '',
             'Reference registration is not publication approval.', '',
             '```json', json.dumps(report, ensure_ascii=False, indent=2), '```', '']
    for r in load('data/research/source_reviews.json')['reviews']:
        if r.get('delivery_id') != DELIVERY:
            continue
        s = sources[r['source_id']]
        lines.extend(['## ' + s['id'] + ': ' + s['title'], '',
                      s['url'], '', r['additional_reading_scope'], '',
                      r['key_findings_ja'] or 'Bibliography only; findings not assessed.', '',
                      r['limitations_ja'], ''])
    (ROOT / 'docs/EDITORIAL_DELIVERY.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    apply_sources()
    import build_research_views
    build_research_views.build()
    render_delivery_docs()
    print(json.dumps(load('data/research/editorial_delivery_report.json'), ensure_ascii=False))


if __name__ == '__main__':
    main()
