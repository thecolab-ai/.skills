#!/usr/bin/env python3
"""Verify the additional council/utility selection without rebuilding Auckland data."""
import argparse
import concurrent.futures
import json
import urllib.parse
from pathlib import Path

import cli
from curate_layers import load_catalogue, restricts_reuse

# Catalogue rows outside the original Auckland selection; keep this reviewable.
SELECTED_IDS = {
    'S0618', 'S0625', 'S0943', 'S0945', 'S1098', 'S1099',
    'S1100', 'S1101', 'S1102', 'S1103', 'S1104', 'S2095', 'S2162',
    'S2516', 'S2686', 'S2927', 'S2932', 'S2933', 'S0789', 'S0790', 'S0792',
}
CLEANING_LAYERS = {2, 3, 4, 5, 6, 7, 8, 12}
FLOODED_FIELDS = 'objectid,obs_date,impact,obs_depth,obs_depth_v2,historic'
DEFERRED = [
    {'catalogue_id': key, 'reason': 'HTML notice, not an ArcGIS data endpoint'}
    for key in ('S2925', 'S2926', 'S2929', 'S2930')
] + [
    {'catalogue_id': key, 'reason': 'tiled image host robots.txt disallows automated paths; metadata/identify verification deferred'}
    for key in ('C0070', 'C0071')
]


def candidates(row):
    """Use published catalogue URLs, dropping only query/operation suffixes."""
    for key in ('direct_endpoint', 'url'):
        p = urllib.parse.urlsplit(row.get(key) or '')
        path = p.path.removesuffix('/query').rstrip('/')
        if '/tile/' in path:
            continue
        if row['id'] in {'S0789', 'S0790', 'S0792'} and path.endswith('/0'):
            path = path.rsplit('/', 1)[0]
        url = urllib.parse.urlunsplit((p.scheme, p.netloc, path, '', ''))
        kind = 'service' if path.rsplit('/', 1)[-1] in cli.SERVER_TYPES else 'layer'
        try:
            org, url = cli.validate_url(url, kind)
        except cli.ClientError:
            continue
        yield org, url, kind


def probe(row):
    if row['grade'] not in {'A', 'B'} or row.get('duplicate_of') or restricts_reuse(row):
        raise cli.ClientError('catalogue grade, duplicate or reuse restriction excludes row', 7)
    candidate = next(candidates(row), None)
    if candidate is None:
        raise cli.ClientError('no allowlisted catalogue endpoint', 7)
    org, url, kind = candidate
    if row['id'] == 'S2516':
        layers = cli.service_layers(url)
        routes = [(r['source_url'], r['name'], 'layer') for r in layers if r['id'] in CLEANING_LAYERS]
        if len(routes) != len(CLEANING_LAYERS):
            raise cli.ClientError('source schema failure: street-cleaning layers changed', 6)
    else:
        routes = [(url, row['name'], kind)]
    records = []
    for url, name, kind in routes:
        metadata = cli.fetch(url, kind=kind)
        if kind == 'layer':
            if metadata.get('type') != 'Feature Layer':
                raise cli.ClientError('not a queryable feature layer', 7)
            cli.list_value(metadata, 'fields')
            if 'Query' not in (metadata.get('capabilities') or '').split(','):
                raise cli.ClientError('query capability missing', 7)
        else:
            cli.list_value(metadata, 'layers')
        now = cli.timestamp()
        r = dict(catalogue_id=row['id'], name=name, grade=row['grade'],
                 source_url=url, publisher=cli.REGISTRY[org]['publisher'], org=org,
                 problem_tags=row['problem_tags'], caveat=row.get('caveat'),
                 catalogue_latest_data=row.get('latest_data'),
                 verified_at=now, retrieved_at=now, kind=kind,
                 layer_name=metadata.get('name') or name,
                 geometry_type=metadata.get('geometryType'))
        licence = row.get('licence')
        if licence:
            r['licence_note' if cli.UNKNOWN_LICENCE.search(licence) else 'licence'] = licence
        edited = (metadata.get('editingInfo') or {}).get('lastEditDate')
        if edited is not None:
            r['latest_data'] = cli.timestamp(edited)
        if kind == 'layer':
            r['verified_count'] = cli.record_count(url)
        else:
            r['operations'] = ['describe', 'layers']
            r['tile_only'] = 'TilesOnly' in (metadata.get('capabilities') or '').split(',')
        if row['id'] == 'S2686':
            r['recommended_fields'] = FLOODED_FIELDS
            r['caveat'] += ' Other fields include personal contact details; the CLI restricts --fields, --where filters and describe output to observation fields (objectid, obs_date, impact, impact_items, obs_depth, obs_depth_v2, historic, status). Do not redistribute submissions without checking their terms.'
        records.append(r)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalogue', type=Path)
    args = parser.parse_args()
    rows = [r for r in load_catalogue(args.catalogue) if r['id'] in SELECTED_IDS]
    if {r['id'] for r in rows} != SELECTED_IDS:
        parser.error('catalogue is missing selected row IDs')
    good, failures = [], []
    def bounded_probe(row):
        try:
            return probe(row), None
        except cli.ClientError as exc:
            return [], dict(catalogue_id=row['id'], name=row['name'], reason=str(exc))
    # Four independent read-only probes at most; each request has a 10 s timeout.
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for records, failure in pool.map(bounded_probe, rows):
            good.extend(records)
            if failure:
                failures.append(failure)
    refs = cli.ROOT / 'references'
    data = dict(verified_at=max(r['verified_at'] for r in good), tags=cli.TAGS, layers=good)
    (refs / 'layers-nz.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    (refs / 'more-layer-exclusions.json').write_text(json.dumps(failures + DEFERRED, ensure_ascii=False, indent=2) + '\n')
    print(f'Additional verified records: {len(good)}; failed rows: {len(failures)}')
    for failure in failures:
        print(f"{failure['catalogue_id']}: {failure['reason']}")
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
