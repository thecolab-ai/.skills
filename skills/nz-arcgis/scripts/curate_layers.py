#!/usr/bin/env python3
"""Derive Auckland layers from nz-data-catalogue/data/catalogue.json.gz."""
import argparse
import concurrent.futures
import gzip
import json
from pathlib import Path
import re
import urllib.parse
import cli

# Keep non-commercial, BY-ND and NZTA commercial terms visible; exclude permission gates.
RESTRICTED = re.compile(r'internal (?:\w+\s+)?use|not (?:suitable|intended) for public|permission required|data[- ]sharing agreement|viewer use only|restricted|terms (?:limit|restrict) (?:use|reuse)|consent (?:required|for)|requires? (?:prior written )?consent', re.I)
UNKNOWN_LICENCE = cli.UNKNOWN_LICENCE


def restricts_reuse(record):
    licence = str(record.get('licence') or '')
    # DataHub commercial pricing is distinct from a public-release permission gate.
    if 'CC BY-ND' in licence:
        licence = licence.replace('commercial restricted use', 'commercial priced use')
    caveat = str(record.get('caveat') or '')
    caveat_pattern = RESTRICTED.pattern.replace('|restricted', '|(?:access is restricted|restricted operational|restricted to)')
    return bool(RESTRICTED.search(licence) or re.search(caveat_pattern, caveat, re.I))


def load_catalogue(path):
    text = gzip.open(path, 'rt').read() if str(path).endswith('.gz') else path.read_text()
    data = json.loads(text)
    if isinstance(data, dict):
        return data['records']
    # Original akl-catalogue-v4.json format, retained for reproducibility.
    return [dict(id=r['ID'], name=r['Name'], grade=r['Grade'], duplicate_of=r.get('Duplicate of'), covers_auckland=r.get('Covers Auckland'), direct_endpoint=r.get('Direct endpoint'), url=r.get('URL'), licence=r.get('Licence'), caveat=r.get('Caveat'), latest_data=r.get('Latest data'), problem_tags=[t for t in cli.TAGS if r.get(t)]) for r in data]


def write_catalogue(good, excluded):
    refs = cli.ROOT / 'references'
    data = dict(verified_at=max(r['verified_at'] for r in good), tags=cli.TAGS, layers=good)
    (refs/'layers-auckland.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    (refs/'curation-exclusions.json').write_text(json.dumps(excluded, ensure_ascii=False, indent=2)+'\n')
    def cell(s):
        return str(s or '').replace('|', '\\|').replace('\n', ' ')
    lines = ['# Curated Auckland ArcGIS layers', '',
             'Unique A/B-grade, non-duplicate layers covering Auckland on verified public-sector and utility routes. Source: `skills/nz-data-catalogue/data/catalogue.json.gz`, derived from `akl-catalogue-v4.json`. National layers covering Auckland are included. Terms restricting public reuse are excluded; retained non-commercial, BY-ND and commercial restrictions still apply.', '',
             'Machine source: `layers-auckland.json`; omitted routes, restricted terms and failed layers: `curation-exclusions.json`. Each record retains its metadata probe time. `catalogue_latest_data` is a source label; `latest_data` is the published edit timestamp, not an observation date.', '',
             '| Code | Meaning |', '|---|---|']
    lines.extend(f'| {code} | {meaning} |' for code, meaning in cli.TAGS.items())
    lines.extend(['', '| ID / grade | Layer | Problem tags | Licence / note | Caveat |', '|---|---|---|---|---|'])
    for r in good:
        lines.append(f"| {r['catalogue_id']} / {r['grade']} | [{cell(r['name'])}]({r['source_url']}) | {', '.join(r['problem_tags'])} | {cell(r.get('licence') or r.get('licence_note') or 'Unknown')} | {cell(r['caveat'])} |")
    (refs/'layers-auckland.md').write_text('\n'.join(lines)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalogue', type=Path)
    parser.add_argument('--reuse-verification', action='store_true', help='rebuild selection using bundled successful metadata probes, preserving their timestamps; omit to probe live')
    args = parser.parse_args()
    records, excluded, restricted_urls = {}, [], set()
    for row in load_catalogue(args.catalogue):
        if row['grade'] not in {'A', 'B'} or row.get('duplicate_of') or str(row.get('covers_auckland')).lower() != 'yes':
            continue
        candidates = []
        for key in ('direct_endpoint', 'url'):
            value = row.get(key) or ''
            p = urllib.parse.urlsplit(value)
            path = p.path.removesuffix('/query').rstrip('/')
            if '/FeatureServer/' in path or '/MapServer/' in path:
                candidates.append(urllib.parse.urlunsplit((p.scheme, p.netloc, path, '', '')))
        if restricts_reuse(row):
            restricted_urls.update(url.casefold() for url in candidates)
            excluded.append(dict(catalogue_id=row['id'], name=row['name'], reason='terms restrict public reuse'))
            continue
        for url in candidates:
            try:
                org, url = cli.validate_url(url)
            except cli.ClientError:
                continue
            record = dict(catalogue_id=row['id'], name=row['name'], grade=row['grade'], source_url=url, publisher=cli.REGISTRY[org]['publisher'], problem_tags=row['problem_tags'], caveat=row.get('caveat'), catalogue_latest_data=row.get('latest_data'), org=org)
            licence = row.get('licence')
            if licence:
                record['licence_note' if UNKNOWN_LICENCE.search(licence) else 'licence'] = licence
            if url in records:
                old = records[url]
                old['problem_tags'] = sorted(set(old['problem_tags'] + record['problem_tags']))
                if record['caveat'] and record['caveat'] not in str(old['caveat']):
                    old['caveat'] = str(old['caveat'] or '') + '; ' + record['caveat']
                for key in ('licence', 'licence_note'):
                    if record.get(key) and record[key] not in str(old.get(key)):
                        old[key] = '; '.join(filter(None, [old.get(key), record[key]]))
            else:
                records[url] = record
            break
        else:
            if candidates:
                excluded.append(dict(catalogue_id=row['id'], name=row['name'], reason='outside verified public-sector and utility registry'))
    # A URL appearing under conflicting terms must not be promoted via a duplicate row.
    for url in list(records):
        if url.casefold() in restricted_urls or restricts_reuse(records[url]):
            record = records.pop(url)
            excluded.append(dict(catalogue_id=record['catalogue_id'], name=record['name'], reason='terms restrict public reuse'))
    previous = {r['source_url']: r for r in cli.CURATED}
    def probe(record):
        try:
            if args.reuse_verification:
                old = previous.get(record['source_url'])
                if not old:
                    return record, 'no bundled metadata verification; run without --reuse-verification'
                record.update({k: old[k] for k in ('verified_at', 'retrieved_at', 'layer_name', 'geometry_type', 'latest_data') if k in old})
            else:
                data = cli.fetch(record['source_url'])
                if data.get('type') not in {'Feature Layer', 'Table'}:
                    raise cli.ClientError('not a queryable feature layer', 7)
                cli.list_value(data, 'fields')
                now = cli.timestamp()
                record.update(verified_at=now, retrieved_at=now, layer_name=data.get('name'), geometry_type=data.get('geometryType'))
                edited = (data.get('editingInfo') or {}).get('lastEditDate')
                if edited is not None:
                    record['latest_data'] = cli.timestamp(edited)
            return record, None
        except cli.ClientError as exc:
            return record, str(exc)
    good = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for record, error in pool.map(probe, records.values()):
            if error:
                excluded.append(dict(catalogue_id=record['catalogue_id'], name=record['name'], source_url=record['source_url'], reason=error))
            else:
                good.append(record)
    write_catalogue(good, excluded)
    print(f'Verified curated layers: {len(good)}; excluded: {len(excluded)}')


if __name__ == '__main__':
    main()
