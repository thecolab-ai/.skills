#!/usr/bin/env python3
"""NZ cinemas lightweight showtimes CLI.

Self-contained stdlib wrapper around public read-only cinema showtime endpoints.
No login, booking mutation, browser automation, or third-party dependencies.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from typing import Any

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - old Python fallback
    ZoneInfo = None  # type: ignore


UA = os.environ.get(
    "NZ_CINEMAS_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)

EVENT_BASE = "https://www.eventcinemas.co.nz"
RIALTO_BASE = "https://www.rialto.co.nz"
HOYTS_API = "https://apim-aea.hoyts.co.nz/cinemaapi-nz-live/api"
HOYTS_WEB = "https://www.hoyts.co.nz"
READING_API = "https://prod-api.readingcinemas.com.au"
READING_WEB = "https://readingcinemas.co.nz"

ALL_CHAINS = ("event", "hoyts", "reading", "rialto")
CHAIN_CHOICES = ("event", "hoyts", "reading", "rialto", "berkley", "berkeley")


class CliError(Exception):
    pass


def die(message: str, code: int = 1) -> None:
    print(f"nz-cinemas: {message}", file=sys.stderr)
    raise SystemExit(code)


def nz_today() -> str:
    if ZoneInfo:
        return datetime.now(ZoneInfo("Pacific/Auckland")).date().isoformat()
    return datetime.now(timezone(timedelta(hours=12))).date().isoformat()


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
    req = urllib.request.Request(url, headers=req_headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        raise CliError(f"HTTP {e.code} from {url}: {raw[:300]}")
    except urllib.error.URLError as e:
        raise CliError(f"network error calling {url}: {e.reason}")


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


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def clean_text(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def abs_url(base: str, value: Any) -> str | None:
    if not value:
        return None
    return urllib.parse.urljoin(base, str(value))


def selected_chains(chain: str | None) -> list[str]:
    if not chain:
        return list(ALL_CHAINS)
    if chain == "berkeley":
        return ["berkley"]
    return [chain]


def matches_query(record: dict[str, Any], query: str | None, keys: tuple[str, ...]) -> bool:
    if not query:
        return True
    qn = norm(query)
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        if qn == norm(value) or qn in norm(value):
            return True
    for value in record.get("alternate_ids") or []:
        if qn == norm(value):
            return True
    return False


def resolve_cinemas(cinemas: list[dict[str, Any]], query: str | None) -> list[dict[str, Any]]:
    if not query:
        return cinemas
    exact = [
        c for c in cinemas
        if norm(query) in {norm(c.get("id")), norm(c.get("slug")), norm(c.get("name"))}
    ]
    if exact:
        return exact
    return [c for c in cinemas if matches_query(c, query, ("name", "slug", "id", "city", "region", "address"))]


def filter_region(cinemas: list[dict[str, Any]], region: str | None) -> list[dict[str, Any]]:
    if not region:
        return cinemas
    return [c for c in cinemas if matches_query(c, region, ("region", "city", "suburb", "address", "name"))]


class EventCinemaParser(HTMLParser):
    def __init__(self, chain: str, base: str) -> None:
        super().__init__()
        self.chain = chain
        self.base = base
        self.cinemas: list[dict[str, Any]] = []
        self._seen: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        data = {k: v for k, v in attrs if v is not None}
        cid = data.get("data-id")
        name = data.get("data-name")
        url = data.get("data-url")
        if not cid or not name or not url or cid in self._seen:
            return
        self._seen.add(cid)
        self.cinemas.append({
            "chain": self.chain,
            "id": str(cid),
            "code": data.get("data-code"),
            "name": name,
            "slug": url.rsplit("/", 1)[-1],
            "short_name": data.get("data-shortname") or None,
            "region": None,
            "city": None,
            "address": None,
            "latitude": float(data["data-lat"]) if data.get("data-lat") else None,
            "longitude": float(data["data-long"]) if data.get("data-long") else None,
            "source_url": abs_url(self.base, url),
        })


def event_config(chain: str) -> tuple[str, str]:
    if chain == "rialto":
        return RIALTO_BASE, "Rialto"
    return EVENT_BASE, "Event Cinemas"


def event_cinemas(chain: str) -> list[dict[str, Any]]:
    base, _ = event_config(chain)
    html_text = request_text(base + "/Cinemas", headers={"Referer": base + "/"})
    parser = EventCinemaParser(chain, base)
    parser.feed(html_text)
    return parser.cinemas


def event_bundle(chain: str, date: str, cinemas: list[dict[str, Any]]) -> dict[str, Any]:
    base, _ = event_config(chain)
    ids = [c["id"] for c in cinemas]
    if not ids:
        return {"Movies": [], "Dates": [], "SelectedDate": date, "CinemaIds": []}
    payload = request_json(
        base + "/Cinemas/GetSessions",
        params={"cinemaIds": ids, "date": date},
        headers={"X-Requested-With": "XMLHttpRequest", "Referer": base + "/Cinemas"},
    )
    if not isinstance(payload, dict) or not payload.get("Success"):
        raise CliError(f"{chain}: sessions endpoint returned unsuccessful response")
    return payload.get("Data") or {}


def parse_event_movies(chain: str, bundle: dict[str, Any]) -> list[dict[str, Any]]:
    base, label = event_config(chain)
    movies = []
    for m in bundle.get("Movies") or []:
        cinema_models = m.get("CinemaModels") or []
        sessions_count = sum(len(cm.get("Sessions") or []) for cm in cinema_models)
        movies.append({
            "chain": chain,
            "id": str(m.get("Id") or ""),
            "alternate_ids": [x for x in [m.get("MovieCode"), m.get("HOCode"), m.get("AbsoluteId")] if x],
            "title": m.get("Name") or "",
            "rating": m.get("Rating"),
            "runtime_minutes": m.get("RunningTime"),
            "genres": [g.get("Name") for g in (m.get("MovieGenres") or []) if isinstance(g, dict) and g.get("Name")],
            "first_session": m.get("FirstSession"),
            "last_session": m.get("LastSession"),
            "cinema_ids": [str(x) for x in (m.get("CinemaIds") or [])],
            "cinemas": [cm.get("Name") for cm in cinema_models if cm.get("Name")],
            "sessions_count": sessions_count,
            "poster_url": m.get("PosterUrl") or m.get("LargePosterUrl"),
            "source_url": abs_url(base, m.get("MovieUrl")),
            "source": label,
        })
    return movies


def parse_event_sessions(chain: str, bundle: dict[str, Any]) -> list[dict[str, Any]]:
    base, label = event_config(chain)
    sessions = []
    for m in bundle.get("Movies") or []:
        movie_id = str(m.get("Id") or "")
        for cm in m.get("CinemaModels") or []:
            for s in cm.get("Sessions") or []:
                attrs = []
                for attr in s.get("Attributes") or []:
                    if isinstance(attr, dict):
                        attrs.append(attr.get("Code") or attr.get("Name"))
                sessions.append({
                    "chain": chain,
                    "id": str(s.get("Id") or ""),
                    "movie_id": movie_id,
                    "alternate_movie_ids": [x for x in [m.get("MovieCode"), m.get("HOCode"), m.get("AbsoluteId")] if x],
                    "movie_title": m.get("Name") or "",
                    "cinema_id": str(s.get("CinemaId") or cm.get("Id") or ""),
                    "cinema_name": cm.get("Name") or "",
                    "start_time": s.get("StartTime"),
                    "date": str(s.get("StartTime") or "")[:10],
                    "screen_name": s.get("ScreenName"),
                    "screen_type": s.get("ScreenTypeName") or s.get("ScreenType"),
                    "attributes": [a for a in attrs if a],
                    "seats_available": s.get("SeatsAvailable"),
                    "booking_url": s.get("BookingUrl") or abs_url(base, f"/Orders/Tickets#sessionId={s.get('Id')}"),
                    "source": label,
                })
    return sessions


def hoyts_json(path: str) -> Any:
    return request_json(HOYTS_API + "/" + path.lstrip("/"), headers={"Origin": HOYTS_WEB, "Referer": HOYTS_WEB + "/"})


def hoyts_cinemas(chain: str = "hoyts") -> list[dict[str, Any]]:
    cinemas = []
    for c in hoyts_json("cinemas"):
        address = c.get("address") or {}
        item = {
            "chain": chain,
            "id": str(c.get("id") or ""),
            "code": c.get("loyaltyCode"),
            "name": c.get("name") or "",
            "slug": c.get("slug") or "",
            "region": address.get("city") or c.get("suburb"),
            "city": address.get("city"),
            "suburb": c.get("suburb"),
            "address": ", ".join(x for x in [c.get("street"), c.get("suburb"), address.get("city")] if x),
            "latitude": c.get("latitude"),
            "longitude": c.get("longitude"),
            "features": c.get("features") or [],
            "source_url": abs_url(HOYTS_WEB, c.get("link")),
        }
        cinemas.append(item)
    if chain == "berkley":
        cinemas = [c for c in cinemas if c["id"] == "1013" or norm(c["name"]) == "berkeleymissionbay"]
        for c in cinemas:
            c["chain"] = "berkley"
    return cinemas


def hoyts_movies(chain: str = "hoyts") -> list[dict[str, Any]]:
    movies = []
    for m in hoyts_json("movies/now-showing"):
        vista_ids = [x.strip() for x in str(m.get("vistaId") or "").split(",") if x.strip()]
        movies.append({
            "chain": chain,
            "id": str(m.get("id") or ""),
            "alternate_ids": vista_ids,
            "title": m.get("name") or "",
            "slug": m.get("slug") or "",
            "rating": (m.get("rating") or {}).get("id") if isinstance(m.get("rating"), dict) else m.get("rating"),
            "runtime_minutes": m.get("duration") or (m.get("runtime") or {}).get("minutes"),
            "genres": m.get("genres") or [],
            "first_session": None,
            "last_session": None,
            "cinema_ids": [],
            "cinemas": [],
            "sessions_count": None,
            "poster_url": abs_url("https://imgix.hoyts.com.au/", m.get("posterImage")),
            "source_url": abs_url(HOYTS_WEB, m.get("link")),
            "source": "HOYTS Berkeley" if chain == "berkley" else "HOYTS",
        })
    return movies


def hoyts_sessions(cinema_ids: list[str] | None = None, chain: str = "hoyts") -> list[dict[str, Any]]:
    raw: list[dict[str, Any]] = []
    if cinema_ids:
        for cid in cinema_ids:
            raw.extend(hoyts_json(f"sessions/{urllib.parse.quote(cid)}"))
    else:
        raw = hoyts_json("sessions")
    cinema_lookup = {c["id"]: c for c in hoyts_cinemas(chain)}
    sessions = []
    for s in raw:
        cid = str(s.get("cinemaId") or "")
        sessions.append({
            "chain": chain,
            "id": str(s.get("id") or ""),
            "movie_id": str(s.get("movieId") or ""),
            "alternate_movie_ids": [],
            "movie_title": None,
            "cinema_id": cid,
            "cinema_name": (cinema_lookup.get(cid) or {}).get("name"),
            "start_time": s.get("date"),
            "date": str(s.get("date") or "")[:10],
            "screen_name": s.get("screenName"),
            "screen_type": s.get("typeId"),
            "attributes": s.get("allTags") or s.get("originalTags") or [],
            "seats_available": None,
            "booking_url": abs_url(HOYTS_WEB, s.get("link")),
            "disabled": bool(s.get("disabled")),
            "sold_out": bool(s.get("soldOut")),
            "selling_fast": bool(s.get("sellingFast")),
            "source": "HOYTS Berkeley" if chain == "berkley" else "HOYTS",
        })
    movies = hoyts_movies(chain)
    by_vista: dict[str, dict[str, Any]] = {}
    for m in movies:
        for vid in m.get("alternate_ids") or []:
            by_vista[str(vid)] = m
    for s in sessions:
        m = by_vista.get(s["movie_id"])
        if m:
            s["movie_title"] = m["title"]
            s["alternate_movie_ids"] = [m["id"], m.get("slug"), *(m.get("alternate_ids") or [])]
    return sessions


def reading_token() -> str:
    payload = request_json(READING_API + "/settings/2", headers={"Referer": READING_WEB + "/"})
    try:
        return payload["data"]["settings"]["token"]
    except Exception as e:
        raise CliError(f"reading: could not read public settings token: {e}")


def reading_json(path: str, params: dict[str, Any] | None = None) -> Any:
    token = reading_token()
    return request_json(
        READING_API + "/" + path.lstrip("/"),
        params=params,
        headers={"Authorization": f"Bearer {token}", "Origin": READING_WEB, "Referer": READING_WEB + "/"},
    )


def reading_cinemas() -> list[dict[str, Any]]:
    cinemas = []
    for c in reading_json("getcinemas", {"countryId": "2"}):
        cinemas.append({
            "chain": "reading",
            "id": c.get("slug") or c.get("name"),
            "code": None,
            "name": c.get("name") or "",
            "slug": c.get("slug") or "",
            "region": c.get("state"),
            "city": c.get("city"),
            "suburb": c.get("city"),
            "address": ", ".join(x for x in [c.get("address"), c.get("city"), c.get("state")] if x),
            "latitude": float(c["latitude"]) if c.get("latitude") else None,
            "longitude": float(c["longitude"]) if c.get("longitude") else None,
            "features": [a.get("Title") for a in (c.get("amenities") or []) if isinstance(a, dict) and a.get("Title")],
            "source_url": abs_url(READING_WEB, f"/cinemas/{c.get('slug')}"),
        })
    return cinemas


def reading_sessions(cinema_ids: list[str] | None = None) -> list[dict[str, Any]]:
    cinemas = reading_cinemas()
    selected = [c for c in cinemas if not cinema_ids or c["id"] in cinema_ids or c["slug"] in cinema_ids]
    sessions: list[dict[str, Any]] = []
    for cinema in selected:
        raw = reading_json("films", {"countryId": "2", "cinemaId": cinema["id"], "status": "nowShowing", "sort": "true"})
        if not isinstance(raw, list):
            continue
        for s in raw:
            movie_id = str(s.get("movieId") or "")
            group_id = str(s.get("movieGroupId") or "")
            session_id = str(s.get("sessionId") or "")
            start = s.get("showDateTime")
            sessions.append({
                "chain": "reading",
                "id": session_id,
                "movie_id": movie_id,
                "alternate_movie_ids": [group_id],
                "movie_title": s.get("movieName") or "",
                "cinema_id": s.get("cinemaId") or cinema["id"],
                "cinema_name": s.get("cinemaName") or cinema["name"],
                "start_time": start,
                "date": str(start or s.get("bussinessDate") or "")[:10],
                "screen_name": s.get("screenName"),
                "screen_type": s.get("sessionAttributes"),
                "attributes": [x.strip() for x in str(s.get("sessionAttributes") or "").split(",") if x.strip()],
                "seats_available": s.get("availableSeats"),
                "booking_url": abs_url(READING_WEB, f"/cinemas/{cinema['slug']}/sessions/{session_id}/{movie_id}"),
                "rating": None,
                "runtime_minutes": int(s["movieDuration"]) if str(s.get("movieDuration") or "").isdigit() else None,
                "poster_url": abs_url("https://d2apwscfoijj3f.cloudfront.net/wpdata/images/", f"{s.get('image')}-m.jpg") if s.get("image") else None,
                "source": "Reading Cinemas",
            })
    return sessions


def reading_movies(cinema_ids: list[str] | None = None, date: str | None = None) -> list[dict[str, Any]]:
    sessions = reading_sessions(cinema_ids)
    if date:
        sessions = [s for s in sessions if s.get("date") == date]
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for s in sessions:
        key = (s.get("movie_id") or "", s.get("movie_title") or "")
        if key not in out:
            out[key] = {
                "chain": "reading",
                "id": s.get("movie_id"),
                "alternate_ids": s.get("alternate_movie_ids") or [],
                "title": s.get("movie_title"),
                "slug": None,
                "rating": s.get("rating"),
                "runtime_minutes": s.get("runtime_minutes"),
                "genres": [],
                "first_session": s.get("start_time"),
                "last_session": s.get("start_time"),
                "cinema_ids": [],
                "cinemas": [],
                "sessions_count": 0,
                "poster_url": s.get("poster_url"),
                "source_url": abs_url(READING_WEB, f"/movies/details/{s.get('cinema_id')}/{(s.get('alternate_movie_ids') or [''])[0]}"),
                "source": "Reading Cinemas",
            }
        m = out[key]
        m["sessions_count"] += 1
        if s.get("cinema_id") not in m["cinema_ids"]:
            m["cinema_ids"].append(s.get("cinema_id"))
        if s.get("cinema_name") not in m["cinemas"]:
            m["cinemas"].append(s.get("cinema_name"))
        if s.get("start_time") and (not m["first_session"] or s["start_time"] < m["first_session"]):
            m["first_session"] = s["start_time"]
        if s.get("start_time") and (not m["last_session"] or s["start_time"] > m["last_session"]):
            m["last_session"] = s["start_time"]
    return list(out.values())


def chain_cinemas(chain: str) -> list[dict[str, Any]]:
    if chain in ("event", "rialto"):
        return event_cinemas(chain)
    if chain in ("hoyts", "berkley"):
        return hoyts_cinemas(chain)
    if chain == "reading":
        return reading_cinemas()
    raise CliError(f"unsupported chain: {chain}")


def sessions_for_chain(chain: str, *, date: str, cinema: str | None) -> list[dict[str, Any]]:
    cinemas = resolve_cinemas(chain_cinemas(chain), "Berkeley Mission Bay" if chain == "berkley" and not cinema else cinema)
    if cinema and not cinemas:
        return []
    if chain in ("event", "rialto"):
        bundle = event_bundle(chain, date, cinemas)
        return parse_event_sessions(chain, bundle)
    if chain in ("hoyts", "berkley"):
        sessions = hoyts_sessions([c["id"] for c in cinemas] if cinemas else None, chain)
        return [s for s in sessions if s.get("date") == date]
    if chain == "reading":
        sessions = reading_sessions([c["id"] for c in cinemas] if cinemas else None)
        return [s for s in sessions if s.get("date") == date]
    raise CliError(f"unsupported chain: {chain}")


def movies_for_chain(chain: str, *, date: str | None, cinema: str | None) -> tuple[list[dict[str, Any]], str | None]:
    cinemas = resolve_cinemas(chain_cinemas(chain), "Berkeley Mission Bay" if chain == "berkley" and not cinema else cinema)
    if cinema and not cinemas:
        return [], date
    if chain in ("event", "rialto"):
        selected_date = date or nz_today()
        bundle = event_bundle(chain, selected_date, cinemas)
        movies = parse_event_movies(chain, bundle)
        if not movies and not date and bundle.get("Dates"):
            selected_date = str(bundle["Dates"][0])
            bundle = event_bundle(chain, selected_date, cinemas)
            movies = parse_event_movies(chain, bundle)
        return movies, selected_date
    if chain in ("hoyts", "berkley"):
        movies = hoyts_movies(chain)
        if cinemas or date:
            sessions = hoyts_sessions([c["id"] for c in cinemas] if cinemas else None, chain)
            if date:
                sessions = [s for s in sessions if s.get("date") == date]
            active_ids = {s["movie_id"] for s in sessions}
            movies = [m for m in movies if active_ids.intersection(set(m.get("alternate_ids") or []))]
            counts: dict[str, int] = {}
            cinema_names: dict[str, set[str]] = {}
            for s in sessions:
                counts[s["movie_id"]] = counts.get(s["movie_id"], 0) + 1
                cinema_names.setdefault(s["movie_id"], set()).add(s.get("cinema_name") or "")
            for m in movies:
                ids = set(m.get("alternate_ids") or [])
                m["sessions_count"] = sum(counts.get(i, 0) for i in ids)
                m["cinemas"] = sorted({name for i in ids for name in cinema_names.get(i, set()) if name})
        return movies, date
    if chain == "reading":
        movies = reading_movies([c["id"] for c in cinemas] if cinemas else None, date)
        return movies, date
    raise CliError(f"unsupported chain: {chain}")


def movie_matches_session(session: dict[str, Any], movie_id: str) -> bool:
    qn = norm(movie_id)
    values = [session.get("movie_id"), session.get("movie_title"), session.get("id")]
    values.extend(session.get("alternate_movie_ids") or [])
    return any(qn == norm(v) or (v and qn in norm(v) and len(qn) >= 4) for v in values)


def emit(data: Any, as_json: bool, render) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=False))
    else:
        print(render())


def collect(chains: list[str], strict_chain: bool, fn) -> tuple[list[Any], list[dict[str, str]]]:
    rows: list[Any] = []
    errors: list[dict[str, str]] = []
    for chain in chains:
        try:
            result = fn(chain)
            if isinstance(result, list):
                rows.extend(result)
            else:
                rows.append(result)
        except CliError as e:
            if strict_chain:
                raise
            errors.append({"chain": chain, "error": str(e)})
    return rows, errors


def cmd_cinemas(args: argparse.Namespace) -> None:
    chains = selected_chains(args.chain)
    rows, errors = collect(chains, args.chain is not None, lambda c: filter_region(chain_cinemas(c), args.region))
    rows = sorted(rows, key=lambda c: (c.get("chain") or "", c.get("name") or ""))
    data = {"count": len(rows), "chains": chains, "region": args.region, "errors": errors, "cinemas": rows}

    def render() -> str:
        lines = [f"cinemas: {len(rows)} locations"]
        for c in rows:
            bits = [c.get("city") or c.get("region"), c.get("address")]
            lines.append(f"{c['chain']:>7}  {c.get('id')}  {c.get('name')}")
            detail = " | ".join(str(x) for x in bits if x)
            if detail:
                lines.append(f"         {detail}")
        if errors:
            lines.append("")
            lines.extend(f"{e['chain']}: {e['error']}" for e in errors)
        return "\n".join(lines)

    emit(data, args.json, render)


def cmd_movies(args: argparse.Namespace) -> None:
    chains = selected_chains(args.chain)
    all_movies: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    dates_used: dict[str, str | None] = {}
    for chain in chains:
        try:
            movies, used_date = movies_for_chain(chain, date=args.date, cinema=args.cinema)
            dates_used[chain] = used_date
            all_movies.extend(movies)
        except CliError as e:
            if args.chain:
                raise
            errors.append({"chain": chain, "error": str(e)})
    if args.limit:
        all_movies = all_movies[: args.limit]
    data = {
        "count": len(all_movies),
        "chains": chains,
        "cinema": args.cinema,
        "date": args.date,
        "dates_used": dates_used,
        "errors": errors,
        "movies": all_movies,
    }

    def render() -> str:
        label = f" at {args.cinema}" if args.cinema else ""
        lines = [f"movies{label}: {len(all_movies)}"]
        for m in all_movies:
            details = []
            if m.get("rating"):
                details.append(str(m["rating"]))
            if m.get("runtime_minutes"):
                details.append(f"{m['runtime_minutes']} min")
            if m.get("sessions_count") is not None:
                details.append(f"{m['sessions_count']} sessions")
            lines.append(f"{m['chain']:>7}  {m.get('id')}  {m.get('title')}")
            if details:
                lines.append(f"         {' | '.join(details)}")
        if errors:
            lines.append("")
            lines.extend(f"{e['chain']}: {e['error']}" for e in errors)
        return "\n".join(lines)

    emit(data, args.json, render)


def cmd_sessions(args: argparse.Namespace) -> None:
    date = args.date or nz_today()
    chains = selected_chains(args.chain)
    rows, errors = collect(
        chains,
        args.chain is not None,
        lambda c: [s for s in sessions_for_chain(c, date=date, cinema=args.cinema) if movie_matches_session(s, args.movie_id)],
    )
    rows = sorted(rows, key=lambda s: (s.get("start_time") or "", s.get("chain") or ""))
    if args.limit:
        rows = rows[: args.limit]
    data = {
        "movie_id": args.movie_id,
        "date": date,
        "cinema": args.cinema,
        "count": len(rows),
        "chains": chains,
        "errors": errors,
        "sessions": rows,
    }

    def render() -> str:
        lines = [f"sessions for {args.movie_id} on {date}: {len(rows)}"]
        for s in rows:
            time_label = str(s.get("start_time") or "").replace("T", " ")
            screen = " | ".join(str(x) for x in [s.get("cinema_name"), s.get("screen_type"), s.get("screen_name")] if x)
            title = s.get("movie_title") or s.get("movie_id")
            lines.append(f"{s['chain']:>7}  {time_label}  {title}")
            if screen:
                lines.append(f"         {screen}")
        if errors:
            lines.append("")
            lines.extend(f"{e['chain']}: {e['error']}" for e in errors)
        return "\n".join(lines)

    emit(data, args.json, render)


def cmd_nowplaying(args: argparse.Namespace) -> None:
    date = args.date or nz_today()
    chains = selected_chains(args.chain)
    rows, errors = collect(chains, args.chain is not None, lambda c: sessions_for_chain(c, date=date, cinema=args.cinema))
    rows = sorted(rows, key=lambda s: (s.get("cinema_name") or "", s.get("start_time") or ""))
    if args.limit:
        rows = rows[: args.limit]
    data = {
        "date": date,
        "cinema": args.cinema,
        "count": len(rows),
        "chains": chains,
        "errors": errors,
        "sessions": rows,
    }

    def render() -> str:
        label = f" at {args.cinema}" if args.cinema else ""
        lines = [f"now playing{label} on {date}: {len(rows)} sessions"]
        for s in rows:
            time_label = str(s.get("start_time") or "").replace("T", " ")
            title = s.get("movie_title") or s.get("movie_id")
            lines.append(f"{s['chain']:>7}  {time_label}  {title}")
            lines.append(f"         {s.get('cinema_name') or s.get('cinema_id')} | {s.get('screen_type') or '-'}")
        if errors:
            lines.append("")
            lines.extend(f"{e['chain']}: {e['error']}" for e in errors)
        return "\n".join(lines)

    emit(data, args.json, render)


def positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return value


def valid_date(raw: str) -> str:
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD")
    return raw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query live NZ cinema movies, locations, and showtimes.")
    parser.add_argument("--version", action="version", version="nz-cinemas 0.1.0")
    sub = parser.add_subparsers(dest="command", required=True)

    cinemas_p = sub.add_parser("cinemas", help="list cinema locations")
    cinemas_p.add_argument("--chain", choices=CHAIN_CHOICES, help="filter chain")
    cinemas_p.add_argument("--region", help="filter by city, island, region, or address text")
    cinemas_p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    cinemas_p.set_defaults(func=cmd_cinemas)

    movies_p = sub.add_parser("movies", help="list current movies playing")
    movies_p.add_argument("--chain", choices=CHAIN_CHOICES, help="filter chain")
    movies_p.add_argument("--cinema", help="filter by cinema name, slug, or id")
    movies_p.add_argument("--date", type=valid_date, help="filter to sessions on YYYY-MM-DD where supported")
    movies_p.add_argument("--limit", type=positive_int, help="limit rows returned")
    movies_p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    movies_p.set_defaults(func=cmd_movies)

    sessions_p = sub.add_parser("sessions", help="show sessions for a movie id, title, slug, or source alternate id")
    sessions_p.add_argument("movie_id", help="movie id, title text, slug, or alternate source id")
    sessions_p.add_argument("--chain", choices=CHAIN_CHOICES, help="filter chain")
    sessions_p.add_argument("--date", type=valid_date, help="session date YYYY-MM-DD, defaults to today in New Zealand")
    sessions_p.add_argument("--cinema", help="filter by cinema name, slug, or id")
    sessions_p.add_argument("--limit", type=positive_int, help="limit rows returned")
    sessions_p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    sessions_p.set_defaults(func=cmd_sessions)

    now_p = sub.add_parser("nowplaying", help="show sessions playing on a date, optionally at a cinema")
    now_p.add_argument("--chain", choices=CHAIN_CHOICES, help="filter chain")
    now_p.add_argument("--cinema", help="filter by cinema name, slug, or id")
    now_p.add_argument("--date", type=valid_date, help="session date YYYY-MM-DD, defaults to today in New Zealand")
    now_p.add_argument("--limit", type=positive_int, help="limit rows returned")
    now_p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    now_p.set_defaults(func=cmd_nowplaying)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    started = time.perf_counter()
    try:
        args.func(args)
    except CliError as e:
        die(str(e))
    finally:
        _ = started


if __name__ == "__main__":
    main()
