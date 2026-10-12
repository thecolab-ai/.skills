#!/usr/bin/env python3
"""Bounded reader for the DfT pedal-cycle factsheet ODS."""
from __future__ import annotations

import io
import re
import ssl
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree

FACTSHEET_URL = (
    "https://www.gov.uk/government/statistics/"
    "reported-road-casualties-great-britain-vulnerable-road-user-factsheets/"
    "reported-road-casualties-great-britain-pedal-cycle-factsheet-2025"
)
PUBLISHER = "Department for Transport"
LICENCE = "Open Government Licence v3.0 except where otherwise stated"
USER_AGENT = (
    "thecolab-dft-pedal-cycle-factsheet/1.0 (+https://github.com/thecolab-ai/.skills)"
)
ALLOWED_HOSTS = frozenset({"www.gov.uk", "assets.publishing.service.gov.uk"})
TIMEOUT_SECONDS = 15
MAX_PAGE_BYTES = 2_000_000
MAX_ODS_BYTES = 2_000_000
MAX_XML_BYTES = 2_000_000
MAX_MEMBERS = 30
MAX_MEMBER_BYTES = 2_000_000
MAX_DECLARED_BYTES = 8_000_000
MAX_REDIRECTS = 3
MAX_LINKS = 400
MAX_SHEETS = 32
MAX_CELL_ELEMENTS = 50_000
MAX_COLUMNS = 64
MAX_PREAMBLE = 12
MAX_TEXT = 1_500
DEFAULT_PREVIEW = 25
MAX_PREVIEW = 100
TRAILING_ROW_REPEAT = 1_000
EMPTY_COLUMN_REPEAT = 8
MAX_NONEMPTY_REPEAT = 8

PUBLICATION_LICENCE = (
    "This publication is licensed under the terms of the "
    "Open Government Licence v3.0 except where otherwise stated."
)
NUMERIC_TYPES = {"float", "double", "percentage", "currency"}
SIBLING_MARKERS = ("pedestrian", "e-scooter", "escooter", "motorcycle", "motorcyclist")
NOTE_MARKER = re.compile(r"^\[note \d+\]$", re.IGNORECASE)
SHORTHAND = re.compile(r"^\[[^\[\]]+\]$")
PERCENT_TEXT = re.compile(r"^-?\d+(?:\.\d+)?%$")
DECIMAL = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
PARENTHETICAL = re.compile(r"\(([^()]*)\)")
HEADER_UNIT = re.compile(r"\(([^()]*)\)\s*$")
PUBLISHED_HEADER = "Date this data was first published"
NEXT_HEADER = "Next publication date"


class FactsheetError(Exception):
    """Typed failure with a repository exit code."""

    def __init__(self, code: int, message: str, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


@dataclass
class FetchRecord:
    url: str
    status: int
    nbytes: int
    kind: str

    def as_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "status": self.status,
            "bytes": self.nbytes,
            "kind": self.kind,
        }


@dataclass
class Cell:
    row: int
    column: int
    text: str
    value_type: str | None = None
    value: str | None = None


@dataclass
class Sheet:
    name: str
    cells: list[Cell] = field(default_factory=list)

    def column_text(self, row: int, column: int) -> str:
        for cell in self.cells:
            if cell.row == row and cell.column == column:
                return cell.text
        return ""

    @property
    def header_row(self) -> int | None:
        counts: dict[int, int] = {}
        for cell in self.cells:
            if cell.text:
                counts[cell.row] = counts.get(cell.row, 0) + 1
        rows = sorted(row for row, count in counts.items() if count >= 2)
        return rows[0] if rows else None

    @property
    def preamble(self) -> list[str]:
        header = self.header_row
        lines: list[str] = []
        seen: set[int] = set()
        for cell in self.cells:
            if cell.column != 1 or not cell.text or cell.row in seen:
                continue
            if header is not None and cell.row >= header:
                break
            seen.add(cell.row)
            lines.append(cell.text[:MAX_TEXT])
            if len(lines) >= MAX_PREAMBLE:
                break
        return lines

    @property
    def title(self) -> str:
        lines = self.preamble
        return lines[0] if lines else ""

    @property
    def headers(self) -> list[dict[str, object]]:
        header = self.header_row
        if header is None:
            return []
        found = [cell for cell in self.cells if cell.row == header and cell.text]
        headers: list[dict[str, object]] = []
        for cell in found:
            match = HEADER_UNIT.search(cell.text)
            headers.append(
                {
                    "column": cell.column,
                    "header": cell.text,
                    "unit": match.group(1).strip() if match else None,
                }
            )
        return headers

    def header_for(self, column: int) -> tuple[str | None, str | None]:
        for header in self.headers:
            if header["column"] == column:
                name = header["header"]
                unit = header["unit"]
                return (name if isinstance(name, str) else None, unit if isinstance(unit, str) else None)
        return None, None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip += 1
        if self._skip or tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1
            return
        if tag == "a" and self._href is not None:
            text = " ".join("".join(self._parts).split())
            self.links.append((self._href.strip(), text))
            self._href = None
            self._parts = []
            if len(self.links) > MAX_LINKS:
                raise FactsheetError(7, "release page exceeded the link cap")

    def handle_data(self, data: str) -> None:
        if self._href is not None and not self._skip:
            self._parts.append(data)


def error_for_http_status(status: int, retry_after: str | None = None) -> FactsheetError:
    """Map an HTTP status that is not a redirect into a typed error."""
    if status in {403, 406, 429, 451}:
        message = f"network error: blocked: HTTP {status}"
        return FactsheetError(4, message, retry_after if status == 429 else None)
    if status == 200:
        raise ValueError("HTTP 200 is not an error status")
    return FactsheetError(5, f"network error: HTTP {status}")


def official_url(url: str) -> str:
    """Accept only HTTPS URLs on the declared official hosts."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.username or parsed.password or host not in ALLOWED_HOSTS:
        raise FactsheetError(7, "refusing a URL outside the official HTTPS hosts")
    try:
        port = parsed.port
    except ValueError as exc:
        raise FactsheetError(7, "refusing an official URL with an invalid port") from exc
    if port not in (None, 443) or parsed.query:
        raise FactsheetError(7, "refusing an official URL with a port or query string")
    segments = [segment for segment in parsed.path.split("/") if segment]
    if any(segment in {".", ".."} or "\\" in segment or "\x00" in segment for segment in segments):
        raise FactsheetError(7, "refusing an official URL with an unsafe path")
    path = "/" + "/".join(segments)
    return f"https://{host}{path}"


def release_parent_url(factsheet_url: str) -> str:
    parsed = urlparse(factsheet_url)
    parent = parsed.path.rstrip("/").rsplit("/", 1)[0]
    return official_url(f"https://{parsed.hostname}{parent}")


def _anchors(html: str) -> list[tuple[str, str]]:
    parser = _AnchorParser()
    try:
        parser.feed(html)
        parser.close()
    except FactsheetError:
        raise
    except Exception as exc:
        raise FactsheetError(6, "release page HTML could not be read") from exc
    return parser.links


def _normalise_space(text: str) -> str:
    return " ".join(text.split())


def assert_factsheet_page(html: str) -> None:
    """Require the pedal-cycle publication identity and its own licence sentence."""
    if "pedal cycle factsheet" not in html.casefold():
        raise FactsheetError(6, "release page is not the pedal-cycle factsheet")
    compact = _normalise_space(html)
    if PUBLICATION_LICENCE not in compact:
        raise FactsheetError(6, "publication licence statement was not found")


def pedal_ods_links(html: str, base_url: str) -> list[str]:
    """Return distinct pedal-cycle ODS URLs. Sibling factsheet files are ignored."""
    selected: list[str] = []
    unsafe = False
    for href, text in _anchors(html):
        absolute = urljoin(base_url, href)
        if not urlparse(absolute).path.lower().endswith(".ods"):
            continue
        blob = f"{text} {absolute}".casefold()
        if any(marker in blob for marker in SIBLING_MARKERS):
            continue
        if "pedal" not in blob or "cycle" not in blob:
            continue
        try:
            clean = official_url(absolute)
        except FactsheetError:
            unsafe = True
            continue
        if clean not in selected:
            selected.append(clean)
    if unsafe and not selected:
        raise FactsheetError(7, "pedal-cycle ODS link was not an allowed HTTPS URL")
    return selected


def linked_parent_release(html: str, factsheet_url: str) -> str | None:
    expected = release_parent_url(factsheet_url)
    for href, _text in _anchors(html):
        try:
            clean = official_url(urljoin(factsheet_url, href))
        except FactsheetError:
            continue
        if clean == expected:
            return clean
    return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attr(element: ElementTree.Element, name: str) -> str | None:
    for key, value in element.attrib.items():
        if _local(key) == name:
            return value
    return None


def _paragraphs(element: ElementTree.Element) -> str:
    parts: list[str] = []
    for child in element.iter():
        if _local(child.tag) != "p":
            continue
        text = "".join(child.itertext()).strip()
        if text:
            parts.append(text)
    return "\n".join(parts)[:MAX_TEXT]


def _member_name_error(name: str) -> str | None:
    if not name or len(name) > 200 or "\x00" in name or "\\" in name or name.startswith("/"):
        return "ODS member name is unsafe"
    segments = [segment for segment in name.split("/") if segment]
    if any(segment in {".", ".."} for segment in segments):
        return "ODS member path is unsafe"
    return None


def assess_members(members: list[zipfile.ZipInfo]) -> None:
    """Reject zip bombs, encryption, and path traversal before reading member bytes."""
    if not members or len(members) > MAX_MEMBERS:
        raise FactsheetError(7, "ODS archive exceeded the member cap")
    declared = 0
    for info in members:
        problem = _member_name_error(info.filename)
        if problem:
            raise FactsheetError(7, problem)
        if info.flag_bits & 0x1:
            raise FactsheetError(7, "encrypted ODS archives are not supported")
        if info.file_size < 0 or info.compress_size < 0:
            raise FactsheetError(7, "ODS member size is invalid")
        if info.file_size > MAX_MEMBER_BYTES:
            raise FactsheetError(7, "ODS member exceeded the uncompressed byte cap")
        if info.compress_size and info.file_size > 500_000 and info.file_size > info.compress_size * 80:
            raise FactsheetError(7, "ODS member exceeded the compression-ratio cap")
        declared += info.file_size
        if declared > MAX_DECLARED_BYTES:
            raise FactsheetError(7, "ODS archive exceeded the uncompressed byte cap")


def _read_capped(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        with archive.open(name, "r") as handle:
            blob = handle.read(MAX_XML_BYTES + 1)
    except RuntimeError as exc:
        raise FactsheetError(7, "ODS member could not be read within bounds") from exc
    if len(blob) > MAX_XML_BYTES:
        raise FactsheetError(7, "ODS member exceeded the read cap")
    return blob


def _repeat(element: ElementTree.Element, name: str) -> int:
    raw = _attr(element, name) or "1"
    if not raw.isdigit() or raw.startswith("0") and raw != "0":
        if not re.fullmatch(r"[1-9][0-9]{0,8}", raw):
            raise FactsheetError(6, "ODS repeat count is malformed")
    if not re.fullmatch(r"[1-9][0-9]{0,8}", raw):
        raise FactsheetError(6, "ODS repeat count is malformed")
    return int(raw)


def _cell_from(element: ElementTree.Element, row: int, column: int) -> Cell | None:
    value_type = _attr(element, "value-type")
    raw_value = _attr(element, "value")
    text = _paragraphs(element)
    value: str | None = None
    if value_type in NUMERIC_TYPES:
        if raw_value is None or not DECIMAL.fullmatch(raw_value.strip()):
            raise FactsheetError(6, "ODS numeric cell has no decimal value")
        token = raw_value.strip()
        try:
            number = float(token)
        except ValueError as exc:
            raise FactsheetError(6, "ODS numeric cell is not a finite decimal") from exc
        if number != number or number in {float("inf"), float("-inf")}:
            raise FactsheetError(6, "ODS numeric cell is not a finite decimal")
        value = token
        value_type = value_type
    elif raw_value is not None and value_type not in {None, "string"}:
        value_type = value_type
    if value is None and not text:
        return None
    return Cell(row=row, column=column, text=text, value_type=value_type, value=value)


def _parse_sheet(table: ElementTree.Element, elements: list[int]) -> Sheet:
    name = (_attr(table, "name") or "").strip()
    if not name or len(name) > 80 or any(ord(char) < 32 for char in name):
        raise FactsheetError(6, "ODS worksheet name is missing or unsafe")
    sheet = Sheet(name=name)
    row_number = 1
    for row in list(table):
        if _local(row.tag) != "table-row":
            continue
        row_repeat = _repeat(row, "number-rows-repeated")
        nonempty = False
        row_cells: list[Cell] = []
        column = 1
        for child in list(row):
            kind = _local(child.tag)
            if kind not in {"table-cell", "covered-table-cell"}:
                continue
            elements[0] += 1
            if elements[0] > MAX_CELL_ELEMENTS:
                raise FactsheetError(7, "ODS worksheet exceeded the cell cap")
            column_repeat = _repeat(child, "number-columns-repeated")
            spanned = _repeat(child, "number-columns-spanned") if _attr(child, "number-columns-spanned") else 1
            if kind == "covered-table-cell" or _cell_from(child, row_number, column) is None:
                if column_repeat >= EMPTY_COLUMN_REPEAT:
                    break
                column += column_repeat
                if column > MAX_COLUMNS:
                    break
                continue
            cell = _cell_from(child, row_number, column)
            if cell is None:
                continue
            nonempty = True
            copies = max(column_repeat, 1)
            if copies > MAX_NONEMPTY_REPEAT or spanned > MAX_NONEMPTY_REPEAT:
                raise FactsheetError(7, "ODS cell repeat exceeded the bounds")
            for offset in range(copies):
                row_cells.append(
                    Cell(
                        row=row_number,
                        column=column + offset,
                        text=cell.text,
                        value_type=cell.value_type,
                        value=cell.value,
                    )
                )
            column += copies
            if column > MAX_COLUMNS:
                raise FactsheetError(7, "ODS worksheet exceeded the column cap")
        if not nonempty:
            if row_repeat >= TRAILING_ROW_REPEAT:
                break
            row_number += row_repeat
            continue
        if row_repeat > MAX_NONEMPTY_REPEAT:
            raise FactsheetError(7, "ODS row repeat exceeded the bounds")
        for copy in range(row_repeat):
            for cell in row_cells:
                sheet.cells.append(
                    Cell(
                        row=row_number + copy,
                        column=cell.column,
                        text=cell.text,
                        value_type=cell.value_type,
                        value=cell.value,
                    )
                )
        row_number += row_repeat
    return sheet


def parse_ods_bytes(blob: bytes) -> list[Sheet]:
    """Parse worksheet text, units, and exact numeric tokens from an ODS zip."""
    if len(blob) > MAX_ODS_BYTES:
        raise FactsheetError(7, "ODS file exceeded the byte cap")
    if not blob.startswith(b"PK"):
        raise FactsheetError(6, "workbook is not a valid ODS zip")
    try:
        archive = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as exc:
        raise FactsheetError(6, "workbook is not a valid ODS zip") from exc
    with archive:
        members = archive.infolist()
        assess_members(members)
        names = [info.filename for info in members]
        if names.count("mimetype") != 1 or names.count("content.xml") != 1:
            raise FactsheetError(6, "ODS archive is missing mimetype or content.xml")
        mimetype = _read_capped(archive, "mimetype").decode("utf-8", "replace").strip()
        if mimetype != "application/vnd.oasis.opendocument.spreadsheet":
            raise FactsheetError(6, "ODS mimetype is not a spreadsheet")
        xml_bytes = _read_capped(archive, "content.xml")
    lowered = xml_bytes[:800].lower() + xml_bytes.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise FactsheetError(6, "ODS content XML contains a forbidden declaration")
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        raise FactsheetError(6, "ODS content XML could not be parsed") from exc
    tables: list[ElementTree.Element] = []
    for element in root.iter():
        if _local(element.tag) != "spreadsheet":
            continue
        tables.extend(child for child in list(element) if _local(child.tag) == "table")
    if not tables or len(tables) > MAX_SHEETS:
        raise FactsheetError(6, "ODS workbook does not contain a bounded set of worksheets")
    elements = [0]
    sheets = [_parse_sheet(table, elements) for table in tables]
    publication = ""
    for sheet in sheets:
        if sheet.name == "Cover_sheet":
            publication = sheet.title
            break
    if "pedal cycle" not in publication.casefold() and not any(
        "pedal cycle" in sheet.title.casefold() for sheet in sheets
    ):
        raise FactsheetError(6, "workbook is not the pedal-cycle factsheet")
    return sheets


def _semantic_kind(text: str) -> str | None:
    if NOTE_MARKER.fullmatch(text):
        return "note_marker"
    if SHORTHAND.fullmatch(text):
        return "missing"
    if PERCENT_TEXT.fullmatch(text):
        return "percent_text"
    return None


def _title_units(title: str) -> list[str]:
    return [match.strip() for match in PARENTHETICAL.findall(title) if match.strip()]


def _publication_dates(sheets: list[Sheet]) -> tuple[str | None, str | None]:
    published: list[str] = []
    upcoming: list[str] = []
    for sheet in sheets:
        headers = {int(item["column"]): str(item["header"]) for item in sheet.headers}
        published_column = next((column for column, name in headers.items() if name == PUBLISHED_HEADER), None)
        next_column = next((column for column, name in headers.items() if name == NEXT_HEADER), None)
        if published_column is None:
            continue
        header = sheet.header_row or 0
        rows = sorted({cell.row for cell in sheet.cells if cell.row > header})
        for row in rows:
            first = sheet.column_text(row, published_column)
            if first:
                published.append(first)
            if next_column is not None:
                following = sheet.column_text(row, next_column)
                if following:
                    upcoming.append(following)
    first_published = published[0] if published and len(set(published)) == 1 else None
    next_publication = upcoming[0] if upcoming and len(set(upcoming)) == 1 else None
    return first_published, next_publication


def workbook_record(
    sheets: list[Sheet],
    *,
    limit: int,
    sheet_name: str | None,
    requests: list[FetchRecord],
    factsheet_url: str,
    release_url: str,
    ods_url: str | None,
    read: str,
) -> tuple[dict[str, object], str | None]:
    """Build one result record and the source-stated first-publication date."""
    if sheet_name is not None and sheet_name not in {sheet.name for sheet in sheets}:
        raise FactsheetError(2, f"worksheet was not found: {sheet_name}")
    selected = [sheet for sheet in sheets if sheet_name in {None, sheet.name}]
    numeric_preview: list[dict[str, object]] = []
    semantic_preview: list[dict[str, object]] = []
    numeric_total = 0
    sheet_records: list[dict[str, object]] = []
    missing_note = None
    for sheet in sheets:
        for line in sheet.preamble:
            if "[x]" in line.casefold() and missing_note is None:
                missing_note = line
        header = sheet.header_row
        numeric_count = 0
        max_row = max((cell.row for cell in sheet.cells), default=0)
        max_column = max((cell.column for cell in sheet.cells), default=0)
        for cell in sheet.cells:
            if header is not None and cell.row <= header:
                continue
            row_label = sheet.column_text(cell.row, 1) if cell.column != 1 else ""
            header_name, unit = sheet.header_for(cell.column)
            if cell.value is not None:
                numeric_count += 1
                if sheet in selected and len(numeric_preview) < limit:
                    numeric_preview.append(
                        {
                            "sheet": sheet.name,
                            "row": cell.row,
                            "column": cell.column,
                            "column_header": header_name,
                            "unit": unit,
                            "row_label": row_label or None,
                            "value_type": cell.value_type,
                            "value": cell.value,
                            "display": cell.text,
                        }
                    )
                continue
            kind = _semantic_kind(cell.text)
            if kind and sheet in selected and len(semantic_preview) < limit:
                semantic_preview.append(
                    {
                        "sheet": sheet.name,
                        "row": cell.row,
                        "column": cell.column,
                        "column_header": header_name,
                        "unit": unit,
                        "row_label": row_label or None,
                        "kind": kind,
                        "text": cell.text,
                    }
                )
        numeric_total += numeric_count
        sheet_records.append(
            {
                "name": sheet.name,
                "title": sheet.title,
                "title_units": _title_units(sheet.title),
                "preamble": sheet.preamble,
                "headers": sheet.headers,
                "numeric_count": numeric_count,
                "max_row": max_row,
                "max_column": max_column,
            }
        )
    if numeric_total == 0:
        raise FactsheetError(6, "workbook contained no numeric cells")
    publication = next(
        (
            sheet.title
            for sheet in sorted(sheets, key=lambda item: item.name != "Cover_sheet")
            if "pedal cycle" in sheet.title.casefold()
        ),
        "",
    )
    if not publication:
        raise FactsheetError(6, "workbook is not the pedal-cycle factsheet")
    selected_numeric = sum(
        record["numeric_count"]
        for record in sheet_records
        if isinstance(record["numeric_count"], int) and sheet_name in {None, record["name"]}
    )
    first_published, next_publication = _publication_dates(sheets)
    record: dict[str, object] = {
        "read": read,
        "publication": publication,
        "factsheet_url": factsheet_url,
        "release_url": release_url,
        "ods_url": ods_url,
        "worksheets": [sheet.name for sheet in sheets],
        "sheets": sheet_records,
        "numeric_cell_count": numeric_total,
        "numeric_preview": numeric_preview,
        "semantic_preview": semantic_preview,
        "preview_limit": limit,
        "preview_truncated": isinstance(selected_numeric, int) and selected_numeric > len(numeric_preview),
        "missing_data_note": missing_note,
        "next_publication": next_publication,
        "requests": [item.as_dict() for item in requests],
    }
    return record, first_published


def _challenge(body: bytes, content_type: str) -> bool:
    if "html" not in content_type.casefold() or len(body) > 20_000:
        return False
    sample = body[:4_000].casefold()
    markers = (b"incapsula", b"cf-browser-verification", b"attention required", b"aws-waf", b"goku")
    return any(marker in sample for marker in markers)


def fetch_url(url: str, *, kind: str, max_bytes: int) -> tuple[bytes, FetchRecord]:
    """GET one official URL with a timeout, byte cap, and host-checked redirects."""
    current = official_url(url)
    opener = build_opener(_NoRedirect)
    for hop in range(MAX_REDIRECTS + 1):
        request = Request(
            current,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/vnd.oasis.opendocument.spreadsheet,application/octet-stream;q=0.5",
            },
            method="GET",
        )
        try:
            response = opener.open(request, timeout=TIMEOUT_SECONDS)
        except HTTPError as exc:
            try:
                location = exc.headers.get("Location") if exc.headers else None
                if exc.code in {301, 302, 303, 307, 308} and location:
                    if hop == MAX_REDIRECTS:
                        raise FactsheetError(5, "network error: too many redirects") from exc
                    try:
                        current = official_url(urljoin(current, location))
                    except FactsheetError as error:
                        raise FactsheetError(7, "refusing redirect to undeclared host") from error
                    continue
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                if retry_after is not None:
                    retry_after = retry_after.strip()[:64]
                raise error_for_http_status(exc.code, retry_after) from exc
            finally:
                exc.close()
        except TimeoutError as exc:
            raise FactsheetError(5, "network error: timed out") from exc
        except URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, TimeoutError):
                raise FactsheetError(5, "network error: timed out") from exc
            raise FactsheetError(5, "network error: upstream request failed") from exc
        except ssl.SSLError as exc:
            raise FactsheetError(5, "network error: upstream request failed") from exc
        except OSError as exc:
            raise FactsheetError(5, "network error: upstream request failed") from exc
        with response:
            status = getattr(response, "status", 200)
            content_type = response.headers.get("Content-Type", "")
            body = response.read(max_bytes + 1)
            final_url = official_url(response.geturl())
        if status != 200:
            raise error_for_http_status(status)
        if len(body) > max_bytes:
            raise FactsheetError(7, "response exceeded the byte cap")
        if _challenge(body, content_type):
            raise FactsheetError(4, "network error: blocked: upstream challenge page")
        if kind == "ods" and not body.startswith(b"PK"):
            raise FactsheetError(6, "ODS response was not a spreadsheet archive")
        return body, FetchRecord(final_url, status, len(body), kind)
    raise FactsheetError(5, "network error: too many redirects")


def load_workbook(
    *,
    fixture: bytes | None,
    limit: int,
    sheet_name: str | None,
) -> tuple[dict[str, object], str | None]:
    """Load a local fixture or the current official pedal-cycle workbook."""
    if fixture is not None:
        sheets = parse_ods_bytes(fixture)
        return workbook_record(
            sheets,
            limit=limit,
            sheet_name=sheet_name,
            requests=[],
            factsheet_url=FACTSHEET_URL,
            release_url=FACTSHEET_URL,
            ods_url=None,
            read="fixture",
        )
    factsheet_body, factsheet_fetch = fetch_url(FACTSHEET_URL, kind="page", max_bytes=MAX_PAGE_BYTES)
    factsheet_html = factsheet_body.decode("utf-8", "replace")
    assert_factsheet_page(factsheet_html)
    requests = [factsheet_fetch]
    release_url = factsheet_fetch.url
    ods_links = pedal_ods_links(factsheet_html, factsheet_fetch.url)
    if not ods_links:
        parent = linked_parent_release(factsheet_html, factsheet_fetch.url)
        if parent is None:
            raise FactsheetError(6, "release page did not link a pedal-cycle ODS")
        parent_body, parent_fetch = fetch_url(parent, kind="page", max_bytes=MAX_PAGE_BYTES)
        requests.append(parent_fetch)
        release_url = parent_fetch.url
        ods_links = pedal_ods_links(parent_body.decode("utf-8", "replace"), parent_fetch.url)
    if len(ods_links) != 1:
        raise FactsheetError(6, "release page did not identify exactly one pedal-cycle ODS")
    ods_body, ods_fetch = fetch_url(ods_links[0], kind="ods", max_bytes=MAX_ODS_BYTES)
    requests.append(ods_fetch)
    sheets = parse_ods_bytes(ods_body)
    return workbook_record(
        sheets,
        limit=limit,
        sheet_name=sheet_name,
        requests=requests,
        factsheet_url=factsheet_fetch.url,
        release_url=release_url,
        ods_url=ods_fetch.url,
        read="live",
    )
