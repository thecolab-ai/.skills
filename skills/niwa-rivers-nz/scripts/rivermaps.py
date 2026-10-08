#!/usr/bin/env python3
"""Bounded read-only client for the public River Maps Shiny/SockJS interface."""
from __future__ import annotations

import html
import json
import math
import re
import time
import uuid

import nzfetch

URL = 'https://shiny.niwa.co.nz/nzrivermaps/'
METRICS = ('Mean Flow', 'Median flow', 'MALF', '1 in 5 year low flow', 'FRE3',
           'February flow seasonality', 'Month lowest mean flow')


class RiverMapsError(Exception):
    def __init__(self, code, message, retry_after=None):
        super().__init__(message)
        self.code, self.retry_after = code, retry_after


def plain_text(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', value))).strip()


def frames(body):
    """Decode SockJS data without retaining config/session identifiers."""
    if body.strip() in ('o', 'h'):
        return []
    if body.startswith('c'):
        raise RiverMapsError(5, 'network error: River Maps closed the public session')
    try:
        if not body.startswith('a'):
            raise ValueError('not a SockJS data frame')
        packets = json.loads(body[1:])
        if not isinstance(packets, list):
            raise ValueError('packet list missing')
        messages = []
        for packet in packets:
            if not isinstance(packet, str) or not packet.startswith('0|m|'):
                raise ValueError('unexpected multiplex frame')
            message = json.loads(packet[4:])
            if not isinstance(message, dict):
                raise ValueError('message is not an object')
            message.pop('config', None)
            messages.append(message)
        return messages
    except (ValueError, TypeError) as exc:
        raise RiverMapsError(6, 'source schema failure: invalid River Maps transport frame') from exc


def lines_from_leaflet(value):
    lines = []
    def walk(item):
        if isinstance(item, dict):
            xs, ys = item.get('lng'), item.get('lat')
            if not isinstance(xs, list) or not isinstance(ys, list) or len(xs) != len(ys) or len(xs) < 2:
                raise RiverMapsError(6, 'source schema failure: malformed River Maps polyline')
            line = []
            for x, y in zip(xs, ys):
                if (type(x) not in (int, float) or type(y) not in (int, float)
                        or not math.isfinite(x) or not math.isfinite(y)
                        or not -180 <= x <= 180 or not -90 <= y <= 90):
                    raise RiverMapsError(6, 'source schema failure: invalid River Maps WGS84 coordinates')
                line.append([x, y])
            lines.append(line)
        elif isinstance(item, list):
            for child in item:
                walk(child)
        else:
            raise RiverMapsError(6, 'source schema failure: unrecognised River Maps line encoding')
    walk(value)
    if not lines:
        raise RiverMapsError(6, 'source schema failure: empty River Maps reach geometry')
    return lines


def parse_polylines(call, metric):
    args = call.get('args')
    if not isinstance(args, list) or len(args) < 5 or args[2] != 'MapLines':
        raise RiverMapsError(6, 'source schema failure: River Maps polyline arguments changed')
    geometry, ids, popups = args[0], args[1], args[4]
    if not isinstance(geometry, list) or not isinstance(ids, list) or len(geometry) != len(ids):
        raise RiverMapsError(6, 'source schema failure: River Maps line/ID counts differ')
    if not geometry:
        return [], isinstance(popups, str) and metric + ':' in popups
    if not isinstance(popups, list) or len(popups) != len(ids):
        raise RiverMapsError(6, 'source schema failure: River Maps tooltip count differs')
    if all(isinstance(p, str) and metric + ':' not in p for p in popups):
        return [], False  # initial map uses the REC climate class before the update
    rows = []
    for encoded, reach_id, popup in zip(geometry, ids, popups):
        if not isinstance(popup, str):
            raise RiverMapsError(6, 'source schema failure: River Maps tooltip is not text')
        pattern = r'^nzsegment: (\d+)<br>Catchment: (.*?)<br>' + re.escape(metric) + r':\s*([^\s]+)(?:\s+(.*))?$'
        match = re.fullmatch(pattern, html.unescape(popup))
        if not match or str(reach_id) != match.group(1):
            raise RiverMapsError(6, 'source schema failure: River Maps prediction tooltip changed')
        raw = match.group(3)
        if ',' in raw and not re.fullmatch(r'[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?', raw):
            raise RiverMapsError(6, 'source schema failure: malformed thousands separator')
        try:
            value = None if raw in ('NA', 'NaN') else float(raw.replace(',', ''))
        except ValueError as exc:
            if metric == 'Month lowest mean flow':
                value = raw  # this metric displays categorical month names
            else:
                raise RiverMapsError(6, 'source schema failure: non-numeric hydrology prediction') from exc
        if isinstance(value, float) and not math.isfinite(value):
            raise RiverMapsError(6, 'source schema failure: non-finite hydrology prediction')
        rows.append({'nzsegment': int(match.group(1)), 'catchment': match.group(2),
                     'metric': metric, 'value': value, 'units': match.group(4) or None,
                     'value_precision': 'Displayed map tooltip precision',
                     'geometry': {'type': 'MultiLineString', 'coordinates': lines_from_leaflet(encoded)}})
    return rows, True


def distance_km(near, geometry):
    """Local equirectangular distance to a segment, adequate for a small search box."""
    lon, lat = near
    scale_x, scale_y = 111.32 * math.cos(math.radians(lat)), 111.32
    best = math.inf
    for line in geometry['coordinates']:
        for a, b in zip(line, line[1:]):
            ax, ay = (a[0] - lon) * scale_x, (a[1] - lat) * scale_y
            bx, by = (b[0] - lon) * scale_x, (b[1] - lat) * scale_y
            dx, dy = bx - ax, by - ay
            length = dx * dx + dy * dy
            t = max(0, min(1, -(ax * dx + ay * dy) / length)) if length else 0
            best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def query(bbox, metric='Mean Flow'):
    """Issue only public application queries; close each ephemeral session."""
    session = URL + '__sockjs__/123/' + uuid.uuid4().hex
    deadline = time.monotonic() + 50
    def request(path, data):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RiverMapsError(5, 'network error: River Maps query exceeded 50 seconds')
        try:
            return nzfetch.fetch_text(session + path, method='POST', data=data,
                                      headers={'Content-Type': 'application/json'}, timeout=min(10, remaining),
                                      allowed_hosts={'shiny.niwa.co.nz'})
        except nzfetch.RateLimited as exc:
            raise RiverMapsError(4, 'network error: River Maps rate limited', exc.retry_after) from exc
        except nzfetch.Blocked as exc:
            raise RiverMapsError(4, 'network error: River Maps access blocked') from exc
        except nzfetch.FetchError as exc:
            # Session URLs are transient; omit them from errors and provenance.
            raise RiverMapsError(5, 'network error: River Maps public session unavailable') from exc
    def send(data, init=False):
        packets = ['0|m|' + json.dumps({'method': 'init' if init else 'update', 'data': data})]
        if init:
            packets.insert(0, '0|o|')
        request('/xhr_send', json.dumps(packets).encode())
    bounds = dict(zip(('west', 'south', 'east', 'north'), bbox))
    initial = {'MetricChoices': 'Hydrology', 'SelectedVariable': metric,
               'ActionUpdate:shiny.action': 0, 'SelectedTransformation': 'None', 'SelectedColour': 'Dark2',
               'manageColourPalette': [], 'Flow': 0, 'downloadAll': 'map', 'SelectMode': 'All',
               'TabChoice': 'Map options', 'HydroMap_zoom': 12, 'HydroMap_bounds': bounds,
               '.clientdata_output_HydroMap_width': 700,
               '.clientdata_output_HydroMap_height': 500, '.clientdata_output_HydroMap_hidden': False}
    for output in ('ui_selectedvariable', 'variableDescription_Hydro', 'UpdateButton'):
        initial['.clientdata_output_' + output + '_hidden'] = False
    initial['.clientdata_output_viewData_hidden'] = True
    initial['.clientdata_output_downloadSelector_hidden'] = True
    rows, description, updated, metric_rendered = [], None, False, False
    selector_ready, initial_map_done, initial_visibility = False, False, None
    try:
        opening = request('/xhr', b'')
        if opening.strip() != 'o':
            frames(opening)  # recognised session closures are network failures
            raise RiverMapsError(6, 'source schema failure: River Maps session did not open')
        send(initial, init=True)
        for _ in range(45):
            for message in frames(request('/xhr', b'')):
                if 'alert' in message.get('custom', {}):
                    raise RiverMapsError(5, 'network error: River Maps application unexpectedly exited')
                errors = message.get('errors', {})
                if isinstance(errors, dict) and any(k in errors for k in ('HydroMap', 'ui_selectedvariable', 'variableDescription_Hydro')):
                    raise RiverMapsError(6, 'source schema failure: River Maps prediction calculation failed')
                values = message.get('values', {})
                if not updated and 'ui_selectedvariable' in values:
                    selector = values['ui_selectedvariable']
                    if not isinstance(selector, dict) or 'value="' + metric + '"' not in selector.get('html', ''):
                        raise RiverMapsError(6, 'source schema failure: requested hydrology metric disappeared')
                    selector_ready = True
                if updated and isinstance(values.get('variableDescription_Hydro'), str):
                    description = plain_text(values['variableDescription_Hydro'])
                calls = message.get('custom', {}).get('leaflet-calls', {}).get('calls', [])
                for call in calls:
                    if not updated:
                        if call.get('method') == 'addControl' and call.get('args', [''])[0].startswith('Stream order'):
                            initial_map_done = True
                            initial_visibility = plain_text(call['args'][0])
                        continue
                    if call.get('method') == 'clearGroup' and call.get('args') == ['MapLines']:
                        rows, metric_rendered = [], False
                    elif call.get('method') == 'addPolylines':
                        parsed, matches = parse_polylines(call, metric)
                        if matches:
                            rows.extend(parsed)
                            metric_rendered = True
                    elif (call.get('method') == 'addControl' and metric_rendered
                          and description and call.get('args', [''])[0].startswith('Stream order')
                          and plain_text(call['args'][0]) != initial_visibility):
                        return rows, description, plain_text(call['args'][0])
                if not updated and selector_ready and initial_map_done:
                    send({'SelectedVariable': metric, 'ActionUpdate:shiny.action': 1,
                          'HydroMap_zoom': 13, 'HydroMap_bounds': bounds})
                    updated = True
        raise RiverMapsError(5, 'network error: River Maps did not finish the bounded prediction query')
    finally:
        try:
            nzfetch.fetch_text(session + '/xhr_send', method='POST',
                               data=json.dumps(['0|c|{"code":1000,"reason":"Query complete"}']).encode(),
                               headers={'Content-Type': 'application/json'}, timeout=2,
                               allowed_hosts={'shiny.niwa.co.nz'})
        except nzfetch.FetchError:
            pass
