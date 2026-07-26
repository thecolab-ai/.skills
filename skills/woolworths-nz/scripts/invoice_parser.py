#!/usr/bin/env python3
"""Parse Woolworths NZ tax-invoice rows and join them to past-order SKUs.

The invoice is the source of supplied quantities and paid prices. Woolworths'
``past-orders/{id}/items`` response is the source of current catalogue product
metadata and SKUs. Matching is deliberately explicit and confidence-scored so
that callers can inspect, rather than silently accept, uncertain joins.
"""
from __future__ import annotations

import pathlib
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any


class InvoiceParseError(RuntimeError):
    """Raised when a PDF is missing, unsupported, or has no invoice rows."""


QUANTITY_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([A-Za-z]+)\s*$")
UNIT_PRICE_RE = re.compile(
    r"^\s*\$?\s*([0-9,]+(?:\.\d+)?)\s*/\s*([A-Za-z]+)\s*$"
)
MONEY_RE = re.compile(r"^\s*(\()?\s*-?\$?\s*([0-9,]+(?:\.\d+)?)\s*\)?\s*$")


def normalize_product_text(value: Any) -> str:
    """Normalise catalogue/invoice wording for deterministic comparison."""
    text = str(value or "").replace("×", " x ").replace("&", " and ")
    text = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    replacements = (
        (r"\bkilograms?\b|\bkgs?\b", "kg"),
        (r"\bgrams?\b|\bgms?\b", "g"),
        (r"\blitres?\b|\bliters?\b|\bltrs?\b", "l"),
        (r"\bmillilitres?\b|\bmilliliters?\b|\bmls\b", "ml"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return " ".join(re.findall(r"[a-z0-9]+", text))


def product_name_candidates(product: dict[str, Any]) -> set[str]:
    size = product.get("size") if isinstance(product.get("size"), dict) else {}
    volume = size.get("volumeSize") or ""
    brand = product.get("brand") or ""
    name = product.get("name") or ""
    variety = product.get("variety") or ""
    candidates = (
        name,
        f"{brand} {name}",
        f"{name} {volume}",
        f"{brand} {name} {volume}",
        f"{brand} {name} {variety} {volume}",
    )
    return {
        normalised
        for candidate in candidates
        if (normalised := normalize_product_text(candidate))
    }


def product_name_score(invoice_description: str, candidate: str) -> float:
    left = normalize_product_text(invoice_description)
    right = normalize_product_text(candidate)
    if not left or not right:
        return 0.0
    sequence = SequenceMatcher(None, left, right).ratio()
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    containment = 0.0
    if left in right or right in left:
        containment = min(len(left), len(right)) / max(len(left), len(right))
    return max(sequence, 0.55 * sequence + 0.45 * jaccard, containment)


def _group_words(words: list[dict[str, Any]], tolerance: float = 1.2) -> list[tuple[float, list[dict[str, Any]]]]:
    groups: list[tuple[float, list[dict[str, Any]]]] = []
    for word in sorted(words, key=lambda item: (float(item["top"]), float(item["x0"]))):
        top = float(word["top"])
        if groups and abs(groups[-1][0] - top) <= tolerance:
            groups[-1][1].append(word)
        else:
            groups.append((top, [word]))
    return groups


def extract_invoice_order_number(words: list[dict[str, Any]]) -> str | None:
    """Extract the `Order Confirmation/Invoice Number` header value."""
    for _top, group in _group_words(words):
        ordered = sorted(group, key=lambda item: float(item["x0"]))
        labels = [str(word.get("text", "")).strip() for word in ordered]
        lower = [label.lower() for label in labels]
        for order_index, label in enumerate(lower):
            if label != "order":
                continue
            number_index = next(
                (
                    index
                    for index in range(order_index + 1, min(order_index + 5, len(lower)))
                    if lower[index] == "number"
                ),
                None,
            )
            if number_index is None or number_index + 1 >= len(labels):
                continue
            qualifier = " ".join(lower[order_index + 1 : number_index])
            if "confirmation" not in qualifier or "invoice" not in qualifier:
                continue
            candidate = labels[number_index + 1].strip()
            if len(re.sub(r"[^A-Za-z0-9]", "", candidate)) >= 4:
                return candidate
    return None


def normalize_order_identifier(value: Any) -> str:
    return "".join(re.findall(r"[A-Za-z0-9]+", str(value or ""))).lower()


def validate_invoice_order_number(
    invoice_order_number: str | None,
    expected_order_id: str,
) -> None:
    actual = normalize_order_identifier(invoice_order_number)
    expected = normalize_order_identifier(expected_order_id)
    if not actual:
        raise InvoiceParseError(
            "the invoice order confirmation number could not be read; refusing to join it to an order"
        )
    if not expected or actual != expected:
        raise InvoiceParseError(
            "the invoice order confirmation number does not match the requested order; "
            "refusing to join potentially unrelated products"
        )


def _line_text(words: list[dict[str, Any]], left: float, right: float) -> str:
    selected = [
        word
        for word in words
        if float(word["x0"]) >= left and float(word["x0"]) < right
    ]
    return " ".join(str(word["text"]) for word in sorted(selected, key=lambda item: float(item["x0"]))).strip()


def _parse_quantity(value: str) -> tuple[float | int, str] | None:
    match = QUANTITY_RE.match(value)
    if not match:
        return None
    quantity = float(match.group(1))
    return (int(quantity) if quantity.is_integer() else quantity, match.group(2).lower())


def _parse_unit_price(value: str) -> tuple[float, str] | None:
    match = UNIT_PRICE_RE.match(value)
    if not match:
        return None
    return float(match.group(1).replace(",", "")), match.group(2).lower()


def _parse_money(value: str) -> float | None:
    match = MONEY_RE.match(value)
    if not match:
        return None
    amount = float(match.group(2).replace(",", ""))
    return -amount if match.group(1) or "-" in value else amount


def parse_invoice_word_rows(
    words: list[dict[str, Any]],
    boundaries: list[float],
    *,
    page_number: int,
    header_top: float,
) -> list[dict[str, Any]]:
    """Parse rows from pdfplumber word dictionaries for one invoice page."""
    if len(boundaries) != 7:
        raise InvoiceParseError("expected seven invoice table boundaries")

    rows: list[dict[str, Any]] = []
    active: dict[str, Any] | None = None
    last_active_top = 0.0

    for top, line_words in _group_words(words):
        if top <= header_top + 8:
            continue
        cells = [
            _line_text(line_words, boundaries[index], boundaries[index + 1])
            for index in range(6)
        ]
        ref_text, description, ordered_text, supplied_text, unit_price_text, amount_text = cells
        ordered = _parse_quantity(ordered_text)
        supplied = _parse_quantity(supplied_text)
        unit_price = _parse_unit_price(unit_price_text)
        amount = _parse_money(amount_text)

        if (
            ref_text.isdigit()
            and description
            and ordered is not None
            and supplied is not None
            and unit_price is not None
            and amount is not None
        ):
            active = {
                "page": page_number,
                "ref": int(ref_text),
                "invoice_description": description,
                "ordered_quantity": ordered[0],
                "ordered_unit": ordered[1],
                "supplied_quantity": supplied[0],
                "supplied_unit": supplied[1],
                "unit_price": unit_price[0],
                "pricing_unit": unit_price[1],
                "amount": amount,
            }
            rows.append(active)
            last_active_top = top
            continue

        description_words = [
            word
            for word in line_words
            if float(word["x0"]) >= boundaries[1]
            and float(word["x0"]) < boundaries[2]
        ]
        is_bold = any("bold" in str(word.get("fontname", "")).lower() for word in description_words)
        has_other_cells = any(cells[index] for index in (0, 2, 3, 4, 5))
        if (
            active
            and description
            and not is_bold
            and not has_other_cells
            and top - last_active_top <= 15.5
        ):
            active["invoice_description"] += " " + description
            last_active_top = top
        elif description and is_bold:
            active = None

    return rows


def _header_words(words: list[dict[str, Any]]) -> dict[str, dict[str, Any]] | None:
    groups = _group_words(words)
    required = ("Ref", "Description", "Ordered", "Supplied", "Price", "Amount")
    for _top, group in groups:
        by_text = {str(word["text"]): word for word in group}
        if all(label in by_text for label in required):
            return {label: by_text[label] for label in required}
    return None


def _between(
    vertical_xs: list[float],
    left: float,
    right: float,
    fallback: float,
) -> float:
    candidates = [value for value in vertical_xs if left < value < right]
    return min(candidates, key=lambda value: abs(value - fallback)) if candidates else fallback


def invoice_boundaries(
    words: list[dict[str, Any]],
    vertical_xs: list[float],
    page_width: float,
) -> tuple[list[float], float] | None:
    headers = _header_words(words)
    if not headers:
        return None
    ref = headers["Ref"]
    description = headers["Description"]
    ordered = headers["Ordered"]
    supplied = headers["Supplied"]
    price = headers["Price"]
    amount = headers["Amount"]
    fallbacks = [
        page_width * ratio
        for ratio in (0.042, 0.099, 0.520, 0.618, 0.733, 0.842, 0.943)
    ]
    boundaries = [
        max((x for x in vertical_xs if x < float(ref["x0"])), default=fallbacks[0]),
        _between(vertical_xs, float(ref["x1"]), float(description["x0"]), fallbacks[1]),
        _between(vertical_xs, float(description["x1"]), float(ordered["x0"]), fallbacks[2]),
        _between(vertical_xs, float(ordered["x1"]), float(supplied["x0"]), fallbacks[3]),
        _between(vertical_xs, float(supplied["x1"]), float(price["x0"]), fallbacks[4]),
        _between(vertical_xs, float(price["x1"]), float(amount["x0"]), fallbacks[5]),
        min((x for x in vertical_xs if x > float(amount["x1"])), default=fallbacks[6]),
    ]
    return boundaries, float(ref["top"])


def parse_invoice_pdf(path: str | pathlib.Path) -> dict[str, Any]:
    pdf_path = pathlib.Path(path).expanduser()
    if not pdf_path.is_file():
        raise InvoiceParseError(f"invoice PDF not found: {pdf_path}")
    try:
        import pdfplumber
    except ImportError as exc:
        raise InvoiceParseError(
            "invoice parsing requires the optional `pdfplumber` package"
        ) from exc

    rows: list[dict[str, Any]] = []
    order_numbers: list[str] = []
    try:
        with pdfplumber.open(pdf_path) as document:
            page_count = len(document.pages)
            for page_number, page in enumerate(document.pages, start=1):
                words = page.extract_words(
                    x_tolerance=1,
                    y_tolerance=2,
                    extra_attrs=["fontname", "size"],
                )
                order_number = extract_invoice_order_number(words)
                if order_number:
                    order_numbers.append(order_number)
                vertical_xs = sorted(
                    {
                        round(float(line["x0"]), 3)
                        for line in page.lines
                        if abs(float(line["x1"]) - float(line["x0"])) < 0.5
                    }
                )
                detected = invoice_boundaries(words, vertical_xs, float(page.width))
                if not detected:
                    continue
                boundaries, header_top = detected
                rows.extend(
                    parse_invoice_word_rows(
                        words,
                        boundaries,
                        page_number=page_number,
                        header_top=header_top,
                    )
                )
    except InvoiceParseError:
        raise
    except Exception as exc:
        raise InvoiceParseError(f"could not parse invoice PDF: {exc}") from exc

    if not rows:
        raise InvoiceParseError(
            "no Woolworths invoice line rows were found; check that this is a text-based tax invoice PDF"
        )
    normalized_order_numbers = {
        normalize_order_identifier(value) for value in order_numbers if value
    }
    if len(normalized_order_numbers) > 1:
        raise InvoiceParseError(
            "the invoice pages contain inconsistent order confirmation numbers"
        )
    return {
        "page_count": page_count,
        "order_number": order_numbers[0] if order_numbers else None,
        "items": rows,
    }


def order_products(payload: Any) -> list[dict[str, Any]]:
    items: list[Any] = []
    if not isinstance(payload, dict):
        return []
    products = payload.get("products")
    if isinstance(products, dict) and isinstance(products.get("items"), list):
        items = products["items"]
    elif isinstance(products, list):
        items = products
    elif isinstance(payload.get("items"), list):
        items = payload["items"]
    return [
        item
        for item in items
        if isinstance(item, dict) and item.get("sku") and item.get("name")
    ]


def match_invoice_items(
    invoice_items: list[dict[str, Any]],
    products: list[dict[str, Any]],
    *,
    min_confidence: float = 0.72,
) -> dict[str, Any]:
    if not 0 <= min_confidence <= 1:
        raise ValueError("min_confidence must be between 0 and 1")

    scored_pairs: list[tuple[float, int, int]] = []
    row_rankings: list[list[tuple[float, int]]] = []
    for row_index, row in enumerate(invoice_items):
        ranking: list[tuple[float, int]] = []
        for product_index, product in enumerate(products):
            candidates = product_name_candidates(product)
            score = max(
                (
                    product_name_score(row.get("invoice_description", ""), candidate)
                    for candidate in candidates
                ),
                default=0.0,
            )
            ranking.append((score, product_index))
            scored_pairs.append((score, row_index, product_index))
        row_rankings.append(sorted(ranking, reverse=True))

    assigned_rows: dict[int, tuple[float, int]] = {}
    assigned_products: set[int] = set()
    for score, row_index, product_index in sorted(scored_pairs, reverse=True):
        if score < min_confidence:
            break
        if row_index in assigned_rows or product_index in assigned_products:
            continue
        assigned_rows[row_index] = (score, product_index)
        assigned_products.add(product_index)

    combined: list[dict[str, Any]] = []
    ambiguous = 0
    for row_index, row in enumerate(invoice_items):
        output = dict(row)
        assignment = assigned_rows.get(row_index)
        if not assignment:
            output.update(
                {
                    "sku": None,
                    "product_name": None,
                    "product_brand": None,
                    "match_confidence": 0.0,
                    "match_method": "unmatched",
                    "match_ambiguous": False,
                }
            )
            combined.append(output)
            continue

        score, product_index = assignment
        product = products[product_index]
        ranking = row_rankings[row_index]
        runner_up = next(
            (
                candidate_score
                for candidate_score, candidate_index in ranking
                if candidate_index != product_index
            ),
            0.0,
        )
        is_ambiguous = runner_up >= min_confidence and score - runner_up < 0.03
        ambiguous += int(is_ambiguous)
        output.update(
            {
                "sku": str(product.get("sku") or "") or None,
                "product_name": product.get("name") or "",
                "product_brand": product.get("brand") or "",
                "match_confidence": round(score, 4),
                "match_method": (
                    "exact-normalized-name" if score >= 0.995 else "name-similarity"
                ),
                "match_ambiguous": is_ambiguous,
            }
        )
        combined.append(output)

    unmatched_product_skus = [
        str(product.get("sku") or "")
        for index, product in enumerate(products)
        if index not in assigned_products and product.get("sku")
    ]
    matched = len(assigned_rows)
    return {
        "summary": {
            "invoice_items": len(invoice_items),
            "order_products": len(products),
            "matched": matched,
            "unmatched_invoice_items": len(invoice_items) - matched,
            "unmatched_order_products": len(products) - len(assigned_products),
            "ambiguous": ambiguous,
            "minimum_confidence": min_confidence,
        },
        "items": combined,
        "unmatched_order_product_skus": unmatched_product_skus,
    }


def combine_parsed_invoice_with_order_items(
    invoice: dict[str, Any],
    order_items_payload: Any,
    *,
    min_confidence: float = 0.72,
) -> dict[str, Any]:
    result = match_invoice_items(
        invoice["items"],
        order_products(order_items_payload),
        min_confidence=min_confidence,
    )
    result["invoice_page_count"] = invoice["page_count"]
    result["invoice_order_number"] = invoice.get("order_number")
    return result


def combine_invoice_with_order_items(
    pdf_path: str | pathlib.Path,
    order_items_payload: Any,
    *,
    min_confidence: float = 0.72,
    expected_order_id: str | None = None,
) -> dict[str, Any]:
    invoice = parse_invoice_pdf(pdf_path)
    if expected_order_id is not None:
        validate_invoice_order_number(invoice.get("order_number"), expected_order_id)
    return combine_parsed_invoice_with_order_items(
        invoice,
        order_items_payload,
        min_confidence=min_confidence,
    )
