#!/usr/bin/env python3
"""Maintainer tool: derive A/B Auckland layers from the supplied catalogue and probe metadata."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import urllib.parse
import cli


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalogue', type=Path)
    args = parser.parse_args()
    records = {}
    excluded = []
    for row in json.loads(args.catalogue.read_text()):
        if row['Grade'] not in {'A', 'B'} or row.get('Duplicate of') or str(row.get('Covers Auckland')).lower() != 'yes':
            continue
        candidates = []
        for key in ['Direct endpoint', 'URL']:
            value = row.get(key) or ''
            p = urllib.parse.urlsplit(value)
            path = p.path.removesuffix('/query').rstrip('/')
            if '/FeatureServer/' in path or '/MapServer/' in path:
                candidates.append(urllib.parse.urlunsplit((p.scheme, p.netloc, path, '', '')))
        for url in candidates:
            try:
                org, url = cli.validate_url(url)
            except cli.ClientError:
                continue
            record = dict(catalogue_id=row['ID'], name=row['Name'], grade=row['Grade'], source_url=url,
                          publisher=cli.REGISTRY[org]['publisher'], licence=row.get('Licence'),
                          problem_tags=[t for t in ['F1','T1','T2','T3','W1','W2','W3'] if row.get(t)],
                          caveat=row.get('Caveat'), catalogue_latest_data=row.get('Latest data'), org=org)
            if url in records:
                old=records[url]
                old['problem_tags']=sorted(set(old['problem_tags']+record['problem_tags']))
                if record['caveat'] and record['caveat'] not in str(old['caveat']): old['caveat']=str(old['caveat'] or '')+'; '+record['caveat']
            else: records[url]=record
            break
        else:
            if candidates: excluded.append(dict(catalogue_id=row['ID'], name=row['Name'], reason='outside verified public-sector registry'))
    def probe(record):
        try:
            data=cli.fetch(record['source_url'])
            cli.list_value(data,'fields')
            record.update(verified_at=cli.timestamp(), retrieved_at=cli.timestamp(), layer_name=data.get('name'), geometry_type=data.get('geometryType'))
            if data.get('editingInfo',{}).get('lastEditDate') is not None:
                record['latest_data']=cli.timestamp(data['editingInfo']['lastEditDate'])
            return record,None
        except cli.ClientError as e: return record,str(e)
    good=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for record,error in pool.map(probe,records.values()):
            if error: excluded.append(dict(catalogue_id=record['catalogue_id'], name=record['name'], source_url=record['source_url'],reason=error))
            else: good.append(record)
    refs=cli.ROOT/'references'
    (refs/'layers-auckland.json').write_text(json.dumps(good,ensure_ascii=False,indent=2)+'\n')
    (refs/'curation-exclusions.json').write_text(json.dumps(excluded,ensure_ascii=False,indent=2)+'\n')
    def cell(s): return str(s or '').replace('|','\\|').replace('\n',' ')
    lines=['# Curated Auckland ArcGIS layers','',
           'Unique A/B-grade, non-duplicate catalogue layers marked as covering Auckland, on verified public-sector routes. Includes national layers that cover Auckland. Metadata was probed live on 8 October 2026; catalogue caveats and licences are retained without assuming a universal licence. Service-only, imagery and scene entries are outside this feature-layer list.','',
           'Machine source: `layers-auckland.json`. Omitted routes and failed layers: `curation-exclusions.json`. Source freshness labels are stored as `catalogue_latest_data`; only upstream editingInfo.lastEditDate becomes `latest_data`, which is an edit timestamp rather than an observation date.','',
           '| ID / grade | Layer | Problem tags | Caveat |','|---|---|---|---|']
    for r in good: lines.append(f"| {r['catalogue_id']} / {r['grade']} | [{cell(r['name'])}]({r['source_url']}) | {', '.join(r['problem_tags'])} | {cell(r['caveat'])} |")
    (refs/'layers-auckland.md').write_text('\n'.join(lines)+'\n')
    print(f'Verified curated layers: {len(good)}; excluded: {len(excluded)}')
if __name__=='__main__': main()
