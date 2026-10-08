#!/usr/bin/env python3
"""Bounded, keyless tile discovery from LINZ's static public STAC catalogues."""
from __future__ import annotations

import argparse
import json
import math
import re
import shlex
import sys
from datetime import datetime, timezone
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOTS = {
    "elevation": "https://nz-elevation.s3.ap-southeast-2.amazonaws.com/catalog.json",
    "imagery": "https://nz-imagery.s3.ap-southeast-2.amazonaws.com/catalog.json",
}
HOSTS = {urlparse(url).hostname for url in ROOTS.values()}
PUBLISHER = "Toitū Te Whenua Land Information New Zealand"
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_CANDIDATES = 100


class SourceError(Exception):
    def __init__(self, message, code=6, retry_after=None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


def safe_url(url):
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.query or parsed.fragment):
        raise SourceError("Only public LINZ elevation/imagery bucket HTTPS URLs are supported", 2)
    return url


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@lru_cache(maxsize=128)
def fetch_json(url):
    safe_url(url)
    try:
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "TheColab-nz-stac/1"})
        with build_opener(SafeRedirect()).open(request, timeout=10) as response:
            data = response.read(MAX_JSON_BYTES + 1)
        if len(data) > MAX_JSON_BYTES:
            raise SourceError("STAC metadata exceeds the 16 MiB limit; narrow the collection", 7)
        doc = json.loads(data)
        if not isinstance(doc, dict):
            raise SourceError("STAC response must be a JSON object")
        return doc
    except HTTPError as exc:
        code = 4 if exc.code in (403, 429) else 5
        if exc.code == 404:
            raise SourceError(f"Collection or tile was not found: {url}", 2) from exc
        raise SourceError(f"network error: HTTP {exc.code} from {url}", code, exc.headers.get("Retry-After")) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SourceError(f"network error: could not retrieve {url}", 5) from exc
    except (ValueError, UnicodeError) as exc:
        raise SourceError(f"Source schema error: invalid STAC JSON from {url}") from exc


def provenance(url, licence=None, latest=None):
    return {"source_url": url, "publisher": PUBLISHER, "licence": licence,
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "latest_data": latest}


def links(doc, rel):
    if not isinstance(doc.get("links"), list):
        raise SourceError("Source schema error: missing STAC links")
    result = [link for link in doc["links"] if isinstance(link, dict) and link.get("rel") == rel]
    if any(not isinstance(link.get("href"), str) for link in result):
        raise SourceError("Source schema error: STAC link has no href")
    return result


def selector(url):
    for kind, root in ROOTS.items():
        base = root.removesuffix("catalog.json")
        if url.startswith(base) and url.endswith("/collection.json"):
            return kind + ":" + url[len(base):].removesuffix("/collection.json")
    raise SourceError("Use a collection selector from collections, or its collection.json HTTPS URL", 2)


def collection_url(value):
    if value.startswith("https://"):
        url = safe_url(value)
        selector(url)
        return url
    kind, sep, path = value.partition(":")
    if not sep or kind not in ROOTS or not path or ".." in path or path.startswith("/"):
        raise SourceError("Use elevation:<path> or imagery:<path> from collections", 2)
    url = urljoin(ROOTS[kind], path.rstrip("/") + "/collection.json")
    safe_url(url)
    return url


def title_fields(title, url):
    path = urlparse(url).path
    years = re.search(r"\((\d{4}(?:-\d{4})?)\)", title)
    resolution = re.search(r"(?:^|[_/ ])(\d+(?:\.\d+)?)m(?:[/_ ]|$)", path + " " + title)
    product = "DEM" if "/dem_" in path else "DSM" if "/dsm_" in path else "infrared" if "/rgbnir/" in path else "RGB" if "/rgb/" in path else "unknown"
    return {"year": years.group(1) if years else None,
            "resolution_m": float(resolution.group(1)) if resolution else None, "product": product}


def collection_summary(doc, url):
    if doc.get("type") != "Collection" or not isinstance(doc.get("id"), str):
        raise SourceError("Source schema error: expected a STAC Collection with an id")
    fields = title_fields(doc.get("title", ""), url)
    interval = doc.get("extent", {}).get("temporal", {}).get("interval", [])
    latest = max((i[1] for i in interval if len(i) == 2 and i[1]), default=None)
    return {"collection": selector(url), "stac_id": doc["id"], "title": doc.get("title"),
            "description": doc.get("description"), "kind": selector(url).split(":")[0],
            "region": doc.get("linz:region"), **fields,
            "resolution_m": doc.get("gsd", fields["resolution_m"]),
            "extent": doc.get("extent"), "providers": doc.get("providers", []),
            "updated": doc.get("updated"), "tile_count": len(links(doc, "item")),
            **provenance(url, doc.get("license"), latest)}


def list_collections(kind, region=None, limit=100, offset=0):
    root = ROOTS[kind]
    doc = fetch_json(root)
    if doc.get("type") != "Catalog":
        raise SourceError("Source schema error: expected a STAC Catalog")
    records = []
    for link in links(doc, "child"):
        url = safe_url(urljoin(root, link["href"]))
        key = selector(url)
        area = key.split(":", 1)[1].split("/")[0]
        if region and area != region.lower().replace(" ", "-"):
            continue
        title = link.get("title", "")
        fields = title_fields(title, url)
        records.append({"collection": key, "kind": kind, "region": area, "title": title,
                        **fields, **provenance(url, latest=fields["year"])})
    return {"command": "collections", "kind": kind, "count": len(records[offset:offset + limit]),
            "matched": len(records), "offset": offset, "limit": limit,
            "truncated": offset + limit < len(records), "collections": records[offset:offset + limit],
            "metadata_basis": "Published catalogue titles and paths; info returns collection licence and capture interval",
            **provenance(root)}


def parse_bbox(value):
    try:
        values = [float(v) for v in value.split(",")]
        if len(values) != 4 or not all(math.isfinite(v) for v in values):
            raise ValueError
        x1, y1, x2, y2 = values
        if not (-180 <= x1 <= x2 <= 180 and -90 <= y1 <= y2 <= 90):
            raise ValueError
        return values
    except ValueError as exc:
        raise argparse.ArgumentTypeError("bbox must be minLon,minLat,maxLon,maxLat in WGS84; no antimeridian crossing") from exc


def nztm(lon, lat):
    """GRS80 transverse Mercator series, EPSG:2193; used only for candidate selection."""
    if not (165 <= lon <= 180 and -48 <= lat <= -33):
        raise SourceError("Tile-grid search supports mainland NZ (165..180 E, 48..33 S); Chatham Islands require another CRS", 7)
    a = 6378137.0
    f = 1 / 298.257222101
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    phi = math.radians(lat)
    dl = math.radians(lon - 173)
    sn, cs, tn = math.sin(phi), math.cos(phi), math.tan(phi)
    n = a / math.sqrt(1 - e2 * sn * sn)
    t, c, aa = tn * tn, ep2 * cs * cs, cs * dl
    m = a * ((1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * phi
             - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * phi)
             + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * phi)
             - 35 * e2**3 / 3072 * math.sin(6 * phi))
    east = 1600000 + .9996 * n * (aa + (1 - t + c) * aa**3 / 6
                                   + (5 - 18 * t + t*t + 72*c - 58*ep2) * aa**5 / 120)
    north = 10000000 + .9996 * (m + n * tn * (aa*aa / 2
              + (5 - t + 9*c + 4*c*c) * aa**4 / 24
              + (61 - 58*t + t*t + 600*c - 330*ep2) * aa**6 / 720))
    return east, north


def grid_bounds(name):
    """LINZ Topo50 grid: sheet origin and row/column subtiles, in NZTM metres."""
    match = re.fullmatch(r"([A-Z]{2})(\d{2})(?:_(10000|5000|2000|1000|500)_(\d{4}|\d{6}))?", name)
    if not match:
        raise SourceError(f"Unsupported tile naming scheme: {name}; use a Topo50 NZTM collection", 7)
    row, col, scale, sub = match.groups()
    if row in ("BI", "BO", "CI") or not ("AS" <= row <= "CK"):
        raise SourceError(f"Unsupported mainland map sheet: {row}", 7)
    row_index = (ord(row[0]) - 65) * 26 + ord(row[1]) - ord("S")
    row_index -= sum(row > missing for missing in ("BI", "BO", "CI"))
    west, north = 988000 + int(col) * 24000, 6234000 - row_index * 36000
    width, height = 24000, 36000
    if scale:
        digits = 3 if scale == "500" else 2
        if len(sub) != 2 * digits:
            raise SourceError(f"Unsupported subtile name: {name}", 7)
        y, x = int(sub[:digits]), int(sub[digits:])
        width, height = 24000 * int(scale) / 50000, 36000 * int(scale) / 50000
        if not (1 <= x <= 50000 / int(scale) and 1 <= y <= 50000 / int(scale)):
            raise SourceError(f"Invalid subtile index: {name}")
        west += (x - 1) * width
        north -= (y - 1) * height
    return [west, north - height, west + width, north]


def intersects(a, b):
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def point_in_ring(point, ring):
    x, y = point
    inside = False
    for p, q in zip(ring, ring[1:]):
        cross = (x - p[0]) * (q[1] - p[1]) - (y - p[1]) * (q[0] - p[0])
        if abs(cross) < 1e-12 and min(p[0], q[0]) <= x <= max(p[0], q[0]) and min(p[1], q[1]) <= y <= max(p[1], q[1]):
            return True
        if (p[1] > y) != (q[1] > y) and x < (q[0] - p[0]) * (y - p[1]) / (q[1] - p[1]) + p[0]:
            inside = not inside
    return inside


def segment_hits_bbox(p, q, bbox):
    # Liang-Barsky clipping also handles a zero-area point bbox.
    low, high = 0.0, 1.0
    dx, dy = q[0] - p[0], q[1] - p[1]
    for direction, distance in ((-dx, p[0]-bbox[0]), (dx, bbox[2]-p[0]),
                                (-dy, p[1]-bbox[1]), (dy, bbox[3]-p[1])):
        if direction == 0:
            if distance < 0:
                return False
        elif direction < 0:
            low = max(low, distance / direction)
        else:
            high = min(high, distance / direction)
        if low > high:
            return False
    return True


def geometry_hits_bbox(geometry, bbox):
    kind = geometry.get("type")
    if kind not in ("Polygon", "MultiPolygon"):
        raise SourceError("Source schema error: tile footprint must be Polygon or MultiPolygon")
    polygons = [geometry["coordinates"]] if kind == "Polygon" else geometry["coordinates"]
    corners = [(bbox[x], bbox[y]) for x in (0, 2) for y in (1, 3)]
    for rings in polygons:
        if any(point_in_ring(c, rings[0]) and not any(point_in_ring(c, hole) for hole in rings[1:]) for c in corners):
            return True
        if any(segment_hits_bbox(p, q, bbox) for ring in rings for p, q in zip(ring, ring[1:])):
            return True
    return False


def candidate_links(doc, url, bbox):
    if not urlparse(url).path.endswith("/2193/collection.json"):
        raise SourceError("Tile-grid search requires an EPSG:2193 Topo50 collection", 7)
    # Sample edges as well as corners; 100 m padding conservatively covers series
    # approximation and curved WGS84 edges. Final filtering uses STAC geometry.
    points = []
    for i in range(21):
        x = bbox[0] + (bbox[2] - bbox[0]) * i / 20
        y = bbox[1] + (bbox[3] - bbox[1]) * i / 20
        points.extend((nztm(x, bbox[1]), nztm(x, bbox[3]), nztm(bbox[0], y), nztm(bbox[2], y)))
    projected = [min(p[0] for p in points)-100, min(p[1] for p in points)-100,
                 max(p[0] for p in points)+100, max(p[1] for p in points)+100]
    candidates = []
    for link in links(doc, "item"):
        item_url = safe_url(urljoin(url, link["href"]))
        name = urlparse(item_url).path.rsplit("/", 1)[-1].removesuffix(".json")
        if intersects(grid_bounds(name), projected):
            candidates.append(item_url)
    if len(candidates) > MAX_CANDIDATES:
        raise SourceError(f"bbox selects {len(candidates)} candidate tiles (maximum {MAX_CANDIDATES}); use a smaller bbox", 7)
    return candidates


def tile_record(item, url, summary):
    if item.get("type") != "Feature" or not item.get("id") or not item.get("geometry"):
        raise SourceError("Source schema error: expected a STAC tile Feature with id and footprint")
    props = item.get("properties", {})
    latest = props.get("end_datetime") or props.get("datetime") or summary["latest_data"]
    assets = []
    for key, asset in item.get("assets", {}).items():
        if "cloud-optimized" in asset.get("type", ""):
            cog_url = safe_url(urljoin(url, asset["href"]))
            assets.append({"key": key, "url": cog_url, "type": asset["type"],
                           **provenance(cog_url, summary["licence"], latest)})
    if not assets:
        raise SourceError("Source schema error: tile has no declared cloud-optimised GeoTIFF asset")
    return {"id": item["id"], "collection": summary["collection"], "bbox": item["bbox"],
            "geometry": item["geometry"], "cog_assets": assets,
            "product": summary["product"], "resolution_m": summary["resolution_m"],
            **provenance(url, summary["licence"], latest)}


def find_tiles(value, bbox, limit=20):
    url = collection_url(value)
    doc = fetch_json(url)
    summary = collection_summary(doc, url)
    candidates = candidate_links(doc, url, bbox)
    records, inspected = [], 0
    # Stop after one extra match so truncated is accurate without downloading all metadata.
    for item_url in candidates:
        item = fetch_json(item_url)
        inspected += 1
        record = tile_record(item, item_url, summary)
        if intersects(record["bbox"], bbox) and geometry_hits_bbox(record["geometry"], bbox):
            records.append(record)
            if len(records) > limit:
                break
    return {"command": "tiles", "collection": summary["collection"], "bbox": bbox,
            "count": min(len(records), limit), "limit": limit, "truncated": len(records) > limit,
            "candidates": len(candidates), "items_inspected": inspected,
            "tiles": records[:limit], **provenance(url, summary["licence"], summary["latest_data"])}


def point_result(value, lon, lat):
    if not math.isfinite(lon) or not math.isfinite(lat):
        raise SourceError("Longitude and latitude must be finite numbers", 2)
    url = collection_url(value)
    summary = collection_summary(fetch_json(url), url)
    if summary["kind"] != "elevation" or summary["product"] not in ("DEM", "DSM"):
        raise SourceError("point requires an elevation DEM or DSM collection", 2)
    result = find_tiles(value, [lon, lat, lon, lat], limit=4)
    for tile in result["tiles"]:
        cog = tile["cog_assets"][0]["url"]
        tile["gdal_command"] = f"gdallocationinfo -valonly -wgs84 {shlex.quote('/vsicurl/' + cog)} {lon} {lat}"
    return {**result, "command": "point", "longitude": lon, "latitude": lat,
            "sampling_status": "sampling_required" if result["tiles"] else "no_tile", "elevation": None,
            "sampling_note": "The stdlib CLI locates tiles only. Run the supplied GDAL command with GDAL installed to sample band 1 using HTTP range reads; check nodata and the source vertical datum.",
            "value_units": "Consult collection documentation"}


def geojson(result):
    if result["command"] == "point":
        features = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [result["longitude"], result["latitude"]]},
                     "properties": {k: v for k, v in result.items() if k != "bbox"}}]
    else:
        features = [{"type": "Feature", "id": r["id"], "bbox": r["bbox"], "geometry": r["geometry"],
                     "properties": {k: v for k, v in r.items() if k not in ("geometry", "bbox")}} for r in result["tiles"]]
    output = {"type": "FeatureCollection", "features": features,
              **{k: v for k, v in result.items() if k not in ("tiles", "bbox")},
              "query_bbox": result["bbox"]}
    if result["command"] == "point":
        output["bbox"] = result["bbox"]
    elif features:
        # RFC 7946 bbox encloses the returned geometry, not the search window.
        output["bbox"] = [min(f["bbox"][0] for f in features), min(f["bbox"][1] for f in features),
                          max(f["bbox"][2] for f in features), max(f["bbox"][3] for f in features)]
    return output


def bounded_int(low, high):
    def parse(value):
        try:
            number = int(value)
            if low <= number <= high:
                return number
        except ValueError:
            pass
        raise argparse.ArgumentTypeError(f"must be an integer between {low} and {high}")
    return parse


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("collections", help="list datasets from a public bucket catalogue")
    c.add_argument("--kind", choices=ROOTS, required=True)
    c.add_argument("--region", help="region path, e.g. auckland")
    c.add_argument("--limit", type=bounded_int(1, 200), default=100)
    c.add_argument("--offset", type=bounded_int(0, 100000), default=0)
    t = sub.add_parser("tiles", help="find COG tile URLs and footprints intersecting a WGS84 bbox")
    t.add_argument("collection", help="selector from collections or collection.json HTTPS URL")
    t.add_argument("--bbox", required=True, type=parse_bbox)
    t.add_argument("--limit", type=bounded_int(1, 50), default=20)
    i = sub.add_parser("info", help="collection capture dates, licence, providers and extent")
    i.add_argument("collection")
    point = sub.add_parser("point", help="locate an elevation tile and return a GDAL range-read sampling command")
    point.add_argument("--lon", required=True, type=float)
    point.add_argument("--lat", required=True, type=float)
    point.add_argument("--collection", required=True)
    for command in (c, t, i, point):
        command.add_argument("--json", action="store_true", help="emit machine-readable JSON with provenance")
    for command in (t, point):
        command.add_argument("--format", choices=("json", "geojson"), default="json")
    return p


def main():
    args = parser().parse_args()
    try:
        if args.command == "collections":
            result = list_collections(args.kind, args.region, args.limit, args.offset)
        elif args.command == "info":
            url = collection_url(args.collection)
            result = {"command": "info", **collection_summary(fetch_json(url), url)}
        elif args.command == "tiles":
            result = find_tiles(args.collection, args.bbox, args.limit)
        else:
            result = point_result(args.collection, args.lon, args.lat)
        if getattr(args, "format", "json") == "geojson":
            result = geojson(result)
        if args.json or getattr(args, "format", "json") == "geojson":
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        elif args.command == "collections":
            for r in result["collections"]:
                print(f"{r['collection']}\n  {r['title']} | {r['product']} | {r['resolution_m']} m")
            print(f"{result['count']} of {result['matched']} collections; truncated={result['truncated']}")
        elif args.command == "info":
            print(f"{result['title']}\n{result['collection']}\n{result['tile_count']} tiles | {result['licence']} | capture ends {result['latest_data']}\n{result['source_url']}")
        else:
            for r in result["tiles"]:
                print(f"{r['id']} | {r['cog_assets'][0]['url']}")
                if r.get("gdal_command"):
                    print(r["gdal_command"])
            if result.get("sampling_note"):
                print(result["sampling_note"])
            print(f"{result['count']} tiles; truncated={result['truncated']}")
        return 0
    except SourceError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc), "exit_code": exc.code,
                              "retry_after": exc.retry_after,
                              **provenance(ROOTS.get(getattr(args, "kind", "elevation"), ROOTS["elevation"]))}))
        print(f"Error: {exc}", file=sys.stderr)
        return exc.code
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        message = f"Source schema error: invalid STAC fields ({type(exc).__name__})"
        if args.json:
            print(json.dumps({"ok": False, "error": message, **provenance(ROOTS["elevation"])}))
        print(f"Error: {message}", file=sys.stderr)
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
