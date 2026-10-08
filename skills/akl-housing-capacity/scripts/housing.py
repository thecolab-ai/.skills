"""Parsers for the observed Council and HUD workbook layouts."""
from __future__ import annotations

import unicodedata

from workbook import SchemaError, Workbook, number


def normalise(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                   if c.isalnum() and not unicodedata.combining(c))


def matches(area, query):
    return not query or normalise(query) in normalise(area)


def select_periods(records, month=None):
    if month:
        return [r for r in records if r["period"] == month]
    latest = {}
    for record in records:
        key = (record["sheet"], record["area"])
        latest[key] = max(record["period"], latest.get(key, ""))
    return [r for r in records if r["period"] == latest[(r["sheet"], r["area"])]]


COUNCIL_COLUMNS = {
    "Dwellings Consented": {
        "B": ("houses", "Houses"),
        "C": ("apartments", "Apartments"),
        "D": ("townhouses_flats_units_other", "Townhouses, flats, units, other"),
        "E": ("retirement_village_units", "Retirement village units"),
        "F": ("all_dwellings", "All dwellings consented"),
        "I": ("all_dwellings_12_month_total", "12-month rolling total (all dwellings consented)"),
        "W": ("kainga_ora_dwellings", "All KO dwellings consented"),
        "AB": ("tamaki_regeneration_dwellings", "All TRC dwellings consented"),
        "AQ": ("dwellings_inside_rub", "Dwellings inside RUB"),
        "BK": ("dwellings_in_hazard_zones", "Total dwellings consented in hazard zones"),
    },
    "Dwellings with CCCs": {
        "B": ("dwellings_with_cccs", "Dwellings with CCCs issued"),
        "C": ("cccs_12_month_total", "12 month total"),
        "F": ("consent_issued_0_to_2_years_before_ccc", "BC issued within 0-2 years"),
        "G": ("consent_issued_2_to_4_years_before_ccc", "BC issued within 2-4 years"),
        "H": ("consent_issued_4_plus_years_before_ccc", "BC issued  4+ years"),
    },
    "Residential Parcels Created": {
        "B": ("parcels_under_5000_m2", "Total Auckland"),
        "E": ("parcels_under_5000_m2_12_month_total", "12 Month Total"),
        "G": ("parcels_all_sizes", "Total Created (All Sizes)"),
        "H": ("parcels_all_sizes_12_month_total", "12 Month Total (All Sizes)"),
        "O": ("parcels_inside_rub", "Inside RUB"),
        "Q": ("parcels_outside_rub", "Outside RUB"),
    },
}


def council_records(body):
    workbook = Workbook(body)
    records = []
    for sheet, columns in COUNCIL_COLUMNS.items():
        headers_seen = False
        for _, row in workbook.rows(sheet):
            if row.get("A") == "Date":
                for column, (_, expected) in columns.items():
                    if normalise(str(row.get(column, ""))) != normalise(expected):
                        raise SchemaError(f"Changed header in {sheet}, column {column}")
                headers_seen = True
                continue
            if not headers_seen or not isinstance(row.get("A"), (int, float)):
                continue
            measures = {key: number(row.get(column)) for column, (key, _) in columns.items()}
            if all(v is None for v in measures.values()):
                continue
            records.append({"sheet": sheet, "area": "Auckland", "area_type": "region",
                            "period": workbook.month(row["A"]),
                            "unit": "parcels" if sheet == "Residential Parcels Created" else "dwellings",
                            "measures": measures})
        if not headers_seen:
            raise SchemaError(f"No Date header in {sheet}")
    sheet = "Dwellings Consented By LB"
    headers = None
    for _, row in workbook.rows(sheet):
        if row.get("A") == "Date":
            headers = {col: name for col, name in row.items()
                       if col != "A" and name != "Monthly total"}
            if not headers or not all(isinstance(v, str) for v in headers.values()):
                raise SchemaError("Changed local-board headers")
            continue
        if not headers or not isinstance(row.get("A"), (int, float)):
            continue
        for col, area in headers.items():
            value = number(row.get(col))
            if value is not None:
                records.append({"sheet": sheet, "area": area, "area_type": "local_board",
                                "period": workbook.month(row["A"]), "unit": "dwellings",
                                "measures": {"all_dwellings": value}})
    if not records or headers is None:
        raise SchemaError("No housing observations found")
    return records


def capacity_records(body):
    workbook = Workbook(body)
    sheet = "Plan-enabled Feasible x LBA"
    headers = None
    totals = None
    for _, row in workbook.rows(sheet):
        if row.get("C") == "Dwelling Value Band":
            headers = row
        if row.get("C") == "Total":
            if totals is not None:
                raise SchemaError("Ambiguous capacity totals")
            totals = row
    if headers is None or totals is None:
        raise SchemaError("Capacity headers or Total row missing")
    groups = {}
    for column, name in headers.items():
        if isinstance(name, str) and (name.endswith(" LBA") or name == "Auckland"):
            area = name.removesuffix(" LBA")
            groups.setdefault(area, []).append(number(totals.get(column)))
    if not groups or any(len(values) != 2 or any(v is None for v in values) for values in groups.values()):
        raise SchemaError("Expected paired plan-enabled and feasible capacity totals")
    return [{"area": area, "area_type": "region" if area == "Auckland" else "local_board",
             "scenario": "PC78", "model_version": "October 2023", "unit": "dwellings",
             "plan_enabled_capacity": values[0], "feasible_capacity": values[1]}
            for area, values in groups.items()]


def typology_records(body):
    workbook = Workbook(body)
    records = []
    required = {"A": "Local board", "B": "FDC_BuiltForm", "C": "Feasible capacity",
                "D": "Minimum dwelling price", "E": "Maximum dwelling price",
                "F": "Average dwelling price", "G": "Median dwelling price"}
    for sheet in ("Max_Profit", "MinDUPrice"):
        headers_seen = False
        for _, row in workbook.rows(sheet):
            if row.get("A") == "Local board":
                if any(row.get(k) != v for k, v in required.items()):
                    raise SchemaError(f"Changed feasibility headers in {sheet}")
                headers_seen = True
                continue
            if not headers_seen or not row:
                continue
            if not isinstance(row.get("A"), str) or not isinstance(row.get("B"), str):
                raise SchemaError("Invalid feasibility area or built form")
            records.append({"area": row["A"], "area_type": "local_board", "scenario": "PC78",
                            "selection": sheet, "built_form": row["B"], "unit": "dwellings",
                            "feasible_capacity": number(row.get("C")), "price_unit": "NZD",
                            "minimum_dwelling_price": number(row.get("D")),
                            "maximum_dwelling_price": number(row.get("E")),
                            "average_dwelling_price": number(row.get("F")),
                            "median_dwelling_price": number(row.get("G"))})
        if not headers_seen:
            raise SchemaError(f"No feasibility header in {sheet}")
    if not records:
        raise SchemaError("No feasibility observations found")
    return records


def hud_records(body, area="Auckland", month=None):
    workbook = Workbook(body)
    headers = None
    latest_data = ""
    records = []
    current_period = ""
    required = {"series", "area_type", "area_name", "reporting_month", "value",
                "category_1_name", "category_1_value", "category_2_name", "category_2_value"}
    for rn, row in workbook.rows("Social housing"):
        if rn == 1:
            headers = {value: col for col, value in row.items()}
            if not required <= headers.keys():
                raise SchemaError("Changed HUD social housing columns")
            continue
        if not row:
            continue
        period = workbook.month(row.get(headers["reporting_month"]))
        latest_data = max(latest_data, period)
        if row.get(headers["series"]) != "Delivery" or not matches(str(row.get(headers["area_name"], "")), area):
            continue
        if month and period != month:
            continue
        if not month:
            if period < current_period:
                continue
            if period > current_period:
                records.clear()
                current_period = period
        dimensions = []
        for index in range(1, 5):
            name = row.get(headers.get(f"category_{index}_name"))
            value = row.get(headers.get(f"category_{index}_value"))
            if name is not None:
                dimensions.append({"name": name, "value": value})
        raw_value = row.get(headers["value"])
        try:
            value = number(raw_value)
        except SchemaError:
            raise SchemaError(f"Unexpected HUD delivery value: {raw_value!r}")
        records.append({"sheet": "Social housing", "series": "Delivery", "period": period,
                        "area": row.get(headers["area_name"]), "area_type": row.get(headers["area_type"]),
                        "unit": "homes", "value": value, "dimensions": dimensions})
    if not headers or not latest_data:
        raise SchemaError("No HUD housing observations found")
    return records, latest_data
