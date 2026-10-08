#!/usr/bin/env python3
"""Small public council probes; no source records are written to disk."""
import concurrent.futures
import csv
import io
import json
from pathlib import Path
import subprocess
import sys

CLI = Path(__file__).with_name('cli.py')
CCC = 'https://gis.ccc.govt.nz/server/rest/services/OpenData/Structure/FeatureServer/2'
DCC = 'https://apps.dunedin.govt.nz/arcgis/rest/services/Public/Search/FeatureServer/0'
HCC = 'https://services1.arcgis.com/R6s0QqCMQdwKY6yp/arcgis/rest/services/RoadHierarchy20260623/FeatureServer/0'
PC120 = 'https://tiles.arcgis.com/tiles/n4yPwebTjJCmXB6W/arcgis/rest/services/PC120Revised_PROD_Precincts/MapServer'
FLOODED = 'https://services-ap1.arcgis.com/eqbFSejuTufXDr0E/arcgis/rest/services/flooded_nz_gdb_v2_202603181308/FeatureServer/0'
FLOODED_FIELDS = {'objectid', 'obs_date', 'impact', 'impact_items', 'obs_depth', 'obs_depth_v2', 'historic', 'status'}
TILED = 'https://tiledimageservices1.arcgis.com/n4yPwebTjJCmXB6W/arcgis/rest/services/Synthetic_DEM/ImageServer'


def run():
    probes = [
        ('Christchurch fences', ['query', CCC, '--bbox', '172.635,-43.535,172.64,-43.53', '--fields', 'FenceID,Height', '--limit', '2', '--format', 'geojson']),
        ('Dunedin formed roads', ['query', DCC, '--bbox', '170.49,-45.885,170.51,-45.87', '--fields', 'OBJECTID', '--limit', '2', '--format', 'geojson']),
        ('Hamilton hierarchy', ['query', HCC, '--bbox', '175.27,-37.79,175.29,-37.78', '--fields', 'OBJECTID', '--limit', '2', '--format', 'geojson']),
        ('PC120 precinct metadata', ['describe', PC120]),
        ('Flooded NZ count', ['count', FLOODED]),
        ('Flooded NZ describe', ['describe', FLOODED]),
        *[(f'Flooded NZ default {fmt} fields', ['query', FLOODED, '--limit', '1', '--format', fmt]) for fmt in ['json', 'geojson', 'csv']],
        ('NZ curated provenance', ['layers', '--curated', 'nz']),
        ('Flooded NZ wildcard refusal', ['query', FLOODED, '--fields', '*']),
        ('Flooded NZ private where refusal', ['query', FLOODED, '--where', "email IS NOT NULL"]),
        ('Tiled-image describe refusal', ['describe', TILED]),
    ]
    def probe(item):
        name, args = item
        try:
            response = subprocess.run([sys.executable, str(CLI), *args, '--json'], capture_output=True, text=True, timeout=35, check=False)
            data = json.loads(response.stdout)
            if name.endswith('refusal'):
                expected = 2 if args[0] == 'query' else 7
                reason = 'invalid_input' if expected == 2 else 'robots_disallowed'
                assert response.returncode == expected and data['results'] == []
                assert data['error']['reason'] == reason
                return 0, f'[PASS] CLI {name}: exit={expected} reason={reason}'
            if response.returncode in {4, 5}:
                return 0, f"[SKIP] live {name}: {data['error']['message']}"
            assert response.returncode == 0, response.stdout.strip() or response.stderr.strip()
            meta = data['meta']
            if args[0] == 'layers':
                expected = ['https://github.com/thecolab-ai/.skills/blob/main/skills/nz-arcgis/references/' + filename for filename in ['layers-auckland.json', 'layers-nz.json']]
                assert meta['source_urls'] == expected and meta['source_url'] == expected[0]
                assert data['results']
                return 0, f"[PASS] CLI {name}: records={len(data['results'])} source_files=2"
            assert meta['source_url'] == args[1] and meta['publisher'] and meta['retrieved_at'].endswith('Z')
            if args[0] == 'query' and args[1] == FLOODED:
                assert data['feature_count'] == 1 and not data['incomplete']
                fmt = args[-1]
                if fmt == 'csv':
                    rows = list(csv.DictReader(io.StringIO(data['results'][0]['csv'])))
                    assert len(rows) == 1
                    fields = {k for k in rows[0] if not k.startswith('provenance_')}
                else:
                    feature = data['features' if fmt == 'geojson' else 'results'][0]
                    fields = set(feature['properties' if fmt == 'geojson' else 'attributes'])
                assert fields == FLOODED_FIELDS
                detail = f"features={data['feature_count']} allowlisted_fields={len(fields)}"
            elif args[0] == 'query':
                assert data['type'] == 'FeatureCollection'
                if not data['features']:
                    return 0, f'[SKIP] live {name}: no current features in bbox'
                assert 1 <= len(data['features']) <= 2
                assert not data['incomplete'] and data['missing_object_ids_count'] == 0
                assert all(f['geometry'] and f['properties'] for f in data['features'])
                detail = f"features={len(data['features'])} matched={data['matched_count']} first_id={data['features'][0]['id']} geometry={data['features'][0]['geometry']['type']}"
            elif args[0] == 'describe' and args[1] == FLOODED:
                fields = {f['name'] for f in data['results'][0]['fields']}
                assert fields == FLOODED_FIELDS
                detail = f'allowlisted_fields={len(fields)}'
            elif args[0] == 'describe':
                row = data['results'][0]
                assert row['tile_only'] and row['server_type'] == 'MapServer' and row['layers']
                assert row['extent']['spatialReference']['wkid'] == 2193
                assert 'record_count' not in row and 'licence' not in meta
                detail = f"layers={len(row['layers'])} capabilities={row['capabilities']} extent_crs=2193"
            else:
                assert isinstance(data['results'][0]['count'], int) and data['results'][0]['count'] >= 0
                assert 'licence' not in meta and meta['latest_data'].endswith('Z')
                detail = f"count={data['results'][0]['count']} latest_data={meta['latest_data']}"
            return 0, f'[PASS] live {name}: {detail}'
        except subprocess.TimeoutExpired:
            return 0, f'[SKIP] live {name}: bounded probe timed out'
        except Exception as exc:
            return 1, f'[FAIL] live {name}: {exc}'
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for failed, message in pool.map(probe, probes):
            failures += failed
            print(message)
    return failures


if __name__ == '__main__':
    raise SystemExit(1 if run() else 0)
