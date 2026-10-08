#!/usr/bin/env python3
"""Keyless NZ reuse, repair and recycling directories (stdlib only)."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import html
from html.parser import HTMLParser
import json
import math
import os
import tempfile
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlparse
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'lib'))
import nzfetch  # noqa: E402
from provenance import result_envelope, error_envelope, geojson_envelope

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'nz-recycling-locator'
PARSER_VERSION = 4
TTL = 86400
PRIMARY_URL = 'https://www.recyclemap.co.nz/'
RM = 'https://www.recyclemap.co.nz/wp-json/wpgmza/v1/'
COUNCIL = 'https://www.aucklandcouncil.govt.nz/en/rubbish-recycling/get-rid-unwanted-items.html'
SOURCES = {
    'recyclemap': {'url': RM + 'markers', 'publisher': 'RecycleMap NZ', 'kind': 'JSON', 'licence': None},
    'wasteminz': {'url': 'https://www.google.com/maps/d/kml?mid=1ncyWOEWbXMSiycgz48swYqMj4aHJnSE&forcekml=1', 'publisher': 'WasteMINZ', 'kind': 'KML', 'licence': None},
    'council': {'url': COUNCIL, 'publisher': 'Auckland Council', 'kind': 'HTML', 'licence': None},
    'repair': {'url': 'https://www.repairnetworkaotearoa.org.nz/dynamic-localrepaircafes_p_8500816c_6fb3_4424_8161_90ad1ae5b8b2_0_5000-sitemap.xml', 'publisher': 'Repair Network Aotearoa', 'kind': 'sitemap + HTML', 'licence': None},
    'tyrewise': {'url': 'https://www.tyrewise.co.nz/participant_cat/collection-site/', 'publisher': 'Tyrewise', 'kind': 'HTML', 'licence': None},
    'ecycle': {'url': 'https://www.e-cycle.co.nz/wp-admin/admin-ajax.php?action=store_search&lat=-36.8485&lng=174.7633&max_results=1000&search_radius=5000&autoload=1', 'publisher': 'E-Cycle', 'kind': 'JSON', 'licence': None},
    'branz': {'url': 'https://services7.arcgis.com/vkPf8weODt71Prmb/arcgis/rest/services/Waste_Map_Facility_Locations/FeatureServer/0', 'publisher': 'BRANZ', 'kind': 'ArcGIS JSON', 'licence': None},
    'agrecovery': {'url': 'https://agrecovery.co.nz/wp-json/wp/v2/ag_site?per_page=100&page=1&acf_format=standard&_fields=id,title,acf&orderby=title&order=asc', 'publisher': 'Agrecovery', 'kind': 'JSON', 'licence': None},
    'beautification': {'url': 'https://api.mapme.com/api/stories/aggregated/af29690b-4cd0-484f-a211-8f3e12fa51b4', 'publisher': 'Beautification Trust', 'kind': 'JSON', 'licence': None},
    'trow': {'url': 'https://base44.app/api/apps/68e5846a599cc4e55639725b/entities/Item?sort=-created_date&limit=1000', 'publisher': 'TROW Group', 'kind': 'JSON stock grouped by location', 'licence': None},
    'christchurch': {'url': 'https://gis.ccc.govt.nz/server/rest/services/OpenData/SiteUtility/FeatureServer/9', 'publisher': 'Christchurch City Council', 'kind': 'ArcGIS JSON', 'licence': None},
    'zerowaste': {'url': 'https://zerowaste.co.nz/wp-json/wpgmza/v1/markers?map_id=2', 'publisher': 'Zero Waste Aotearoa', 'kind': 'JSON member map', 'licence': None},
    'habitat': {'url': 'https://www.habitat.org.nz/op-shops', 'publisher': 'Habitat for Humanity New Zealand', 'kind': 'HTML directory', 'licence': None},
    'crc': {'url': 'https://www.makingzerowastework.org.nz/find-your-local-crc', 'publisher': 'Zero Waste Tāmaki Makaurau Trust', 'kind': 'HTML directory', 'licence': None},
    'techcollect': {'url': 'https://techcollect.nz/', 'publisher': 'TechCollect NZ', 'kind': 'unsupported', 'licence': None},
}
DEFAULT_SOURCES = [s for s in SOURCES if s not in ('council', 'techcollect', 'trow')]
FETCH_HOSTS = {urlparse(spec['url']).hostname for source, spec in SOURCES.items()
               if source not in ('council', 'techcollect')}


class SourceError(Exception):
    def __init__(self, message, code=6, retry_after=None, source_url=None, source=None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after
        self.source_url = source_url
        self.source = source


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def provenance(source, url=None, retrieved=None, latest=None):
    s = SOURCES[source]
    result = {'source_url': url or s['url'], 'publisher': s['publisher'],
              'retrieved_at': retrieved or utc_now()}
    if s.get('licence'):
        result['licence'] = s['licence']
    if latest is not None:
        result['latest_data'] = latest
    return result


class Page(HTMLParser):
    """Extract visible text and public links; never use Wix global business coords."""
    def __init__(self):
        super().__init__()
        self.lines, self.links = [], []
        self.hidden = 0
        self.href = None
        self.label = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'noscript', 'svg'):
            self.hidden += 1
        if tag == 'a':
            self.href, self.label = attrs.get('href'), []

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'svg'):
            self.hidden = max(0, self.hidden - 1)
        if tag == 'a' and self.href:
            self.links.append((self.href, ' '.join(self.label)))
            self.href = None

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.lines.append(data.strip())
            if self.href:
                self.label.append(data.strip())


def page(text):
    p = Page()
    p.feed(text or '')
    return p


def clean(text):
    return ' '.join(page(str(text or '')).lines)


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def record(source, name, address=None, lon=None, lat=None, materials=(), hours=None,
           details=None, url=None, retrieved=None, latest=None, **extra):
    lon, lat = number(lon), number(lat)
    if lon is None or lat is None or not (-180 <= lon <= 180 and -90 <= lat <= 90):
        lon = lat = None
    p = provenance(source, url, retrieved, latest)
    return {'name': clean(name), 'address': clean(address) or None, 'lon': lon, 'lat': lat,
            'materials': sorted(set(clean(x) for x in materials if clean(x))),
            'hours': clean(hours) or None, 'source': source, 'provenance': p,
            **p, 'details': clean(details) or None, **extra}


def hours_from(text):
    lines = page(text).lines
    start = next((i for i, s in enumerate(lines) if re.search(r'\b(opening hours|hours)\b', s, re.I)), None)
    if start is None:
        return None
    remainder = re.split(r'(?i)(?:opening\s+)?hours\s*:?', lines[start], 1)[1].strip()
    if re.match(r'^unknown\b', remainder, re.I):
        return None
    after = [remainder] if remainder else []
    for line in lines[start + 1:]:
        if re.match(r'(accepts|what we accept|phone|email|website|restrictions|does not accept|recycled by|this facility)\b', line, re.I):
            break
        if re.match(r'^unknown\b', line, re.I):
            return None
        after.append(line)
    return ' '.join(after) or None


def get(url, json_data=False):
    try:
        if json_data:
            return nzfetch.fetch_json(url, timeout=10, allowed_hosts=FETCH_HOSTS)
        return nzfetch.fetch_text(url, timeout=10, allowed_hosts=FETCH_HOSTS)
    except nzfetch.RateLimited as exc:
        raise SourceError(f'network error: rate_limited: {exc}', 4, exc.retry_after, url) from exc
    except nzfetch.Blocked as exc:
        raise SourceError(f'network error: {exc}', 4, source_url=url) from exc
    except nzfetch.FetchError as exc:
        raise SourceError(f'network error: {exc}', 5, source_url=url) from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise SourceError(f'Source returned invalid JSON: {url}') from exc


def require(value, message):
    if not value:
        raise SourceError(message)


def parse_recyclemap(markers, maps, categories, retrieved):
    require(isinstance(markers, list) and markers, 'RecycleMap markers are missing')
    require(isinstance(maps, list) and maps, 'RecycleMap material maps are missing')
    titles = {str(m['id']): html.unescape(m['map_title']) for m in maps}
    cats = {}
    def visit(c):
        cats[str(c['id'])] = c['name']
        for child in c.get('children', []):
            visit(child)
    visit(categories)
    rows = []
    for m in markers:
        require(str(m['map_id']) in titles, 'RecycleMap marker references an unknown material map')
        if str(m.get('approved', '1')) != '1':
            continue
        tags = [cats[str(c)] for c in m.get('categories', []) if str(c) in cats]
        rows.append(record('recyclemap', m['title'], m.get('address'), m['lng'], m['lat'],
                           [titles[str(m['map_id'])]], hours_from(m.get('description')),
                           m.get('description'), retrieved=retrieved, id=str(m['id']),
                           categories=tags, website=m.get('link') or None))
    return rows


def parse_kml(text, retrieved):
    ns = {'k': 'http://www.opengis.net/kml/2.2'}
    tree = ET.fromstring(text)
    rows = []
    for marker in tree.findall('.//k:Placemark', ns):
        coord = marker.findtext('.//k:Point/k:coordinates', namespaces=ns)
        if not coord:
            continue
        xy = coord.strip().split(',')
        require(len(xy) >= 2, 'WasteMINZ point coordinates require longitude and latitude')
        desc = marker.findtext('k:description', '', ns)
        rows.append(record('wasteminz', marker.findtext('k:name', '', ns),
                           lon=xy[0], lat=xy[1], materials=['Batteries'],
                           details=desc, retrieved=retrieved))
    require(rows, 'WasteMINZ KML contains no point placemarks')
    return rows


BRANZ_MATERIALS = {
    'Timber__mixed_unknown_': 'Timber (mixed/unknown)', 'Timber__untreated_': 'Untreated timber',
    'timber_treated': 'Treated timber', 'Plasterboard': 'Plasterboard', 'Plastics': 'Plastics',
    'Other_packaging': 'Other packaging', 'Flooring': 'Flooring', 'Concrete': 'Concrete',
    'Metal__ferrous_': 'Ferrous metal', 'Metal__non_ferrous_': 'Non-ferrous metal',
    'Cardboard': 'Cardboard', 'Aggregate': 'Aggregate', 'Combined_C_D': 'Combined C&D',
    'Specialist_C_D': 'Specialist C&D', 'Commercial_and_industrial': 'Commercial and industrial',
    'Glass': 'Glass', 'Concrete_aggregate_soil': 'Concrete, aggregate and soil',
    'Paint': 'Paint', 'EWaste': 'E-waste', 'Tyres': 'Tyres',
}


def parse_branz(data, retrieved, latest=None):
    require('features' in data and not data.get('error'), 'BRANZ ArcGIS features are missing')
    require(not data.get('exceededTransferLimit'), 'BRANZ query was truncated; refusing incomplete data')
    rows = []
    for f in data['features']:
        a, g = f['attributes'], f.get('geometry') or {}
        if str(a.get('Status') or '').casefold() == 'planned':
            continue
        materials = [label for key, label in BRANZ_MATERIALS.items()
                     if str(a.get(key) or '').strip().lower() in ('yes', 'y', '1', 'true')]
        # Other free text is retained as details, not silently inferred as acceptance.
        rows.append(record('branz', a['Facility'], a.get('Address'), g.get('x'), g.get('y'),
                           materials, details=' '.join(str(a[k]) for k in ('Description', 'Accepted_Waste_Streams') if a.get(k)),
                           retrieved=retrieved, latest=latest, id=a['OBJECTID'], region=a.get('Region'),
                           status=a.get('Status'), facility_type=a.get('Facility_Type'), website=a.get('URL')))
    require(rows, 'BRANZ returned no facilities')
    return rows


def parse_ecycle(data, retrieved):
    require(isinstance(data, list) and data, 'E-Cycle store-search array is missing')
    return [record('ecycle', x['store'], ', '.join(str(x.get(k) or '') for k in ('address', 'address2', 'city', 'zip') if x.get(k)),
                   x['lng'], x['lat'], ['E-waste'] + (['Polystyrene'] if 'polystyrene' in str(x.get('fax', '')).lower() else []),
                   x.get('hours'), x.get('description'), retrieved=retrieved,
                   id=str(x['id']), website=x.get('url')) for x in data]


def parse_agrecovery(data, retrieved, url=None):
    require(isinstance(data, list), 'Agrecovery sites array is missing')
    rows = []
    for x in data:
        a = x.get('acf') or {}
        if not a.get('ag_site_active'):
            continue
        hours = '; '.join(f'{day}: {a.get("ag_site_" + day + "_hours") or a.get("ag_site_" + day + "_status", "unknown")}'
                          for day in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'))
        rows.append(record('agrecovery', x['title']['rendered'], a.get('ag_site_address'),
                           a.get('ag_site_lon'), a.get('ag_site_lat'), a.get('ag_site_schemes', []),
                           hours, a.get('ag_site_notes'), url=url, retrieved=retrieved,
                           id=x['id'], region=a.get('ag_site_region')))
    return rows


def parse_beautification(data, retrieved):
    scene = data['scene']
    sections, cats = scene['sections'], scene['categories']
    rows = []
    for sid, s in sections.items():
        if not s.get('name'):
            continue  # Four unlabelled draft sections in the published response.
        center = s.get('mapView', {}).get('center', {})
        materials = [c['name'] for c in cats.values() if sid in (c.get('sections') or [])]
        rows.append(record('beautification', s['name'], s.get('address'), center.get('lng'), center.get('lat'),
                           materials, hours_from(s.get('description')), s.get('description'),
                           retrieved=retrieved, id=sid, website=s.get('callToAction', {}).get('url')))
    require(rows, 'Beautification Trust directory has no sections')
    return rows


def parse_trow(data, retrieved):
    """Return locations with available/pre-sale stock, never seller/account data."""
    require(isinstance(data, list) and data, 'TROW ReStore stock array is missing')
    require(len(data) < 1000, 'TROW ReStore reached the 1,000-item bound; refusing incomplete data')
    groups = {}
    for item in data:
        require(isinstance(item, dict) and all(k in item for k in ('location', 'status', 'category')),
                'TROW ReStore location/status/category fields are missing')
        require(item['status'] in ('available', 'pre-sale', 'sold'), 'TROW ReStore stock status is unknown')
        if item['status'] == 'sold':
            continue
        location = clean(item['location'])
        # These two publisher labels refer to the same yard. Keep other and
        # unspecified locations separate rather than guessing from locality.
        if location.casefold() in ('trow group yard, ranui', 'trow yard - ranui. auckland 0612'):
            location = 'Trow Group Yard, Ranui'
        group = groups.setdefault(location, {'materials': set(), 'available': 0, 'pre-sale': 0, 'dates': []})
        group['materials'].add(clean(item['category']))
        group[item['status']] += 1
        if item.get('updated_date'):
            group['dates'].append(str(item['updated_date']))
    require(groups, 'TROW ReStore returned no available or pre-sale locations')
    latest = max((date for group in groups.values() for date in group['dates']), default=None)
    return [record('trow', 'TROW ReStore — ' + (location or 'location not stated'), location,
                   materials=['Reuse', 'Salvaged building materials'] + sorted(g['materials']),
                   details='Stock location, not confirmed donation acceptance. Pre-sale items may not be ready; arrange collection with TROW.',
                   retrieved=retrieved, latest=latest, available_items=g['available'],
                   pre_sale_items=g['pre-sale'], website='https://trowrestore.com/')
            for location, g in sorted(groups.items())]


def parse_christchurch(data, retrieved, url=None):
    require(isinstance(data, dict) and 'features' in data and not data.get('error'),
            'Christchurch collection-depot features are missing')
    require(not data.get('exceededTransferLimit'), 'Christchurch depot query was truncated; refusing incomplete data')
    require(data.get('spatialReference', {}).get('wkid') == 4326,
            'Christchurch depot response must use WGS84 (outSR=4326)')
    dates = [f['attributes'].get('LastEditDate') for f in data['features']]
    latest = branz_latest({'editingInfo': {'dataLastEditDate': max((d for d in dates if d is not None), default=None)}})
    rows = []
    for feature in data['features']:
        a, g = feature['attributes'], feature.get('geometry') or {}
        require(all(key in a for key in ('DepotName', 'AcceptsRefuse', 'AcceptsRecycling', 'AcceptsGreenWaste')),
                'Christchurch depot name/acceptance fields are missing')
        materials = [label for field, label in (('AcceptsRefuse', 'Refuse'), ('AcceptsRecycling', 'Recycling'),
                                               ('AcceptsGreenWaste', 'Green waste')) if a[field] == 1]
        rows.append(record('christchurch', a['DepotName'], lon=g.get('x'), lat=g.get('y'),
                           materials=materials, hours=a.get('OperatingHours'),
                           details='Council collection depot. Broad acceptance flags do not specify individual materials or reuse services.',
                           url=url, retrieved=retrieved, latest=latest, id=a['CollectionDepotID']))
    require(rows, 'Christchurch returned no collection depots')
    return rows


def parse_zerowaste(data, retrieved):
    require(isinstance(data, list) and data, 'Zero Waste Aotearoa member-marker array is missing')
    rows = []
    for marker in data:
        require(all(k in marker for k in ('id', 'title', 'map_id', 'lat', 'lng')),
                'Zero Waste Aotearoa marker fields are missing')
        # The endpoint ignores map_id and returns multiple maps. Select the
        # published member map locally, rather than mixing other map content.
        if str(marker['map_id']) != '2':
            continue
        if str(marker.get('approved', '1')) != '1':
            continue
        rows.append(record('zerowaste', marker['title'], marker.get('address'), marker['lng'], marker['lat'],
                           materials=['Resource recovery network member'], details=marker.get('description'),
                           retrieved=retrieved, id=str(marker['id']), website=marker.get('link') or None))
    require(rows, 'Zero Waste Aotearoa returned no approved members')
    return rows


def parse_habitat(text, retrieved):
    class Cards(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows = []

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag != 'div' or 'js-op-shop-card' not in a.get('class', '').split():
                return
            require(all(a.get(key) for key in ('data-id', 'data-title', 'data-address')),
                    'Habitat op-shop card fields are missing')
            self.rows.append(record('habitat', a['data-title'], a['data-address'], a.get('data-lng'), a.get('data-lat'),
                                    materials=['Op Shops', 'Reuse', 'Second hand'],
                                    details='Pre-loved goods. Confirm donation acceptance and opening hours with the store.',
                                    retrieved=retrieved, id=a['data-id']))
    parser = Cards()
    parser.feed(text)
    require(parser.rows, 'Habitat directory contains no op-shop cards')
    require(len({r['id'] for r in parser.rows}) == len(parser.rows), 'Habitat directory contains duplicate store cards')
    return parser.rows


def parse_crc(text, retrieved):
    """Read the visible CRC list; ignore unrelated Wix business coordinates."""
    lines = page(text).lines
    marker = 'More information about each CRC is coming soon!'
    require(marker in lines, 'Auckland CRC directory list marker is missing')
    start = lines.index(marker) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith('©')), None)
    require(end is not None, 'Auckland CRC directory list end is missing')
    entries = [line for line in lines[start:end] if line.strip('\u200b \xa0')]
    require(entries and len(entries) % 4 == 0, 'Auckland CRC directory name/locality/address structure changed')
    rows = []
    for i in range(0, len(entries), 4):
        name, locality, address, display_address = entries[i:i + 4]
        require(address.endswith('New Zealand') and re.search(r'\d', display_address),
                'Auckland CRC directory address fields are missing')
        rows.append(record('crc', name, address, materials=['Reuse', 'Community recycling centre'],
                           details='Community recycling directory; confirm individual material acceptance, charges and hours with the operator.',
                           retrieved=retrieved, locality=locality, display_address=display_address))
    return rows


def repair_urls(text):
    root = ET.fromstring(text)
    urls = [e.text for e in root.iter() if e.tag.endswith('}loc')]
    require(urls, 'Repair Network sitemap has no café URLs')
    for url in urls:
        require(urlparse(url).hostname == 'www.repairnetworkaotearoa.org.nz'
                and urlparse(url).path.startswith('/localrepaircafes/'), 'Unexpected repair café URL')
    return urls


def parse_repair(text, url, retrieved):
    lines = page(text).lines
    require('◀ Back' in lines and '◀ Previous' in lines, 'Repair café detail layout has changed')
    details = lines[lines.index('◀ Back') + 1:lines.index('◀ Previous')]
    require(len(details) >= 3, 'Repair café detail is incomplete')
    address = next((s for s in details if re.search(r'New Zealand|\b\d{4}\b', s)
                    and not s.startswith('http')), None)
    schedules = [s for s in details if re.search(r'\b(month|monthly|saturday|sunday|monday|tuesday|wednesday|thursday|friday|fortnight|weekly|\d[ap]m)\b', s, re.I)
                 and s != address and not s.startswith('http')]
    return record('repair', details[0], address, materials=['Repair café'], hours=' '.join(schedules),
                  details=' '.join(details[1:]), url=url, retrieved=retrieved)


def parse_tyrewise(text, url, retrieved):
    archives = re.findall(r'<article\b.*?</article>', text, re.S)
    if archives:
        rows = []
        for card in archives:
            name = re.search(r'<h2\b[^>]*class="[^"]*entry-title[^>]*>(.*?)</h2>', card, re.S)
            require(name, 'Tyrewise archive site title is missing')
            attrs = re.search(r'<article\b[^>]*class="([^"]*)"', card, re.S)
            classes = attrs.group(1).split() if attrs else []
            require('participant_cat-collection-site' in classes, 'Tyrewise archive contains a non-collection site')
            def taxonomy(prefix):
                slug = next((c[len(prefix):] for c in classes if c.startswith(prefix)), None)
                return slug.replace('-', ' ').title() if slug else None
            link = next((href for href, _ in page(name.group(1)).links), None)
            if link:
                require(urlparse(link).hostname == 'www.tyrewise.co.nz' and urlparse(link).path.startswith('/registered-partners/'), 'Unexpected Tyrewise site link')
            rows.append(record('tyrewise', name.group(1), materials=['Tyres'], url=url, retrieved=retrieved,
                               region=taxonomy('region-'), territory=taxonomy('city-'), website=link))
        nxt = next((href for href, label in page(text).links if label.startswith('Next')), None)
        return rows, nxt
    cards = re.split(r'<div\s+data-elementor-type="loop-item"', text)[1:]
    require(cards, 'Tyrewise collection-site cards are missing')
    rows = []
    for card in cards:
        name = re.search(r'<h3\b[^>]*>(.*?)</h3>', card, re.S)
        require(name, 'Tyrewise site title is missing')
        # The card gives region/territory and a short map link, not a street address.
        # Do not use territory text as a street address or infer coordinates.
        maplink = re.search(r'href="(https://maps\.app\.goo\.gl/[^"<>]+)"', card)
        terms = re.findall(r'<span class="dce-term-item[^"<>]*">(.*?)</span>', card, re.S)
        rows.append(record('tyrewise', name.group(1), materials=['Tyres'], url=url, retrieved=retrieved,
                           region=clean(terms[1]) if len(terms) > 1 else None,
                           territory=clean(terms[0]) if terms else None,
                           map_url=html.unescape(maplink.group(1)) if maplink else None))
    nxt = re.search(r'data-next-page="([^"]+)"', text)
    bounds = re.search(r'data-page="(\d+)" data-max-page="(\d+)"', text)
    # Elementor leaves a next-page link even on the final page. Honour its bound.
    last = bounds and int(bounds.group(1)) >= int(bounds.group(2))
    return rows, html.unescape(nxt.group(1)) if nxt and not last else None


def branz_latest(meta):
    stamp = meta.get('editingInfo', {}).get('dataLastEditDate')
    return datetime.fromtimestamp(stamp / 1000, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z') if stamp else None


def invalid_agrecovery_page(exc):
    """nzfetch retains the HTTPError cause; accept only WP's terminal-page code."""
    cause = exc.__cause__
    while cause is not None:
        if isinstance(cause, HTTPError) and cause.code == 400:
            try:
                return json.loads(cause.read()).get('code') == 'rest_post_invalid_page_number'
            except (ValueError, OSError, AttributeError):
                return False
        cause = cause.__cause__
    return False


def load_uncached(source, probe=False):
    spec, retrieved = SOURCES[source], utc_now()
    url = spec['url']
    if source == 'council':
        raise SourceError(f'Council item guidance is not implemented; consult {COUNCIL}', 7, source_url=COUNCIL)
    if source == 'techcollect':
        raise SourceError('TechCollect is skipped: script access is blocked; no verified keyless feed', 7)
    if source == 'recyclemap':
        data = get(url, True)
        rows = parse_recyclemap(data, get(RM + 'maps', True), get(RM + 'categories', True), retrieved)
    elif source == 'wasteminz':
        rows = parse_kml(get(url), retrieved)
    elif source == 'branz':
        meta = get(url + '?f=json', True)
        latest = branz_latest(meta)
        query = url + '/query?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=json'
        rows = parse_branz(get(query, True), retrieved, latest)
        for row in rows:
            row['source_url'] = row['provenance']['source_url'] = query
    elif source == 'ecycle':
        rows = parse_ecycle(get(url, True), retrieved)
    elif source == 'agrecovery':
        rows = []
        for index in range(1, 21):
            endpoint = url.replace('page=1&', f'page={index}&')
            if index > 1:
                time.sleep(10)  # Agrecovery declares Crawl-delay: 10.
            try:
                data = get(endpoint, True)
            except SourceError as exc:
                if index > 1 and invalid_agrecovery_page(exc):
                    break
                raise
            rows.extend(parse_agrecovery(data, retrieved, endpoint))
            if len(data) < 100:
                break
        else:
            raise SourceError('Agrecovery exceeded the 20-page bound')
        require(rows, 'Agrecovery returned no active collection sites')
    elif source == 'beautification':
        rows = parse_beautification(get(url, True), retrieved)
    elif source == 'trow':
        rows = parse_trow(get(url, True), retrieved)
    elif source == 'christchurch':
        query = url + '/query?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=json'
        rows = parse_christchurch(get(query, True), retrieved, query)
    elif source == 'zerowaste':
        rows = parse_zerowaste(get(url, True), retrieved)
    elif source == 'habitat':
        rows = parse_habitat(get(url), retrieved)
    elif source == 'crc':
        rows = parse_crc(get(url), retrieved)
    elif source == 'repair':
        urls = repair_urls(get(url))
        require(len(urls) <= 150, 'Repair café sitemap exceeds the 150-page bound')
        if probe:
            rows = [record('repair', url.rsplit('/', 1)[-1], url=url, retrieved=retrieved) for url in urls]
        else:
            def detail(link):
                time.sleep(0.25)
                try:
                    return parse_repair(get(link), link, retrieved), None
                except (SourceError, KeyError, TypeError, ValueError, AttributeError, IndexError, ET.ParseError) as exc:
                    return None, f'Repair café unavailable: {link}: {exc}'
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(detail, urls))
            rows = [row for row, warning in outcomes if row is not None]
            warnings = [warning for row, warning in outcomes if warning]
            require(len(warnings) <= len(urls) / 2, 'More than half of repair café detail pages failed: ' + '; '.join(warnings))
            require(rows, 'No repair café detail pages could be parsed')
            if warnings:
                rows[0]['source_warnings'] = warnings
    elif source == 'tyrewise':
        rows, next_url = [], url
        for _ in range(20):
            text = get(next_url)
            batch, next_url = parse_tyrewise(text, next_url, retrieved)
            rows.extend(batch)
            if not next_url:
                break
            require(next_url.startswith(url + 'page/'), 'Tyrewise pagination leaves the collection-site directory')
            time.sleep(0.25)
        else:
            raise SourceError('Tyrewise exceeded the 20-page bound')
    else:
        raise SourceError('Unsupported source', 7)
    return rows


def load(source, refresh=False):
    cache = CACHE / (source + '.json')
    if not refresh:
        try:
            saved = json.loads(cache.read_text())
            if saved.get('version') == PARSER_VERSION and time.time() - saved['saved_at'] < TTL:
                require(isinstance(saved.get('records'), list) and saved['records'], 'Cache records are missing')
                return saved['records'], True
        except (OSError, ValueError, KeyError, TypeError):
            pass
    rows = load_uncached(source)
    # Cache only normalised public directory fields, never complete site settings.
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=CACHE, delete=False) as handle:
            temp = Path(handle.name)
            json.dump({'version': PARSER_VERSION, 'saved_at': time.time(), 'records': rows}, handle)
        try:
            temp.replace(cache)
        finally:
            temp.unlink(missing_ok=True)
    except OSError:
        pass  # Read-only installations can still query public sources.
    return rows, False


def selected(args):
    return list(dict.fromkeys(args.source or DEFAULT_SOURCES))


def combined(args):
    rows, health = [], []
    failures = []
    sources = selected(args)
    # Parallelise directories, retaining each source's own request pacing and
    # selection order for records, health entries and the first failure.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(load, source, args.refresh) for source in sources]
        for source, future in zip(sources, futures):
            try:
                data, cached = future.result()
                url = SOURCES[source]['url'] if source == 'repair' else data[0]['source_url']
                health.append({'source': source, 'status': 'ok', 'count': len(data), 'cached': cached,
                               'warnings': data[0].get('source_warnings', []),
                               **provenance(source, url=url, retrieved=data[0]['retrieved_at'], latest=data[0].get('latest_data'))})
                rows.extend(data)
            except (SourceError, KeyError, TypeError, ET.ParseError, ValueError, AttributeError, IndexError) as exc:
                error = exc if isinstance(exc, SourceError) else SourceError(f'{source} parser/schema error: {exc}')
                error.source = source
                failures.append(error)
                health.append({'source': source, 'status': 'error', 'code': error.code, 'error': str(error),
                               **({'retry_after': error.retry_after} if error.retry_after is not None else {}),
                               **provenance(source, url=error.source_url)})
    if not rows and failures:
        raise failures[0]
    return rows, health


ALIASES = {'battery': ['batteries', 'household batteries'], 'batteries': ['batteries', 'household batteries'],
           'car battery': ['car batteries'], 'car batteries': ['car batteries'],
           'ewaste': ['e-waste', 'e-waste and electrical items'], 'e-waste': ['e-waste', 'e-waste and electrical items'],
           'electronics': ['e-waste', 'e-waste and electrical items'], 'tyre': ['tyres'],
           'repair': ['repair café'],
           'clothing': ['clothing', 'clothing (resalable)', 'clothing (not resalable)', 'op shops', 'textiles'],
           'reuse': ['op shops', 'reuse', 'second hand', 'rehome'], 'rehoming': ['rehome'],
           'salvage': ['salvaged building materials'], 'paper': ['cardboard and paper', 'paper'],
           'cardboard': ['cardboard and paper', 'cardboard'], 'metal': ['scrap metal', 'ferrous metal', 'non-ferrous metal']}


def material_matches(row, query):
    query = query.casefold()
    if query in ALIASES:
        return any(label.casefold() in ALIASES[query] for label in row['materials'])
    return any(query in label.casefold() for label in row['materials'])


def coordinates(value, count=2):
    try:
        parts = [float(x) for x in value.split(',')]
        if len(parts) != count or not all(math.isfinite(x) for x in parts):
            raise ValueError
        for lon, lat in zip(parts[::2], parts[1::2]):
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError
        if count == 4 and (parts[0] >= parts[2] or parts[1] >= parts[3]):
            raise ValueError
        return parts
    except ValueError:
        raise argparse.ArgumentTypeError('Use valid longitude,latitude' if count == 2 else 'Use minLon,minLat,maxLon,maxLat without crossing the antimeridian')


def distance(lon, lat, near):
    a, b, c, d = map(math.radians, (near[0], near[1], lon, lat))
    h = math.sin((d-b)/2)**2 + math.cos(b)*math.cos(d)*math.sin((c-a)/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, h)))


def spatial_filter(rows, bbox=None, near=None, radius=20):
    result = []
    for row in rows:
        if bbox or near:
            if row['lon'] is None or row['lat'] is None:
                continue
            lon, lat = row['lon'], row['lat']
            if bbox and not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
                continue
            if near:
                km = distance(lon, lat, near)
                if km > radius:
                    continue
                row = {**row, 'distance_km': round(km, 3)}
        result.append(row)
    if near:
        result.sort(key=lambda r: r['distance_km'])
    return result


def envelope(rows, args, health=(), warnings=(), total=None):
    stamps = [s['retrieved_at'] for s in health if s['status'] == 'ok']
    p = {'source_url': PRIMARY_URL,
         'publisher': 'Multiple NZ collection directories', 'retrieved_at': min(stamps) if stamps else utc_now()}
    if len(health) == 1:
        p = {key: health[0][key] for key in ('source_url', 'publisher', 'licence', 'retrieved_at', 'latest_data') if key in health[0]}
    elif any(s.get('latest_data') for s in health):
        p['latest_data'] = {s['source']: s['latest_data'] for s in health if s.get('latest_data')}
    if getattr(args, 'format', 'json') == 'geojson':
        features = [{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [r['lon'], r['lat']]}
                     if r['lon'] is not None and r['lat'] is not None else None,
                     'properties': r} for r in rows]
        result = geojson_envelope(features, p)
    else:
        result = result_envelope(rows, p)
    # run_skill reserves top-level status for a complete success/failure marker.
    result.update(result_status='partial' if any(s['status'] not in ('ok', 'skipped') or s.get('warnings') for s in health) else 'ok',
                  query={'command': args.command}, count=len(rows),
                  total_matches=len(rows) if total is None else total,
                  source_status=list(health), warnings=list(warnings))
    return result


def command_sources(args):
    statuses = []
    sources = list(dict.fromkeys(args.source or SOURCES))
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [None if source == 'trow' and not args.source else
                   pool.submit(load_uncached, source, probe=True) for source in sources]
        for source, future in zip(sources, futures):
            try:
                if future is None:
                    raise SourceError('TROW is explicit-only: use --source trow; its internal endpoint returns personal seller/account fields.', 7)
                rows = future.result()
                url = SOURCES[source]['url'] if source == 'repair' else rows[0]['source_url']
                statuses.append({'source': source, 'status': 'ok', 'count': len(rows), 'kind': SOURCES[source]['kind'],
                                 'count_kind': 'sitemap detail URLs' if source == 'repair' else 'directory records',
                                 'located': None if source == 'repair' else sum(r['lon'] is not None for r in rows),
                                 **provenance(source, url=url, retrieved=rows[0]['retrieved_at'], latest=rows[0].get('latest_data'))})
            except (SourceError, KeyError, TypeError, ValueError, ET.ParseError, AttributeError, IndexError) as exc:
                error = exc if isinstance(exc, SourceError) else SourceError(f'parser/schema error: {exc}')
                statuses.append({'source': source, 'status': 'skipped' if error.code == 7 else 'blocked' if error.code == 4 else 'error',
                                 'code': error.code, 'error': str(error),
                                 **({'retry_after': error.retry_after} if error.retry_after is not None else {}),
                                 **provenance(source)})
    return envelope(statuses, args, statuses, ['sources always checks live; a status listing can succeed while some sources are blocked.'])


def fail_if_empty(rows, health):
    if not rows:
        failed = next((s for s in health if s['status'] != 'ok'), None)
        if failed:
            raise SourceError(failed['error'], failed['code'], failed.get('retry_after'), failed['source_url'], failed['source'])


def command_data(args):
    skipped = []
    if not args.source and (args.command == 'find' or getattr(args, 'bbox', None)):
        skipped = ['repair', 'tyrewise', 'crc']
        args.source = [s for s in DEFAULT_SOURCES if s not in skipped]
    rows, health = combined(args)
    warnings = ['Listings may be stale; confirm material restrictions, charges and opening times with the operator.',
                'Records remain separate across sources; counts are directory entries, not unique physical sites.']
    if skipped:
        warnings.append('repair, tyrewise and crc listings have no verified coordinates; use search <town> for them. TROW requires --source trow and has no verified coordinates.')
    if any(r['source'] == 'trow' for r in rows):
        warnings.append('TROW lists locations of available/pre-sale stock, not confirmed donation drop-offs; unspecified locations remain unlocated.')
    if any(r['source'] == 'zerowaste' for r in rows):
        warnings.append('Zero Waste Aotearoa lists network members, not verified drop-offs. Some map coordinates conflict with addresses; confirm location and services with the operator.')
    for source in health:
        warnings.extend(source.get('warnings', []))
        if source['status'] != 'ok':
            warnings.append(f"{source['source']} unavailable (code {source['code']}): {source['error']}; results may be incomplete")
    unlocated = sum(r['lon'] is None for r in rows)
    if unlocated and (getattr(args, 'bbox', None) or getattr(args, 'near', None)):
        warnings.append(f'{unlocated} entries have no verified coordinates and are excluded from spatial filters.')
    if any(r['source'] == 'recyclemap' for r in rows):
        warnings.append('RecycleMap categories describe fees, restrictions and organisations; material labels come from its maps feed.')
    if args.command == 'materials':
        grouped = {}
        for row in rows:
            for label in row['materials']:
                group = grouped.setdefault(label, {'material': label, 'count': 0, 'sources': set(), 'provenance': []})
                group['count'] += 1
                if row['source'] not in group['sources']:
                    group['sources'].add(row['source'])
                    group['provenance'].append(row['provenance'])
        records = []
        for label in sorted(grouped, key=str.casefold):
            g = grouped[label]
            g['sources'] = sorted(g['sources'])
            if len(g['sources']) == 1:
                g.update(g['provenance'][0])
            records.append(g)
        fail_if_empty(records, health)
        return envelope(records, args, health, warnings)
    if args.command == 'find':
        rows = [r for r in rows if material_matches(r, args.material)]
    elif args.command == 'search':
        terms = args.text.casefold().split()
        rows = [r for r in rows if all(t in ' '.join(str(r.get(k) or '') for k in
                 ('name', 'address', 'materials', 'details', 'region', 'territory')).casefold() for t in terms)]
    rows = spatial_filter(rows, args.bbox, getattr(args, 'near', None), getattr(args, 'radius', 20))
    fail_if_empty(rows, health)
    if any(r['source'] == 'branz' and (r.get('facility_type') == 'Service' or r.get('status') != 'Existing') for r in rows):
        warnings.append('BRANZ includes service contractors or facilities not marked Existing; check access and drop-off eligibility with the operator.')
    total = len(rows)
    if args.limit:
        rows = rows[:args.limit]
    result = envelope(rows, args, health, warnings, total)
    result['query'].update({k: v for k, v in vars(args).items() if k not in ('command', 'json', 'refresh', 'format')})
    return result


def command_item(args):
    raise SourceError(f'Council item guidance is not implemented; consult {COUNCIL}', 7, source_url=COUNCIL)


class InputError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InputError(message)


def build_parser():
    parser = Parser(description='Locate NZ reuse and recycling drop-offs; text-search repair and tyre collection services.')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('sources', 'materials', 'find', 'search', 'item'):
        p = sub.add_parser(name)
        p.add_argument('--json', action='store_true', help='Machine-readable JSON with provenance')
        if name != 'item':
            p.add_argument('--source', choices=list(SOURCES), action='append', help='Repeat to combine selected sources')
        if name not in ('sources', 'item'):
            p.add_argument('--refresh', action='store_true', help='Bypass the 24-hour normalised-record cache')
        if name in ('find', 'search'):
            p.add_argument('--bbox', type=lambda s: coordinates(s, 4))
            p.add_argument('--format', choices=('json', 'geojson'), default='json')
            p.add_argument('--limit', type=int, default=20, help='Maximum records (0 returns all)')
        if name == 'find':
            p.add_argument('--material', required=True)
            p.add_argument('--near', required=True, type=coordinates, help='Longitude,latitude; use --near=174.76,-36.85')
            p.add_argument('--radius', type=float, default=20, help='Radius in km (default 20)')
        if name == 'search':
            p.add_argument('text')
        if name == 'item':
            p.add_argument('thing', help='Council item name or published numeric item ID; not implemented')
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    machine = '--json' in argv or '--format=geojson' in argv or any(
        argv[i:i+2] == ['--format', 'geojson'] for i in range(len(argv)))
    parser = build_parser()
    args = None
    try:
        args = parser.parse_args(argv)
        machine = args.json or getattr(args, 'format', None) == 'geojson'
        if getattr(args, 'limit', 0) < 0:
            parser.error('--limit must be non-negative')
        if hasattr(args, 'radius') and (not math.isfinite(args.radius) or args.radius <= 0):
            parser.error('--radius must be a finite positive number')
        if hasattr(args, 'text') and not args.text.strip():
            parser.error('search text must not be empty')
        if hasattr(args, 'material') and not args.material.strip():
            parser.error('--material must not be empty')
        result = command_sources(args) if args.command == 'sources' else command_item(args) if args.command == 'item' else command_data(args)
    except (InputError, SourceError, KeyError, TypeError, ValueError, ET.ParseError, AttributeError, IndexError) as exc:
        error = exc if isinstance(exc, SourceError) else SourceError(str(exc) if isinstance(exc, InputError) else f'Source parser/schema error: {exc}', 2 if isinstance(exc, InputError) else 6)
        source = error.source or ('council' if args and args.command == 'item' else selected(args)[0] if args else 'recyclemap')
        p = ({'source_url': PRIMARY_URL, 'publisher': 'Multiple NZ collection directories', 'retrieved_at': utc_now()}
             if isinstance(exc, InputError) else provenance(source, url=error.source_url))
        # Error timestamps describe the attempted operation, per docs/contracts.md.
        result = error_envelope(error.code, str(error), p, retry_after=error.retry_after)
        if machine:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(str(error), file=sys.stderr)
        return error.code
    if args.json or getattr(args, 'format', None) == 'geojson':
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{result['count']} result(s); {result['total_matches']} matching entries")
        for r in result['results']:
            label = r.get('name') or r.get('material') or r.get('source')
            extra = r.get('address') or r.get('status') or str(r.get('count', ''))
            km = f" ({r['distance_km']} km)" if 'distance_km' in r else ''
            facility = f" [type: {r.get('facility_type') or 'unknown'}; status: {r.get('status') or 'unknown'}]" if r.get('source') == 'branz' else ''
            print(f'{label}: {extra}{km}{facility}')
        for w in result['warnings']:
            print('Note: ' + w)
        for s in result['source_status']:
            if s['status'] != 'ok':
                print(f"Note: {s['source']}: {s['error']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
