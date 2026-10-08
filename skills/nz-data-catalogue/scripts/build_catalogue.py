#!/usr/bin/env python3
"""Rebuild the compact catalogue from the Auckland catalogue JSON row export."""
from __future__ import annotations
import argparse
import collections
import gzip
import hashlib
import json
import math
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {
    'id': 'ID', 'name': 'Name', 'grade': 'Grade', 'agent_check': 'Agent check', 'score': 'Score (0-5)',
    'category': 'Category', 'subcategory': 'Subcategory', 'scope': 'Scope',
    'country_iso': 'Country (ISO 3166-1)', 'region_iso': 'Region (ISO 3166-2)',
    'data_type': 'Data type', 'access': 'Access', 'owner': 'Owner / publisher', 'format': 'Format',
    'licence': 'Licence', 'why_useful': 'Why it is useful', 'url': 'URL', 'direct_endpoint': 'Direct endpoint',
    'latest_data': 'Latest data', 'caveat': 'Caveat', 'covers_auckland': 'Covers Auckland', 'records_size': 'Records / size',
}
PROBLEMS = ('F1', 'T1', 'T2', 'T3', 'W1', 'W2', 'W3')
AUTH_PARAMETER = re.compile(r'^(?:api|api_?key|token|access_?token|key|subscription-key|password|signature|sig|x-amz-credential|x-amz-signature)$', re.I)

def redact_url(url):
    """Do not redistribute credential-like values included in a source export."""
    if not url:
        return url, False
    parsed = urllib.parse.urlsplit(url)
    if parsed.username or parsed.password:
        raise ValueError('export contains URL user credentials; remove them before rebuilding')
    pairs, changed = [], False
    for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
        # Taginfo's key parameter identifies an OSM tag, not authentication.
        taginfo_key = key == 'key' and parsed.hostname in ('taginfo.geofabrik.de', 'taginfo.openstreetmap.org')
        if AUTH_PARAMETER.fullmatch(key) and not taginfo_key and value and not re.search(r'[{}<>]', value):
            value, changed = '{credential}', True
        pairs.append((key, value))
    if not changed:
        return url, False
    query = urllib.parse.urlencode(pairs).replace('%7Bcredential%7D', '{credential}')
    return urllib.parse.urlunsplit(parsed._replace(query=query)), True

def build(rows, source_name, source_sha256):
    if not isinstance(rows, list) or not rows:
        raise ValueError('expected a non-empty JSON array of catalogue rows')
    records, seen, excluded = [], set(), collections.Counter()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f'row {index}: expected an object')
        if row.get('Duplicate of'):
            excluded['duplicate_of'] += 1
            continue
        if row.get('Agent check') == 'Broken':
            excluded['broken'] += 1
            continue
        missing = [name for name in FIELDS.values() if name not in row]
        if missing:
            raise ValueError(f'row {index}: missing columns: {", ".join(missing)}')
        record = {key: row[value] for key, value in FIELDS.items()}
        if not isinstance(record['id'], str) or not record['id'].strip():
            raise ValueError(f'row {index}: invalid ID')
        if record['id'] in seen:
            raise ValueError(f"duplicate ID without Duplicate of marker: {record['id']}")
        score = record['score']
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 5:
            raise ValueError(f"{record['id']}: score must be finite and between 0 and 5")
        if record['grade'] not in ('A', 'B', 'C', 'D', 'E') or not record['name'] or not record['url']:
            raise ValueError(f"{record['id']}: invalid grade, name or URL")
        record['covers_auckland'] = (record['covers_auckland'] or 'unknown').casefold()
        record['problem_tags'] = [p for p in PROBLEMS if row.get(p) == '✓']
        record['not_data'] = record['agent_check'] == 'Not data'
        record['credential_redacted'] = False
        for field in ('url', 'direct_endpoint'):
            record[field], changed = redact_url(record[field])
            record['credential_redacted'] |= changed
        records.append(record)
        seen.add(record['id'])
    records.sort(key=lambda r: r['id'])
    hosts = {'github.com'}
    for row in records:
        for field in ('url', 'direct_endpoint'):
            if row[field]:
                parsed = urllib.parse.urlsplit(row[field])
                if parsed.scheme in ('http', 'https') and parsed.hostname:
                    hosts.add(parsed.hostname)
    return {'schema_version': '1', 'metadata': {
        'source_file': source_name, 'source_sha256': source_sha256,
        'source_url': 'https://github.com/thecolab-ai/.skills', 'publisher': 'TheColab', 'licence': None,
        'input_rows': len(rows), 'retained_rows': len(records), 'excluded': dict(excluded),
        'credential_redacted_rows': sum(r['credential_redacted'] for r in records), 'allowed_domains': sorted(hosts),
    }, 'records': records}

def write_catalogue(data, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    # Fixed mtime and empty gzip filename make identical exports byte reproducible.
    with destination.open('wb') as target:
        with gzip.GzipFile(filename='', fileobj=target, mode='wb', mtime=0, compresslevel=9) as compressed:
            compressed.write(encoded)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/catalogue.json.gz')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--sync-domains', action='store_true', help='sync this skill\'s frontmatter and source-note host declarations')
    args = parser.parse_args(argv)
    try:
        raw = args.export.read_bytes()
        data = build(json.loads(raw), args.export.name, hashlib.sha256(raw).hexdigest())
        write_catalogue(data, args.output)
        if args.sync_domains:
            sync_domains(data['metadata']['allowed_domains'])
    except (OSError, ValueError, TypeError) as exc:
        print(f'build_catalogue: {exc}', file=sys.stderr)
        return 6
    result = dict(data['metadata'], output=str(args.output), compressed_bytes=args.output.stat().st_size)
    result.pop('allowed_domains')
    if args.json:
        from cli import utc_now
        result.update(retrieved_at=utc_now(), latest_data=None)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Built {result['retained_rows']} sources from {result['input_rows']} rows; {result['compressed_bytes']} compressed bytes")
    return 0

def sync_domains(hosts):
    skill_path = ROOT / 'SKILL.md'
    text = skill_path.read_text(encoding='utf-8')
    text, changed = re.subn(r'^  thecolab.allowed_domains:.*$', '  thecolab.allowed_domains: ' + json.dumps(','.join(hosts)), text, count=1, flags=re.M)
    if changed != 1:
        raise ValueError('cannot find the skill outbound-domain declaration')
    skill_path.write_text(text, encoding='utf-8')
    notes_path = ROOT / 'references/source-notes.md'
    notes = notes_path.read_text(encoding='utf-8').split('\n## Declared outbound hosts\n')[0].rstrip()
    notes_path.write_text(notes + '\n\n## Declared outbound hosts\n\nSynced from the bundled catalogue by `--sync-domains`; exact hostnames only.\n\n' + ', '.join(hosts) + '\n', encoding='utf-8')

if __name__ == '__main__':
    raise SystemExit(main())
