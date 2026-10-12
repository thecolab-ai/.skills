"""Bounded OOXML reader using ZIP and ElementTree, with cached formula values."""
from __future__ import annotations

import io
import math
import posixpath
import re
import zipfile
import zlib
import xml.etree.ElementTree as ET
from datetime import date, timedelta

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


class SchemaError(ValueError):
    """A source does not match its supported published format."""


# Spreadsheet numbers are plain decimals. Python's float() also accepts
# underscores, whitespace and non-finite names, which are not cell values.
_NUMBER_TEXT = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
# Auckland supply series start in the 2010s. A bare year such as 2026 is an
# Excel serial for 1905, not a reporting month.
MIN_PERIOD_YEAR = 1990
MAX_PERIOD_YEAR = 2100


def number(value):
    if value is None or value == "" or value == "-":
        return None
    if isinstance(value, bool):
        raise SchemaError(f"Expected a number, received {value!r}")
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str) and _NUMBER_TEXT.fullmatch(value):
        result = float(value)
    else:
        raise SchemaError(f"Expected a number, received {value!r}")
    if not math.isfinite(result):
        raise SchemaError("Workbook contains a non-finite number")
    return int(result) if result.is_integer() else result


def _unsupported_archive(exc):
    if isinstance(exc, NotImplementedError):
        return True
    if isinstance(exc, RuntimeError):
        text = str(exc).lower()
        return "encrypt" in text or "password" in text
    return False


class Workbook:
    def __init__(self, body: bytes):
        try:
            self.zip = zipfile.ZipFile(io.BytesIO(body))
            infos = self.zip.infolist()
            if len(infos) > 2000 or sum(i.file_size for i in infos) > 256 * 1024 * 1024:
                raise SchemaError("Workbook exceeds the 256 MiB expanded-size limit")
            root = ET.fromstring(self.zip.read("xl/workbook.xml"))
            rels = ET.fromstring(self.zip.read("xl/_rels/workbook.xml.rels"))
            targets = {r.attrib["Id"]: r.attrib["Target"] for r in rels
                       if r.attrib.get("TargetMode") != "External"}
            props = root.find(f"{{{NS}}}workbookPr")
            self.epoch = date(1904, 1, 1) if props is not None and props.get("date1904") in {"1", "true"} else date(1899, 12, 30)
            self.sheets = {}
            for sheet in root.find(f"{{{NS}}}sheets"):
                target = targets[sheet.attrib[RID]]
                path = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
                if not path.startswith("xl/") or path not in self.zip.namelist():
                    raise SchemaError("Invalid worksheet relationship")
                self.sheets[sheet.attrib["name"]] = path
            self.strings = []
            if "xl/sharedStrings.xml" in self.zip.namelist():
                with self.zip.open("xl/sharedStrings.xml") as stream:
                    for _, element in ET.iterparse(stream, events=("end",)):
                        if element.tag == f"{{{NS}}}si":
                            self.strings.append("".join(t.text or "" for t in element.iter(f"{{{NS}}}t")))
                            element.clear()
        except (KeyError, IndexError, ValueError, TypeError, OSError, zlib.error, ET.ParseError, zipfile.BadZipFile, NotImplementedError, RuntimeError) as exc:
            if isinstance(exc, SchemaError):
                raise
            if isinstance(exc, (NotImplementedError, RuntimeError)) and not _unsupported_archive(exc):
                raise
            raise SchemaError("Source is not a supported XLSX workbook") from exc

    def month(self, value):
        if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}", value):
            try:
                period = date.fromisoformat(value[:10]).isoformat()[:7]
            except ValueError as exc:
                raise SchemaError("Invalid workbook reporting date") from exc
        else:
            value = number(value)
            if value is None:
                raise SchemaError("Invalid workbook reporting date")
            try:
                period = (self.epoch + timedelta(days=value)).isoformat()[:7]
            except (OverflowError, ValueError) as exc:
                raise SchemaError("Invalid workbook reporting date") from exc
        year = int(period[:4])
        if year < MIN_PERIOD_YEAR or year > MAX_PERIOD_YEAR:
            raise SchemaError("Implausible workbook reporting period")
        return period

    def rows(self, sheet):
        if sheet not in self.sheets:
            raise SchemaError(f"Missing worksheet: {sheet}")
        try:
            with self.zip.open(self.sheets[sheet]) as stream:
                # Clear sheetData as well as each row so large HUD sheets stay bounded.
                sheet_data = None
                for event, element in ET.iterparse(stream, events=("start", "end")):
                    if event == "start" and element.tag == f"{{{NS}}}sheetData":
                        sheet_data = element
                    if event != "end" or element.tag != f"{{{NS}}}row":
                        continue
                    row = {}
                    for cell in element:
                        reference = cell.attrib.get("r", "")
                        match = re.fullmatch(r"([A-Z]+)\d+", reference)
                        if not match:
                            raise SchemaError("Cell has no valid column reference")
                        kind = cell.attrib.get("t")
                        value_element = cell.find(f"{{{NS}}}v")
                        value = value_element.text if value_element is not None else None
                        if kind == "s":
                            if not isinstance(value, str) or not value.isdigit():
                                raise SchemaError(f"Missing or invalid shared-string index in {sheet}!{reference}")
                            index = int(value)
                            if index >= len(self.strings):
                                raise SchemaError(f"Shared-string index is out of range in {sheet}!{reference}")
                            value = self.strings[index]
                        elif kind == "inlineStr":
                            value = "".join(t.text or "" for t in cell.iter(f"{{{NS}}}t"))
                        elif kind == "e":
                            raise SchemaError(f"Excel error in {sheet}!{reference}: {value}")
                        elif value is not None and kind not in {"str", "d"}:
                            value = number(value)
                        elif cell.find(f"{{{NS}}}f") is not None and value is None:
                            raise SchemaError(f"Formula has no cached value in {sheet}!{reference}")
                        if value is not None and value != "":
                            row[match.group(1)] = value
                    row_number = int(element.attrib["r"])
                    element.clear()
                    if sheet_data is not None:
                        sheet_data.clear()
                    yield row_number, row
        except (KeyError, IndexError, ValueError, OSError, zlib.error, ET.ParseError, zipfile.BadZipFile) as exc:
            if isinstance(exc, SchemaError):
                raise
            raise SchemaError(f"Cannot parse worksheet {sheet}: {exc}") from exc
        except NotImplementedError as exc:
            raise SchemaError(f"Cannot parse worksheet {sheet}: unsupported archive") from exc
        except RuntimeError as exc:
            if not _unsupported_archive(exc):
                raise
            raise SchemaError(f"Cannot parse worksheet {sheet}: unsupported archive") from exc
