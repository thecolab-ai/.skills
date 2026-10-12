#!/usr/bin/env python3
"""Read Berlin Starkregen model areas from the official Geoportal Berlin WFS."""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402
from provenance import error_envelope, provenance, result_envelope  # noqa: E402

SERVICE_ROOT = "https://gdi.berlin.de/services/wfs/ua_srgk"
ALLOWED_HOSTS = ("gdi.berlin.de",)
PUBLISHER = "Senatsverwaltung für Stadtentwicklung, Bauen und Wohnen Berlin"
LICENCE = "CC BY 4.0 International"
ATTRIBUTION = (
    "Gebiete Moabit, Flughafensee, Neukölln, Rudow, Kladow/Gatow: "
    "Berliner Wasserbetriebe / Starkregengefahrenkarte; "
    "Gebiete Niederschönhausen Ost, Obersee, Frankentaler Ufer: "
    "Geoportal Berlin / Starkregengefahrenkarte / Starkregengefahrenkarte"
)
MODEL_AREA_TYPE = "ua_srgk:a_modellgebiete"
VELOCITY_TYPES = (
    "ua_srgk:ca_fliessgeschwindigkeit_aussergewoehnlich",
    "ua_srgk:da_fliessgeschwindigkeit_extrem",
    "ua_srgk:ba_fliessgeschwindigkeit_selten",
)
USER_AGENT = (
    "thecolab-skills berlin-starkregen-wfs/1.0 "
    "(public WFS read; +https://github.com/thecolab-ai/.skills)"
)
TIMEOUT_SECONDS = 10
MAX_CAPABILITIES_BYTES = 262_144
MAX_FEATURE_BYTES = 1_048_576
MAX_AREA_COUNT = 8
CRS_NOTE = (
    "Envelope coordinates are EPSG metres from the source CRS, "
    "not WGS84 longitude and latitude."
)
DECIMAL = re.compile(r"^-?\d+(?:\.\d+)?$")


class SkillError(Exception):
    def __init__(self, message: str, code: int = 6, source_url: str = SERVICE_ROOT, retry_after: str | None = None):
        super().__init__(message)
        self.code = code
        self.source_url = source_url
        self.retry_after = retry_after


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SkillError(message, 2)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def service_url(params: dict[str, str]) -> str:
    return SERVICE_ROOT + "?" + urlencode(params)


def capabilities_url() -> str:
    return service_url({"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"})


def areas_url(count: int) -> str:
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= MAX_AREA_COUNT:
        raise SkillError(f"--count must be an integer from 1 to {MAX_AREA_COUNT}", 2)
    return service_url(
        {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": MODEL_AREA_TYPE,
            "count": str(count),
        }
    )


def hits_url() -> str:
    return service_url(
        {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": MODEL_AREA_TYPE,
            "count": "1",
            "resultType": "hits",
        }
    )


def fetch_xml(url: str, max_bytes: int) -> bytes:
    try:
        body, content_type, final_url = nzfetch.fetch_bytes(
            url,
            timeout=TIMEOUT_SECONDS,
            accept="application/xml, text/xml;q=0.9",
            headers={"User-Agent": USER_AGENT, "Accept": "application/xml, text/xml;q=0.9"},
            browser_headers=False,
            allowed_hosts=ALLOWED_HOSTS,
            expect_json=False,
            max_bytes=max_bytes,
        )
    except nzfetch.RateLimited as exc:
        raise SkillError("network error: source rate-limited", 4, url, exc.retry_after) from exc
    except nzfetch.Blocked as exc:
        raise SkillError("network error: source access blocked", 4, url) from exc
    except nzfetch.ResponseTooLarge as exc:
        raise SkillError(f"response exceeded the {max_bytes}-byte cap", 7, url) from exc
    except nzfetch.FetchError as exc:
        raise SkillError("network error: source unavailable", 5, url) from exc
    final_host = urlsplit(final_url).hostname
    if final_host != "gdi.berlin.de":
        raise SkillError("network error: redirect left the official host", 4, url)
    if content_type and "html" in content_type.lower():
        raise SkillError("network error: source access blocked", 4, url)
    return body


def parse_xml(body: bytes, source_url: str) -> ET.Element:
    sample = body.lstrip()[:300].lower()
    if not body.strip():
        raise SkillError("empty response is not a WFS document", 6, source_url)
    if sample.startswith(b"<!doctype") or b"<!entity" in sample or sample.startswith(b"<html") or b"<html" in sample:
        raise SkillError("network error: source access blocked", 4, source_url)
    try:
        return ET.fromstring(body)
    except ET.ParseError as exc:
        raise SkillError("WFS document is not well-formed XML", 6, source_url) from exc


def direct_child(element: ET.Element, name: str) -> ET.Element | None:
    for child in list(element):
        if local_name(child.tag) == name:
            return child
    return None


def direct_text(element: ET.Element, name: str) -> str:
    child = direct_child(element, name)
    if child is None or child.text is None:
        return ""
    return " ".join(child.text.split())


def gml_identifier(element: ET.Element) -> str:
    for key, value in element.attrib.items():
        if key == "id" or key.endswith("}id"):
            return value.strip()
    return ""


def epsg_code(srs_name: str, source_url: str) -> str:
    match = re.search(r"EPSG(?:::|:)(\d+)\s*$", srs_name.strip())
    if not match:
        raise SkillError("model-area CRS is not an EPSG identifier", 6, source_url)
    return "EPSG:" + match.group(1)


def require_licence(root: ET.Element, source_url: str) -> str:
    fees = ""
    access = ""
    provider = ""
    for element in root.iter():
        name = local_name(element.tag)
        text = " ".join((element.text or "").split())
        if name == "Fees" and text and not fees:
            fees = text
        elif name == "AccessConstraints" and text and not access:
            access = text
        elif name == "ProviderName" and text and not provider:
            provider = text
    if "CC-BY-4.0" not in fees.upper() and "CC BY 4.0" not in fees.upper():
        raise SkillError("licence terms are not the confirmed CC BY 4.0 statement", 4, source_url)
    if "keine Zugriffsbeschränkungen" not in access:
        raise SkillError("access terms are not the confirmed public statement", 4, source_url)
    if provider != PUBLISHER:
        raise SkillError("service provider name is not the confirmed Senate department", 6, source_url)
    match = re.search(r'lautet "([^"]+)"', fees)
    attribution = match.group(1).strip() if match else ""
    anchors = ("Neukölln", "Berliner Wasserbetriebe", "Geoportal Berlin")
    if not attribution or any(anchor not in attribution for anchor in anchors):
        raise SkillError("attribution statement is not the confirmed Quellenvermerk", 4, source_url)
    return attribution


def parse_types(body: bytes, source_url: str) -> tuple[list[dict[str, str]], str]:
    root = parse_xml(body, source_url)
    if local_name(root.tag) == "ExceptionReport":
        raise SkillError(exception_message(root), 6, source_url)
    attribution = require_licence(root, source_url)
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for feature_type in root.iter():
        if local_name(feature_type.tag) != "FeatureType":
            continue
        type_name = direct_text(feature_type, "Name")
        title = direct_text(feature_type, "Title")
        default_crs = direct_text(feature_type, "DefaultCRS")
        if not type_name or not title or not default_crs:
            raise SkillError("feature type is missing a name, title, or default CRS", 6, source_url)
        if type_name in seen:
            raise SkillError("feature type name is repeated", 6, source_url)
        seen.add(type_name)
        results.append(
            {
                "type_name": type_name,
                "title": title,
                "default_crs": epsg_code(default_crs, source_url),
                "query": "areas" if type_name == MODEL_AREA_TYPE else "none",
            }
        )
    if not results:
        raise SkillError("capabilities document lists no feature types", 6, source_url)
    return results, attribution


def pair(text: str, source_url: str) -> tuple[str, str]:
    parts = text.split()
    if len(parts) != 2 or any(DECIMAL.fullmatch(part) is None for part in parts):
        raise SkillError("model-area envelope is not two finite coordinates", 6, source_url)
    return parts[0], parts[1]


def parse_envelope(feature: ET.Element, source_url: str) -> dict[str, str]:
    bounded = direct_child(feature, "boundedBy")
    if bounded is None:
        raise SkillError("model area has no envelope", 6, source_url)
    envelope = direct_child(bounded, "Envelope")
    if envelope is None:
        raise SkillError("model area has no envelope", 6, source_url)
    srs_name = ""
    for key, value in envelope.attrib.items():
        if key == "srsName" or key.endswith("}srsName"):
            srs_name = value
    lower = direct_text(envelope, "lowerCorner")
    upper = direct_text(envelope, "upperCorner")
    lower_easting, lower_northing = pair(lower, source_url)
    upper_easting, upper_northing = pair(upper, source_url)
    if float(lower_easting) >= float(upper_easting) or float(lower_northing) >= float(upper_northing):
        raise SkillError("model-area envelope bounds do not increase", 6, source_url)
    crs = epsg_code(srs_name, source_url)
    return {
        "crs": crs,
        "unit": "metre",
        "lower_easting": lower_easting,
        "lower_northing": lower_northing,
        "upper_easting": upper_easting,
        "upper_northing": upper_northing,
    }


def collection_counts(root: ET.Element, source_url: str) -> tuple[int, int]:
    if local_name(root.tag) == "ExceptionReport":
        raise SkillError(exception_message(root), 6, source_url)
    if local_name(root.tag) != "FeatureCollection":
        raise SkillError("WFS response is not a feature collection", 6, source_url)
    try:
        matched = int(root.attrib["numberMatched"])
        returned = int(root.attrib["numberReturned"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SkillError("feature collection has no integer match counts", 6, source_url) from exc
    if matched < 0 or returned < 0:
        raise SkillError("feature collection counts are negative", 6, source_url)
    if returned > matched:
        raise SkillError("returned count exceeds matched count", 6, source_url)
    return matched, returned


def exception_message(root: ET.Element) -> str:
    texts = [
        " ".join((element.text or "").split())
        for element in root.iter()
        if local_name(element.tag) == "ExceptionText" and element.text and element.text.strip()
    ]
    detail = texts[0][:240] if texts else "WFS exception report"
    return "WFS exception: " + detail


def parse_areas(body: bytes, source_url: str, count: int) -> tuple[list[dict[str, object]], dict[str, object]]:
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= MAX_AREA_COUNT:
        raise SkillError(f"--count must be an integer from 1 to {MAX_AREA_COUNT}", 2, source_url)
    root = parse_xml(body, source_url)
    matched, returned = collection_counts(root, source_url)
    features = [child for child in list(root) if local_name(child.tag) == "member"]
    if len(features) != returned:
        raise SkillError("member count does not match numberReturned", 6, source_url)
    if len(features) > count:
        raise SkillError("source returned more model areas than the requested count", 6, source_url)
    if matched == 0 and returned == 0:
        return [], {"number_matched": 0, "number_returned": 0, "truncated": False}
    if returned == 0:
        raise SkillError("feature collection matched areas but returned none", 6, source_url)
    results: list[dict[str, object]] = []
    for member in features:
        feature_elements = list(member)
        if len(feature_elements) != 1:
            raise SkillError("model-area member does not contain one feature", 6, source_url)
        feature = feature_elements[0]
        if local_name(feature.tag) != "a_modellgebiete":
            raise SkillError("response feature is not a model area", 6, source_url)
        identifier = direct_text(feature, "id")
        name = direct_text(feature, "name")
        if not identifier or not name:
            raise SkillError("model area is missing an id or name", 6, source_url)
        envelope = parse_envelope(feature, source_url)
        results.append(
            {
                "id": identifier,
                "name": name,
                "gml_id": gml_identifier(feature),
                "crs": envelope["crs"],
                "envelope": envelope,
            }
        )
    return results, {
        "number_matched": matched,
        "number_returned": returned,
        "truncated": matched > returned,
    }


def parse_hits(body: bytes, source_url: str) -> int:
    root = parse_xml(body, source_url)
    matched, returned = collection_counts(root, source_url)
    if returned != 0 or any(local_name(child.tag) == "member" for child in list(root)):
        raise SkillError("hits response included features", 6, source_url)
    return matched


def success_meta(source_url: str, attribution: str, extra: dict[str, object] | None = None) -> dict[str, object]:
    meta: dict[str, object] = provenance(source_url, PUBLISHER, licence=LICENCE)
    meta["attribution"] = attribution
    meta["crs_note"] = CRS_NOTE
    if extra:
        meta.update(extra)
    return meta


def command_types() -> dict[str, object]:
    url = capabilities_url()
    body = fetch_xml(url, MAX_CAPABILITIES_BYTES)
    results, attribution = parse_types(body, url)
    return result_envelope(results, success_meta(url, attribution))


def command_areas(count: int) -> dict[str, object]:
    url = areas_url(count)
    body = fetch_xml(url, MAX_FEATURE_BYTES)
    results, counts = parse_areas(body, url, count)
    return result_envelope(results, success_meta(url, ATTRIBUTION, counts))


def command_hits() -> int:
    url = hits_url()
    body = fetch_xml(url, MAX_CAPABILITIES_BYTES)
    return parse_hits(body, url)


def build_parser() -> Parser:
    parser = Parser(prog="berlin-starkregen-wfs", description="Berlin Starkregen model-area WFS")
    commands = parser.add_subparsers(dest="command", required=True)
    types = commands.add_parser("types", help="list WFS feature types from GetCapabilities")
    types.add_argument("--json", action="store_true", help="emit the provenance JSON envelope")
    areas = commands.add_parser("areas", help="list bounded Starkregen model areas")
    areas.add_argument("--count", type=int, default=1, help=f"model areas to request, from 1 to {MAX_AREA_COUNT}")
    areas.add_argument("--json", action="store_true", help="emit the provenance JSON envelope")
    return parser


def execute(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "types":
        return command_types()
    if args.command == "areas":
        return command_areas(args.count)
    raise SkillError("unsupported command", 7)


def print_human(payload: dict[str, object]) -> None:
    meta = payload["meta"]
    results = payload["results"]
    print(f"{PUBLISHER} — {meta['licence']}")
    print(meta["attribution"])
    if results and "type_name" in results[0]:
        for row in results:
            print(f"{row['type_name']} | {row['title']} | {row['default_crs']} | query={row['query']}")
        return
    print(
        f"model areas {meta['number_returned']} of {meta['number_matched']}; "
        "coordinates are source-CRS metres"
    )
    for row in results:
        envelope = row["envelope"]
        print(
            f"{row['id']} | {row['name']} | {row['crs']} | "
            f"easting {envelope['lower_easting']} to {envelope['upper_easting']} | "
            f"northing {envelope['lower_northing']} to {envelope['upper_northing']}"
        )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = build_parser().parse_args(argv)
        payload = execute(args)
    except SkillError as exc:
        meta = provenance(exc.source_url, PUBLISHER)
        if "--json" in argv:
            print(json.dumps(error_envelope(exc.code, str(exc), meta, retry_after=exc.retry_after), ensure_ascii=False))
        else:
            print(f"berlin-starkregen-wfs: {exc}", file=sys.stderr)
        return exc.code
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
