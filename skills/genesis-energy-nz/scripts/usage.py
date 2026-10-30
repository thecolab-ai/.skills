#!/usr/bin/env python3
"""Normalise only electricity interval fields and report explicit coverage."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from genesis import GenesisError

NZ = ZoneInfo("Pacific/Auckland")
HOUR = timedelta(hours=1)


def midnight(day):
    return datetime.combine(day, time(), NZ).astimezone(timezone.utc)


def date_range(start_text, end_text, today):
    try:
        start, end = date.fromisoformat(start_text), date.fromisoformat(end_text)
        if start.isoformat() != start_text or end.isoformat() != end_text:
            raise ValueError
        if end < start or (end - start).days >= 31 or end > today:
            raise ValueError
        return start, end
    except (ValueError, TypeError):
        raise GenesisError(2, "Use ISO dates YYYY-MM-DD, start <= end <= today, at most 31 inclusive days") from None


def normalise(data, start, end, now):
    """Discard every provider field except timestamp, kw and costNZD."""
    rows = {}
    lower, upper = midnight(start), midnight(end + timedelta(days=1))
    try:
        items = data["usage"]
        if not isinstance(items, list) or len(items) >= 100:
            raise ValueError
        for item in items:
            stamp = datetime.fromisoformat(item["startDate"])
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError
            stamp = stamp.astimezone(timezone.utc)
            if stamp.minute or stamp.second or stamp.microsecond or not lower <= stamp < upper:
                raise ValueError
            values = []
            for key in ("kw", "costNZD"):
                raw = item[key]
                if not isinstance(raw, (str, int, float)) or isinstance(raw, bool) or len(str(raw)) > 64:
                    raise ValueError
                value = Decimal(str(raw))
                if not value.is_finite() or abs(value) > Decimal("1000000000") or value.as_tuple().exponent < -12:
                    raise ValueError
                values.append(value)
            values = tuple(values)
            if stamp in rows and rows[stamp] != values:
                raise ValueError
            if stamp + HOUR <= now:
                rows[stamp] = values
    except (KeyError, ValueError, TypeError, AttributeError, InvalidOperation, OverflowError):
        raise GenesisError(6, "Invalid, conflicting, out-of-range or capped Genesis intervals") from None
    return rows


def fetch_usage(client, start, end, now, pause):
    """Inclusive two-date requests stay below the observed 100-row limit."""
    rows, cursor = {}, start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=1), end)
        incoming = normalise(client.electricity(cursor, chunk_end), cursor, chunk_end, now)
        rows.update(incoming)
        cursor = chunk_end + timedelta(days=1)
        if cursor <= end:
            pause(1)
    return dict(sorted(rows.items()))


def coverage(rows, start, end):
    selected = {stamp: values for stamp, values in rows.items() if midnight(start) <= stamp < midnight(end + timedelta(days=1))}
    expected = int((midnight(end + timedelta(days=1)) - midnight(start)) / HOUR)
    latest = max(selected) if selected else None
    return {
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "timezone": "Pacific/Auckland", "expected_intervals": expected,
        "received_intervals": len(selected), "missing_intervals": expected - len(selected),
        "coverage": "complete" if len(selected) == expected else "incomplete" if selected else "no_readings",
        "latest_interval_start": latest.astimezone(NZ).isoformat() if latest else None,
        "observed_usage_kwh": str(sum((v[0] for v in selected.values()), Decimal(0))) if selected else None,
        "observed_usage_cost_nzd": str(sum((v[1] for v in selected.values()), Decimal(0))) if selected else None,
    }


def records(rows, start, end, command, group="day"):
    if command == "usage":
        return [{"interval_start": stamp.astimezone(NZ).isoformat(), "usage_kwh": str(values[0]),
                 "usage_cost_nzd": str(values[1])} for stamp, values in rows.items()]
    if group == "range":
        return [coverage(rows, start, end)]
    result, cursor = [], start
    while cursor <= end:
        result.append(coverage(rows, cursor, cursor))
        cursor += timedelta(days=1)
    return result
