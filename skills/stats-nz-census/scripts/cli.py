#!/usr/bin/env python3
"""Query official public Stats NZ 2018 Census national-highlights CSV tables."""
from __future__ import annotations

import argparse
import csv
import io
import json
import pathlib
import re
import sys
import zipfile
from dataclasses import dataclass
from typing import Any, Iterable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402
from result_contract import result_envelope  # noqa: E402

SOURCE_NAME = "Stats NZ — 2018 Census totals by topic: national highlights"
SOURCE_URL = (
    "https://www.stats.govt.nz/assets/Uploads/"
    "2018-Census-totals-by-topic-national-highlights-csv-update-30-04-20.zip"
)
ALLOWED_HOSTS = {"www.stats.govt.nz"}
TIMEOUT_SECONDS = 10
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024
MAX_EXPANDED_BYTES = 10 * 1024 * 1024
MAX_MEMBERS = 100
MAX_MEMBER_BYTES = 2 * 1024 * 1024
MAX_EXPANSION_RATIO = 100
MAX_RESULTS = 100
EXPECTED_SUFFIX = "-2018-census-csv.csv"

STATUS_MARKERS = {
    "C": "confidentialised",
    "..C": "confidentialised",
    "S": "suppressed",
    "..": "not_available",
    "...": "not_available",
    "-": "not_applicable",
    "P": "provisional_symbol",
    "R": "revised_symbol",
}
NUMBER = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")


class SkillError(Exception):
    exit_code = 5
    error_code = "upstream_unavailable"
    blocked = False


class InputError(SkillError):
    exit_code = 2
    error_code = "invalid_input"


class SourceBlockedError(SkillError):
    exit_code = 4
    error_code = "source_blocked"
    blocked = True


class SourceSchemaError(SkillError):
    exit_code = 6
    error_code = "source_schema_error"


@dataclass(frozen=True)
class TopicFile:
    topic: str
    member: str
    body: bytes


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print(json.dumps({"error": "invalid_input", "message": message}), file=sys.stderr)
        raise SystemExit(2)


def bounded_limit(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("limit must be an integer") from exc
    if not 1 <= value <= MAX_RESULTS:
        raise argparse.ArgumentTypeError(f"limit must be between 1 and {MAX_RESULTS}")
    return value


def normalise_topic(filename: str) -> str:
    name = pathlib.PurePosixPath(filename).name
    if name.casefold().endswith(EXPECTED_SUFFIX):
        name = name[: -len(EXPECTED_SUFFIX)]
    elif name.casefold().endswith(".csv"):
        name = name[:-4]
    return name.strip().casefold()


def parse_value(raw: str | None) -> tuple[int | float | None, str, str]:
    """Preserve source symbols; only unambiguous published numbers become values."""
    text = "" if raw is None else raw.strip()
    if not text:
        return None, "missing", ""
    compact = text.upper().replace(" ", "")
    if compact in STATUS_MARKERS:
        return None, STATUS_MARKERS[compact], text
    if NUMBER.fullmatch(text):
        canonical = text.replace(",", "")
        return (float(canonical) if "." in canonical else int(canonical)), "observed", ""
    return None, "non_numeric_source_symbol", text


def validate_archive(body: bytes) -> list[TopicFile]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
    except (zipfile.BadZipFile, OSError) as exc:
        raise SourceSchemaError("download is not a valid ZIP archive") from exc
    with archive:
        infos = archive.infolist()
        if not infos or len(infos) > MAX_MEMBERS:
            raise SourceSchemaError(f"archive member count must be between 1 and {MAX_MEMBERS}")
        expanded = sum(info.file_size for info in infos)
        compressed = max(1, sum(info.compress_size for info in infos))
        if expanded > MAX_EXPANDED_BYTES:
            raise SourceSchemaError("archive exceeds the expanded-size limit")
        if expanded / compressed > MAX_EXPANSION_RATIO:
            raise SourceSchemaError("archive exceeds the expansion-ratio limit")
        topics: list[TopicFile] = []
        seen: set[str] = set()
        for info in infos:
            path = pathlib.PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts or info.file_size > MAX_MEMBER_BYTES:
                raise SourceSchemaError(f"unsafe archive member: {info.filename}")
            if info.is_dir() or not info.filename.casefold().endswith(".csv"):
                continue
            topic = normalise_topic(info.filename)
            if not topic or topic in seen:
                raise SourceSchemaError(f"duplicate or empty Census topic: {topic or info.filename}")
            seen.add(topic)
            try:
                member_body = archive.read(info)
            except (zipfile.BadZipFile, OSError, RuntimeError, EOFError) as exc:
                raise SourceSchemaError(f"could not read archive member: {info.filename}") from exc
            topics.append(TopicFile(topic, info.filename, member_body))
    if not topics:
        raise SourceSchemaError("archive contains no CSV topic tables")
    return sorted(topics, key=lambda item: item.topic)


def decode_csv(body: bytes, member: str) -> str:
    """Decode the archive's UTF-8 or Windows-1252 CSV members without replacement."""
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return body.decode("cp1252")
        except UnicodeDecodeError as exc:
            raise SourceSchemaError(f"{member} is not valid UTF-8 or Windows-1252 CSV") from exc


def parse_topic(topic_file: TopicFile) -> list[dict[str, Any]]:
    """Normalise every published category/measure cell without collapsing dimensions."""
    reader = csv.reader(io.StringIO(decode_csv(topic_file.body, topic_file.member), newline=""), strict=True)
    try:
        header = next(reader, None)
        if header is None:
            raise SourceSchemaError(f"{topic_file.member} is empty")
        fields = [field.lstrip("\ufeff").strip() for field in header]
        if len(fields) < 3 or not fields[0] or not fields[1] or any(not field for field in fields[2:]):
            raise SourceSchemaError(f"{topic_file.member} has an invalid header")
        if len(set(fields)) != len(fields):
            raise SourceSchemaError(f"{topic_file.member} has duplicate columns")
        observations: list[dict[str, Any]] = []
        source_rows = 0
        for row_number, row in enumerate(reader, 2):
            if not row or not any(value.strip() for value in row):
                continue
            if len(row) != len(fields):
                raise SourceSchemaError(f"{topic_file.member} row {row_number} has an unexpected field count")
            code, label = row[0].strip(), row[1].strip()
            if not code or not label:
                raise SourceSchemaError(f"{topic_file.member} row {row_number} lacks category code or label")
            source_rows += 1
            for index, measure in enumerate(fields[2:], 2):
                raw = row[index].strip()
                value, status, symbol = parse_value(raw)
                observations.append(
                    {
                        "census_year": 2018,
                        "geography_level": "national",
                        "geography_code": "NZ",
                        "geography_name": "New Zealand",
                        "topic": topic_file.topic,
                        "category_dimension": fields[1],
                        "category_code": code,
                        "category_label": label,
                        "measure": measure,
                        "value": value,
                        "value_status": status,
                        "source_symbol": symbol,
                        "raw_value": raw,
                        "unit": "count",
                        "source_member": topic_file.member,
                        "source_row": row_number,
                    }
                )
    except csv.Error as exc:
        raise SourceSchemaError(f"invalid CSV in {topic_file.member}: {exc}") from exc
    if source_rows == 0:
        raise SourceSchemaError(f"{topic_file.member} contains no data rows")
    return observations


def fetch_topics() -> tuple[list[TopicFile], str]:
    try:
        body, content_type, final_url = nzfetch.fetch_bytes(
            SOURCE_URL,
            timeout=TIMEOUT_SECONDS,
            accept="application/zip,*/*;q=0.8",
            allowed_hosts=ALLOWED_HOSTS,
            max_bytes=MAX_DOWNLOAD_BYTES,
        )
    except (nzfetch.Blocked, nzfetch.RateLimited) as exc:
        raise SourceBlockedError(str(exc)) from exc
    except (nzfetch.ResponseTooLarge, nzfetch.InvalidCompressedBody) as exc:
        raise SourceSchemaError(str(exc)) from exc
    except nzfetch.FetchError as exc:
        raise SkillError(str(exc)) from exc
    if "zip" not in content_type.casefold() and not body.startswith(b"PK"):
        raise SourceSchemaError(f"expected ZIP but source returned {content_type or 'no content type'}")
    return validate_archive(body), final_url


def includes(value: str, query: str | None) -> bool:
    return not query or query.casefold() in value.casefold()


def query_topics(
    topics: Iterable[TopicFile],
    topic_query: str | None,
    category: str | None,
    measure: str | None,
    limit: int,
) -> tuple[dict[str, Any], list[str]]:
    available = list(topics)
    if not topic_query:
        return {
            "kind": "census_topics",
            "dataset": "2018 Census totals by topic — national highlights",
            "census_year": 2018,
            "geography_level": "national",
            "topic_count": len(available),
            "topics": [item.topic for item in available],
        }, []
    selected = [item for item in available if includes(item.topic, topic_query)]
    matches: list[dict[str, Any]] = []
    matched_total = 0
    for topic_file in selected:
        for observation in parse_topic(topic_file):
            if not includes(observation["category_code"] + " " + observation["category_label"], category):
                continue
            if not includes(observation["measure"], measure):
                continue
            matched_total += 1
            if len(matches) < limit:
                matches.append(observation)
    warnings: list[str] = []
    if not selected:
        warnings.append("No published topic matched the positional topic query.")
    elif matched_total == 0:
        warnings.append("The topic matched, but no published observations matched the filters.")
    if matched_total > limit:
        warnings.append(f"Result truncated to {limit} of {matched_total} matching observations.")
    return {
        "kind": "census_observations",
        "dataset": "2018 Census totals by topic — national highlights",
        "census_year": 2018,
        "geography_level": "national",
        "selected_topics": [item.topic for item in selected],
        "matched_count": matched_total,
        "returned_count": len(matches),
        "observations": matches,
    }, warnings


def build_parser() -> argparse.ArgumentParser:
    parser = Parser(description=__doc__)
    parser.add_argument("topic", nargs="?", help="published topic slug or substring; omit to list topics")
    parser.add_argument("--category", help="case-insensitive category code/label filter")
    parser.add_argument("--measure", help="case-insensitive published measure-heading filter")
    parser.add_argument("--limit", type=bounded_limit, default=20, help="maximum observations (1-100; default 20)")
    parser.add_argument("--json", action="store_true", help="emit the machine-readable result envelope")
    return parser


def render_human(payload: dict[str, Any]) -> None:
    data = payload["data"]
    if data["kind"] == "census_topics":
        print(f"2018 Census national-highlight topics ({data['topic_count']}):")
        for topic in data["topics"]:
            print(f"- {topic}")
    else:
        print(f"2018 Census national observations: {data['returned_count']} of {data['matched_count']}")
        for row in data["observations"]:
            shown = row["raw_value"] if row["value_status"] == "observed" else f"{row['source_symbol'] or '(blank)'} [{row['value_status']}]"
            print(f"- {row['topic']} | {row['category_label']} | {row['measure']}: {shown}")
    for warning in payload["warnings"]:
        print(f"Warning: {warning}", file=sys.stderr)
    print(f"Source: {payload['source']['url']}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    query = {
        "topic": args.topic,
        "category": args.category,
        "measure": args.measure,
        "limit": args.limit,
    }
    try:
        topics, final_url = fetch_topics()
        data, warnings = query_topics(topics, args.topic, args.category, args.measure, args.limit)
        data["download_final_url"] = final_url
        payload = result_envelope(
            ok=True,
            source_name=SOURCE_NAME,
            source_url=SOURCE_URL,
            query=query,
            data=data,
            warnings=warnings,
        )
        exit_code = 0
    except SkillError as exc:
        payload = result_envelope(
            ok=False,
            source_name=SOURCE_NAME,
            source_url=SOURCE_URL,
            query=query,
            data=None,
            blocked=exc.blocked,
            error={"code": exc.exit_code, "type": exc.error_code, "message": str(exc)},
        )
        exit_code = exc.exit_code
    if args.json or exit_code:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        render_human(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
