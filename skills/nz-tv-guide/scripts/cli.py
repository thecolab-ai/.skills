#!/usr/bin/env python3
"""NZ TV guide lightweight EPG CLI.

Self-contained stdlib wrapper around public read-only NZ TV guide sources.
No login, streaming, recording, browser automation, or third-party dependencies.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import pathlib
import re
import sys
import time
import urllib.parse
from datetime import date, datetime, time as dt_time, timedelta, timezone
from html.parser import HTMLParser
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - old Python fallback
    ZoneInfo = None  # type: ignore


SKY_GRAPH = "https://api.skyone.co.nz/exp/graph"
SKY_WEB = "https://tvguide.sky.co.nz/"
FREEVIEW_GUIDE = "https://freeviewnz.tv/whats-on/tv-guide/"
NZ_TZ_NAME = "Pacific/Auckland"
NZ = ZoneInfo(NZ_TZ_NAME) if ZoneInfo else timezone(timedelta(hours=12))

UA = os.environ.get(
    "NZ_TV_GUIDE_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)

SKY_GROUPS = {
    "all": ("4b7LA20J4iHaThwky9iVqn", "All Channels"),
    "sport": ("5P95WEpsEA6TcDMOsPmV19", "Sports"),
    "movies": ("23robtuSx9VbRD5j0iZslh", "Movies"),
    "entertainment": ("LOXeZgvmRZ6T0b9geXwgy", "Entertainment & Lifestyle"),
    "news": ("2ZuubrhJhHFsY3RaH43QS2", "News & Documentaries"),
    "kids": ("2kHaAIbt50eqGIotu6Azew", "Kids"),
    "music": ("5M4HwW3cqjzeku0EfMazEV", "Music"),
    "ppv": ("3RkCYpW5t7ZBmcgIZ0796i", "Pay-Per-View"),
}

SKY_CHANNEL_QUERY = """
query getChannelGroup($id: ID!) {
  experience(appId: TV_GUIDE_WEB) {
    channelGroup(id: $id) {
      id
      title
      channels {
        ... on LinearChannel {
          id
          title
          number
          tileImage { uri }
          __typename
        }
        __typename
      }
      __typename
    }
    appId
    __typename
  }
}
"""

SKY_SCHEDULE_QUERY = """
query getChannelGroup($id: ID!, $date: LocalDate) {
  experience(appId: TV_GUIDE_WEB) {
    channelGroup(id: $id) {
      id
      title
      channels {
        ... on LinearChannel {
          id
          title
          number
          tileImage { uri }
          slotsForDay(date: $date) {
            slots {
              id
              startMs
              endMs
              live
              programme {
                ... on Episode {
                  id
                  title
                  synopsis
                  show {
                    id
                    title
                    type
                    __typename
                  }
                  __typename
                }
                ... on Movie {
                  id
                  title
                  synopsis
                  __typename
                }
                ... on PayPerViewEventProgram {
                  id
                  title
                  synopsis
                  __typename
                }
                __typename
              }
              __typename
            }
            __typename
          }
          __typename
        }
        __typename
      }
      __typename
    }
    appId
    __typename
  }
}
"""

SPORT_KEYWORDS = {
    "rugby": ("rugby", "all blacks", "black ferns", "super rugby", "srp:", "npc", "1st xv", "six nations", "rugby championship"),
    "cricket": ("cricket", "black caps", "white ferns", "t20", "odi", "test match", "ipl", "ashes", "wpl", "bbl"),
    "football": ("football", "soccer", "premier league", "a-league", "fifa", "uefa", "champions league", "europa", "facup", "fa cup"),
    "f1": ("formula 1", "formula one", "f1", "fia formula", "grand prix", "qualifying", "sprint race"),
    "netball": ("netball", "tactix", "mystics", "pulse", "stars", "steel", "magic"),
    "basketball": ("basketball", "nba", "nbl", "rapid league", "tauihi", "wnba"),
    "nfl": ("nfl", "national football league", "super bowl"),
    "tennis": ("tennis", "roland-garros", "roland garros", "wimbledon", "us open", "australian open", "atp", "wta"),
}

GENERAL_SPORT_TERMS = tuple(sorted({term for terms in SPORT_KEYWORDS.values() for term in terms} | {
    "live coverage", "sport", "racing", "golf", "motogp", "supercars", "ufc", "mma", "boxing", "darts", "afl", "nrl",
}))

MOVIE_TERMS = ("movie", "film", "cinema", "premiere")

PROVIDERS = ("sky", "freeview", "tvnz")

_sky_channels_cache: dict[str, list[dict[str, Any]]] = {}
_sky_program_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
_freeview_cache: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]] = {}


class CliError(Exception):
    pass


def die(message: str, code: int = 1) -> None:
    print(f"nz-tv-guide: {message}", file=sys.stderr)
    raise SystemExit(code)


def nz_now() -> datetime:
    return datetime.now(NZ)


def nz_today() -> str:
    return nz_now().date().isoformat()


def valid_date(raw: str) -> str:
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD")
    return raw


def valid_hhmm(raw: str) -> str:
    try:
        datetime.strptime(raw, "%H:%M")
    except ValueError:
        raise argparse.ArgumentTypeError("expected HH:MM")
    return raw


def positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return value


def parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def request_text(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 25,
) -> str:
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req_headers = {
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "User-Agent": UA,
    }
    if headers:
        req_headers.update(headers)
    try:
        return nzfetch.fetch_text(
            url,
            timeout=timeout,
            accept="text/html,application/xhtml+xml,*/*;q=0.8",
            headers=req_headers,
        )
    except nzfetch.Blocked as e:
        raise CliError(f"network error: {e}")
    except nzfetch.FetchError as e:
        raise CliError(str(e))


def request_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 25,
) -> Any:
    raw = request_text(url, params=params, headers={"Accept": "application/json, text/plain, */*", **(headers or {})}, timeout=timeout)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise CliError(f"invalid JSON from {url}: {e}")


def clean_text(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def lower_words(*values: Any) -> str:
    return " ".join(clean_text(v).lower() for v in values if v)


def display_dt(value: datetime) -> str:
    return value.astimezone(NZ).strftime("%a %d %b %-I:%M %p")


def display_time(value: datetime) -> str:
    return value.astimezone(NZ).strftime("%-I:%M %p")


def display_range(row: dict[str, Any]) -> str:
    start = datetime.fromisoformat(row["start"])
    end = datetime.fromisoformat(row["end"])
    if start.date() == end.date():
        return f"{display_dt(start)}-{display_time(end)}"
    return f"{display_dt(start)}-{display_dt(end)}"


def iso_local(value: datetime) -> str:
    return value.astimezone(NZ).isoformat(timespec="seconds")


def sky_group_key_for_type(type_name: str | None) -> str:
    if not type_name:
        return "all"
    if type_name == "sport":
        return "sport"
    if type_name == "entertainment":
        return "entertainment"
    if type_name == "news":
        return "news"
    return "all"


def sky_graph(query: str, operation_name: str, variables: dict[str, Any]) -> Any:
    payload = request_json(
        SKY_GRAPH,
        params={
            "query": query,
            "operationName": operation_name,
            "variables": json.dumps(variables, separators=(",", ":")),
        },
        headers={"Origin": SKY_WEB.rstrip("/"), "Referer": SKY_WEB},
    )
    if isinstance(payload, dict) and payload.get("errors"):
        first = payload["errors"][0]
        raise CliError(f"sky GraphQL error: {first.get('message') or first}")
    return payload


def sky_channel_rows(group_key: str) -> list[dict[str, Any]]:
    if group_key in _sky_channels_cache:
        return _sky_channels_cache[group_key]
    group_id, group_title = SKY_GROUPS[group_key]
    payload = sky_graph(SKY_CHANNEL_QUERY, "getChannelGroup", {"id": group_id})
    group = (((payload.get("data") or {}).get("experience") or {}).get("channelGroup") or {})
    rows = []
    for ch in group.get("channels") or []:
        if not isinstance(ch, dict) or ch.get("__typename") != "LinearChannel":
            continue
        image = ch.get("tileImage") or {}
        rows.append({
            "provider": "sky",
            "id": str(ch.get("id") or ""),
            "name": clean_text(ch.get("title")),
            "number": ch.get("number"),
            "type": "sport" if group_key == "sport" else ("movies" if group_key == "movies" else ("news" if group_key == "news" else "entertainment")),
            "group": group_title,
            "image": image.get("uri") if isinstance(image, dict) else None,
            "source_url": SKY_WEB,
        })
    _sky_channels_cache[group_key] = rows
    return rows


def sky_program_rows(group_key: str, day: str) -> list[dict[str, Any]]:
    cache_key = (group_key, day)
    if cache_key in _sky_program_cache:
        return _sky_program_cache[cache_key]
    group_id, group_title = SKY_GROUPS[group_key]
    payload = sky_graph(SKY_SCHEDULE_QUERY, "getChannelGroup", {"id": group_id, "date": day})
    group = (((payload.get("data") or {}).get("experience") or {}).get("channelGroup") or {})
    rows: list[dict[str, Any]] = []
    for ch in group.get("channels") or []:
        if not isinstance(ch, dict) or ch.get("__typename") != "LinearChannel":
            continue
        channel = clean_text(ch.get("title"))
        channel_id = str(ch.get("id") or "")
        channel_number = ch.get("number")
        slots = ((ch.get("slotsForDay") or {}).get("slots") or [])
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            start_ms = slot.get("startMs")
            end_ms = slot.get("endMs")
            if start_ms is None or end_ms is None:
                continue
            programme = slot.get("programme") or {}
            show = programme.get("show") if isinstance(programme.get("show"), dict) else {}
            start = datetime.fromtimestamp(float(start_ms) / 1000, NZ)
            end = datetime.fromtimestamp(float(end_ms) / 1000, NZ)
            kind = programme.get("__typename")
            title = clean_text(programme.get("title") or (show or {}).get("title") or "Untitled")
            show_title = clean_text((show or {}).get("title"))
            category = clean_text((show or {}).get("type") or ("MOVIE" if kind == "Movie" else group_title.upper()))
            rows.append({
                "provider": "sky",
                "id": str(slot.get("id") or ""),
                "program_id": str(programme.get("id") or ""),
                "title": title,
                "show_title": show_title if show_title and show_title != title else None,
                "synopsis": clean_text(programme.get("synopsis")),
                "category": category,
                "kind": kind,
                "live": bool(slot.get("live")),
                "channel": channel,
                "channel_id": channel_id,
                "channel_number": channel_number,
                "channel_group": group_title,
                "start": iso_local(start),
                "end": iso_local(end),
                "date": start.date().isoformat(),
                "timezone": NZ_TZ_NAME,
                "source_url": SKY_WEB,
            })
    rows.sort(key=lambda r: (r["start"], int(r["channel_number"] or 9999), r["channel"]))
    _sky_program_cache[cache_key] = rows
    return rows


def class_names(attrs: list[tuple[str, str | None]]) -> set[str]:
    for key, value in attrs:
        if key == "class" and value:
            return set(value.split())
    return set()


def attr_value(attrs: list[tuple[str, str | None]], name: str) -> str | None:
    for key, value in attrs:
        if key == name:
            return value
    return None


class FreeviewGuideParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.channels: list[dict[str, Any]] = []
        self.schedules: list[list[dict[str, Any]]] = []
        self._in_channel_nav = False
        self._channel_nav_depth = 0
        self._channel: dict[str, Any] | None = None
        self._channel_capture: str | None = None
        self._channel_buffer: list[str] = []
        self._in_schedule = False
        self._schedule_depth = 0
        self._schedule: list[dict[str, Any]] | None = None
        self._item: dict[str, Any] | None = None
        self._item_depth = 0
        self._item_capture: str | None = None
        self._item_buffer: list[str] = []
        self._extra_depth = 0
        self._extra_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = class_names(attrs)
        if tag == "ul" and "channel-nav" in classes:
            self._in_channel_nav = True
            self._channel_nav_depth = 1
            return
        if self._in_channel_nav:
            self._channel_nav_depth += 1
            if tag == "li" and "channel" in classes:
                self._channel = {"provider": "freeview", "id": None, "name": None, "number": None, "source_url": None, "image": None}
            elif self._channel is not None and tag == "a" and "channel-link" in classes:
                href = attr_value(attrs, "href")
                if href:
                    self._channel["id"] = href.strip("/").split("/")[-1]
                    self._channel["source_url"] = urllib.parse.urljoin(FREEVIEW_GUIDE, href)
            elif self._channel is not None and tag == "img":
                alt = clean_text(attr_value(attrs, "alt"))
                src = attr_value(attrs, "src")
                if alt:
                    self._channel["name"] = alt
                if src:
                    self._channel["image"] = urllib.parse.urljoin(FREEVIEW_GUIDE, src)
            elif self._channel is not None and tag == "span" and "ch-number" in classes:
                self._channel_capture = "number"
                self._channel_buffer = []
            return

        if tag == "ul" and "schedule" in classes:
            self._in_schedule = True
            self._schedule_depth = 1
            self._schedule = []
            return
        if self._in_schedule:
            self._schedule_depth += 1
            if tag == "li" and "schedule-item" in classes:
                self._item = {"title": None, "time": None, "description": None}
                self._item_depth = 1
            elif self._item is not None:
                self._item_depth += 1
                if tag == "h3" and "title" in classes:
                    self._item_capture = "title"
                    self._item_buffer = []
                elif tag == "p" and "sub-title" in classes:
                    self._item_capture = "time"
                    self._item_buffer = []
                elif tag == "div" and "schedule-extra-info" in classes:
                    self._extra_depth = 1
                    self._extra_buffer = []
            return

    def handle_endtag(self, tag: str) -> None:
        if self._channel_capture and tag == "span":
            text = clean_text(" ".join(self._channel_buffer))
            if self._channel is not None and self._channel_capture == "number":
                self._channel["number"] = int(text) if text.isdigit() else text
            self._channel_capture = None
            self._channel_buffer = []

        if self._item_capture and tag in ("h3", "p"):
            text = clean_text(" ".join(self._item_buffer))
            if self._item is not None:
                self._item[self._item_capture] = text
            self._item_capture = None
            self._item_buffer = []

        if self._extra_depth:
            self._extra_depth -= 1
            if self._extra_depth == 0 and self._item is not None:
                self._item["description"] = clean_text(" ".join(self._extra_buffer))
                self._extra_buffer = []

        if self._in_channel_nav:
            if tag == "li" and self._channel is not None:
                if self._channel.get("name"):
                    channel = dict(self._channel)
                    channel["type"] = classify_channel(channel.get("name"))
                    self.channels.append(channel)
                self._channel = None
            self._channel_nav_depth -= 1
            if tag == "ul" and self._channel_nav_depth <= 0:
                self._in_channel_nav = False
            return

        if self._in_schedule:
            if self._item is not None and tag == "li":
                if self._schedule is not None and self._item.get("title"):
                    self._schedule.append(dict(self._item))
                self._item = None
                self._item_depth = 0
            self._schedule_depth -= 1
            if tag == "ul" and self._schedule_depth <= 0:
                if self._schedule is not None:
                    self.schedules.append(self._schedule)
                self._schedule = None
                self._in_schedule = False

    def handle_data(self, data: str) -> None:
        if self._channel_capture:
            self._channel_buffer.append(data)
        if self._item_capture:
            self._item_buffer.append(data)
        if self._extra_depth:
            self._extra_buffer.append(data)


def classify_channel(name: Any) -> str:
    text = lower_words(name)
    if any(x in text for x in ("sport", "espn", "trackside", "racing")):
        return "sport"
    if any(x in text for x in ("news", "parliament", "rnz", "bbc", "cnn", "al jazeera")):
        return "news"
    if any(x in text for x in ("movie", "cinema")):
        return "movies"
    return "entertainment"


def parse_freeview_range(day: str, value: str | None, *, first_crosses_from_previous_day: bool = False) -> tuple[datetime, datetime] | None:
    if not value:
        return None
    match = re.search(r"(\d{1,2}:\d{2}\s*[AP]M)\s*-\s*(\d{1,2}:\d{2}\s*[AP]M)", value, re.I)
    if not match:
        return None
    base = parse_day(day)
    start_time = datetime.strptime(match.group(1).upper().replace(" ", ""), "%I:%M%p").time()
    end_time = datetime.strptime(match.group(2).upper().replace(" ", ""), "%I:%M%p").time()
    start = datetime.combine(base, start_time, NZ)
    end = datetime.combine(base, end_time, NZ)
    if end <= start:
        if first_crosses_from_previous_day:
            start -= timedelta(days=1)
        else:
            end += timedelta(days=1)
    return start, end


def freeview_page(day: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if day in _freeview_cache:
        return _freeview_cache[day]
    d = parse_day(day)
    date_param = d.strftime("%m/%d/%Y 00:00:00")
    raw = request_text(FREEVIEW_GUIDE, params={"date": date_param, "st": ""}, headers={"Referer": FREEVIEW_GUIDE})
    parser = FreeviewGuideParser()
    parser.feed(raw)
    channels = parser.channels
    programmes: list[dict[str, Any]] = []
    for idx, channel in enumerate(channels):
        schedule = parser.schedules[idx] if idx < len(parser.schedules) else []
        for item_index, item in enumerate(schedule):
            title = clean_text(item.get("title"))
            if not title or title.lower() == "no program information":
                continue
            span = parse_freeview_range(day, item.get("time"), first_crosses_from_previous_day=item_index == 0)
            if not span:
                continue
            start, end = span
            programmes.append({
                "provider": "freeview",
                "id": f"{channel.get('id')}-{start.isoformat()}-{norm(title)}",
                "program_id": None,
                "title": title,
                "show_title": None,
                "synopsis": clean_text(item.get("description")),
                "category": classify_program(title, item.get("description")),
                "kind": "HtmlProgramme",
                "live": "live" in lower_words(title, item.get("description")),
                "channel": channel.get("name"),
                "channel_id": channel.get("id"),
                "channel_number": channel.get("number"),
                "channel_group": "Freeview",
                "start": iso_local(start),
                "end": iso_local(end),
                "date": start.date().isoformat(),
                "timezone": NZ_TZ_NAME,
                "source_url": channel.get("source_url") or FREEVIEW_GUIDE,
            })
    programmes.sort(key=lambda r: (r["start"], int(r["channel_number"] or 9999), r["channel"] or ""))
    _freeview_cache[day] = (channels, programmes)
    return channels, programmes


def tvnz_only(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        name = row.get("name") or row.get("channel") or ""
        text = norm(name)
        if text.startswith("tvnz") or "duke" in text:
            item = dict(row)
            item["provider"] = "tvnz"
            out.append(item)
    return out


def classify_program(title: Any, synopsis: Any = None) -> str:
    text = lower_words(title, synopsis)
    if any(term in text for term in GENERAL_SPORT_TERMS):
        return "SPORT"
    if any(term in text for term in MOVIE_TERMS):
        return "MOVIE"
    return "PROGRAM"


def provider_channels(provider: str, type_name: str | None = None) -> list[dict[str, Any]]:
    if provider == "sky":
        group_key = sky_group_key_for_type(type_name)
        rows = sky_channel_rows(group_key)
    elif provider in ("freeview", "tvnz"):
        channels, _ = freeview_page(nz_today())
        rows = tvnz_only(channels) if provider == "tvnz" else channels
        if type_name:
            rows = [r for r in rows if r.get("type") == type_name]
    else:
        raise CliError(f"unsupported provider: {provider}")
    return sorted(rows, key=lambda r: int(r.get("number") or 9999))


def provider_programs(provider: str, day: str, *, group_key: str | None = None) -> list[dict[str, Any]]:
    if provider == "sky":
        return sky_program_rows(group_key or "all", day)
    if provider in ("freeview", "tvnz"):
        _, rows = freeview_page(day)
        return tvnz_only(rows) if provider == "tvnz" else rows
    raise CliError(f"unsupported provider: {provider}")


def matches_channel(row: dict[str, Any], query: str) -> bool:
    q = norm(query)
    values = [row.get("channel"), row.get("name"), row.get("channel_id"), row.get("id"), row.get("channel_number"), row.get("number")]
    normalized = [norm(v) for v in values if v is not None]
    if q in normalized:
        return True
    return any(q and q in value for value in normalized)


def exact_channel_matches(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    q = norm(query)
    exact = []
    partial = []
    for row in rows:
        values = [row.get("channel"), row.get("name"), row.get("channel_id"), row.get("id"), row.get("channel_number"), row.get("number")]
        normalized = [norm(v) for v in values if v is not None]
        if q in normalized:
            exact.append(row)
        elif any(q and q in value for value in normalized):
            partial.append(row)
    return exact or partial


def infer_provider(channel: str | None, requested: str | None) -> str:
    if requested:
        return requested
    text = norm(channel or "")
    if text.startswith("tvnz") or "duke" in text or text in {"three", "bravo", "eden", "rush", "skyopen"}:
        return "freeview"
    return "sky"


def sky_group_for_channel(channel: str) -> str:
    for group_key in ("sport", "movies", "entertainment", "news", "kids", "music", "ppv", "all"):
        if exact_channel_matches(sky_channel_rows(group_key), channel):
            return group_key
    raise CliError(f"no Sky channel matching {channel!r}")


def schedule_for_channel(provider: str, channel: str, day: str) -> list[dict[str, Any]]:
    if provider == "sky":
        group_key = sky_group_for_channel(channel)
        rows = exact_channel_matches(provider_programs("sky", day, group_key=group_key), channel)
    else:
        rows = exact_channel_matches(provider_programs(provider, day), channel)
    if not rows:
        raise CliError(f"no channel matching {channel!r} for provider {provider}")
    return sorted(rows, key=lambda r: r["start"])


def row_text(row: dict[str, Any]) -> str:
    return lower_words(row.get("title"), row.get("show_title"), row.get("synopsis"), row.get("channel"), row.get("category"))


def programme_text(row: dict[str, Any]) -> str:
    return lower_words(row.get("title"), row.get("show_title"), row.get("synopsis"), row.get("category"))


def matches_query(row: dict[str, Any], query: str) -> bool:
    return norm(query) in norm(row_text(row))


def matches_sport_code(row: dict[str, Any], code: str | None) -> bool:
    text = programme_text(row)
    if not code:
        return "sport" in text or row.get("provider") == "sky" and row.get("channel_group") == "Sports" or any(term in text for term in GENERAL_SPORT_TERMS)
    return any(term in text for term in SPORT_KEYWORDS[code])


def matches_type(row: dict[str, Any], type_name: str) -> bool:
    text = programme_text(row)
    if type_name == "sport":
        return matches_sport_code(row, None)
    if type_name == "movies":
        return row.get("channel_group") == "Movies" or row.get("category") == "MOVIE" or any(term in text for term in MOVIE_TERMS)
    return True


def is_promotional_slot(row: dict[str, Any]) -> bool:
    title = clean_text(row.get("title")).lower()
    return title.startswith("coming up:")


def overlaps(row: dict[str, Any], start: datetime, end: datetime) -> bool:
    row_start = datetime.fromisoformat(row["start"])
    row_end = datetime.fromisoformat(row["end"])
    return row_start < end and row_end > start


def starts_after(row: dict[str, Any], start: datetime) -> bool:
    return datetime.fromisoformat(row["start"]) >= start


def day_range(day: str, start_hhmm: str, end_hhmm: str) -> tuple[datetime, datetime]:
    base = parse_day(day)
    start_t = datetime.strptime(start_hhmm, "%H:%M").time()
    end_t = datetime.strptime(end_hhmm, "%H:%M").time()
    start = datetime.combine(base, start_t, NZ)
    end = datetime.combine(base, end_t, NZ)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def next_days(count: int = 7) -> list[str]:
    today = nz_now().date()
    return [(today + timedelta(days=i)).isoformat() for i in range(count)]


def dedupe_programs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out = []
    for row in rows:
        key = (row.get("provider"), row.get("channel_id"), row.get("channel"), row.get("start"), row.get("end"), row.get("title"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def emit(data: Any, as_json: bool, render) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render())


def render_programs(title: str, rows: list[dict[str, Any]], *, errors: list[str] | None = None) -> str:
    lines = [f"{title}: {len(rows)}"]
    for row in rows:
        bits = [display_range(row), f"CH {row.get('channel_number')}" if row.get("channel_number") else None, row.get("channel")]
        live = " LIVE" if row.get("live") else ""
        lines.append(f"{' | '.join(str(x) for x in bits if x)}  {row.get('title')}{live}")
        if row.get("show_title"):
            lines.append(f"    {row.get('show_title')}")
    if errors:
        lines.append("")
        lines.extend(errors)
    return "\n".join(lines)


def cmd_channels(args: argparse.Namespace) -> None:
    provider = args.provider or "sky"
    rows = provider_channels(provider, args.type)
    data = {"provider": provider, "type": args.type, "count": len(rows), "channels": rows}

    def render() -> str:
        lines = [f"channels ({provider}): {len(rows)}"]
        for ch in rows:
            number = ch.get("number") if ch.get("number") is not None else "-"
            lines.append(f"{str(number):>4}  {ch.get('name')}  {ch.get('id') or '-'}  {ch.get('group') or ch.get('type') or '-'}")
        return "\n".join(lines)

    emit(data, args.json, render)


def cmd_schedule(args: argparse.Namespace) -> None:
    day = args.date or nz_today()
    provider = infer_provider(args.channel, args.provider)
    rows = schedule_for_channel(provider, args.channel, day)
    data = {"provider": provider, "channel": args.channel, "date": day, "timezone": NZ_TZ_NAME, "count": len(rows), "programmes": rows}

    def render() -> str:
        channel = rows[0].get("channel") if rows else args.channel
        return render_programs(f"{channel} on {day} ({NZ_TZ_NAME})", rows)

    emit(data, args.json, render)


def cmd_now(args: argparse.Namespace) -> None:
    provider = infer_provider(args.channel, args.provider)
    now = nz_now()
    day = now.date().isoformat()
    if args.channel:
        rows = [r for r in schedule_for_channel(provider, args.channel, day) if overlaps(r, now, now + timedelta(seconds=1))]
    else:
        group_key = "sport" if provider == "sky" else None
        rows = [r for r in provider_programs(provider, day, group_key=group_key) if overlaps(r, now, now + timedelta(seconds=1))]
    data = {"provider": provider, "channel": args.channel, "as_at": iso_local(now), "timezone": NZ_TZ_NAME, "count": len(rows), "programmes": rows}

    def render() -> str:
        label = f"now on {args.channel}" if args.channel else f"now ({provider})"
        return render_programs(label, rows)

    emit(data, args.json, render)


def cmd_next(args: argparse.Namespace) -> None:
    provider = infer_provider(args.channel, args.provider)
    now = nz_now()
    rows: list[dict[str, Any]] = []
    for day in next_days(8):
        if args.channel:
            day_rows = schedule_for_channel(provider, args.channel, day)
        else:
            day_rows = provider_programs(provider, day, group_key="sport" if provider == "sky" else None)
        rows.extend(r for r in day_rows if starts_after(r, now))
        rows = sorted(dedupe_programs(rows), key=lambda r: r["start"])[: args.limit]
        if len(rows) >= args.limit:
            break
    data = {"provider": provider, "channel": args.channel, "limit": args.limit, "timezone": NZ_TZ_NAME, "count": len(rows), "programmes": rows}

    def render() -> str:
        label = f"next on {args.channel}" if args.channel else f"next ({provider})"
        return render_programs(label, rows)

    emit(data, args.json, render)


def cmd_search(args: argparse.Namespace) -> None:
    provider = args.provider or "sky"
    days = [args.date] if args.date else next_days(8)
    now = nz_now()
    rows: list[dict[str, Any]] = []
    for day in days:
        day_rows = provider_programs(provider, day, group_key="all" if provider == "sky" else None)
        if not args.date:
            day_rows = [r for r in day_rows if datetime.fromisoformat(r["end"]) > now]
        rows.extend(r for r in day_rows if matches_query(r, args.query))
        rows = sorted(dedupe_programs(rows), key=lambda r: r["start"])[: args.limit]
        if len(rows) >= args.limit:
            break
    data = {"provider": provider, "query": args.query, "date": args.date, "limit": args.limit, "timezone": NZ_TZ_NAME, "count": len(rows), "programmes": rows}

    def render() -> str:
        return render_programs(f"search {args.query!r} ({provider})", rows)

    emit(data, args.json, render)


def cmd_sport(args: argparse.Namespace) -> None:
    provider = args.provider or "sky"
    now = nz_now()
    if args.date:
        days = [args.date]
    elif args.from_time or args.to_time:
        days = [nz_today()]
    else:
        days = next_days(8)
    rows: list[dict[str, Any]] = []
    for day in days:
        day_rows = provider_programs(provider, day, group_key="sport" if provider == "sky" else None)
        if not args.date and not args.from_time and not args.to_time:
            day_rows = [r for r in day_rows if datetime.fromisoformat(r["end"]) > now]
        if args.from_time or args.to_time:
            start, end = day_range(day, args.from_time or "00:00", args.to_time or "23:59")
            day_rows = [r for r in day_rows if overlaps(r, start, end)]
        rows.extend(r for r in day_rows if matches_sport_code(r, args.code) and not is_promotional_slot(r))
        rows = sorted(dedupe_programs(rows), key=lambda r: r["start"])[: args.limit]
        if len(rows) >= args.limit:
            break
    data = {
        "provider": provider,
        "code": args.code,
        "date": args.date,
        "from": args.from_time,
        "to": args.to_time,
        "limit": args.limit,
        "timezone": NZ_TZ_NAME,
        "count": len(rows),
        "programmes": rows,
    }

    def render() -> str:
        label = "sport"
        if args.code:
            label += f" {args.code}"
        if args.date:
            label += f" on {args.date}"
        elif args.from_time or args.to_time:
            label += f" today {args.from_time or '00:00'}-{args.to_time or '23:59'}"
        else:
            label += " upcoming"
        return render_programs(label, rows)

    emit(data, args.json, render)


def cmd_tonight(args: argparse.Namespace) -> None:
    provider = args.provider or "sky"
    day = nz_today()
    start, end = day_range(day, "19:00", "23:59")
    group_key = "sport" if args.type == "sport" and provider == "sky" else ("movies" if args.type == "movies" and provider == "sky" else None)
    rows = [r for r in provider_programs(provider, day, group_key=group_key) if overlaps(r, start, end) and matches_type(r, args.type)]
    if args.type == "sport":
        rows = [r for r in rows if not is_promotional_slot(r)]
    rows = sorted(rows, key=lambda r: (r["start"], int(r.get("channel_number") or 9999), r.get("channel") or ""))
    data = {"provider": provider, "type": args.type, "date": day, "from": "19:00", "to": "23:59", "timezone": NZ_TZ_NAME, "count": len(rows), "programmes": rows}

    def render() -> str:
        return render_programs(f"tonight {args.type} ({provider})", rows)

    emit(data, args.json, render)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lightweight NZ TV guide / EPG CLI focused on Sky Sport.")
    parser.add_argument("--version", action="version", version="nz-tv-guide 0.1.0")
    sub = parser.add_subparsers(dest="command", required=True)

    channels_p = sub.add_parser("channels", help="list channels")
    channels_p.add_argument("--provider", choices=PROVIDERS, help="guide provider, defaults to sky")
    channels_p.add_argument("--type", choices=("sport", "entertainment", "news"), help="channel type filter")
    channels_p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    channels_p.set_defaults(func=cmd_channels)

    now_p = sub.add_parser("now", help="show what is on right now")
    now_p.add_argument("--channel", help="channel name, number, or id")
    now_p.add_argument("--provider", choices=PROVIDERS, help="guide provider, inferred from channel when omitted")
    now_p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    now_p.set_defaults(func=cmd_now)

    next_p = sub.add_parser("next", help="show upcoming programmes")
    next_p.add_argument("--channel", help="channel name, number, or id")
    next_p.add_argument("--provider", choices=PROVIDERS, help="guide provider, inferred from channel when omitted")
    next_p.add_argument("--limit", type=positive_int, default=10, help="limit rows returned")
    next_p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    next_p.set_defaults(func=cmd_next)

    schedule_p = sub.add_parser("schedule", help="show a full-day schedule for a channel")
    schedule_p.add_argument("channel", help="channel name, number, or id")
    schedule_p.add_argument("--date", type=valid_date, help="schedule date YYYY-MM-DD, defaults to today in New Zealand")
    schedule_p.add_argument("--provider", choices=PROVIDERS, help="guide provider, inferred from channel when omitted")
    schedule_p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    schedule_p.set_defaults(func=cmd_schedule)

    search_p = sub.add_parser("search", help="search programmes")
    search_p.add_argument("query", help="programme, team, sport, competition, or channel text")
    search_p.add_argument("--date", type=valid_date, help="search one date YYYY-MM-DD; omitted searches upcoming days")
    search_p.add_argument("--provider", choices=PROVIDERS, help="guide provider, defaults to sky")
    search_p.add_argument("--limit", type=positive_int, default=10, help="limit rows returned")
    search_p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    search_p.set_defaults(func=cmd_search)

    sport_p = sub.add_parser("sport", help="show sport programmes")
    sport_p.add_argument("--code", choices=tuple(SPORT_KEYWORDS.keys()), help="sport code filter")
    sport_p.add_argument("--date", type=valid_date, help="search one date YYYY-MM-DD; omitted searches upcoming days")
    sport_p.add_argument("--from", dest="from_time", type=valid_hhmm, help="start time HH:MM in NZ time")
    sport_p.add_argument("--to", dest="to_time", type=valid_hhmm, help="end time HH:MM in NZ time")
    sport_p.add_argument("--provider", choices=PROVIDERS, help="guide provider, defaults to sky")
    sport_p.add_argument("--limit", type=positive_int, default=20, help="limit rows returned")
    sport_p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    sport_p.set_defaults(func=cmd_sport)

    tonight_p = sub.add_parser("tonight", help="show tonight's 7pm-late programmes")
    tonight_p.add_argument("--provider", choices=PROVIDERS, help="guide provider, defaults to sky")
    tonight_p.add_argument("--type", choices=("sport", "movies"), default="sport", help="programme type")
    tonight_p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    tonight_p.set_defaults(func=cmd_tonight)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    started = time.perf_counter()
    try:
        args.func(args)
    except CliError as e:
        die(str(e))
    finally:
        _ = started
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
