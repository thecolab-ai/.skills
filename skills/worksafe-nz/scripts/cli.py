#!/usr/bin/env python3
"""Read-only WorkSafe NZ exports with bounded caches and local filters."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
import nzfetch  # noqa: E402
from provenance import error_envelope, provenance, result_envelope  # noqa: E402

PUBLISHER = 'WorkSafe New Zealand'
ROOT_URL = 'https://data.worksafe.govt.nz/'
S3_HOST = 'data-centre-public.s3.ap-southeast-2.amazonaws.com'
DATASETS = ('incidents', 'concerns', 'injuries_serious_harm', 'serious_harm', 'fatalities')
CACHE_DIR = Path(__file__).resolve().parents[1] / '.cache'
# Data Centre asks for credit; no specific open-data licence is stated.
TERMS = 'Credit WorkSafe New Zealand; no specific data licence stated'


class SkillError(Exception):
    def __init__(self, message, code=6, source_url=ROOT_URL, retry_after=None):
        super().__init__(message)
        self.code, self.source_url, self.retry_after = code, source_url, retry_after


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise SkillError(message, 2)


def fetch_cached(url, max_age, cache_dir=CACHE_DIR):
    """Cache only successful bounded responses; never serve expired data on failure."""
    path = cache_dir / (hashlib.sha256(url.encode()).hexdigest() + '.json')
    try:
        cached = json.loads(path.read_text(encoding='utf-8'))
        stamp = datetime.fromisoformat(cached['retrieved_at'].replace('Z', '+00:00'))
        age = (datetime.now(timezone.utc) - stamp).total_seconds()
        if cached['url'] == url and isinstance(cached['text'], str) and 0 <= age < max_age:
            return cached['text'], cached['retrieved_at']
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        body, _, _ = nzfetch.fetch_bytes(url, timeout=10, allowed_hosts=(urlsplit(url).hostname,))
        text = body.decode('utf-8-sig')
    except nzfetch.RateLimited as exc:
        raise SkillError('network error: source rate-limited', 4, url, exc.retry_after) from exc
    except nzfetch.Blocked as exc:
        raise SkillError('network error: source access blocked', 4, url) from exc
    except nzfetch.FetchError as exc:
        raise SkillError('network error: source unavailable', 5, url) from exc
    except UnicodeError as exc:
        raise SkillError('Source is not UTF-8 text', 6, url) from exc
    stamp = provenance(url, PUBLISHER)['retrieved_at']
    temporary = None
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
        temporary.write_text(json.dumps({'url': url, 'text': text, 'retrieved_at': stamp}), encoding='utf-8')
        temporary.replace(path)
    except OSError:
        pass  # A read command still works when its cache directory is unwritable.
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return text, stamp


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.props = None

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key == 'data-props' and value:
                try:
                    props = json.loads(value)
                except ValueError:
                    continue
                if isinstance(props, dict) and 'datasetDownload' in props:
                    self.props = props


def parse_source_page(text, dataset):
    parser = PageParser()
    parser.feed(text)
    props = parser.props
    if not props:
        raise SkillError('Source page has no datasetDownload metadata')
    try:
        download = props['datasetDownload']
        if dataset == 'serious_harm':
            download = next(item for item in props['supplementaryDownloadFiles'] if item['title'] == 'Download Serious Harm - HSE')
        url = download['path']
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.hostname != S3_HOST or parts.username or parts.password or not parts.path.endswith('.csv'):
            raise ValueError('Unrecognised download URL')
        return {'dataset': dataset, 'title': download['title'], 'description': download['description'],
                'source_url': url, 'page_updated': str(props['lastUpdated'])}
    except (KeyError, TypeError, ValueError, StopIteration) as exc:
        raise SkillError('Source download metadata has changed') from exc


def source(dataset, max_age):
    page_dataset = 'injuries_serious_harm' if dataset == 'serious_harm' else dataset
    page_url = ROOT_URL + 'graph/summary/' + page_dataset
    text, stamp = fetch_cached(page_url, max_age)
    try:
        result = parse_source_page(text, dataset)
    except SkillError as exc:
        exc.source_url = page_url
        raise
    result.update(provenance(result['source_url'], PUBLISHER, licence=TERMS, latest_data=result['page_updated'], retrieved_at=stamp))
    result['landing_page'] = page_url
    return result


def parse_csv(text, dataset):
    reader = csv.DictReader(io.StringIO(text, newline=''), strict=True)
    try:
        names = reader.fieldnames or []
    except csv.Error as exc:
        raise SkillError('CSV schema failure: invalid header') from exc
    required = {'Year', 'Month', 'IndustryLvl1'}
    required.add('local_government_region' if dataset == 'fatalities' else 'Local_Government_Region')
    required.update({'FatalID'} if dataset == 'fatalities' else {'Count', 'Notification_Type'})
    if not required.issubset(names) or len(names) != len(set(names)):
        raise SkillError('CSV schema has changed: required columns missing or repeated')
    rows, fatal_ids = [], set()
    try:
        for raw in reader:
            if None in raw or any(value is None for value in raw.values()):
                raise ValueError('CSV row width differs from header')
            year, month = int(raw['Year']), int(raw['Month'])
            datetime(year, month, 1)
            count = 1 if dataset == 'fatalities' else int(raw['Count'])
            if count < 0:
                raise ValueError('Negative count')
            if dataset == 'fatalities':
                fatal_id = raw['FatalID']
                if not fatal_id or fatal_id in fatal_ids:
                    raise ValueError('Missing or duplicate fatality identifier')
                fatal_ids.add(fatal_id)
            row = {'dataset': dataset, 'year': year, 'month': month, 'period': f'{year:04d}-{month:02d}',
                   'industry': raw['IndustryLvl1'], 'region': raw.get('Local_Government_Region', raw.get('local_government_region')),
                   'count': count, 'aff2017': raw.get('AFF2017', ''), 'aff2017_level2': raw.get('AFF2017_Lvl2', '')}
            for level in (2, 3, 4):
                row[f'industry_level{level}'] = raw.get(f'IndustryLvl{level}', raw.get(f'IndustryLVL{level}', ''))
            if dataset != 'fatalities':
                row.update(notification_type=raw['Notification_Type'], classification=raw.get('HSWA_Classification', ''),
                           investigated=raw.get('Investigated', ''), notice_warning_or_agreement=raw.get('Notice_Warning_or_Agreement', ''))
            rows.append(row)
    except (ValueError, csv.Error) as exc:
        raise SkillError('CSV schema failure: invalid year, month, count or row') from exc
    if not rows:
        raise SkillError('CSV has no data rows')
    return rows


def load_dataset(dataset, max_age):
    info = source(dataset, max_age)
    text, stamp = fetch_cached(info['source_url'], max_age)
    try:
        rows = parse_csv(text, dataset)
    except SkillError as exc:
        exc.source_url = info['source_url']
        raise
    # latest_data is the maximum month explicitly recorded in the CSV, not the dashboard label.
    meta = provenance(info['source_url'], PUBLISHER, licence=TERMS,
                      latest_data=max(row['period'] for row in rows), retrieved_at=stamp)
    return rows, meta, info


def filter_rows(rows, industry=None, region=None, from_period=None, to_period=None, year=None,
                industry_match='top-level'):
    return [row for row in rows
            if (not industry or (industry.casefold() == row['industry'].casefold()
                if industry_match == 'top-level' else
                any(industry.casefold() in row[key].casefold() for key in ('industry', 'industry_level2', 'industry_level3', 'industry_level4', 'aff2017', 'aff2017_level2'))))
            and (not region or region.casefold() in row['region'].casefold())
            and (not from_period or row['period'] >= from_period)
            and (not to_period or row['period'] <= to_period)
            and (year is None or row['year'] == year)]


def aggregate(rows, by):
    groups = defaultdict(int)
    for row in rows:
        keys = (row['year'], row['industry'], row['region']) if by == 'fatalities' else (row[by],)
        groups[keys] += row['count']
    if by == 'fatalities':
        return [{'year': k[0], 'industry': k[1], 'region': k[2], 'count': v} for k, v in sorted(groups.items())]
    return [{by: k[0], 'count': v} for k, v in sorted(groups.items())]


def period(value):
    if not re.fullmatch(r'\d{4}-\d{2}', value):
        raise argparse.ArgumentTypeError('Use YYYY-MM for monthly bounds')
    try:
        datetime.strptime(value, '%Y-%m')
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Use a valid month in YYYY-MM') from exc
    return value


def build_parser():
    parser = Parser(description='Query public WorkSafe NZ workplace harm CSV exports')
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('sources', 'datasets', 'incidents', 'fatalities', 'summary'):
        p = sub.add_parser(command)
        p.add_argument('--json', action='store_true', help='print provenance and results as JSON')
        p.add_argument('--max-age', type=float, default=86400, help='maximum cache age in seconds; 0 refreshes (default 86400)')
        if command in ('incidents', 'fatalities', 'summary'):
            p.add_argument('--industry', help='case-insensitive exact top-level industry name by default')
            p.add_argument('--industry-match', choices=('top-level', 'any-level'), default='top-level',
                           help='top-level: exact name (default); any-level: substring across industry levels and AFF2017 groups')
        if command in ('incidents', 'summary'):
            p.add_argument('--dataset', choices=DATASETS if command == 'summary' else DATASETS[:-1], default='incidents')
            p.add_argument('--region', help='case-insensitive substring of local government region')
            p.add_argument('--from', dest='from_period', type=period)
            p.add_argument('--to', dest='to_period', type=period)
        if command == 'incidents':
            p.add_argument('--limit', type=int, default=100, help='maximum rows; 0 returns all (default 100)')
        if command == 'fatalities':
            p.add_argument('--year', type=int)
        if command == 'summary':
            p.add_argument('--by', choices=('industry', 'region', 'year'), required=True)
    return parser


def execute(args):
    if not math.isfinite(args.max_age) or args.max_age < 0:
        raise SkillError('--max-age must be finite and non-negative', 2)
    if getattr(args, 'limit', 0) < 0:
        raise SkillError('--limit must be non-negative', 2)
    if getattr(args, 'year', None) is not None and not 1 <= args.year <= 9999:
        raise SkillError('--year must be between 1 and 9999', 2)
    if getattr(args, 'from_period', None) and getattr(args, 'to_period', None) and args.from_period > args.to_period:
        raise SkillError('--from must be no later than --to', 2)
    if args.command in ('sources', 'datasets'):
        results = []
        for dataset in DATASETS:
            if args.command == 'sources':
                results.append(source(dataset, args.max_age))
            else:
                rows, meta, info = load_dataset(dataset, args.max_age)
                results.append({**info, **meta, 'row_count': len(rows), 'count': sum(r['count'] for r in rows),
                                'first_data': min(r['period'] for r in rows)})
        return result_envelope(results, provenance(ROOT_URL, PUBLISHER))
    dataset = 'fatalities' if args.command == 'fatalities' else args.dataset
    rows, meta, _ = load_dataset(dataset, args.max_age)
    selected = filter_rows(rows, getattr(args, 'industry', None), getattr(args, 'region', None),
                           getattr(args, 'from_period', None), getattr(args, 'to_period', None), getattr(args, 'year', None),
                           args.industry_match)
    meta.update(dataset=dataset, matched_rows=len(selected), matched_count=sum(r['count'] for r in selected))
    if args.command == 'summary':
        result = aggregate(selected, args.by)
    elif args.command == 'fatalities':
        result = aggregate(selected, 'fatalities')
    else:
        result = sorted(selected, key=lambda r: (r['period'], r['industry'], r['region'], r['classification']))
        if args.limit:
            result = result[:args.limit]
        meta.update(returned_rows=len(result), truncated=len(result) < len(selected))
    return result_envelope(result, meta)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        args = build_parser().parse_args(argv)
        payload = execute(args)
    except SkillError as exc:
        if '--json' in argv:
            print(json.dumps(error_envelope(exc.code, str(exc), provenance(exc.source_url, PUBLISHER), retry_after=exc.retry_after)))
        else:
            print(f'worksafe-nz: {exc}', file=sys.stderr)
        return exc.code
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"WorkSafe New Zealand: {len(payload['results'])} result(s)")
        for row in payload['results']:
            print(' | '.join(f'{key}: {value}' for key, value in row.items()))
        if payload['meta'].get('truncated'):
            print(f"Showing {payload['meta']['returned_rows']} of {payload['meta']['matched_rows']} grouped rows; use --limit 0 for all.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
