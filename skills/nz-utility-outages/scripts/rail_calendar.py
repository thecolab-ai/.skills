#!/usr/bin/env python3
"""Read the verified KiwiRail single-page, CMYK rectangle calendar PDF layout.

This is deliberately a restricted PDF reader, not a general PDF implementation.
Unsupported layouts fail rather than interpreting an uncoloured day as a closure.
"""
from __future__ import annotations

import calendar
import re
import zlib
from datetime import date

NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
MONTHS = {name: index for index, name in enumerate(calendar.month_abbr) if name}
FULL = (0.05, 0.0, 0.0, 0.65)
PARTIAL = {(0.8, 0.15, 0.15, 0.0), (0.64, 0.12, 0.12, 0.0)}
PLAIN = {(0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.1)}


def page_content(body: bytes) -> str:
    if not body.startswith(b"%PDF-") or b"/Encrypt" in body or len(body) > 2_000_000:
        raise ValueError("calendar must be a bounded, unencrypted PDF")
    objects = {int(m[1]): m[2] for m in re.finditer(rb"(\d+) 0 obj\b(.*?)endobj", body, re.S)}
    pages = [value for value in objects.values() if re.search(rb"/Type\s*/Page\b", value)]
    if len(pages) != 1:
        raise ValueError("calendar must use the verified single-page layout")
    refs = re.search(rb"/Contents\s*\[([^]]+)\]", pages[0])
    if not refs:
        raise ValueError("calendar content references are missing")
    streams = []
    for number in re.findall(rb"(\d+) 0 R", refs[1]):
        obj = objects.get(int(number), b"")
        match = re.search(rb"stream\r?\n(.*?)\r?\nendstream", obj, re.S)
        if not match or not re.search(rb"/Filter\s*/FlateDecode\b", obj):
            raise ValueError("calendar content must use the verified Flate streams")
        decoder = zlib.decompressobj()
        decoded = decoder.decompress(match[1], 1_000_001)
        if len(decoded) > 1_000_000 or not decoder.eof:
            raise ValueError("calendar content exceeds the bounded stream size")
        streams.append(decoded.decode("latin1"))
    return "\n".join(streams)


def parse_content(content: str) -> dict:
    text = []
    for block in re.findall(r"BT\b(.*?)\bET", content, re.S):
        matrix = re.search(rf"((?:{NUMBER}\s+){{5}}{NUMBER})\s+Tm\b", block)
        if not matrix:
            raise ValueError("calendar text has no absolute position")
        values = tuple(map(float, matrix[1].split()))
        label = "".join(re.findall(r"\(([^()]*)\)", block))
        text.append((label, values[4], values[5]))
    title = [label for label, _, _ in text if re.fullmatch(r"\d{4} Rail Closures", label)]
    if len(title) != 1 or not any(label == "Full Network Closure" for label, _, _ in text) or not any(
        label == "Partial Closure or Reduced Frequency Services" for label, _, _ in text
    ):
        raise ValueError("calendar title or closure legend changed")
    year = int(title[0][:4])
    published = [label for label, _, _ in text if re.fullmatch(r"\d{1,2}/\d{2}/\d{4}", label)]
    if len(published) != 1:
        raise ValueError("calendar publication date is missing or ambiguous")
    day, month, publication_year = map(int, published[0].split("/"))
    latest = date(publication_year, month, day).isoformat()
    headings = []
    for label, x, y in text:
        match = re.fullmatch(r"([A-Z][a-z]{2})-(\d{2})", label)
        if match:
            if match[1] not in MONTHS or int(match[2]) != year % 100:
                raise ValueError("calendar month headings disagree with the title")
            headings.append((MONTHS[match[1]], x, y))
    if not headings or len({month for month, _, _ in headings}) != len(headings):
        raise ValueError("calendar month headings are missing or duplicated")

    # Track graphic colour and saved state. Rectangle paths use absolute coordinates.
    operation = re.compile(
        rf"(?P<colour>(?:{NUMBER}\s+){{3}}{NUMBER})\s+k\b|"
        rf"(?P<rect>(?:{NUMBER}\s+){{3}}{NUMBER})\s+re\b|"
        rf"(?P<matrix>(?:{NUMBER}\s+){{5}}{NUMBER})\s+cm\b|"
        r"(?<!\S)(?P<op>q|Q|f|f\*|n)(?!\S)"
    )
    colour = (0.0, 0.0, 0.0, 1.0)
    transformed = False
    stack, pending, rectangles = [], [], []
    for match in operation.finditer(content):
        if match['colour']:
            colour = tuple(map(float, match['colour'].split()))
        elif match['matrix']:
            transformed = True
        elif match['rect']:
            if transformed:
                raise ValueError("calendar rectangle transforms are unsupported")
            x, y, width, height = map(float, match['rect'].split())
            pending.append((min(x, x + width), min(y, y + height), max(x, x + width), max(y, y + height)))
        elif match['op'] == 'q':
            stack.append((colour, transformed))
        elif match['op'] == 'Q':
            if not stack:
                raise ValueError("calendar graphic state is unbalanced")
            colour, transformed = stack.pop()
        elif match['op'] in ('f', 'f*'):
            rectangles.extend((box, colour) for box in pending)
            pending = []
        elif match['op'] == 'n':
            pending = []
    if stack:
        raise ValueError("calendar graphic state is unbalanced")
    observed = {month: {} for month, _, _ in headings}
    closures = []
    for label, x, y in text:
        if not re.fullmatch(r"\d{1,2}", label):
            continue
        # Month grids share width; choose the closest heading above each day label.
        candidates = [(hy - y, abs(hx - x), month) for month, hx, hy in headings if hy > y and abs(hx - x) < 110]
        if not candidates:
            raise ValueError("calendar day has no containing month")
        month = min(candidates)[2]
        day = int(label)
        value = date(year, month, day).isoformat()
        if day in observed[month]:
            raise ValueError("calendar day is duplicated")
        fills = [c for (left, bottom, right, top), c in rectangles if left <= x <= right and bottom <= y <= top and right - left < 40 and top - bottom < 25]
        if len(fills) != 1:
            raise ValueError("calendar day has ambiguous or missing background")
        fill = fills[0]
        if fill == FULL:
            kind = "full_network_closure"
        elif fill in PARTIAL:
            kind = "partial_closure_or_reduced_frequency"
        elif fill in PLAIN:
            kind = None
        else:
            raise ValueError("calendar uses an unrecognised day colour")
        observed[month][day] = kind
        if kind:
            closures.append({"date": value, "kind": kind})
    for month, days in observed.items():
        if set(days) != set(range(1, calendar.monthrange(year, month)[1] + 1)):
            raise ValueError("calendar month grid is incomplete")
    if sorted(observed) != list(range(min(observed), max(observed) + 1)):
        raise ValueError("calendar coverage contains missing months")
    return {
        "latest_data": latest,
        "coverage_start": date(year, min(observed), 1).isoformat(),
        "coverage_end": date(year, max(observed), calendar.monthrange(year, max(observed))[1]).isoformat(),
        "closures": sorted(closures, key=lambda item: item['date']),
    }


def parse_pdf(body: bytes) -> dict:
    return parse_content(page_content(body))
