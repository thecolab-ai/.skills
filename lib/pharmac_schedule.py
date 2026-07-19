"""Parser for Pharmac's published Pharmaceutical Schedule XML."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Iterable


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_text(node: ET.Element | None, name: str) -> str | None:
    if node is None:
        return None
    for child in node:
        if local(child.tag) == name:
            value = " ".join("".join(child.itertext()).split())
            return value or None
    return None


def _normalised_attributes(node: ET.Element) -> dict[str, str]:
    return {local(key): value for key, value in node.attrib.items()}


def _node_text(node: ET.Element) -> str | None:
    value = " ".join("".join(node.itertext()).split())
    return value or None


def restriction_details(nodes: Iterable[ET.Element]) -> list[dict[str, Any]]:
    """Preserve rule/request structure rather than flattening eligibility text."""
    details: list[dict[str, Any]] = []
    seen: set[tuple[object, ...]] = set()
    for owner in nodes:
        for node in owner.iter():
            kind = local(node.tag)
            if kind not in {"Rule", "Request", "Restriction", "Criteria", "Criterion"}:
                continue
            attributes = _normalised_attributes(node)
            text = _node_text(node)
            codes = sorted(set(re.findall(r"\bSA\d{3,5}\b", " ".join([*attributes.values(), text or ""]), re.I)))
            item = {
                "kind": kind,
                "attributes": attributes,
                "text": text,
                "special_authority_codes": [code.upper() for code in codes],
            }
            marker = (kind, tuple(sorted(attributes.items())), text)
            if marker not in seen:
                seen.add(marker)
                details.append(item)
    return details


def special_authorities(details: list[dict[str, Any]], effective_date: str, source_url: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for detail in details:
        for code in detail["special_authority_codes"]:
            grouped.setdefault(code, []).append({
                "kind": detail["kind"],
                "text": detail["text"],
                "attributes": detail["attributes"],
            })
    return [
        {
            "code": code,
            "criteria": criteria,
            "effective_date": effective_date,
            "effective_date_source": "Schedule publication date",
            "form_url": f"https://schedule.pharmac.govt.nz/SAForms.php?code={code}",
            "schedule_source_url": source_url,
        }
        for code, criteria in sorted(grouped.items())
    ]


def parse_schedule(body: bytes, source_url: str, retrieved_at: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ValueError(f"Pharmaceutical Schedule XML was invalid: {exc}") from exc
    if local(root.tag) != "Schedule":
        raise ValueError("Pharmaceutical Schedule XML root element was not Schedule")
    front = next((node for node in root if local(node.tag) == "Front"), None)
    metadata = {
        "edition": child_text(front, "Edition"),
        "published": child_text(front, "Published"),
        "volume": child_text(front, "Volume"),
        "source_url": source_url,
        "retrieved_at": retrieved_at,
    }
    if not metadata["edition"] or not metadata["published"]:
        raise ValueError("Schedule XML is missing Front/Edition or Front/Published")
    records: list[dict[str, Any]] = []
    for section in (node for node in root if local(node.tag) == "Section"):
        section_name = child_text(section, "Name") or section.attrib.get("ID", "")
        for chemical in (node for node in section.iter() if local(node.tag) == "Chemical"):
            chemical_name = child_text(chemical, "Name")
            if not chemical_name:
                continue
            for formulation in (node for node in chemical if local(node.tag) == "Formulation"):
                formulation_name = child_text(formulation, "Name")
                for brand in (node for node in formulation if local(node.tag) == "Brand"):
                    brand_name = child_text(brand, "Name")
                    details = restriction_details((chemical, formulation, brand))
                    authorities = special_authorities(details, str(metadata["published"]), source_url)
                    for pack in (node for node in brand if local(node.tag) == "Pack"):
                        pack_id = pack.attrib.get("ID")
                        if not pack_id:
                            continue
                        records.append({
                            "id": pack_id,
                            "pharmacode": re.sub(r"^P", "", pack_id),
                            "record_type": "device" if "device" in section_name.lower() else "medicine",
                            "section": section_name,
                            "chemical": chemical_name,
                            "presentation": formulation_name,
                            "brand": brand_name,
                            "quantity": child_text(pack, "Quantity"),
                            "subsidy": child_text(pack, "Subsidy"),
                            "price": child_text(pack, "Price"),
                            "restrictions": details,
                            "special_authorities": authorities,
                            "special_authority_codes": [item["code"] for item in authorities],
                            "effective_date": metadata["published"],
                            "effective_date_source": "Schedule publication date",
                            "schedule_edition": metadata["edition"],
                            "source_url": source_url,
                            "retrieved_at": retrieved_at,
                        })
    if not records:
        raise ValueError("Schedule XML contained no funded pack records")
    return metadata, records


CHANGE_FIELDS = ("chemical", "presentation", "brand", "quantity", "subsidy", "price", "restrictions", "special_authorities")


def _comparable(field: str, value: Any) -> Any:
    if field != "special_authorities" or not isinstance(value, list):
        return value
    return [
        {key: item[key] for key in ("code", "criteria") if key in item}
        for item in value
        if isinstance(item, dict)
    ]


def diff_records(
    old_meta: dict[str, Any], old: list[dict[str, Any]], new_meta: dict[str, Any], new: list[dict[str, Any]],
    from_version: str, to_version: str,
) -> list[dict[str, Any]]:
    old_map = {str(row["id"]): row for row in old}
    new_map = {str(row["id"]): row for row in new}
    changes: list[dict[str, Any]] = []
    for key in sorted(set(old_map) | set(new_map)):
        before, after = old_map.get(key), new_map.get(key)
        if before is None: kind = "added"
        elif after is None: kind = "removed"
        elif any(_comparable(field, before.get(field)) != _comparable(field, after.get(field)) for field in CHANGE_FIELDS): kind = "changed"
        else: continue
        row = after or before
        assert row is not None
        changes.append({
            "change": kind, "id": key, "chemical": row["chemical"], "from_version": from_version, "to_version": to_version,
            "field_changes": {field: {"before": before.get(field) if before else None, "after": after.get(field) if after else None} for field in CHANGE_FIELDS if before is None or after is None or _comparable(field, before.get(field)) != _comparable(field, after.get(field))},
            "before": before, "after": after,
            "from_source": {"url": old_meta["source_url"], "published": old_meta["published"], "retrieved_at": old_meta["retrieved_at"]},
            "to_source": {"url": new_meta["source_url"], "published": new_meta["published"], "retrieved_at": new_meta["retrieved_at"]},
            "source_url": row["source_url"], "retrieved_at": row["retrieved_at"],
        })
    return changes
