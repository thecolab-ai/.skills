"""Parser and selectors for the official Ministry of Education Schools Directory."""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

RESOURCE_ID = "4b292323-9fcc-41f8-814b-3c7b19cf14b3"
API_BASE = "https://catalogue.data.govt.nz/api/3/action"
RESOURCE_URL = f"{API_BASE}/resource_show?id={RESOURCE_ID}"
DATA_URL = f"{API_BASE}/datastore_search?resource_id={RESOURCE_ID}&limit=5000"

# Canonical Ministry school-type labels whose class bounds are inherent in the
# type. Ambiguous types (for example Special School) intentionally remain
# unmapped unless the directory publishes literal Lowest_Class/Highest_Class or
# a "Year N-M" range in Org_Type.
SCHOOL_TYPE_YEAR_LEVELS = {
    "contributing": (1, 6),
    "full primary": (1, 8),
    "intermediate": (7, 8),
}


def normalize(record: dict[str, Any], *, source_url: str, retrieved_at: str, last_modified: str | None) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("Schools Directory record must be an object")
    school_type = record.get("Org_Type")
    range_match = re.search(r"Year\s*(\d+)\s*[-–]\s*(\d+)", str(school_type or ""), re.I)
    literal_lowest = _year_level(record.get("Lowest_Class"))
    literal_highest = _year_level(record.get("Highest_Class"))
    type_range = (int(range_match.group(1)), int(range_match.group(2))) if range_match else None
    mapped_range = SCHOOL_TYPE_YEAR_LEVELS.get(str(school_type or "").strip().casefold())
    derived_range = type_range or mapped_range
    lowest = literal_lowest or (derived_range[0] if derived_range else None)
    highest = literal_highest or (derived_range[1] if derived_range else None)
    if literal_lowest is not None or literal_highest is not None:
        year_level_method = "directory_class_fields"
    elif type_range:
        year_level_method = "school_type_literal_range"
    elif mapped_range:
        year_level_method = "school_type_mapping"
    else:
        year_level_method = "unavailable"
    address_parts = [record.get("Add1_Line1"), record.get("Add1_Suburb"), record.get("Add1_City")]
    return {
        "school_id": str(record.get("School_Id") or ""),
        "name": record.get("Org_Name"),
        "status": record.get("Status"),
        "school_type": school_type,
        "authority": record.get("Authority"),
        "gender": record.get("CoEd_Status"),
        "address": {
            "street": record.get("Add1_Line1"),
            "suburb": record.get("Add1_Suburb"),
            "town_city": record.get("Add1_City"),
        },
        "address_text": ", ".join(str(value) for value in address_parts if value),
        "town_city": record.get("Add1_City"),
        "year_levels": {"lowest": lowest, "highest": highest},
        "year_levels_provenance": {
            "method": year_level_method,
            "source_field": "Lowest_Class/Highest_Class" if year_level_method == "directory_class_fields" else "Org_Type",
            "source_value": school_type if year_level_method != "directory_class_fields" else {
                "lowest": record.get("Lowest_Class"),
                "highest": record.get("Highest_Class"),
            },
        },
        "territorial_authority": record.get("Territorial_Authority"),
        "regional_council": record.get("Regional_Council"),
        "education_region": record.get("Education_Region"),
        "latitude": _number(record.get("Latitude")),
        "longitude": _number(record.get("Longitude")),
        "enrolment_scheme": record.get("Enrolment_Scheme"),
        "equity_index": record.get("EQi_Index"),
        "roll_date": record.get("Roll_Date"),
        "total_roll": record.get("Total"),
        "date_opened": record.get("DateSchoolOpened"),
        "directory_last_modified": last_modified,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
    }


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _year_level(value: Any) -> int | None:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else None


def haversine_km(lat: float, lon: float, other_lat: float, other_lon: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat), math.radians(other_lat)
    dp = math.radians(other_lat - lat)
    dl = math.radians(other_lon - lon)
    value = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def nearest(records: list[dict[str, Any]], lat: float, lon: float, limit: int) -> list[dict[str, Any]]:
    candidates = []
    for record in records:
        if record["latitude"] is None or record["longitude"] is None:
            continue
        item = dict(record)
        item["distance_km"] = round(haversine_km(lat, lon, item["latitude"], item["longitude"]), 3)
        candidates.append(item)
    return sorted(candidates, key=lambda item: item["distance_km"])[:limit]


def opened_since(records: list[dict[str, Any]], since: date, limit: int) -> list[dict[str, Any]]:
    selected = []
    for record in records:
        raw = str(record.get("date_opened") or "")[:10]
        try:
            opened = date.fromisoformat(raw)
        except ValueError:
            continue
        if opened >= since:
            item = dict(record)
            item["change_type"] = "opened_or_proposed_in_current_directory"
            selected.append(item)
    return sorted(selected, key=lambda item: item["date_opened"], reverse=True)[:limit]
