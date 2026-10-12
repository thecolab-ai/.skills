#!/usr/bin/env python3
"""Keyless NZ point-cloud catalogue search and bounded file listing."""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import nzfetch  # noqa: E402
from provenance import error_envelope, geojson_envelope, parse_bbox, provenance, result_envelope  # noqa: E402

PORTAL_HOST = "portal.opentopography.org"
S3_HOST = "opentopography.s3.sdsc.edu"
PORTAL_ORIGIN = "https://portal.opentopography.org"
S3_ORIGIN = "https://opentopography.s3.sdsc.edu"
PUBLISHER = "OpenTopography"
USER_AGENT = "TheColab-nz-point-clouds/1 (public metadata; no point-cloud download)"
TIMEOUT_SECONDS = 10
CATALOG_MAX_BYTES = 524_288
DOCUMENT_MAX_BYTES = 262_144
MAX_JSON_DEPTH = 30
MAX_COLLECTIONS = 200
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_OFFSET = 500
MAX_TEXT = 600
REUSABLE_LICENCE = "CC-BY-4.0"
NZ_MIN_LON, NZ_MAX_LON = 165.0, 179.5
NZ_MIN_LAT, NZ_MAX_LAT = -48.0, -33.0
ID_RE = re.compile(r"^OTLAS\.[0-9]{6}\.[0-9]{3,6}\.[0-9]{1,4}$")
ALT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")
PAGE_RE = re.compile(r"^[A-Za-z0-9+/=_-]{1,1024}$")
FIXTURE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
SUFFIXES = frozenset({".laz", ".las", ".lax", ".json"})
JSON_LD_RE = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>\s*(.*?)\s*</script>",
    re.IGNORECASE | re.DOTALL,
)
_FIXTURE_STATE: dict[str, Any] = {"name": None, "index": 0, "payload": None}


class InputError(ValueError):
    """Caller input that must be a JSON invalid_input error, not a traceback."""


class BlockedError(Exception):
    def __init__(self, message: str, *, retry_after: str | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class UpstreamError(Exception):
    pass


class SchemaError(Exception):
    pass


class UnsafeError(Exception):
    pass


class NotFoundError(Exception):
    pass


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError(message)


def source_meta(
    url: str,
    *,
    licence: str | None = None,
    latest_data: str | None = None,
) -> dict[str, str]:
    return provenance(url, PUBLISHER, licence=licence, latest_data=latest_data)


def parse_nz_bbox(value: str) -> tuple[float, float, float, float]:
    """Keep searches inside the published NZ window, including Chatham Islands."""
    box = parse_bbox(value)
    min_lon, min_lat, max_lon, max_lat = box
    if not (
        NZ_MIN_LON <= min_lon
        and max_lon <= NZ_MAX_LON
        and NZ_MIN_LAT <= min_lat
        and max_lat <= NZ_MAX_LAT
    ):
        raise argparse.ArgumentTypeError(
            "--bbox must lie inside longitude 165 to 179.5 and latitude -48 to -33"
        )
    return box


def parse_limit(value: str) -> int:
    if not str(value).isdigit():
        raise argparse.ArgumentTypeError("--limit must be an integer from 1 to 50")
    number = int(value)
    if not 1 <= number <= MAX_LIMIT:
        raise argparse.ArgumentTypeError("--limit must be an integer from 1 to 50")
    return number


def parse_offset(value: str) -> int:
    if not str(value).isdigit():
        raise argparse.ArgumentTypeError("--offset must be an integer from 0 to 500")
    number = int(value)
    if number > MAX_OFFSET:
        raise argparse.ArgumentTypeError("--offset must be an integer from 0 to 500")
    return number


def parse_suffix(value: str) -> str:
    text = value if value.startswith(".") else f".{value}"
    if text.lower() not in SUFFIXES:
        raise argparse.ArgumentTypeError("--suffix must be laz, las, lax, or json")
    return text.lower()


def parse_page(value: str) -> str:
    if not PAGE_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("--page must be a next_page value from a previous files result")
    return value


def parse_opentopo_id(value: str) -> str:
    if not ID_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("opentopo id must look like OTLAS.042025.2193.1")
    return value


def format_coord(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def assert_allowed_url(url: str, kind: str) -> None:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or not host
    ):
        raise UnsafeError("refusing a request outside the OpenTopography allowlist")
    if kind in {"catalog", "dataset"}:
        if host != PORTAL_HOST:
            raise UnsafeError("refusing off-host redirect; requests stay on portal.opentopography.org")
        expected = "/API/otCatalog" if kind == "catalog" else "/lidarDataset"
        if parsed.path != expected:
            raise UnsafeError(f"refusing a request outside {expected}")
        return
    if kind == "listing":
        if host != S3_HOST or parsed.path != "/pc-bulk":
            raise UnsafeError("refusing a listing request outside the pc-bulk list endpoint")
        return
    raise UnsafeError("refusing an unknown request kind")


def catalog_url(box: tuple[float, float, float, float]) -> str:
    min_lon, min_lat, max_lon, max_lat = box
    query = urllib.parse.urlencode(
        {
            "productFormat": "PointCloud",
            "detail": "false",
            "minx": format_coord(min_lon),
            "miny": format_coord(min_lat),
            "maxx": format_coord(max_lon),
            "maxy": format_coord(max_lat),
            "outputFormat": "json",
        }
    )
    return f"{PORTAL_ORIGIN}/API/otCatalog?{query}"


def dataset_url(opentopo_id: str) -> str:
    query = urllib.parse.urlencode({"opentopoID": opentopo_id})
    return f"{PORTAL_ORIGIN}/lidarDataset?{query}"


def list_url(prefix: str, limit: int, page: str | None) -> str:
    params = {"list-type": "2", "prefix": prefix, "max-keys": str(limit)}
    if page:
        params["continuation-token"] = page
    return f"{S3_ORIGIN}/pc-bulk?{urllib.parse.urlencode(params)}"


def asset_url(key: str) -> str:
    """Public object URL for display only. The client never requests it."""
    return f"{S3_ORIGIN}/pc-bulk/{urllib.parse.quote(key, safe='/')}"


def json_nesting_depth(text: str) -> int:
    depth = 0
    maximum = 0
    in_string = False
    escape = False
    for char in text:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
            maximum = max(maximum, depth)
            if maximum > MAX_JSON_DEPTH:
                return maximum
        elif char in "}]":
            depth = max(0, depth - 1)
    return maximum


def parse_json_document(text: str) -> Any:
    if json_nesting_depth(text) > MAX_JSON_DEPTH:
        raise SchemaError("upstream JSON exceeds the supported nesting depth")
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except RecursionError as exc:
        raise SchemaError("upstream JSON exceeds the supported nesting depth") from exc
    except ValueError as exc:
        raise SchemaError("upstream returned malformed JSON") from exc


def _reject_constant(value: str) -> Any:
    raise ValueError(f"unsupported JSON constant {value}")


def plain_text(value: str, limit: int = MAX_TEXT) -> tuple[str, bool]:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text, False
    return text[:limit].rstrip(), True


def optional_text(value: Any, label: str) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise SchemaError(f"{label} was not a string")
    text, _truncated = plain_text(value)
    return text or None


def capture_end(value: str | None) -> str | None:
    """Use the source capture interval end, not the catalogue publication date."""
    if not value:
        return None
    match = re.search(r"(\d{4}-\d{2}-\d{2})\s*$", value.replace(" / ", "/"))
    if not match:
        return None
    return match.group(1)


def safe_prefix(alternate_name: str) -> str:
    if not ALT_RE.fullmatch(alternate_name):
        raise SchemaError("alternate name is not a single safe collection prefix")
    return f"{alternate_name}/"


def _identifier(dataset: dict[str, Any]) -> str | None:
    ident = dataset.get("identifier")
    if not isinstance(ident, dict):
        return None
    value = ident.get("value")
    if not isinstance(value, str):
        return None
    return value


def parse_catalog(payload: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(payload, dict):
        raise SchemaError("catalogue response was not a JSON object")
    datasets = payload.get("Datasets")
    if not isinstance(datasets, list):
        raise SchemaError("catalogue Datasets was not a list")
    if len(datasets) > MAX_COLLECTIONS:
        raise SchemaError("catalogue exceeds the supported collection cap; narrow the bounding box")
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    skipped = 0
    for item in datasets:
        if not isinstance(item, dict) or not isinstance(item.get("Dataset"), dict):
            raise SchemaError("catalogue entry was not a Dataset object")
        dataset = item["Dataset"]
        file_format = dataset.get("fileFormat")
        if not isinstance(file_format, str):
            raise SchemaError("catalogue fileFormat was not a string")
        if "point cloud" not in file_format.lower():
            skipped += 1
            continue
        opentopo_id = _identifier(dataset)
        if opentopo_id is None or not ID_RE.fullmatch(opentopo_id):
            raise SchemaError("catalogue identifier was not an OpenTopography point-cloud id")
        name = optional_text(dataset.get("name"), "catalogue name")
        alternate = dataset.get("alternateName")
        if not name or not isinstance(alternate, str) or not ALT_RE.fullmatch(alternate):
            raise SchemaError("catalogue point-cloud name or prefix was unusable")
        record: dict[str, Any] = {
            "opentopo_id": opentopo_id,
            "name": name,
            "alternate_name": alternate,
            "file_format": "Point Cloud Data",
        }
        doi = dataset.get("url")
        if isinstance(doi, str) and doi:
            parsed = urllib.parse.urlparse(doi)
            host = (parsed.hostname or "").lower().rstrip(".")
            if parsed.scheme == "https" and host == "doi.org" and parsed.username is None and parsed.password is None:
                record["doi"] = doi
        temporal = optional_text(dataset.get("temporalCoverage"), "temporalCoverage")
        if temporal:
            record["temporal_coverage"] = temporal
        created = optional_text(dataset.get("dateCreated"), "dateCreated")
        if created:
            record["date_created"] = created
        records.append(record)
    if skipped:
        warnings.append(
            f"skipped {skipped} non-point-cloud catalogue "
            f"{'record' if skipped == 1 else 'records'}"
        )
    warnings.append("licence is not in the catalogue response; use info before files")
    return records, warnings


def _publisher_name(payload: dict[str, Any]) -> str:
    publisher = payload.get("publisher")
    if isinstance(publisher, list) and publisher:
        publisher = publisher[0]
    if isinstance(publisher, dict):
        name = publisher.get("name") or publisher.get("legalName")
        if isinstance(name, str):
            text, _truncated = plain_text(name, 120)
            if text and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .,&()'/-]{0,119}", text):
                return text
    return PUBLISHER


def _geo_box(payload: dict[str, Any]) -> list[float] | None:
    spatial = payload.get("spatialCoverage")
    if not isinstance(spatial, dict):
        return None
    geo = spatial.get("geo")
    if not isinstance(geo, dict) or "box" not in geo:
        return None
    raw = geo.get("box")
    if not isinstance(raw, str):
        raise SchemaError("dataset boundary box was not a string")
    parts = raw.replace(",", " ").split()
    if len(parts) != 4:
        raise SchemaError("dataset boundary box was not south,west north,east")
    try:
        south, west, north, east = (float(part) for part in parts)
    except ValueError as exc:
        raise SchemaError("dataset boundary box was not numeric") from exc
    if not all(map(_finite, (south, west, north, east))):
        raise SchemaError("dataset boundary box was not finite")
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise SchemaError("dataset boundary box was reversed or outside WGS84")
    return [west, south, east, north]


def _finite(value: float) -> bool:
    return value == value and value not in {float("inf"), float("-inf")}


def parse_dataset_page(page: str, opentopo_id: str) -> dict[str, Any]:
    match = JSON_LD_RE.search(page)
    if not match:
        raise SchemaError("dataset page did not contain JSON-LD metadata")
    script = match.group(1).replace("<\\/", "</")
    payload = parse_json_document(script)
    if isinstance(payload, list):
        payload = next((item for item in payload if isinstance(item, dict)), None)
    if not isinstance(payload, dict):
        raise SchemaError("dataset JSON-LD was not an object")
    kind = payload.get("@type")
    if kind != "Dataset" and kind != ["Dataset"]:
        raise SchemaError("dataset JSON-LD @type was not Dataset")
    found = _identifier(payload)
    if found != opentopo_id:
        raise SchemaError("dataset JSON-LD identifier did not match the requested id")
    name = optional_text(payload.get("name"), "dataset name")
    alternate = payload.get("alternateName")
    licence = payload.get("license")
    if not name or not isinstance(alternate, str) or not isinstance(licence, str):
        raise SchemaError("dataset name, prefix, or licence was missing")
    licence = licence.strip()
    if not licence:
        raise SchemaError("dataset licence was empty")
    prefix = safe_prefix(alternate)
    record: dict[str, Any] = {
        "opentopo_id": opentopo_id,
        "name": name,
        "alternate_name": alternate,
        "prefix": prefix,
        "licence": licence,
        "reusable": licence == REUSABLE_LICENCE,
        "publisher": _publisher_name(payload),
        "dataset_url": dataset_url(opentopo_id),
    }
    temporal = optional_text(payload.get("temporalCoverage"), "temporalCoverage")
    if temporal:
        record["temporal_coverage"] = temporal
    citation = optional_text(payload.get("citation"), "citation")
    if citation:
        full, truncated = plain_text(str(payload.get("citation")))
        record["citation"] = full
        if truncated:
            record["citation_truncated"] = True
    box = _geo_box(payload)
    if box:
        record["bbox"] = box
    file_format = payload.get("fileFormat")
    if isinstance(file_format, str) and "point cloud" not in file_format.lower():
        raise UnsafeError("dataset is not point-cloud data; this skill does not read rasters")
    return record


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_listing(xml_text: str, prefix: str, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    folded = xml_text.lower()
    if "<!doctype" in folded or "<!entity" in folded:
        raise SchemaError("listing XML contained a forbidden declaration")
    if folded.count("<contents") > limit:
        raise SchemaError("listing page is larger than the requested limit")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise SchemaError("listing XML was malformed") from exc
    if local_name(root.tag) == "Error":
        code = next((child.text or "" for child in root if local_name(child.tag) == "Code"), "")
        if code in {"AccessDenied", "AllAccessDisabled", "SignatureDoesNotMatch"}:
            raise BlockedError(f"network error: listing access blocked ({code})")
        if code in {"SlowDown", "ServiceUnavailable", "InternalError"}:
            raise UpstreamError(f"upstream unavailable ({code})")
        if code == "InvalidArgument":
            raise InputError("the page cursor was rejected by the listing endpoint")
        raise SchemaError(f"listing failed with {code or 'an unknown code'}")
    if local_name(root.tag) != "ListBucketResult":
        raise SchemaError("listing root was not ListBucketResult")
    values = {local_name(child.tag): (child.text or "").strip() for child in list(root)}
    if values.get("Name") != "pc-bulk":
        raise SchemaError("listing bucket was not pc-bulk")
    if values.get("Prefix") != prefix:
        raise SchemaError("listing prefix did not match the dataset prefix")
    truncated_text = values.get("IsTruncated", "")
    if truncated_text not in {"true", "false"}:
        raise SchemaError("listing truncation flag was missing")
    truncated = truncated_text == "true"
    next_page = values.get("NextContinuationToken") or ""
    if truncated and not PAGE_RE.fullmatch(next_page):
        raise SchemaError("truncated listing did not include a usable next page")
    if not truncated:
        next_page = ""
    records: list[dict[str, Any]] = []
    for child in root:
        if local_name(child.tag) != "Contents":
            continue
        fields = {local_name(field.tag): (field.text or "").strip() for field in list(child)}
        key = fields.get("Key", "")
        if not key.startswith(prefix) or key == prefix or ".." in key or "\\" in key or "?" in key or "#" in key:
            raise SchemaError("listing key escaped the dataset prefix")
        size_text = fields.get("Size", "")
        if not size_text.isdigit():
            raise SchemaError("listing size was not a non-negative integer")
        record: dict[str, Any] = {
            "key": key,
            "size_bytes": int(size_text),
            "url": asset_url(key),
            "suffix": Path(key).suffix.lower(),
        }
        modified = fields.get("LastModified")
        if modified:
            record["last_modified"] = modified
        records.append(record)
    if len(records) > limit:
        raise SchemaError("listing page is larger than the requested limit")
    page = {"limit": limit, "returned": len(records), "truncated": truncated}
    if next_page:
        page["next_page"] = next_page
    return records, page


def slice_records(
    records: list[dict[str, Any]], offset: int, limit: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected = records[offset : offset + limit]
    return selected, {
        "matched": len(records),
        "offset": offset,
        "limit": limit,
        "returned": len(selected),
        "truncated": offset + limit < len(records),
    }


def box_polygon(box: list[float]) -> dict[str, Any]:
    west, south, east, north = box
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Polygon", "coordinates": [ring]}


def collection_features(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features = []
    for record in records:
        geometry = box_polygon(record["bbox"]) if record.get("bbox") else None
        properties = {key: value for key, value in record.items() if key != "bbox"}
        feature: dict[str, Any] = {"type": "Feature", "geometry": geometry, "properties": properties}
        if record.get("bbox"):
            feature["bbox"] = record["bbox"]
        features.append(feature)
    return features


def fixture_file(name: str) -> Path:
    if not FIXTURE_RE.fullmatch(name):
        raise InputError("fixture name is not allowed")
    root = (Path(__file__).resolve().parent.parent / "tests" / "fixtures").resolve()
    path = (root / f"{name}.json").resolve()
    if path.parent != root or not path.is_file():
        raise InputError("fixture is not available")
    return path


def load_fixture_payload(name: str) -> dict[str, Any]:
    if _FIXTURE_STATE["name"] != name:
        try:
            payload = json.loads(fixture_file(name).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SchemaError("fixture JSON is malformed") from exc
        if not isinstance(payload, dict):
            raise SchemaError("fixture JSON was not an object")
        _FIXTURE_STATE["name"] = name
        _FIXTURE_STATE["index"] = 0
        _FIXTURE_STATE["payload"] = payload
    payload = _FIXTURE_STATE["payload"]
    if not isinstance(payload, dict):
        raise SchemaError("fixture JSON was not an object")
    return payload


def canned_response(name: str, url: str, kind: str) -> tuple[int, str, str]:
    payload = load_fixture_payload(name)
    fault = payload.get("fault")
    if fault == "timeout":
        raise UpstreamError("network error: source request timed out")
    if fault == "rate_limit":
        retry_after = payload.get("retry_after")
        if retry_after is not None and not isinstance(retry_after, str):
            raise SchemaError("fixture retry_after was not a string")
        raise BlockedError(
            "network error: rate_limited: retry_after="
            f"{retry_after}: HTTP 429",
            retry_after=retry_after,
        )
    if fault == "off_host":
        raise UnsafeError("refusing off-host redirect; requests stay on the OpenTopography allowlist")
    responses = payload.get("responses")
    if not isinstance(responses, list):
        raise SchemaError("fixture responses was not a list")
    index = int(_FIXTURE_STATE["index"])
    if index >= len(responses):
        raise UnsafeError("refusing a further request that the fixture does not allow")
    item = responses[index]
    _FIXTURE_STATE["index"] = index + 1
    if not isinstance(item, dict):
        raise SchemaError("fixture response was not an object")
    status = item.get("status", 200)
    if isinstance(status, bool) or not isinstance(status, int):
        raise SchemaError("fixture status was not an integer")
    body = item.get("body", "")
    if not isinstance(body, str):
        body = json.dumps(body)
    final_url = item.get("final_url") or url
    if not isinstance(final_url, str):
        raise SchemaError("fixture final_url was not a string")
    assert_allowed_url(final_url, kind)
    if status == 429:
        raise BlockedError(f"network error: rate_limited: retry_after=None: HTTP {status}")
    if status == 404 and kind == "dataset":
        raise NotFoundError("dataset page was not found")
    if status == 404:
        raise UpstreamError("upstream unavailable (HTTP 404)")
    if status in {401, 403}:
        raise BlockedError(f"network error: upstream access blocked (HTTP {status})")
    if status >= 500:
        raise UpstreamError(f"upstream unavailable (HTTP {status})")
    if status != 200:
        raise UpstreamError(f"upstream unavailable (HTTP {status})")
    return status, body, final_url


def classify_fetch_error(exc: nzfetch.FetchError, kind: str) -> None:
    message = str(exc)
    lowered = message.lower()
    if "allowlist" in lowered or "downgrade" in lowered:
        raise UnsafeError("refusing off-host redirect; requests stay on the OpenTopography allowlist") from exc
    if "exceeded" in lowered or "too large" in lowered:
        raise UpstreamError("upstream response exceeds the safety cap") from exc
    if "timed out" in lowered or isinstance(exc.__cause__, TimeoutError):
        raise UpstreamError("network error: source request timed out") from exc
    cause = exc.__cause__
    status = cause.code if isinstance(cause, urllib_error_type()) else None
    if status == 404 and kind == "dataset":
        raise NotFoundError("dataset page was not found") from exc
    if status == 404:
        raise UpstreamError("upstream unavailable (HTTP 404)") from exc
    if status in {401, 403}:
        raise BlockedError(f"network error: upstream access blocked (HTTP {status})") from exc
    if status is not None and status >= 500:
        raise UpstreamError(f"upstream unavailable (HTTP {status})") from exc
    if "http 429" in lowered or "rate-limited" in lowered:
        raise BlockedError(f"network error: rate_limited: retry_after=None: {message}") from exc
    raise UpstreamError(f"network error: {message}") from exc


def urllib_error_type() -> type:
    import urllib.error

    return urllib.error.HTTPError


def retrieve(url: str, kind: str) -> tuple[int, str, str]:
    assert_allowed_url(url, kind)
    accept = {
        "catalog": "application/json",
        "dataset": "text/html",
        "listing": "application/xml",
    }[kind]
    try:
        body, _content_type, final_url = nzfetch.fetch_bytes(
            url,
            timeout=TIMEOUT_SECONDS,
            accept=accept,
            headers={"User-Agent": USER_AGENT, "Accept": accept},
            browser_headers=False,
            allowed_hosts=frozenset({PORTAL_HOST if kind != "listing" else S3_HOST}),
            max_bytes=CATALOG_MAX_BYTES if kind == "catalog" else DOCUMENT_MAX_BYTES,
            expect_json=kind == "catalog",
        )
    except nzfetch.RateLimited as exc:
        raise BlockedError(
            f"network error: rate_limited: retry_after={exc.retry_after}: {exc}",
            retry_after=exc.retry_after,
        ) from exc
    except nzfetch.Blocked as exc:
        raise BlockedError(f"network error: {exc}") from exc
    except nzfetch.FetchError as exc:
        classify_fetch_error(exc, kind)
        raise
    assert_allowed_url(final_url, kind)
    if len(body) > (CATALOG_MAX_BYTES if kind == "catalog" else DOCUMENT_MAX_BYTES):
        raise UpstreamError("upstream response exceeds the safety cap")
    text = body.decode("latin-1") if kind == "dataset" else body.decode("utf-8", "replace")
    return 200, text, final_url


def response_for(url: str, fixture: str | None, kind: str) -> tuple[int, str, str]:
    if fixture:
        return canned_response(fixture, url, kind)
    return retrieve(url, kind)


def emit_success(
    results: list[dict[str, Any]],
    meta: dict[str, str],
    lines: list[str],
    *,
    as_json: bool,
    geojson: bool,
    features: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> int:
    if geojson:
        payload = geojson_envelope(features or [], meta)
        if extra:
            payload.update(extra)
        if warnings:
            payload["warnings"] = warnings
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if as_json:
        payload = result_envelope(results, meta)
        if extra:
            payload.update(extra)
        if warnings:
            payload["warnings"] = warnings
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    for line in lines:
        print(line)
    return 0


def emit_error(
    code: int,
    message: str,
    meta: dict[str, str],
    as_json: bool,
    *,
    retry_after: str | None = None,
) -> int:
    if as_json:
        print(json.dumps(error_envelope(code, message, meta, retry_after=retry_after), indent=2, ensure_ascii=False))
    else:
        print(f"nz-point-clouds: {message}", file=sys.stderr)
    return code


def wants_json(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "json", False) or getattr(args, "format", "json") == "geojson")


def wants_geojson(args: argparse.Namespace) -> bool:
    return getattr(args, "format", "json") == "geojson"


def mark_fixture(warnings: list[str], fixture: str | None) -> list[str]:
    if not fixture:
        return warnings
    return [f"fixture: {fixture}; not a live OpenTopography response", *warnings]


def human_collections(records: list[dict[str, Any]], page: dict[str, Any], url: str, warnings: list[str]) -> list[str]:
    lines = [
        f"OpenTopography NZ point-cloud collections ({page['returned']} shown, {page['matched']} matched)",
    ]
    lines.extend(warnings)
    if not records:
        lines.append("No point-cloud collections matched this bounding box.")
    for record in records:
        coverage = record.get("temporal_coverage") or "capture interval not stated"
        lines.append(f"- {record['opentopo_id']} {record['name']} [{record['alternate_name']}] {coverage}")
    if page["truncated"]:
        lines.append("Further collections match. Raise --offset to read the next slice.")
    lines.append(f"Source: {url}")
    lines.append("This list does not include a reuse licence. Run info before files.")
    return lines


def human_dataset(record: dict[str, Any]) -> list[str]:
    lines = [f"{record['name']} ({record['opentopo_id']})"]
    lines.append(f"Prefix: {record['prefix']}")
    lines.append(f"Licence: {record['licence']}")
    if record.get("temporal_coverage"):
        lines.append(f"Capture interval: {record['temporal_coverage']}")
    if record.get("bbox"):
        west, south, east, north = record["bbox"]
        lines.append(f"Bounding box: {west},{south},{east},{north}")
    if record.get("citation"):
        lines.append(f"Citation: {record['citation']}")
    lines.append(f"Source: {record['dataset_url']}")
    if record["reusable"]:
        lines.append("File listing is allowed for this CC-BY-4.0 dataset. Bodies are not downloaded.")
    else:
        lines.append("File listing is refused because the stated reuse terms are not CC-BY-4.0.")
    return lines


def human_files(
    dataset: dict[str, Any],
    records: list[dict[str, Any]],
    page: dict[str, Any],
    url: str,
) -> list[str]:
    lines = [f"{dataset['name']} ({dataset['opentopo_id']})", f"Licence: {dataset['licence']}"]
    lines.append(f"Showing {page['returned']} file record(s).")
    if not records:
        lines.append("No files were in this page.")
    for record in records:
        lines.append(f"- {record['key']} {record['size_bytes']} bytes {record['url']}")
    if page["truncated"]:
        lines.append("Further files exist. Pass --page with the returned next_page value.")
    lines.append(f"Source: {url}")
    lines.append("These records are URLs and sizes only. The command does not download point-cloud files.")
    return lines


def run_collections(args: argparse.Namespace) -> int:
    url = catalog_url(args.bbox)
    meta = source_meta(url)
    status, body, _final = response_for(url, args.fixture, "catalog")
    if status != 200:
        raise UpstreamError(f"upstream unavailable (HTTP {status})")
    records, warnings = parse_catalog(parse_json_document(body))
    selected, page = slice_records(records, args.offset, args.limit)
    warnings = mark_fixture(warnings, args.fixture)
    return emit_success(
        selected,
        meta,
        human_collections(selected, page, url, warnings),
        as_json=wants_json(args),
        geojson=wants_geojson(args),
        features=collection_features(selected),
        warnings=warnings,
        extra={"page": page},
    )


def load_dataset(opentopo_id: str, fixture: str | None) -> dict[str, Any]:
    url = dataset_url(opentopo_id)
    _status, body, _final = response_for(url, fixture, "dataset")
    return parse_dataset_page(body, opentopo_id)


def run_info(args: argparse.Namespace) -> int:
    url = dataset_url(args.opentopo_id)
    try:
        record = load_dataset(args.opentopo_id, args.fixture)
    except NotFoundError:
        warnings = mark_fixture(["dataset_not_found"], args.fixture)
        lines = [f"No OpenTopography dataset for {args.opentopo_id}.", f"Source: {url}"]
        return emit_success(
            [],
            source_meta(url),
            lines,
            as_json=wants_json(args),
            geojson=wants_geojson(args),
            features=[],
            warnings=warnings,
        )
    meta = source_meta(url, licence=record["licence"], latest_data=capture_end(record.get("temporal_coverage")))
    warnings = mark_fixture([], args.fixture)
    if not record.get("bbox"):
        warnings.append("boundary box was not in the dataset metadata")
    return emit_success(
        [record],
        meta,
        human_dataset(record),
        as_json=wants_json(args),
        geojson=wants_geojson(args),
        features=collection_features([record]),
        warnings=warnings or None,
    )


def run_files(args: argparse.Namespace) -> int:
    try:
        dataset = load_dataset(args.opentopo_id, args.fixture)
    except NotFoundError as exc:
        raise UnsafeError(
            "dataset was not found; file listing requires a verified CC-BY-4.0 record"
        ) from exc
    if not dataset["reusable"]:
        raise UnsafeError(
            "reuse terms are not CC-BY-4.0 "
            f"(source licence: {dataset['licence']}); file listing is refused"
        )
    url = list_url(dataset["prefix"], args.limit, args.page)
    _status, body, _final = response_for(url, args.fixture, "listing")
    records, page = parse_listing(body, dataset["prefix"], args.limit)
    if args.suffix:
        records = [record for record in records if record["suffix"] == args.suffix]
        page = {**page, "returned": len(records), "suffix": args.suffix}
    meta = source_meta(
        url,
        licence=dataset["licence"],
        latest_data=capture_end(dataset.get("temporal_coverage")),
    )
    warnings = mark_fixture(
        ["file bodies are not downloaded"],
        args.fixture,
    )
    extra = {
        "dataset": {
            "opentopo_id": dataset["opentopo_id"],
            "name": dataset["name"],
            "alternate_name": dataset["alternate_name"],
            "dataset_url": dataset["dataset_url"],
        },
        "page": page,
    }
    return emit_success(
        records,
        meta,
        human_files(dataset, records, page, url),
        as_json=wants_json(args),
        geojson=False,
        warnings=warnings,
        extra=extra,
    )


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Find NZ LiDAR point-cloud collections and bounded file URLs")
    sub = parser.add_subparsers(dest="command", required=True)
    collections = sub.add_parser("collections", help="search the point-cloud catalogue inside the NZ window")
    collections.add_argument("--bbox", type=parse_nz_bbox, required=True, metavar="minLon,minLat,maxLon,maxLat")
    collections.add_argument("--limit", type=parse_limit, default=DEFAULT_LIMIT, help="1 to 50 records (default 20)")
    collections.add_argument("--offset", type=parse_offset, default=0, help="slice start from 0 to 500")
    collections.add_argument("--format", choices=("json", "geojson"), default="json")
    collections.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    collections.add_argument("--fixture", help="named fixture under tests/fixtures; not a live query")
    info = sub.add_parser("info", help="read one dataset's metadata, boundary box, and stated licence")
    info.add_argument("opentopo_id", type=parse_opentopo_id)
    info.add_argument("--format", choices=("json", "geojson"), default="json")
    info.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    info.add_argument("--fixture", help="named fixture under tests/fixtures; not a live query")
    files = sub.add_parser("files", help="list file URLs and sizes when the dataset states CC-BY-4.0")
    files.add_argument("opentopo_id", type=parse_opentopo_id)
    files.add_argument("--limit", type=parse_limit, default=DEFAULT_LIMIT, help="1 to 50 keys (default 20)")
    files.add_argument("--page", type=parse_page, help="next_page cursor from the previous files result")
    files.add_argument("--suffix", type=parse_suffix, help="keep laz, las, lax, or json keys from this page")
    files.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    files.add_argument("--fixture", help="named fixture under tests/fixtures; not a live query")
    return parser


def main(argv: list[str] | None = None) -> int:
    _FIXTURE_STATE["name"] = None
    _FIXTURE_STATE["index"] = 0
    _FIXTURE_STATE["payload"] = None
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    as_json = "--json" in argv or "--format=geojson" in argv or ("--format" in argv and "geojson" in argv)
    try:
        args = parser.parse_args(argv)
        if args.command == "collections":
            return run_collections(args)
        if args.command == "info":
            return run_info(args)
        if args.command == "files":
            return run_files(args)
        raise InputError(f"unsupported command: {args.command}")
    except InputError as exc:
        return emit_error(2, str(exc), source_meta(PORTAL_ORIGIN), as_json)
    except BlockedError as exc:
        return emit_error(4, str(exc), source_meta(PORTAL_ORIGIN), as_json, retry_after=exc.retry_after)
    except UpstreamError as exc:
        return emit_error(5, str(exc), source_meta(PORTAL_ORIGIN), as_json)
    except SchemaError as exc:
        return emit_error(6, str(exc), source_meta(PORTAL_ORIGIN), as_json)
    except UnsafeError as exc:
        return emit_error(7, str(exc), source_meta(PORTAL_ORIGIN), as_json)


if __name__ == "__main__":
    raise SystemExit(main())
