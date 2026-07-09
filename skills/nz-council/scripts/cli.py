#!/usr/bin/env python3
"""Read-only NZ council events and recreation lookup CLI.

This is intentionally stdlib-only. It reads public pages and public JSON-like
attributes exposed by council/event websites; it never logs in, books, pays, or
submits forms.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import copy
import datetime as dt
import hashlib
import html
import json
import os
import re
import socket
import struct
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "lib"))
import nzfetch  # noqa: E402

EVENTFINDA_BASE = "https://www.eventfinda.co.nz"
AKL_LEISURE_BASE = "https://www.aucklandleisure.co.nz"
AKL_LOCATION_ENDPOINT = AKL_LEISURE_BASE + "/umbraco/surface/LocationListing/RenderLocationListing"
WLG_BASE = "https://wellington.govt.nz"
ROT_BASE = "https://www.rotorualakescouncil.nz"
ROT_AQUATIC_BASE = "https://www.clmnz.co.nz/rotorua-aquatic-centre"
NPL_BASE = "https://www.npdc.govt.nz"
NPL_COMMUNITY_POOLS_URL = NPL_BASE + "/leisure-and-culture/community-swimming-pools/"
NPL_TEAC_URL = NPL_BASE + "/leisure-and-culture/todd-energy-aquatic-centre/"
BELL_BLOCK_POOL_URL = "https://www.bellblockaquaticcentre.co.nz/"
NPR_BASE = "https://www.napier.govt.nz"
HAS_BASE = "https://www.hastingsdc.govt.nz"
HAM_POOLS_BASE = "https://www.hamiltonpools.co.nz"
HUTT_POOLS_BASE = "https://pools.huttcity.govt.nz"
PORIRUA_ARENA_BASE = "https://terauparaha-arena.co.nz"
UHUTT_H2O_BASE = "https://www.h2oxtream.com"
KAPITI_AQUATICS_BASE = "https://www.kapiticoastaquatics.co.nz"
PNCC_BASE = "https://www.pncc.govt.nz"
PNCC_SWIMMING_PATH = "/Parks-recreation/Swimming-pools"
CDP_HTTP_BASE = "http://127.0.0.1:5100"
BROWSER_MODE = False
WHG_WDC_BASE = "https://www.wdc.govt.nz"
WHG_CLM_BASE = "https://www.clmnz.co.nz"
WHG_RECREATION_URL = WHG_WDC_BASE + "/Community/Parks-and-recreation"
WHG_AQUATIC_URL = WHG_CLM_BASE + "/whangarei-aquatic-centre/"
WHG_AQUATIC_POOLS_URL = WHG_AQUATIC_URL + "pools/"
WHG_AQUATIC_CONTACT_URL = WHG_AQUATIC_URL + "contact/"
CHC_REC_BASE = "https://recandsport.ccc.govt.nz"
CHC_FILTER_ENDPOINT = CHC_REC_BASE + "/api/FilterCardData/getCentres"
CHC_HE_PUNA_BASE = "https://www.hepunataimoana.co.nz"
CHC_WHARENUI_BASE = "https://www.wharenuisportscentre.co.nz"
TGA_BASE = "https://www.tauranga.govt.nz"
TGA_POOLS_BASE = "https://www.taurangapools.co.nz"
MOUNT_HOT_POOLS_BASE = "https://www.mounthotpools.co.nz"
TGA_RECREATION_POOLS_URL = TGA_BASE + "/parks-and-recreation/swimming-pools-and-aquatic-centres"
TGA_POOL_LOCATIONS_URL = TGA_POOLS_BASE + "/about-us/locations"
TGA_CDP_ENDPOINT = CDP_HTTP_BASE
QLDC_BASE = "https://www.qldc.govt.nz"
QLDC_RECREATION_SOURCE = QLDC_BASE + "/recreation/"
QLDC_SWIM_SOURCE = QLDC_BASE + "/recreation/swim/"
DUD_BASE = "https://www.dunedin.govt.nz"
DUD_POOLS_URL = DUD_BASE + "/community-facilities/swimming-pools"
DUD_SPORTS_REVIEW_URL = DUD_BASE + "/community-facilities/parks-and-reserves/dunedin-sports-facilities-review"
NSN_BASE = "https://www.nelson.govt.nz"
TDC_BASE = "https://www.tasman.govt.nz"
CLM_BASE = "https://www.clmnz.co.nz"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146 Safari/537.36"

COUNCIL_LOCATIONS = {
    "akl": "auckland",
    "wlg": "wellington",
    "chc": "christchurch",
    "rot": "rotorua",
    "npl": "new-plymouth",
    "npr": "napier",
    "has": "hastings",
    "ham": "hamilton",
    "whg": "whangarei",
    "pmn": "palmerston-north",
    "tga": "tauranga",
    "qldc": "queenstown",
    "dud": "dunedin",
    "nsn": "nelson-region",
    "tdc": "tasman-district",
}

COUNCIL_NAMES = {
    "akl": "Auckland",
    "wlg": "Wellington",
    "chc": "Christchurch",
    "rot": "Rotorua Lakes",
    "npl": "New Plymouth",
    "npr": "Napier",
    "has": "Hastings",
    "ham": "Hamilton",
    "hutt": "Hutt City",
    "porirua": "Porirua City",
    "uhutt": "Upper Hutt City",
    "kapiti": "Kāpiti Coast",
    "whg": "Whangarei",
    "pmn": "Palmerston North",
    "tga": "Tauranga",
    "qldc": "Queenstown Lakes",
    "dud": "Dunedin",
    "nsn": "Nelson",
    "tdc": "Tasman",
}

RECREATION_COUNCILS = (
    "akl",
    "wlg",
    "chc",
    "rot",
    "npl",
    "nsn",
    "tdc",
    "npr",
    "has",
    "ham",
    "hutt",
    "porirua",
    "uhutt",
    "kapiti",
    "whg",
    "pmn",
    "tga",
    "qldc",
    "dud",
)

AKL_AREA_IDS = {
    "central": "1134",
    "east": "1138",
    "north": "1141",
    "south": "1144",
    "west": "1147",
}

AKL_FACILITY_IDS = {
    "pool": "1126",
    "gym": "1119",
}

ROT_RECREATION_SOURCE_URL = ROT_BASE + "/parks-lakes-recreation"
ROT_PARK_RESERVES_SOURCE_URL = ROT_BASE + "/parks-lakes-recreation/park-reserves"
ROT_FACILITIES: list[dict[str, Any]] = [
    {
        "name": "Rotorua Aquatic Centre",
        "id": "rotorua-aquatic-centre",
        "type": "pool",
        "facility_types": ["pool", "gym", "leisure-centre"],
        "council": "rot",
        "council_name": "Rotorua Lakes",
        "source": "rotorua-lakes-council",
        "source_url": ROT_BASE + "/parks-lakes-recreation/recreational-venues/aquatic-centre",
        "operator_source_url": ROT_AQUATIC_BASE + "/",
        "pools_source_url": ROT_AQUATIC_BASE + "/pools/",
        "contact_source_url": ROT_AQUATIC_BASE + "/contact/",
        "listing_source_url": ROT_RECREATION_SOURCE_URL,
        "address": "Kuirau Park, 18 Tarewa Rd, Rotorua 3010",
        "operator": "Community Leisure Management (CLM)",
        "status": None,
        "description": (
            "Main Rotorua aquatic centre for aquatic sports, recreation, health, fitness, "
            "leisure programmes, swimming lessons, and community use."
        ),
        "hours": [{"label": "Opening hours", "text": "Monday - Sunday: 6:00am - 9:00pm"}],
        "hours_summary": "Monday - Sunday: 6:00am - 9:00pm",
        "phone": "07 348 8833",
        "email": "racr@clmnz.co.nz",
        "features": [
            "Outdoor 50m heated pool",
            "Indoor 25m heated pool",
            "Indoor learner pool",
            "Gym",
            "Fitness classes",
            "Swim programmes",
            "Birthday party spaces",
        ],
        "availability_urls": [
            {
                "label": "Outdoor Pool Availability",
                "url": "https://clm.perfectgym.com.au/ClientPortal2/ClubZoneOccupancyCalendar/6935ad313",
            },
            {
                "label": "Indoor Pool Availability",
                "url": "https://clm.perfectgym.com.au/ClientPortal2/ClubZoneOccupancyCalendar/d905956020",
            },
        ],
        "hours_note": "Use the linked operator pages for live lane availability and programme changes.",
    },
    {
        "name": "Butcher's Pool",
        "id": "butchers-pool",
        "type": "pool",
        "facility_types": ["pool"],
        "council": "rot",
        "council_name": "Rotorua Lakes",
        "source": "rotorua-lakes-council",
        "source_url": ROT_BASE + "/parks-lakes-recreation/park-reserves/butchers-pool",
        "listing_source_url": ROT_PARK_RESERVES_SOURCE_URL,
        "address": "Broadlands Road, 1.8km south of Reporoa Village",
        "operator": "Rotorua Lakes Council",
        "status": "Unsupervised",
        "description": "Free hot mineral pool with mineral water piped from an adjacent spring.",
        "hours": None,
        "hours_summary": None,
        "hours_note": "Free public hot mineral pool; no opening hours are published on the council page.",
        "phone": None,
        "email": None,
        "features": ["Hot mineral pool", "Changing rooms", "Toilets"],
        "safety_notes": [
            "Keep your head above water to avoid amoebic meningitis risk.",
            "Pool is unsupervised.",
        ],
    },
    {
        "name": "Kuirau Park foot pools and paddling pool",
        "id": "kuirau-park-foot-pools-paddling-pool",
        "type": "pool",
        "facility_types": ["pool"],
        "council": "rot",
        "council_name": "Rotorua Lakes",
        "source": "rotorua-lakes-council",
        "source_url": ROT_BASE + "/parks-lakes-recreation/park-reserves/kuirau-park",
        "listing_source_url": ROT_PARK_RESERVES_SOURCE_URL,
        "address": "Corner of Ranolf Street and Lake Road, Rotorua",
        "operator": "Rotorua Lakes Council",
        "status": None,
        "description": "Public park facilities include geothermal foot pools and a paddling pool.",
        "hours": None,
        "hours_summary": None,
        "hours_note": "Park page lists facilities but not pool opening hours; stay on tracks around geothermal features.",
        "phone": None,
        "email": None,
        "features": ["Foot pools", "Paddling pool", "BBQs", "Picnic tables", "Playground", "Public toilets"],
    },
]

NPL_POOL_FACILITIES = [
    {
        "name": "Todd Energy Aquatic Centre",
        "id": "todd-energy-aquatic-centre",
        "aliases": ["Todd Energy", "TEAC"],
        "type": "pool",
        "council": "npl",
        "council_name": "New Plymouth",
        "source": "new-plymouth-district-council",
        "source_url": NPL_TEAC_URL,
        "listing_source_url": NPL_COMMUNITY_POOLS_URL,
        "description": "Indoor and outdoor aquatic centre at Kawaroa Park with pools, hydroslides, sauna, spa, and fitness centre.",
        "address": "8-10 Tisch Avenue, New Plymouth",
        "operator": "New Plymouth District Council",
        "status": None,
        "seasonal": False,
        "hours": [
            {"label": "Monday to Friday", "text": "5:30am - 7:15pm"},
            {"label": "Saturday and Sunday", "text": "7:00am - 6:45pm"},
        ],
        "hours_summary": "Mon-Fri 5:30am-7:15pm; Sat-Sun 7:00am-6:45pm",
        "hours_note": "Opening hours can change; verify the linked NPDC page before travel.",
        "phone": "06 759 6060",
        "email": "enquiries@npdc.govt.nz",
        "features": ["Indoor pools", "Outdoor pools", "Hydroslides", "Sauna", "Spa", "Fitness centre", "Programmes"],
    },
    {
        "name": "Methanex Bell Block Aquatic Centre",
        "id": "bell-block-pool",
        "aliases": ["Bell Block Pool", "Bell Block Swimming Pool"],
        "type": "pool",
        "council": "npl",
        "council_name": "New Plymouth",
        "source": "bell-block-aquatic-centre",
        "source_url": BELL_BLOCK_POOL_URL,
        "listing_source_url": BELL_BLOCK_POOL_URL,
        "description": "Community aquatic centre with a 25 metre six-lane indoor pool and a seasonal outdoor summer pool.",
        "address": "10 Murray Street, Bell Block",
        "operator": "Bell Block Community Pool Charitable Trust",
        "status": None,
        "seasonal": True,
        "hours": [
            {"label": "Monday to Friday", "text": "5:30am - 6:30pm"},
            {"label": "Saturday and Sunday", "text": "8:00am - 3:00pm"},
        ],
        "hours_summary": "Mon-Fri 5:30am-6:30pm; Sat-Sun 8:00am-3:00pm",
        "hours_note": "Outdoor pool is seasonal; the linked pool site asks visitors to check Facebook for schedule updates.",
        "phone": "06 755 3993",
        "email": "Poolmanager@bellblockaquaticcentre.co.nz",
        "features": ["25m six-lane indoor pool", "Seasonal outdoor pool", "Aqua aerobics", "Aquabikes", "Weekend inflatables"],
    },
    {
        "name": "Inglewood Pool",
        "id": "inglewood-pool",
        "type": "pool",
        "council": "npl",
        "council_name": "New Plymouth",
        "source": "new-plymouth-district-council",
        "source_url": NPL_COMMUNITY_POOLS_URL + "inglewood-pool/",
        "listing_source_url": NPL_COMMUNITY_POOLS_URL,
        "description": "Seasonal community pool with a six-lane outdoor pool and a toddlers' pool.",
        "address": "Corner of Elliot and Rata Streets, Inglewood",
        "operator": "New Plymouth District Council",
        "status": "Closed for the season",
        "seasonal": True,
        "hours": [],
        "hours_summary": "Closed for the season",
        "hours_note": "Seasonal 2025/26 opening hours are published on the linked NPDC page when available.",
        "phone": "06 759 6060",
        "email": "enquiries@npdc.govt.nz",
        "features": ["Six-lane outdoor pool", "Toddlers' pool"],
    },
    {
        "name": "Waitara Pool",
        "id": "waitara-pool",
        "type": "pool",
        "council": "npl",
        "council_name": "New Plymouth",
        "source": "new-plymouth-district-council",
        "source_url": NPL_COMMUNITY_POOLS_URL + "waitara-pool/",
        "listing_source_url": NPL_COMMUNITY_POOLS_URL,
        "description": "Seasonal community pool with a 33m six-lane outdoor pool, learners' pool, toddlers' pool, and deep dive pool.",
        "address": "1 Leslie Street, Waitara",
        "operator": "New Plymouth District Council",
        "status": "Closed for the season",
        "seasonal": True,
        "hours": [],
        "hours_summary": "Closed for the season",
        "hours_note": "Seasonal 2025/26 opening hours are published on the linked NPDC page when available.",
        "phone": "06 759 6060",
        "email": "enquiries@npdc.govt.nz",
        "features": ["33m six-lane outdoor pool", "Learners' pool", "Toddlers' pool", "Deep dive pool"],
    },
]

NSN_POOL_LISTING_URL = NSN_BASE + "/5community/2recreation/swimming-pools"
TDC_SWIMMING_LISTING_URL = TDC_BASE + "/my-region/recreation/beaches-and-swimming"
TDC_RECREATION_LISTING_URL = TDC_BASE + "/my-region/recreation/sport-and-recreation-centres"
NPR_AQUATIC_SOURCE_URL = NPR_BASE + "/napier/facilities/napier-aquatic-centre/"
HAS_SWIMMING_POOLS_URL = HAS_BASE + "/hastings/facilities/swimming-pools/"

STATIC_RECREATION_FACILITIES: dict[str, list[dict[str, Any]]] = {
    "npr": [
        {
            "name": "Napier Aquatic Centre",
            "aliases": ["Onekawa Aquatic Centre", "Onekawa Pools", "Te Whare Kaukau o Ahuriri"],
            "type": "pool",
            "council": "npr",
            "council_name": "Napier",
            "source": "napier-city-council",
            "source_url": NPR_AQUATIC_SOURCE_URL,
            "listing_source_url": NPR_AQUATIC_SOURCE_URL,
            "website": "http://www.napieraquatic.co.nz",
            "address": "Maadi Road, Onekawa, Napier",
            "operator": "Napier City Council",
            "status": "open year-round",
            "description": (
                "Napier's main year-round aquatic facility in Onekawa Park, with heated pools, "
                "swim school, aqua fitness, hydro slides, spa pools, and accessible pool facilities."
            ),
            "hours_note": "Open times are published by Napier Aquatic Centre; verify before travel.",
            "features": [
                "heated pools",
                "25m lap pools",
                "learners pool",
                "toddlers area",
                "spa pools",
                "hydro slides",
                "swim school",
                "aqua fitness",
            ],
        }
    ],
    "has": [
        {
            "name": "Splash Planet",
            "aliases": ["Splash Planet Theme Park"],
            "type": "water-park",
            "council": "has",
            "council_name": "Hastings",
            "source": "hastings-district-council",
            "source_url": HAS_BASE + "/hastings/facilities/splash-planet/",
            "listing_source_url": HAS_SWIMMING_POOLS_URL,
            "website": "https://www.splashplanet.co.nz/",
            "address": "1001 Grove Road, Hastings",
            "operator": "Hastings District Council",
            "status": "seasonal water park; dry Play Park weekends outside the water season",
            "description": (
                "Hastings water theme park with water slides and family attractions; HDC lists it "
                "as open each summer between mid-November and early February."
            ),
            "hours_summary": (
                "Water park operates in summer; Splash Planet Play Park opens weekends outside the "
                "water season with dry rides and playgrounds only."
            ),
            "features": [
                "water slides",
                "mini-golf",
                "Fantasyland Express train",
                "go-karts",
                "beach volleyball",
                "bumper boats",
            ],
        },
        {
            "name": "Flaxmere Pool",
            "aliases": ["Swim Heretaunga", "Swim Heretaunga Pool", "Flaxmere Aquatics Pool"],
            "type": "pool",
            "council": "has",
            "council_name": "Hastings",
            "source": "aquatics-hastings",
            "source_url": "https://www.aquaticshastings.co.nz/facilities/flaxmere-aquatics-pool",
            "listing_source_url": HAS_SWIMMING_POOLS_URL,
            "address": "Swansea Road, Flaxmere, Hastings",
            "operator": "Hastings District Council",
            "status": "open year-round",
            "description": "Two-pool heated indoor complex in Flaxmere with a 25m training pool and 15m learn-to-swim pool.",
            "hours": [
                {"label": "Monday-Thursday", "text": "6am-7pm"},
                {"label": "Friday", "text": "6am-7am and 9am-5pm"},
                {"label": "Saturday", "text": "9am-3pm"},
                {"label": "Sunday", "text": "Closed"},
            ],
            "hours_summary": "Mon-Thu 6am-7pm; Fri 6am-7am and 9am-5pm; Sat 9am-3pm; Sun closed.",
            "phone": "+64 6 879 7676",
            "email": "flaxmerepool@hdc.govt.nz",
            "features": [
                "25m training pool",
                "learn-to-swim pool",
                "recreational swimming",
                "lap swimming",
                "learn to swim",
                "AquaFit",
                "giant inflatables",
            ],
            "resource_availability_url": "https://portal.hastingsdc.govt.nz/ResourceAvailability/4",
        },
        {
            "name": "Clive War Memorial Pool",
            "aliases": ["Clive Memorial Pool", "Clive Pool"],
            "type": "pool",
            "council": "has",
            "council_name": "Hastings",
            "source": "aquatics-hastings",
            "source_url": "https://www.aquaticshastings.co.nz/facilities/clive-war-memorial-pool",
            "listing_source_url": HAS_SWIMMING_POOLS_URL,
            "address": "15 Farndon Road, Clive",
            "operator": "Hastings District Council",
            "status": "open year-round",
            "description": "Two-pool heated indoor complex at Farndon Park with a 25m training pool and learner pool.",
            "hours": [
                {"label": "Monday", "text": "6am-6:30pm"},
                {"label": "Tuesday-Thursday", "text": "6am-6pm"},
                {"label": "Friday", "text": "6am-5pm"},
                {"label": "Saturday", "text": "8:30am-3pm"},
                {"label": "Sunday", "text": "Closed"},
            ],
            "hours_summary": "Mon 6am-6:30pm; Tue-Thu 6am-6pm; Fri 6am-5pm; Sat 8:30am-3pm; Sun closed.",
            "phone": "+64 6 870 0492",
            "email": "swimmingclive@hdc.govt.nz",
            "features": [
                "25m training pool",
                "learner pool",
                "recreational swimming",
                "lap swimming",
                "learn to swim",
                "AquaFit",
                "school holiday inflatables",
            ],
        },
        {
            "name": "Havelock North Village Pool",
            "aliases": ["Village Pool", "Village Pool - Havelock North", "Havelock North Pool"],
            "type": "pool",
            "council": "has",
            "council_name": "Hastings",
            "source": "aquatics-hastings",
            "source_url": "https://www.aquaticshastings.co.nz/facilities/village-pool",
            "listing_source_url": HAS_SWIMMING_POOLS_URL,
            "address": "Havelock North Domain, Te Mata Road, Havelock North",
            "operator": "Hastings District Council",
            "status": "closed until summer 2026/7",
            "description": "Seasonal outdoor pool complex in Havelock North Village Green.",
            "hours_summary": "Closed until summer 2026/7.",
            "phone": "+64 6 877 5544",
            "email": "villagepool@hdc.govt.nz",
            "features": [
                "seasonal outdoor pools",
                "33m pool",
                "toddlers pool",
                "learners pools",
                "lap swimming",
                "BBQ hire",
            ],
        },
        {
            "name": "Frimley Pool",
            "aliases": ["Frimley Park Pool"],
            "type": "pool",
            "council": "has",
            "council_name": "Hastings",
            "source": "hastings-district-council",
            "source_url": HAS_SWIMMING_POOLS_URL,
            "listing_source_url": HAS_SWIMMING_POOLS_URL,
            "address": "503 Frimley Road, Frimley, Hastings",
            "operator": "Hastings District Council",
            "status": "closed following a September 2024 Hastings District Council decision",
            "description": "Former seasonal outdoor pool; HDC's current swimming-pools page notes the council decision to close Frimley Pool.",
            "hours_summary": "Closed.",
            "features": ["former outdoor pool", "closed"],
        },
        {
            "name": "Hawke's Bay Regional Aquatic Centre",
            "id": "hawkes-bay-regional-aquatic-centre",
            "aliases": ["Hastings Aquatic Centre", "Regional Aquatic Centre", "HB Regional Aquatic Centre"],
            "type": "aquatic-centre",
            "council": "has",
            "council_name": "Hastings",
            "source": "hawkes-bay-regional-aquatic-centre",
            "source_url": "https://www.hbaquatic.co.nz/",
            "listing_source_url": HAS_SWIMMING_POOLS_URL,
            "address": "42 Percival Road, Hastings 4120",
            "operator": "Hawke's Bay Community Fitness Centre Trust",
            "status": "open year-round",
            "description": (
                "Separate Hastings aquatic centre with a 50m Olympic pool, training pool, swim school, "
                "and hydrotherapy pools; not listed by HDC as one of its three council-run Aquatics Hastings pools."
            ),
            "hours": [
                {"label": "Monday-Friday", "text": "5:30am-8pm"},
                {"label": "Saturday-Sunday", "text": "8am-5pm"},
            ],
            "hours_summary": "Mon-Fri 5:30am-8pm; Sat-Sun 8am-5pm.",
            "phone": "+64 6 651 2324",
            "email": "reception@hbaquatic.co.nz",
            "features": [
                "50m Olympic pool",
                "training pool",
                "learn-to-swim pool",
                "hydrotherapy pools",
                "swim school",
            ],
        },
    ],
    "nsn": [
        {
            "name": "Riverside Pool",
            "id": "riverside-pool",
            "type": "pool",
            "facility_types": ["pool", "gym", "leisure-centre"],
            "council": "nsn",
            "council_name": "Nelson",
            "source": "nelson-city-council",
            "source_url": CLM_BASE + "/riverside-swimming-pool/",
            "listing_source_url": NSN_POOL_LISTING_URL,
            "address": "25 Riverside Drive, Nelson",
            "operator": "CLM",
            "description": "Council-owned indoor pool and fitness facility in central Nelson with all-year access.",
            "hours": None,
            "hours_summary": "Open all year; current hours are published on the linked CLM page.",
            "phone": "03 546 3221",
            "email": "nelsonaquatics@clmnz.co.nz",
            "features": [
                "Lane swimming",
                "Open swimming",
                "Kids swimming",
                "Spa pool",
                "Swimming lessons",
                "Fitness centre",
                "Aquafitness classes",
            ],
        },
        {
            "name": "Nayland Park Pool",
            "id": "nayland-park-pool",
            "aliases": ["nayland-pool"],
            "type": "pool",
            "facility_types": ["pool"],
            "council": "nsn",
            "council_name": "Nelson",
            "source": "nelson-city-council",
            "source_url": CLM_BASE + "/nayland-park-pool/",
            "listing_source_url": NSN_POOL_LISTING_URL,
            "address": "192 Nayland Park, Nelson",
            "operator": "CLM",
            "description": "Council-owned community summer pool in Stoke, adjacent to Nayland College.",
            "hours": None,
            "hours_summary": "Open for the summer season; current hours are published on the linked CLM page.",
            "phone": "03 547 0292",
            "email": "naylandpark@clmnz.co.nz",
            "features": [
                "50 metre lane pool",
                "Toddlers pool",
                "Teaching pool",
                "Diving boards",
            ],
        },
    ],
    "tdc": [
        {
            "name": "Richmond Aquatic Centre",
            "id": "richmond-aquatic-centre",
            "type": "pool",
            "facility_types": ["pool", "gym", "leisure-centre"],
            "council": "tdc",
            "council_name": "Tasman",
            "source": "tasman-district-council",
            "source_url": TDC_RECREATION_LISTING_URL + "/richmond-aquatic-centre",
            "listing_source_url": TDC_SWIMMING_LISTING_URL,
            "address": "161 Salisbury Road, Richmond, Nelson",
            "operator": "CLM",
            "operator_url": CLM_BASE + "/richmond/",
            "description": "Tasman public year-round aquatic and fitness centre with lane, wave, hydrotherapy, spa, tots, and learn-to-swim pools.",
            "hours": None,
            "hours_summary": "Open all year; current hours are published on the linked CLM page.",
            "phone": "03 543 9755",
            "email": "aru@clmnz.co.nz",
            "features": [
                "25m lane pool",
                "Wave pool",
                "Lazy river",
                "Spa pools",
                "Hydrotherapy pool",
                "Sauna",
                "Tots pool",
                "Learn to swim pool",
                "Fitness centre",
            ],
        },
        {
            "name": "Motueka Recreation Centre",
            "id": "motueka-recreation-centre",
            "type": "leisure-centre",
            "facility_types": ["leisure-centre", "gym"],
            "council": "tdc",
            "council_name": "Tasman",
            "source": "tasman-district-council",
            "source_url": TDC_RECREATION_LISTING_URL + "/motueka-recreation-centre",
            "listing_source_url": TDC_RECREATION_LISTING_URL,
            "address": "40 Old Wharf Road, Motueka, Tasman",
            "operator": "Sport Tasman",
            "description": "Multi-purpose recreation facility with an office space, fitness lounge, theatre facility, stadium, games room, skating rink, netball courts, and climbing wall.",
            "hours": None,
            "hours_note": "Opening details are published by the linked Tasman District Council and operator pages.",
            "phone": "03 528 8228",
            "email": "MRC@sporttasman.org.nz",
            "features": [
                "Fitness lounge",
                "Theatre facility",
                "Stadium",
                "Games room",
                "Skating rink",
                "Netball courts",
                "Climbing wall",
            ],
        },
    ],
}

HAM_MAIN_POOL_PATHS = (
    "/facilities/waterworld",
    "/facilities/gallagher-aquatic-centre",
)

HAM_PARTNER_POOLS_PATH = "/facilities/partner-pools"

DUD_POOL_PAGES = {
    "Moana Pool": {
        "url": DUD_BASE + "/community-facilities/swimming-pools/moana-pool",
        "hours_url": DUD_BASE + "/community-facilities/swimming-pools/moana-pool/moana-pool-opening-hours",
        "pools_url": DUD_BASE + "/community-facilities/swimming-pools/moana-pool/pools",
        "aliases": [],
    },
    "Te Puna o Whakaehu": {
        "url": DUD_BASE + "/community-facilities/swimming-pools/te-puna-o-whakaehu",
        "aliases": ["Mosgiel Pool"],
    },
    "Port Chalmers Pool": {
        "url": DUD_BASE + "/community-facilities/swimming-pools/port-chalmers-pool",
        "aliases": [],
    },
    "St Clair Hot Salt Water Pool": {
        "url": DUD_BASE + "/community-facilities/swimming-pools/st-clair-pool",
        "aliases": ["St Clair Pool"],
    },
}

DUD_POOL_PROP_KEYS = {
    "temperature": "temperature",
    "depth": "depth",
    "features": "features",
    "access": "access",
    "activities": "activities",
    "pool access": "pool_access",
    "slide access": "slide_access",
}

WHG_POOL_NO_COMMUNITY_NOTE = (
    "Current public Whangarei District Council pages checked for v1 expose parks, beaches, sports parks, "
    "and community facilities but no council-managed Kamo or Ruakaka community pool listing. "
    "Whangarei Aquatic Centre is the public pool/leisure-centre source currently wired."
)

WHG_FACILITIES = [
    {
        "name": "Whangarei Aquatic Centre",
        "id": "whangarei-aquatic-centre",
        "aliases": ["ASB Leisure Centre", "ASB Leisure", "Whangarei Aquatic Centre"],
        "type": "pool",
        "facility_types": ["pool", "gym", "leisure-centre"],
        "council": "whg",
        "council_name": "Whangarei",
        "source": "clmnz-whangarei-aquatic-centre",
        "source_url": WHG_AQUATIC_URL,
        "listing_source_url": WHG_RECREATION_URL,
        "operator": "Community Leisure Management",
        "address": "Ewing Road, Whangarei",
        "phone": "09 430 4072",
        "email": "whr@clmnz.co.nz",
        "description": (
            "Public aquatic and leisure centre with pool, spa, sauna, gym, swim school, "
            "kids programmes, and pool availability links."
        ),
        "hours": [
            {"label": "Pool hours", "text": "Monday-Friday 6:00am-8:00pm; Saturday-Sunday 8:00am-6:00pm"},
            {"label": "Gym hours", "text": "Monday-Friday 6:00am-8:00pm; weekends 8:00am-4:00pm"},
            {
                "label": "Public holidays",
                "text": "10:00am-6:00pm; Good Friday closed; Anzac Day 1:00pm-6:00pm",
            },
        ],
        "hours_summary": "Monday-Friday 6:00am-8:00pm; Saturday-Sunday 8:00am-6:00pm",
        "hours_note": "Pools close 15 minutes before centre closing.",
        "features": [
            "Competition Pool",
            "Wave Pool",
            "Tots Pool",
            "Hydrotherapy Pool",
            "Learn To Swim Pool",
            "Spa Pool",
            "Sauna",
            "Gym",
            "Group fitness",
            "Swim school",
        ],
        "availability_urls": [
            {
                "label": "25m Pool Lane Availability",
                "url": "https://clm.perfectgym.com.au/ClientPortal2/ClubZoneOccupancyCalendar/15e262e78",
            },
            {
                "label": "Wave Pool Availability",
                "url": "https://clm.perfectgym.com.au/ClientPortal2/ClubZoneOccupancyCalendar/08ad415711",
            },
        ],
        "source_urls": [WHG_RECREATION_URL, WHG_AQUATIC_URL, WHG_AQUATIC_POOLS_URL, WHG_AQUATIC_CONTACT_URL],
    },
]

CHC_FILTERS = {
    "pool": {
        "source_path": "/swim/pools/",
        "payload": {
            "DefaultFilters": "1347",
            "CustomFilters": [
                {"text": "Summer pool", "value": 1353, "isSelected": False},
                {"text": "Cafe", "value": 1355, "isSelected": False},
                {"text": "Steam room & sauna", "value": 1350, "isSelected": False},
                {"text": "Spa", "value": 1349, "isSelected": False},
                {"text": "Toddlers pool", "value": 1348, "isSelected": False},
                {"text": "Lane swimming", "value": 1347, "isSelected": False},
            ],
        },
    },
    "gym": {
        "source_path": "/workout/gyms/",
        "payload": {"DefaultFilters": "1346", "CustomFilters": []},
    },
    "leisure-centre": {
        "source_path": "/visit/centres/",
        "payload": {"DefaultFilters": "", "CustomFilters": []},
    },
}

CHC_REC_PHONE = "03 941 8999"
CHC_LANE_PHONE = "03 941 6446"
CHC_LANE_EMAIL = "rsebookings@ccc.govt.nz"

TGA_POOL_DETAIL_URLS = {
    "baywave-tect-aquatic": TGA_POOLS_BASE + "/public-pools/baywave",
    "greerton-aquatic-leisure-centre": TGA_POOLS_BASE + "/public-pools/greerton",
    "mount-hot-pools": MOUNT_HOT_POOLS_BASE + "/",
    "memorial-pool": TGA_POOLS_BASE + "/public-pools/memorial-pool",
    "otumoetai-pool": TGA_POOLS_BASE + "/public-pools/otumoetai-pool",
}

TGA_POOL_INFO_URLS = {
    "mount-hot-pools": MOUNT_HOT_POOLS_BASE + "/facilities/our-pools",
    "memorial-pool": TGA_POOLS_BASE + "/public-pools/memorial-pool/memorial-pool-information",
}

TGA_KIND_HINTS = {
    "baywave-tect-aquatic": {"pool", "leisure-centre", "gym"},
    "greerton-aquatic-leisure-centre": {"pool", "leisure-centre", "gym"},
    "mount-hot-pools": {"pool"},
    "memorial-pool": {"pool"},
    "otumoetai-pool": {"pool"},
}

QLDC_FACILITIES: list[dict[str, Any]] = [
    {
        "name": "Alpine Aqualand",
        "id": "alpine-aqualand",
        "type": "pool",
        "facility_types": ["pool"],
        "council": "qldc",
        "council_name": "Queenstown Lakes",
        "source": "queenstown-lakes-district-council",
        "source_url": QLDC_BASE + "/recreation/swim/alpine-aqualand/",
        "listing_source_url": QLDC_SWIM_SOURCE,
        "description": "Lap pool, leisure pool and hydroslides at Queenstown Events Centre in Frankton.",
        "address": "Joe O'Connell Drive, Frankton, Queenstown",
        "operator": "QLDC Sport and Recreation",
        "phone": "03-450-9005",
        "email": "qec@qldc.govt.nz",
        "status": None,
        "hours": [
            {"label": "Weekdays", "text": "Pools and changing rooms 6.00am-9.00pm; hydroslides 4.00pm-6.30pm"},
            {"label": "Saturdays and Sundays", "text": "Pools and changing rooms 8.00am-6.00pm; hydroslides 10.30am-4.00pm"},
            {"label": "School holidays", "text": "Pools as normal; hydroslides 10.30am-4.00pm"},
            {"label": "Public holidays", "text": "Pools and changing rooms 8.00am-8.00pm; hydroslides 10.30am-6.30pm"},
            {"label": "ANZAC Day", "text": "Pools and changing rooms 1.00pm-8.00pm; hydroslides 1.00pm-6.30pm"},
            {"label": "Christmas Day and New Year's Day", "text": "Closed"},
        ],
        "hours_summary": "Weekdays pools 6.00am-9.00pm; weekends 8.00am-6.00pm; public holidays 8.00am-8.00pm.",
        "features": ["Lap pool", "Leisure pool", "Hydroslides", "Swim school", "Lane availability and bookings"],
    },
    {
        "name": "Wānaka Recreation Centre",
        "id": "wanaka-recreation-centre",
        "type": "leisure-centre",
        "facility_types": ["pool", "leisure-centre"],
        "council": "qldc",
        "council_name": "Queenstown Lakes",
        "source": "queenstown-lakes-district-council",
        "source_url": QLDC_BASE + "/recreation/wanaka-recreation-centre/",
        "listing_source_url": QLDC_RECREATION_SOURCE,
        "description": "Three-pool complex with lap, leisure and hot pools, plus courts and sport programmes.",
        "address": "41 Sir Tim Wallis Drive (off Ballantyne Road), Wānaka",
        "operator": "QLDC Sport and Recreation",
        "phone": "03-443-9334",
        "email": "wrc@qldc.govt.nz",
        "status": None,
        "hours": [
            {"label": "Weekdays", "text": "6.00am-9.00pm"},
            {"label": "Saturdays and Sundays", "text": "8.00am-8.00pm; stadium 8.00am-8.00pm; pool 8.00am-6.00pm"},
            {"label": "Public holidays", "text": "8.00am-8.00pm"},
            {"label": "ANZAC Day", "text": "1.00pm-8.00pm"},
            {"label": "Christmas Day and New Year's Day", "text": "Closed"},
        ],
        "hours_summary": "Weekdays 6.00am-9.00pm; weekends 8.00am-8.00pm, with pool hours listed as 8.00am-6.00pm.",
        "features": ["Lap pool", "Leisure pool", "Hot pool", "Courts", "Stadium", "Swim school"],
    },
    {
        "name": "Arrowtown Memorial Pool",
        "id": "arrowtown-memorial-pool",
        "type": "pool",
        "facility_types": ["pool"],
        "council": "qldc",
        "council_name": "Queenstown Lakes",
        "source": "queenstown-lakes-district-council",
        "source_url": QLDC_BASE + "/recreation/swim/arrowtown-memorial-pool/",
        "listing_source_url": QLDC_SWIM_SOURCE,
        "description": "Seasonal heated outdoor pool in historic Arrowtown.",
        "address": "4 Hertford Street, Arrowtown 9302",
        "operator": "QLDC Sport and Recreation",
        "phone": "03-442-0145",
        "email": None,
        "status": "Seasonal outdoor pool; check the linked QLDC page before travel.",
        "hours": [
            {"label": "Normal summer season", "text": "11.00am-6.00pm daily"},
            {"label": "Christmas Day and New Year's Day", "text": "Closed"},
        ],
        "hours_summary": "Seasonal summer pool; normal opening hours 11.00am-6.00pm daily.",
        "features": ["Heated outdoor pool", "Lane bookings", "Summer season passes"],
    },
    {
        "name": "Glenorchy Community Pool",
        "id": "glenorchy-community-pool",
        "type": "pool",
        "facility_types": ["pool"],
        "council": "qldc",
        "council_name": "Queenstown Lakes",
        "source": "queenstown-lakes-district-council",
        "source_url": QLDC_SWIM_SOURCE,
        "listing_source_url": QLDC_SWIM_SOURCE,
        "description": "Community pool listed by QLDC as grant-assisted.",
        "address": "Cantire Street, Glenorchy",
        "operator": "Community pool",
        "phone": None,
        "email": None,
        "status": "Community-operated; QLDC lists grant support rather than direct operation.",
        "hours": [{"label": "Season", "text": "Open Labour weekend until Easter weekend"}],
        "hours_summary": "Open Labour weekend until Easter weekend.",
        "features": ["Community pool"],
    },
    {
        "name": "Hāwea Community Pool",
        "id": "hawea-community-pool",
        "type": "pool",
        "facility_types": ["pool"],
        "council": "qldc",
        "council_name": "Queenstown Lakes",
        "source": "queenstown-lakes-district-council",
        "source_url": QLDC_SWIM_SOURCE,
        "listing_source_url": QLDC_SWIM_SOURCE,
        "description": "Community pool listed by QLDC as grant-assisted.",
        "address": "Hāwea Flat School, Camp Hill Road",
        "operator": "Community pool",
        "phone": None,
        "email": None,
        "status": "Community-operated; weather permitting.",
        "hours": [{"label": "Season", "text": "Open Labour weekend until early March; weather permitting"}],
        "hours_summary": "Open Labour weekend until early March; weather permitting.",
        "features": ["Community pool"],
    },
    {
        "name": "Queenstown Events Centre",
        "id": "queenstown-events-centre",
        "type": "leisure-centre",
        "facility_types": ["leisure-centre"],
        "council": "qldc",
        "council_name": "Queenstown Lakes",
        "source": "queenstown-lakes-district-council",
        "source_url": QLDC_BASE + "/recreation/queenstown-events-centre/",
        "listing_source_url": QLDC_RECREATION_SOURCE,
        "description": "Multi-purpose indoor sports and events centre with aquatic, gym, court, field, climbing and golf facilities.",
        "address": "Joe O'Connell Drive, Frankton, Queenstown",
        "operator": "QLDC Sport and Recreation",
        "phone": "03-450-9005",
        "email": "qec@qldc.govt.nz",
        "status": None,
        "hours": None,
        "hours_summary": None,
        "features": ["Alpine Aqualand", "Alpine Health and Fitness", "Indoor courts", "Outdoor fields", "Rockatipu Climbing Wall", "Frankton Golf Centre"],
    },
    {
        "name": "Alpine Health and Fitness",
        "id": "alpine-health-and-fitness",
        "type": "gym",
        "facility_types": ["gym"],
        "council": "qldc",
        "council_name": "Queenstown Lakes",
        "source": "queenstown-lakes-district-council",
        "source_url": QLDC_BASE + "/recreation/queenstown-events-centre/gym-group-fitness/",
        "listing_source_url": QLDC_BASE + "/recreation/queenstown-events-centre/",
        "description": "Full-service gym at Queenstown Events Centre with weights, cycle studio and group fitness studio.",
        "address": "Joe O'Connell Drive, Frankton, Queenstown",
        "operator": "QLDC Sport and Recreation",
        "phone": "03-450-9005",
        "email": "qec@qldc.govt.nz",
        "status": None,
        "hours": None,
        "hours_summary": None,
        "features": ["Weights", "Cycle studio", "Group fitness studio"],
    },
    {
        "name": "Paetara Aspiring Central",
        "id": "paetara-aspiring-central",
        "type": "leisure-centre",
        "facility_types": ["leisure-centre"],
        "council": "qldc",
        "council_name": "Queenstown Lakes",
        "source": "queenstown-lakes-district-council",
        "source_url": QLDC_BASE + "/recreation/paetara-aspiring-central/",
        "listing_source_url": QLDC_RECREATION_SOURCE,
        "description": "Community recreation space with two multi-use indoor courts, a studio, and community areas.",
        "address": "35 Plantation Road, Wānaka",
        "operator": "QLDC Sport and Recreation",
        "phone": "03-450-1721",
        "email": "pac@qldc.govt.nz",
        "status": None,
        "hours": [
            {"label": "Sunday", "text": "Closed"},
            {"label": "Monday-Friday", "text": "9.00am-9.00pm"},
            {"label": "Saturday", "text": "9.00am-3.00pm"},
        ],
        "hours_summary": "Monday-Friday 9.00am-9.00pm; Saturday 9.00am-3.00pm; Sunday closed.",
        "features": ["Two multi-use indoor courts", "Studio", "Community space", "Kahu Youth", "Aspiring Gymsports"],
    },
]

EVENT_TYPES = {
    "Event",
    "BusinessEvent",
    "ChildrensEvent",
    "ComedyEvent",
    "CourseInstance",
    "DanceEvent",
    "DeliveryEvent",
    "EducationEvent",
    "ExhibitionEvent",
    "Festival",
    "FoodEvent",
    "LiteraryEvent",
    "MusicEvent",
    "PublicationEvent",
    "SaleEvent",
    "ScreeningEvent",
    "SocialEvent",
    "SportsEvent",
    "TheaterEvent",
    "VisualArtsEvent",
}

REGIONAL_LISTING_URLS = {
    "hutt": HUTT_POOLS_BASE + "/our-pools",
    "porirua": PORIRUA_ARENA_BASE + "/aquatics/",
    "uhutt": UHUTT_H2O_BASE + "/Facility/hours-and-prices",
    "kapiti": KAPITI_AQUATICS_BASE + "/our-pools/",
}

REGIONAL_POOL_CATALOG: dict[str, list[dict[str, Any]]] = {
    "hutt": [
        {
            "name": "Huia Pool + Fitness",
            "aliases": ["Huia Pool"],
            "id": "huia-pool-fitness",
            "type": "pool",
            "council": "hutt",
            "council_name": "Hutt City",
            "source": "hutt-city-pools-and-fitness",
            "source_url": HUTT_POOLS_BASE + "/our-pools/huia-pool",
            "listing_source_url": REGIONAL_LISTING_URLS["hutt"],
            "description": "Year-round central Lower Hutt aquatic and fitness facility, home of Swim City.",
            "address": "Huia Street, Lower Hutt",
            "phone": "04 570 6655",
            "email": None,
            "contact": {"phone": "04 570 6655 (Pool); 04 560 1053 (Fitness Suite)", "email": None},
            "hours_summary": "Main pool and spa: Mon 5:30am-8pm, Tue 5:30am-6:30pm, Wed-Thu 5:30am-8pm, Fri 5:30am-7pm, Sat-Sun 8am-6pm, public holidays 9am-6pm.",
            "hours": [
                {"label": "Main pool and spa pool", "text": "Mon 5:30am-8pm; Tue 5:30am-6:30pm; Wed-Thu 5:30am-8pm; Fri 5:30am-7pm; Sat-Sun 8am-6pm; public holidays 9am-6pm."},
                {"label": "Children's pool", "text": "Mon 8am-8pm; Tue 8am-6:15pm; Wed-Thu 8am-8pm; Fri 8am-7pm; Sat-Sun 8am-6pm; public holidays 9am-6pm."},
                {"label": "Hydro pool", "text": "Varies around programmes; generally weekday morning/afternoon/evening blocks and Sat-Sun 1pm-6pm."},
            ],
            "features": ["25m main pool with movable floor", "spa pool", "children's pool", "hydrotherapy pool", "sauna", "fitness suite", "family change rooms"],
            "pool_details": [
                {"name": "Main pool and spa pool", "description": "25m main pool with a movable floor and ladder access for lane swimming, aquatic sport, aquajogging and recreation."},
                {"name": "Children's pool", "description": "Kids pool heated to about 31C with ramp access, for recreational swimming by children under 10."},
                {"name": "Hydro pool", "description": "25m hydrotherapy pool heated to about 32.5-33C, with therapy bench, 15m ramp and hoist."},
            ],
        },
        {
            "name": "Te Ngaengae Pool + Fitness",
            "aliases": ["Naenae Pool", "Naenae Pool and Fitness", "Te Ngaengae Pool"],
            "id": "te-ngaengae-pool-fitness",
            "type": "pool",
            "council": "hutt",
            "council_name": "Hutt City",
            "source": "hutt-city-pools-and-fitness",
            "source_url": HUTT_POOLS_BASE + "/our-pools/te-ngaengae-pool",
            "listing_source_url": REGIONAL_LISTING_URLS["hutt"],
            "description": "Naenae aquatic and fitness centre with a 50m pool, leisure/kids pool and hydroslides.",
            "address": "12 Everest Avenue, Naenae",
            "phone": "04 567 5043",
            "email": None,
            "contact": {"phone": "04 567 5043 (Pool); 04 567 5431 (Fitness)", "email": None},
            "hours_summary": "Main pool: Mon-Tue 5:30am-6:30pm, Wed term-dependent, Thu-Fri 5:30am-8pm, Sat-Sun 8am-6pm, public holidays 9am-6pm.",
            "hours": [
                {"label": "Main pool", "text": "Mon-Tue 5:30am-6:30pm; Wed varies by term and school holidays; Thu-Fri 5:30am-8pm; Sat-Sun 8am-6pm; public holidays 9am-6pm."},
                {"label": "Kids pool", "text": "Mon-Tue 7am-6pm; Wed-Fri 7am-8pm; Sat-Sun 8am-6pm; public holidays 9am-6pm."},
                {"label": "Zoom Tubes", "text": "Term weekdays 4pm-6pm; weekends, public holidays and school holidays 11:30am-5:30pm."},
            ],
            "features": ["50m main pool", "two hydroslides", "kids pool", "fitness centre", "pool-side party room", "movable bulkheads", "family change rooms"],
            "pool_details": [
                {"name": "Main pool", "description": "50m pool with two moveable bulkheads for flexible lane and event layouts."},
                {"name": "Kids pool", "description": "Family-friendly leisure pool for recreational use and younger swimmers."},
                {"name": "Zoom Tubes", "description": "Hydroslides with published operating blocks and height/weight rules."},
            ],
        },
        {
            "name": "Stokes Valley Pool + Fitness",
            "aliases": ["Stokes Valley Pool"],
            "id": "stokes-valley-pool-fitness",
            "type": "pool",
            "council": "hutt",
            "council_name": "Hutt City",
            "source": "hutt-city-pools-and-fitness",
            "source_url": HUTT_POOLS_BASE + "/our-pools/stokes-valley-pool",
            "listing_source_url": REGIONAL_LISTING_URLS["hutt"],
            "description": "Small year-round indoor pool and fitness facility with outdoor recreation space.",
            "address": "Bowers Street, Stokes Valley",
            "phone": "04 562 9030",
            "email": None,
            "contact": {"phone": "04 562 9030 (Pool + Fitness)", "email": None},
            "hours_summary": "Main pool: Mon 6am-7pm, Tue 6am-8pm, Wed 6am-3:30pm, Thu-Fri 6am-8pm, Sat 9am-6pm, Sun 10am-6pm, public holidays 10am-6pm.",
            "hours": [
                {"label": "Main pool", "text": "Mon 6am-7pm; Tue 6am-8pm; Wed 6am-3:30pm; Thu-Fri 6am-8pm; Sat 9am-6pm; Sun 10am-6pm; public holidays 10am-6pm."},
                {"label": "Learners pool", "text": "Mon 6am-6pm; Tue 6am-8pm; Wed 6am-6:30pm; Thu 6am-3:15pm; Fri 6am-8pm; Sat 9am-6pm; Sun/public holidays 10am-6pm."},
            ],
            "features": ["25m indoor pool", "learners pool", "sauna", "fitness suite", "BBQ", "family change rooms"],
            "pool_details": [
                {"name": "Main pool", "description": "25m indoor pool with ramp access through the learners pool and facilities for people with disabilities."},
                {"name": "Learners pool", "description": "Learners pool with ramp access; space can be limited during school bookings."},
            ],
        },
        {
            "name": "McKenzie Baths Summer Pool",
            "aliases": ["McKenzie Baths", "McKenzie Baths Pool"],
            "id": "mckenzie-baths-summer-pool",
            "type": "pool",
            "council": "hutt",
            "council_name": "Hutt City",
            "source": "hutt-city-pools-and-fitness",
            "source_url": HUTT_POOLS_BASE + "/our-pools/mckenzie-baths-summer-pool",
            "listing_source_url": REGIONAL_LISTING_URLS["hutt"],
            "description": "Historic heated summer pool opposite Petone Recreation Ground.",
            "address": "79 Udy Street, Petone",
            "phone": "04 568 6563",
            "email": None,
            "contact": {"phone": "04 568 6563 (Nov-Mar); 04 570 6655 (Apr-Oct)", "email": None},
            "status": "Summer season facility; 2025-26 season listed as 15 November 2025 to 8 March 2026.",
            "hours_summary": "Seasonal. 26 Jan-8 Mar 2026: Mon-Fri noon-6pm, Sat-Sun/public holidays 11am-6pm.",
            "hours": [
                {"label": "15 Nov-21 Dec", "text": "Mon-Fri noon-6pm; Sat-Sun 11am-6pm."},
                {"label": "5-25 Jan", "text": "Mon-Wed 11am-7pm; Thu 11am-6pm; Fri 11am-7pm; Sat-Sun/public holidays 11am-6pm."},
                {"label": "26 Jan-8 Mar 2026", "text": "Mon-Fri noon-6pm; Sat-Sun/public holidays 11am-6pm."},
            ],
            "features": ["25m heated outdoor main pool", "learners pool", "toddler play area", "splash pad", "Splash Zone", "after-hours hire"],
            "pool_details": [
                {"name": "Main pool", "description": "25m heated pool with built-in access ramp, used for lanes, aquajogging, school programmes and recreation."},
                {"name": "Learners pool", "description": "Space for children under 10 or non-swimmers, lessons and recreational play."},
                {"name": "Splash Pad", "description": "Interactive water play area."},
            ],
        },
    ],
    "porirua": [
        {
            "name": "Arena Aquatic Centre",
            "aliases": ["Arena Aquatics", "Te Rauparaha Arena Aquatics"],
            "id": "arena-aquatic-centre",
            "type": "pool",
            "council": "porirua",
            "council_name": "Porirua City",
            "source": "te-rauparaha-arena",
            "source_url": PORIRUA_ARENA_BASE + "/aquatics/visit-arena-pool/",
            "listing_source_url": REGIONAL_LISTING_URLS["porirua"],
            "description": "Indoor heated aquatic centre at Te Rauparaha Arena.",
            "address": "Te Rauparaha Arena Aquatics, 17 Parumoana Street, Porirua",
            "phone": "04 237 1521",
            "email": "aquaticsbooking@poriruacity.govt.nz",
            "contact": {"phone": "(04) 237 1521", "email": "aquaticsbooking@poriruacity.govt.nz"},
            "hours_summary": "Mon-Fri 5:30am-9pm; Sat-Sun/public holidays 8am-7pm; Anzac Day noon-7pm. Last pool entry 30 minutes before close.",
            "hours": [
                {"label": "Arena Aquatics", "text": "Mon-Fri 5:30am-9pm; Sat-Sun 8am-7pm; public holidays 8am-7pm; Anzac Day noon-7pm."},
            ],
            "features": ["lane pool", "leisure pool", "toddlers pool", "lazy river", "wave pool", "hydroslide", "spa pools", "sauna", "steam room", "cafe"],
            "pool_details": [
                {"name": "Aquatic centre", "description": "Indoor heated facility with lane pool, leisure pool, toddlers pool, lazy river, wave pool, hydroslide, spa pools, sauna and steam room."},
                {"name": "Lane availability", "description": "Regular term bookings are published separately; call customer services for live lane availability."},
            ],
        },
    ],
    "uhutt": [
        {
            "name": "H2O Xtream Aquatic Centre",
            "aliases": ["H2O Xtream", "H₂O Xtream"],
            "id": "h2o-xtream-aquatic-centre",
            "type": "pool",
            "council": "uhutt",
            "council_name": "Upper Hutt City",
            "source": "h2o-xtream",
            "source_url": UHUTT_H2O_BASE + "/Facility/hours-and-prices",
            "listing_source_url": REGIONAL_LISTING_URLS["uhutt"],
            "description": "Upper Hutt aquatic centre with lane swimming, wave/leisure areas, slides and wellness spaces.",
            "address": "26 Brown Street, Upper Hutt",
            "phone": "04 527 2113",
            "email": "h2oxtream@uhcc.govt.nz",
            "contact": {"phone": "(04) 527 2113", "email": "h2oxtream@uhcc.govt.nz"},
            "hours_summary": "Mon-Fri 5:30am-9pm; Sat 8am-7pm; Sun 8am-6:30pm; Women's Only Swim Night Sun 7pm-9pm; most public holidays 8am-7pm.",
            "hours": [
                {"label": "Standard opening hours", "text": "Mon-Fri 5:30am-9pm; Sat 8am-7pm; Sun 8am-6:30pm; Women's Only Swim Night Sun 7pm-9pm."},
                {"label": "Public holidays", "text": "Most public holidays 8am-7pm; Anzac Day noon-7pm; Christmas Day closed."},
            ],
            "features": ["25m lane pool", "leisure pool", "wave pool", "rapid river ride", "hydroslides", "junior leisure area", "spa", "sauna", "steam room"],
            "pool_details": [
                {"name": "Lane pool", "description": "25m lane pool for lane swimming and fitness swimming."},
                {"name": "Leisure pool", "description": "Wave Pool and Rapid River Ride; wave pool reaches 1.8m and rapid river is 1.2m."},
                {"name": "Junior Leisure Area", "description": "Splash pad, mini playground and slide, toddler pool and junior play pool for young children."},
                {"name": "Spa, steam and sauna", "description": "Spa pool around 38.5-39.5C plus cedar sauna and steam room for users over 16."},
            ],
        },
    ],
    "kapiti": [
        {
            "name": "Coastlands Aquatic Centre",
            "aliases": ["Coastlands Pool"],
            "id": "coastlands-aquatic-centre",
            "type": "pool",
            "council": "kapiti",
            "council_name": "Kāpiti Coast",
            "source": "kapiti-coast-aquatics",
            "source_url": KAPITI_AQUATICS_BASE + "/our-pools/coastlands-aquatic-centre/",
            "listing_source_url": REGIONAL_LISTING_URLS["kapiti"],
            "description": "Paraparaumu aquatic centre with lane, programmes and leisure facilities.",
            "address": "10 Brett Ambler Way, Paraparaumu, Kāpiti Coast",
            "phone": "04 296 4746",
            "email": "swim@kapiticoast.govt.nz",
            "contact": {"phone": "04 296 4746", "email": "swim@kapiticoast.govt.nz"},
            "hours_summary": "Mon/Wed/Thu/Fri 5:30am-9pm; Tue 5:30am-8pm; weekends 8am-8pm, with some programme-pool closures for lessons.",
            "hours": [
                {"label": "Opening hours", "text": "Mon 5:30am-9pm; Tue 5:30am-8pm; Wed-Fri 5:30am-9pm; weekends 8am-8pm."},
                {"label": "Notes", "text": "Programmes pool has lesson closures; all pools and spa must be vacated 15 minutes before closing."},
            ],
            "features": ["25 x 25m lane pool", "programmes pool", "toddler pool", "hydroslide", "Te Manu Rere flying fox", "spa", "sauna", "cafe", "meeting room"],
            "pool_details": [
                {"name": "Main pool", "description": "25 x 25m lane pool with moveable floor, heated to about 28C, with removable ramp access."},
                {"name": "Programmes pool", "description": "Smaller 1.2m-deep pool with ramp access, heated to about 32C for lessons, hydrotherapy-style activities and SPLASH sessions."},
                {"name": "Toddler pool", "description": "Toddler pool with water features and waterfall wall."},
            ],
        },
        {
            "name": "Waikanae Pool",
            "aliases": ["Waikanae Outdoor Pool"],
            "id": "waikanae-pool",
            "type": "pool",
            "council": "kapiti",
            "council_name": "Kāpiti Coast",
            "source": "kapiti-coast-aquatics",
            "source_url": KAPITI_AQUATICS_BASE + "/our-pools/waikanae-pool/",
            "listing_source_url": REGIONAL_LISTING_URLS["kapiti"],
            "description": "Seasonal outdoor summer pool in Waikanae.",
            "address": "52 Ngarara Road, Waikanae, Kāpiti Coast",
            "phone": "04 296 4789",
            "email": "swim@kapiticoast.govt.nz",
            "contact": {"phone": "04 296 4789", "email": "swim@kapiticoast.govt.nz"},
            "status": "Closed for the season as listed on the public page; summer season hours are published for next opening.",
            "hours_summary": "Seasonal. Summer hours: Mon/Thu 6am-6pm (8pm school holidays), Tue/Wed/Fri 6am-8pm, Sat-Sun 8am-8pm.",
            "hours": [
                {"label": "Summer season", "text": "Mon 6am-6pm (8pm school holidays); Tue-Wed 6am-8pm; Thu 6am-6pm (8pm school holidays); Fri 6am-8pm; Sat-Sun 8am-8pm."},
            ],
            "features": ["33.5m outdoor heated main pool", "toddler pool", "hydroslide", "BBQ bookings", "gazebo bookings", "general store", "swim shop"],
            "pool_details": [
                {"name": "Main pool", "description": "33.5m outdoor heated pool, heated to about 29C, for lane swimming, learn to swim, AquaFit and SPLASH."},
                {"name": "Toddler pool", "description": "Warm outdoor toddler pool heated to about 32C with shade sails."},
                {"name": "Hydroslide", "description": "Can be opened on request; use rules vary by age."},
            ],
        },
        {
            "name": "Ōtaki Pool",
            "aliases": ["Otaki Pool"],
            "id": "otaki-pool",
            "type": "pool",
            "council": "kapiti",
            "council_name": "Kāpiti Coast",
            "source": "kapiti-coast-aquatics",
            "source_url": KAPITI_AQUATICS_BASE + "/our-pools/otaki-pool/",
            "listing_source_url": REGIONAL_LISTING_URLS["kapiti"],
            "description": "Haruātai Park aquatic facility for swimming, programmes and SPLASH sessions.",
            "address": "Haruātai Park, 200 Mill Road, Ōtaki, Kāpiti Coast",
            "phone": "06 364 5542",
            "email": "swim@kapiticoast.govt.nz",
            "contact": {"phone": "06 364 5542", "email": "swim@kapiticoast.govt.nz"},
            "hours_summary": "Mon/Wed/Thu/Fri 5:30am-8pm; Tue 5:30am-7pm; Sat 8am-6pm; Sun 8am-4:30pm.",
            "hours": [
                {"label": "Opening hours", "text": "Mon 5:30am-8pm; Tue 5:30am-7pm; Wed-Fri 5:30am-8pm; Sat 8am-6pm; Sun 8am-4:30pm."},
                {"label": "Notes", "text": "All pools and spa must be vacated 15 minutes before closing; spa closes at 6pm Tuesdays and Fridays for cleaning."},
            ],
            "features": ["33.5m lane pool", "toddler pool", "spa", "sauna", "Te Mania Auheke slippery slope", "splashpad", "swim shop"],
            "pool_details": [
                {"name": "Main pool", "description": "33.5m lane pool with removable ramp and hoist access; at least three public lanes when bookings/programmes are in the main pool."},
                {"name": "Toddler pool", "description": "Toddler pool for babies and young children."},
                {"name": "Spa and sauna", "description": "Adult-only spa heated to about 38C, plus sauna; both restricted to 16+ years."},
            ],
        },
    ],
}


class BrowserUnavailableError(RuntimeError):
    """Raised when --browser is requested but CloakBrowser is unavailable."""


class BrowserBlockedError(RuntimeError):
    """Raised when --browser reaches a public-page challenge or unusable page."""


def die(message: str, code: int = 1) -> None:
    print(f"nz-council: {message}", file=sys.stderr)
    raise SystemExit(code)


def resolve_url(url_or_path: str, base: str = "") -> str:
    if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
        return url_or_path
    if base:
        return urllib.parse.urljoin(base, url_or_path)
    die(f"relative URL without base: {url_or_path}")


def fetch_text_result(
    url_or_path: str,
    base: str = "",
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    allow_http_error: bool = False,
) -> tuple[str | None, str, int | None, str | None]:
    url = resolve_url(url_or_path, base)

    # MIGRATED onto the shared nzfetch helper in LEAN-headers mode
    # (browser_headers=False). These public-page HTML fetches (Eventfinda
    # listings, Auckland Leisure pool/facility pages, etc.) are served REAL 200
    # content to a minimal request but a bot-wall CHALLENGE to nzfetch's full
    # Client-Hint / Sec-Fetch-* header set — so we send only the lean
    # UA + Accept + language + encoding set (equivalent to the bare urllib request
    # this replaced) while gaining nzfetch's rotating-proxy fallback. expect_json
    # is forced False so a real HTML page (even with application/json in Accept)
    # is never mis-read as a JSON challenge. On a genuine block nzfetch raises
    # Blocked; we surface it as a network error (never a hard die here) so the
    # SAME downstream bot-wall / CDP / CloakBrowser fallback the old urllib
    # challenge/HTTPError routed into (fetch_text_with_cdp / fetch_dud_text /
    # try_fetch_live_page) still handles it. The JSON POST path (fetch_json_post)
    # also goes through nzfetch; the CDP browser-control calls to 127.0.0.1:5100
    # stay on urllib (localhost, never proxied).
    accept = "text/html,application/xhtml+xml,application/json"
    req_headers = {
        "Accept": accept,
    }
    if headers:
        req_headers.update(headers)
    try:
        body_bytes, _ct, final_url = nzfetch.fetch_bytes(
            url,
            timeout=timeout,
            accept=accept,
            headers=req_headers,
            browser_headers=False,
            expect_json=False,
        )
    except nzfetch.Blocked as e:
        # Transient bot-block — route to the skill's own bot-wall / CDP /
        # CloakBrowser fallback exactly as the old urllib challenge/HTTPError did.
        return None, url, None, f"network error calling {url}: {e}"
    except nzfetch.FetchError as e:
        return None, url, None, str(e)
    body = body_bytes.decode("utf-8", "replace")
    return body, final_url, 200, None


def fetch_text(url_or_path: str, base: str = "", headers: dict[str, str] | None = None, timeout: int = 30) -> tuple[str, str, int]:
    body, final_url, status, error = fetch_text_result(url_or_path, base, headers, timeout)
    if error:
        die(error)
    return body or "", final_url, status or 0


def fetch_json_post(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None, timeout: int = 30) -> tuple[Any, str, int]:
    # Routed through the shared nzfetch helper (browser UA + rotating-proxy retry
    # on a bot-block). This is a JSON API, so nzfetch's HTML-challenge detection
    # does not misfire on real responses.
    req_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if headers:
        req_headers.update(headers)
    data = json.dumps(payload).encode("utf-8")
    try:
        body_bytes, _ct, final_url = nzfetch.fetch_bytes(
            url,
            timeout=timeout,
            accept="application/json",
            headers=req_headers,
            data=data,
            method="POST",
        )
    except nzfetch.Blocked as e:
        die(f"network error calling {url}: {e}")
    except nzfetch.FetchError as e:
        die(str(e))
    body = body_bytes.decode("utf-8", "replace")
    try:
        return json.loads(body), final_url, 200
    except json.JSONDecodeError as exc:
        die(f"invalid JSON from {url}: {exc}")


def looks_bot_walled(page_html: str) -> bool:
    text = (strip_tags(page_html) + " " + page_html).lower()
    markers = (
        "incapsula",
        "imperva",
        "cloudflare",
        "checking your browser",
        "enable javascript and cookies",
        "access denied",
        "bot detection",
        "captcha",
    )
    return any(marker in text for marker in markers)


def read_http_response(sock: socket.socket, marker: bytes = b"\r\n\r\n") -> bytes:
    chunks: list[bytes] = []
    data = b""
    while marker not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        data = b"".join(chunks)
    return data


class WebSocket:
    def __init__(self, ws_url: str, timeout: int = 20):
        parsed = urllib.parse.urlparse(ws_url)
        if parsed.scheme != "ws":
            raise RuntimeError(f"unsupported CDP websocket scheme: {parsed.scheme}")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode("ascii"))
        response = read_http_response(self.sock)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError("CDP websocket handshake failed")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def send_json(self, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        header = bytearray([0x81])
        if len(raw) < 126:
            header.append(0x80 | len(raw))
        elif len(raw) < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", len(raw)))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", len(raw)))
        mask = os.urandom(4)
        header.extend(mask)
        header.extend(b ^ mask[i % 4] for i, b in enumerate(raw))
        self.sock.sendall(header)

    def recv_json(self) -> dict[str, Any]:
        while True:
            first = self._recv_exact(2)
            opcode = first[0] & 0x0F
            masked = bool(first[1] & 0x80)
            length = first[1] & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if masked else b""
            payload = bytearray(self._recv_exact(length))
            if masked:
                for i in range(len(payload)):
                    payload[i] ^= mask[i % 4]
            if opcode == 8:
                raise RuntimeError("CDP websocket closed")
            if opcode in (1, 2):
                return json.loads(payload.decode("utf-8", "replace"))

    def _recv_exact(self, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise RuntimeError("CDP websocket closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)


def cdp_call(ws: WebSocket, message_id: int, method: str, params: dict[str, Any] | None = None, timeout: int = 20) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": message_id, "method": method}
    if params is not None:
        payload["params"] = params
    ws.send_json(payload)
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = ws.recv_json()
        if msg.get("id") != message_id:
            continue
        if msg.get("error"):
            raise RuntimeError(f"CDP {method} failed: {msg['error']}")
        return msg.get("result") or {}
    raise RuntimeError(f"timed out waiting for CDP {method}")


def fetch_text_cdp(url: str, endpoint: str = TGA_CDP_ENDPOINT, timeout: int = 25) -> str:
    endpoint = endpoint.rstrip("/")
    new_url = endpoint + "/json/new?" + urllib.parse.quote(url, safe=":/?&=%")
    req = urllib.request.Request(new_url, method="PUT", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=5) as resp:
        target = json.loads(resp.read().decode("utf-8", "replace"))
    ws_url = target.get("webSocketDebuggerUrl")
    if not ws_url:
        raise RuntimeError("CDP target did not expose a websocket URL")
    ws = WebSocket(ws_url, timeout=timeout)
    try:
        message_id = 1
        for method in ("Page.enable", "Runtime.enable"):
            cdp_call(ws, message_id, method)
            message_id += 1
        cdp_call(ws, message_id, "Page.navigate", {"url": url})
        message_id += 1
        for _ in range(20):
            time.sleep(0.5)
            result = cdp_call(
                ws,
                message_id,
                "Runtime.evaluate",
                {"expression": "document.readyState", "returnByValue": True},
            )
            message_id += 1
            value = ((result.get("result") or {}).get("value") or "").lower()
            if value == "complete":
                break
        result = cdp_call(
            ws,
            message_id,
            "Runtime.evaluate",
            {"expression": "document.documentElement.outerHTML", "returnByValue": True},
        )
        value = (result.get("result") or {}).get("value")
        if not isinstance(value, str) or not value:
            raise RuntimeError("CDP returned empty page HTML")
        return value
    finally:
        ws.close()
        target_id = target.get("id")
        if target_id:
            close_url = endpoint + "/json/close/" + urllib.parse.quote(str(target_id))
            try:
                urllib.request.urlopen(urllib.request.Request(close_url, headers={"User-Agent": UA}), timeout=3).read()
            except Exception:
                pass



def fetch_text_cloakbrowser(url: str, timeout_ms: int = 90000) -> str:
    try:
        from cloakbrowser import launch
    except Exception as exc:  # pragma: no cover - optional host dependency
        raise BrowserUnavailableError(
            "cloakbrowser_not_installed: install CloakBrowser to use --browser for nz-council public pages."
        ) from exc

    browser = None
    try:
        browser = launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            timezone="Pacific/Auckland",
            locale="en-NZ",
        )
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        html_text = page.content()
        if is_bot_wall(html_text):
            raise BrowserBlockedError("browser_blocked: browser reached bot-wall/challenge page")
        if is_missing_page(html_text):
            raise BrowserBlockedError("browser_blocked: browser returned missing-page HTML")
        return html_text
    finally:
        if browser is not None:
            browser.close()


def fetch_text_browser_or_cdp(url: str, *, cdp_timeout: int = 8) -> str | None:
    if BROWSER_MODE:
        try:
            return fetch_text_cloakbrowser(url)
        except BrowserBlockedError:
            return None
    return fetch_text_via_cdp(url, timeout=cdp_timeout)


def fetch_text_with_cdp(url_or_path: str, base: str = "", headers: dict[str, str] | None = None, timeout: int = 30) -> tuple[str, str, int]:
    body, final_url, status, error = fetch_text_result(url_or_path, base, headers=headers, timeout=timeout, allow_http_error=True)
    body = body or ""
    status = status or 0
    if status >= 400 and not looks_bot_walled(body):
        message = strip_tags(body)[:240] or "HTTP error"
        die(f"HTTP {status} from {final_url}: {message}")
    if error or status >= 400 or looks_bot_walled(body):
        try:
            body = fetch_text_cloakbrowser(final_url) if BROWSER_MODE else fetch_text_cdp(final_url)
        except BrowserUnavailableError:
            raise
        except BrowserBlockedError:
            raise
        except Exception as exc:
            fallback = "CloakBrowser --browser" if BROWSER_MODE else f"CDP fallback at {TGA_CDP_ENDPOINT}"
            die(f"direct fetch looked bot-walled and {fallback} failed: {exc}")
    return body, final_url, status


def strip_tags(value: str, br: str = " ") -> str:
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<br\s*/?>", br, value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip(" |;\t\r\n")


def attr(tag: str, name: str) -> str | None:
    m = re.search(rf"\b{name}\s*=\s*(['\"])(.*?)\1", tag, flags=re.I | re.S)
    return html.unescape(m.group(2)) if m else None


def absolutize(url: str | None, base: str) -> str | None:
    if not url:
        return None
    return urllib.parse.urljoin(base, html.unescape(url))


def meta_content(page_html: str, key: str) -> str | None:
    for m in re.finditer(r"<meta\s+([^>]+)>", page_html, flags=re.I | re.S):
        tag = m.group(1)
        name = (attr(tag, "name") or attr(tag, "property") or "").lower()
        if name == key.lower():
            content = attr(tag, "content")
            return html.unescape(content).strip() if content else None
    return None


def slug_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", html.unescape(value).lower())
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def is_bot_wall(page_html: str | None) -> bool:
    if not page_html:
        return False
    lowered = page_html.lower()
    return any(
        marker in lowered
        for marker in (
            "just a moment...",
            "cf_chl",
            "challenge-platform",
            "enable javascript and cookies",
        )
    )


def is_missing_page(page_html: str | None) -> bool:
    if not page_html:
        return True
    title_m = re.search(r"<title[^>]*>(.*?)</title>", page_html, flags=re.I | re.S)
    title = strip_tags(title_m.group(1)).lower() if title_m else ""
    return "404" in title or "page not found" in title or "content error" in title


def cdp_json(path: str, method: str = "GET", timeout: int = 3) -> dict[str, Any] | None:
    try:
        req = urllib.request.Request(CDP_HTTP_BASE + path, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None


def ws_read_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise OSError("websocket closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def ws_connect(ws_url: str, timeout: int = 5) -> socket.socket:
    parsed = urllib.parse.urlparse(ws_url)
    if parsed.scheme != "ws" or not parsed.hostname or not parsed.port:
        raise OSError(f"unsupported CDP websocket URL: {ws_url}")
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    sock = socket.create_connection((parsed.hostname, parsed.port), timeout=timeout)
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {parsed.hostname}:{parsed.port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(request.encode("ascii"))
    response = b""
    while b"\r\n\r\n" not in response:
        response += sock.recv(4096)
        if len(response) > 65536:
            raise OSError("websocket handshake too large")
    if b" 101 " not in response.split(b"\r\n", 1)[0]:
        raise OSError("websocket handshake failed")
    return sock


def ws_send(sock: socket.socket, payload: str, opcode: int = 1) -> None:
    data = payload.encode("utf-8")
    header = bytearray([0x80 | opcode])
    if len(data) < 126:
        header.append(0x80 | len(data))
    elif len(data) < 65536:
        header.extend([0x80 | 126, (len(data) >> 8) & 0xFF, len(data) & 0xFF])
    else:
        header.append(0x80 | 127)
        header.extend(len(data).to_bytes(8, "big"))
    mask = os.urandom(4)
    masked = bytes(byte ^ mask[idx % 4] for idx, byte in enumerate(data))
    sock.sendall(bytes(header) + mask + masked)


def ws_recv(sock: socket.socket) -> str:
    while True:
        first, second = ws_read_exact(sock, 2)
        opcode = first & 0x0F
        length = second & 0x7F
        masked = bool(second & 0x80)
        if length == 126:
            length = int.from_bytes(ws_read_exact(sock, 2), "big")
        elif length == 127:
            length = int.from_bytes(ws_read_exact(sock, 8), "big")
        mask = ws_read_exact(sock, 4) if masked else b""
        payload = ws_read_exact(sock, length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[idx % 4] for idx, byte in enumerate(payload))
        if opcode == 8:
            raise OSError("websocket closed")
        if opcode == 9:
            ws_send(sock, payload.decode("utf-8", "replace"), opcode=10)
            continue
        if opcode in (1, 2, 0):
            return payload.decode("utf-8", "replace")


def fetch_text_via_cdp(url: str, timeout: int = 8) -> str | None:
    target_id = None
    sock: socket.socket | None = None
    try:
        encoded_url = urllib.parse.quote(url, safe="")
        target = cdp_json("/json/new?" + encoded_url, method="PUT")
        if not target or not target.get("webSocketDebuggerUrl"):
            return None
        target_id = target.get("id")
        sock = ws_connect(str(target["webSocketDebuggerUrl"]))
        msg_id = 0

        def call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            nonlocal msg_id
            msg_id += 1
            ws_send(sock, json.dumps({"id": msg_id, "method": method, "params": params or {}}))
            while True:
                message = json.loads(ws_recv(sock))
                if message.get("id") == msg_id:
                    return message

        call("Page.enable")
        call("Runtime.enable")
        call("Page.navigate", {"url": url})
        deadline = time.time() + timeout
        best_html = None
        while time.time() < deadline:
            ready_response = call(
                "Runtime.evaluate",
                {
                    "expression": "document.readyState",
                    "returnByValue": True,
                },
            )
            ready_result = ready_response.get("result", {}).get("result", {})
            ready_state = ready_result.get("value") if isinstance(ready_result, dict) else None
            response = call(
                "Runtime.evaluate",
                {
                    "expression": "document.documentElement ? document.documentElement.outerHTML : ''",
                    "returnByValue": True,
                },
            )
            result = response.get("result", {}).get("result", {})
            value = result.get("value") if isinstance(result, dict) else None
            if isinstance(value, str) and value:
                best_html = value
                if ready_state in {"interactive", "complete"} and not is_bot_wall(value) and not is_missing_page(value):
                    return value
            time.sleep(0.5)
        return best_html
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None
    finally:
        if sock:
            try:
                sock.close()
            except OSError:
                pass
        if target_id:
            cdp_json("/json/close/" + urllib.parse.quote(str(target_id), safe=""), method="GET")


def try_fetch_live_page(url: str, use_cdp: bool = True) -> tuple[str | None, str, int | None, str]:
    body, final_url, status, error = fetch_text_result(url)
    if body and (status is None or status < 400) and not is_bot_wall(body) and not is_missing_page(body):
        return body, final_url, status, "direct"
    if use_cdp and ((body and is_bot_wall(body)) or error or (status is not None and status >= 400)):
        cdp_body = fetch_text_browser_or_cdp(final_url)
        method = "browser" if BROWSER_MODE else "cdp"
        if cdp_body and not is_bot_wall(cdp_body) and not is_missing_page(cdp_body):
            return cdp_body, final_url, 200, method
        if BROWSER_MODE:
            return None, final_url, status, "browser_blocked"
    if error:
        return None, final_url, status, error
    if body and is_bot_wall(body):
        return None, final_url, status, "bot-wall"
    return None, final_url, status, "missing-page"


def source_probe(url: str) -> dict[str, Any]:
    _, final_url, status, method = try_fetch_live_page(url)
    ok = method in {"direct", "cdp", "browser"}
    return {"ok": ok, "method": method, "status": status, "url": final_url}


def compact_text(value: str) -> str:
    value = re.sub(r"\s+;\s*", "; ", value)
    value = re.sub(r":\s*;\s*", ": ", value)
    value = re.sub(r"(;\s*){2,}", "; ", value)
    return value.strip(" ;")


def dedupe_strings(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.lower()
        if not value or key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def parse_date_arg(value: str | None, label: str) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        die(f"{label} must be an ISO date like 2026-05-24")


def parse_event_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    cleaned = value.strip()
    # Eventfinda often uses +1200; fromisoformat expects +12:00.
    cleaned = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", cleaned)
    try:
        return dt.datetime.fromisoformat(cleaned).date()
    except ValueError:
        try:
            return dt.date.fromisoformat(cleaned[:10])
        except ValueError:
            return None


def json_ld_objects(page_html: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page_html, flags=re.I | re.S):
        raw = html.unescape(m.group(1)).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            out.extend(x for x in parsed if isinstance(x, dict))
        elif isinstance(parsed, dict):
            out.append(parsed)
    return out


def eventfinda_list_path(council: str | None, category: str | None, page: int) -> str:
    location = COUNCIL_LOCATIONS.get(council or "", "new-zealand")
    if category:
        bits = [urllib.parse.quote(category.strip("/")), "events", urllib.parse.quote(location)]
    else:
        bits = ["whatson", "events", urllib.parse.quote(location)]
    path = "/" + "/".join(bits)
    if page > 1:
        path += "?page=" + str(page)
    return path


def eventfinda_cards(page_html: str) -> list[dict[str, Any]]:
    starts = [m.start() for m in re.finditer(r'<div\s+class="card\s+h-event\b', page_html, flags=re.I)]
    cards: list[dict[str, Any]] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else min(len(page_html), start + 9000)
        block = page_html[start:end]
        title_m = re.search(r'<h2[^>]*class="[^"]*p-summary[^"]*"[^>]*>\s*<a\s+([^>]+)>(.*?)</a>', block, flags=re.I | re.S)
        if not title_m:
            continue
        href = attr(title_m.group(1), "href")
        title = strip_tags(title_m.group(2))
        if not href or not title:
            continue
        id_m = re.search(r'_efC\(\s*\d+\s*,\s*(\d+)\s*\)', block)
        loc_m = re.search(r'<p[^>]*class="[^"]*meta-location[^"]*"[^>]*>(.*?)</p>', block, flags=re.I | re.S)
        date_title_m = re.search(r'<span\s+class="value-title"\s+title="([^"]+)"', block, flags=re.I)
        date_display_m = re.search(r'<span\s+class="value-title"\s+title="[^"]+"\s*>\s*(.*?)\s*</span>', block, flags=re.I | re.S)
        category_m = re.search(r'<span\s+class="category"[^>]*>(.*?)</span>', block, flags=re.I | re.S)
        img_m = re.search(r'<img\s+([^>]+)>', block, flags=re.I | re.S)
        badge_texts = [strip_tags(x) for x in re.findall(r'<span[^>]*class="[^"]*badge[^"]*"[^>]*>(.*?)</span>', block, flags=re.I | re.S)]
        cards.append(
            {
                "id": href,
                "eventfinda_id": id_m.group(1) if id_m else None,
                "title": title,
                "url": absolutize(href, EVENTFINDA_BASE),
                "location": strip_tags(loc_m.group(1)) if loc_m else None,
                "start": html.unescape(date_title_m.group(1)) if date_title_m else None,
                "date_text": strip_tags(date_display_m.group(1)) if date_display_m else None,
                "category": strip_tags(category_m.group(1)) if category_m else None,
                "image": absolutize(attr(img_m.group(1), "src") or attr(img_m.group(1), "data-src"), EVENTFINDA_BASE) if img_m else None,
                "badges": [b for b in badge_texts if b],
                "source": "eventfinda",
            }
        )
    return cards


def cmd_events(args: argparse.Namespace) -> None:
    date_from = parse_date_arg(args.date_from, "--from")
    date_to = parse_date_arg(args.date_to, "--to")
    if date_from and date_to and date_to < date_from:
        die("--to must be on or after --from")

    started = time.perf_counter()
    events: list[dict[str, Any]] = []
    source_urls: list[str] = []
    max_pages = 8 if (date_from or date_to or args.free) else 1
    for page in range(1, max_pages + 1):
        body, final_url, _ = fetch_text(eventfinda_list_path(args.council, args.category, page), EVENTFINDA_BASE)
        source_urls.append(final_url)
        page_cards = eventfinda_cards(body)
        if not page_cards:
            break
        for item in page_cards:
            event_date = parse_event_date(item.get("start"))
            if date_from and (not event_date or event_date < date_from):
                continue
            if date_to and (not event_date or event_date > date_to):
                continue
            if args.free:
                haystack = " ".join(
                    str(x or "")
                    for x in [item.get("title"), item.get("category"), item.get("location"), " ".join(item.get("badges") or [])]
                ).lower()
                if "free" not in haystack:
                    continue
            item["council"] = args.council
            item["council_name"] = COUNCIL_NAMES.get(args.council or "", "NZ")
            events.append(item)
            if len(events) >= args.limit:
                break
        if len(events) >= args.limit:
            break

    data = {
        "query": {
            "council": args.council,
            "council_name": COUNCIL_NAMES.get(args.council or "", "NZ"),
            "from": date_from.isoformat() if date_from else None,
            "to": date_to.isoformat() if date_to else None,
            "category": args.category,
            "free": args.free,
            "limit": args.limit,
        },
        "source": "eventfinda-public-pages",
        "source_urls": source_urls,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "events": events,
    }
    emit_event_list(data, args.json)


def simplify_offer(offer: dict[str, Any]) -> dict[str, Any]:
    return {k: offer.get(k) for k in ("@id", "name", "price", "priceCurrency", "availability", "url") if offer.get(k) is not None}


def cmd_event(args: argparse.Namespace) -> None:
    if re.fullmatch(r"\d+", args.id_or_url):
        die("event id must be a URL or path from `events --json`; numeric Eventfinda ids are not stable enough by themselves")

    started = time.perf_counter()
    body, final_url, status = fetch_text(args.id_or_url, EVENTFINDA_BASE)
    objs = json_ld_objects(body)
    places = {o.get("@id"): o for o in objs if o.get("@type") == "Place" and o.get("@id")}
    offers = {o.get("@id"): o for o in objs if o.get("@type") == "Offer" and o.get("@id")}
    events = [o for o in objs if str(o.get("@type", "")).split("/")[-1] in EVENT_TYPES or str(o.get("@type", "")).endswith("Event")]
    if not events:
        die("no event JSON-LD found on page")

    first = events[0]
    loc_ref = first.get("location") if isinstance(first.get("location"), dict) else {}
    place = places.get(loc_ref.get("@id")) or (loc_ref if isinstance(loc_ref, dict) else {})
    resolved_offers: list[dict[str, Any]] = []
    for ref in first.get("offers") or []:
        if isinstance(ref, dict) and ref.get("@id") in offers:
            resolved_offers.append(simplify_offer(offers[ref["@id"]]))
        elif isinstance(ref, dict):
            resolved_offers.append(simplify_offer(ref))

    sessions: list[dict[str, Any]] = []
    seen = set()
    for event_obj in events:
        key = (event_obj.get("startDate"), event_obj.get("endDate"))
        if key in seen:
            continue
        seen.add(key)
        sessions.append({"start": event_obj.get("startDate"), "end": event_obj.get("endDate")})

    address = place.get("address") if isinstance(place.get("address"), dict) else {}
    data = {
        "source": "eventfinda-public-pages",
        "source_url": final_url,
        "status": status,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "event": {
            "title": first.get("name"),
            "type": first.get("@type"),
            "url": first.get("url") or final_url,
            "description": first.get("description"),
            "image": first.get("image"),
            "venue": place.get("name"),
            "venue_url": place.get("url") or place.get("@id"),
            "address": {
                "street": address.get("streetAddress"),
                "locality": address.get("addressLocality"),
                "country": address.get("addressCountry"),
            },
            "geo": place.get("geo") if isinstance(place.get("geo"), dict) else None,
            "sessions": sessions,
            "offers": resolved_offers,
        },
    }
    emit_event_detail(data, args.json)


def akl_location_listing(kind: str | None = None, region: str | None = None) -> tuple[list[dict[str, Any]], str]:
    params: dict[str, str] = {}
    if kind in AKL_FACILITY_IDS:
        params["facilitiesFilters"] = AKL_FACILITY_IDS[kind]
    if region:
        if region not in AKL_AREA_IDS:
            die(f"unknown Auckland region {region!r}; use one of: {', '.join(sorted(AKL_AREA_IDS))}")
        params["areaFilters"] = AKL_AREA_IDS[region]
    url = AKL_LOCATION_ENDPOINT
    if params:
        url += "?" + urllib.parse.urlencode(params)
    body, final_url, _ = fetch_text(
        url,
        AKL_LEISURE_BASE,
        headers={"X-Requested-With": "XMLHttpRequest", "Referer": AKL_LEISURE_BASE + "/locations/"},
    )
    cards = parse_akl_location_cards(body, final_url)
    if kind == "leisure-centre":
        cards = [c for c in cards if "leisure" in c["name"].lower() or "recreation" in c["name"].lower()]
    elif kind == "library":
        cards = [c for c in cards if "library" in c["name"].lower()]
    return cards, final_url


def parse_akl_location_cards(page_html: str, source_url: str) -> list[dict[str, Any]]:
    starts = [m.start() for m in re.finditer(r'<div\s+class="card\s+card-shadow"', page_html, flags=re.I)]
    cards: list[dict[str, Any]] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else min(len(page_html), start + 9000)
        block = page_html[start:end]
        title_m = re.search(r'<h3[^>]*class="[^"]*card-title[^"]*"[^>]*>(.*?)</h3>', block, flags=re.I | re.S)
        link_m = re.search(r'<a\s+([^>]*class="[^"]*card-inner-wrap[^"]*"[^>]*)>', block, flags=re.I | re.S)
        if not title_m or not link_m:
            continue
        name = strip_tags(title_m.group(1))
        href = attr(link_m.group(1), "href")
        if not name or not href:
            continue
        paragraphs = [strip_tags(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", block, flags=re.I | re.S)]
        address = next((p for p in paragraphs if p and "View on map" not in p and "Operated by" not in p), None)
        operator = next((p.replace("Operated by ", "") for p in paragraphs if p.startswith("Operated by ")), None)
        status = None
        footer_m = re.search(r'<div[^>]*class="[^"]*card-footer[^"]*"[^>]*>(.*?)</div>', block, flags=re.I | re.S)
        if footer_m:
            status = strip_tags(footer_m.group(1)) or None
        map_m = re.search(r'\bdata-target="([^"]+)"', block, flags=re.I)
        image_m = re.search(r"background-image:\s*url\(['\"]?([^'\")]+)", block, flags=re.I)
        cards.append(
            {
                "name": name,
                "id": slug_text(name),
                "council": "akl",
                "council_name": "Auckland",
                "source": "aucklandleisure",
                "source_url": absolutize(href, AKL_LEISURE_BASE),
                "listing_source_url": source_url,
                "address": address,
                "operator": operator,
                "status": status,
                "map_id": map_m.group(1) if map_m else None,
                "image": absolutize(image_m.group(1), AKL_LEISURE_BASE) if image_m else None,
            }
        )
    return cards


def text_between(page_html: str, start_pattern: str, end_patterns: list[str]) -> str:
    start = re.search(start_pattern, page_html, flags=re.I | re.S)
    if not start:
        return ""
    start_pos = start.end()
    end_pos = len(page_html)
    for pat in end_patterns:
        end = re.search(pat, page_html[start_pos:], flags=re.I | re.S)
        if end:
            end_pos = min(end_pos, start_pos + end.start())
    return page_html[start_pos:end_pos]


def parse_akl_detail(page_html: str, final_url: str, card: dict[str, Any] | None = None) -> dict[str, Any]:
    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", page_html, flags=re.I | re.S)
    meta_m = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)', page_html, flags=re.I)
    name = strip_tags(title_m.group(1)) if title_m else (card or {}).get("name")
    hours_section = text_between(page_html, r"<h3[^>]*>\s*Hours\s*</h3>", [r"<h3[^>]*>\s*Address\s*</h3>", r"<h3[^>]*>\s*Contact"])
    hours: list[dict[str, str]] = []
    for m in re.finditer(r'<h4[^>]*class="[^"]*page-link-with-description-title[^"]*"[^>]*>(.*?)</h4>\s*<p[^>]*>(.*?)</p>', hours_section, flags=re.I | re.S):
        label = strip_tags(m.group(1))
        text = strip_tags(m.group(2), br="; ")
        if label and text:
            hours.append({"label": label, "text": text})

    address = (card or {}).get("address")
    address_section = text_between(page_html, r"<h3[^>]*>\s*Address\s*</h3>", [r"<h3[^>]*>\s*Contact"])
    address_m = re.search(r"<p[^>]*>(.*?)</p>", address_section, flags=re.I | re.S)
    if address_m:
        parsed_address = strip_tags(address_m.group(1), br=", ")
        if parsed_address:
            address = parsed_address

    phones = [html.unescape(x).strip() for x in re.findall(r'href=["\']tel:([^"\']+)', page_html, flags=re.I)]
    emails = [html.unescape(x).strip() for x in re.findall(r'href=["\']mailto:([^"?\']+)', page_html, flags=re.I)]
    availability_m = re.search(r'href=["\'](https://portal\.aucklandleisure\.co\.nz/ResourceAvailability/\d+)["\']', page_html, flags=re.I)
    group_fitness_m = re.search(r'href=["\'](https://portal\.aucklandleisure\.co\.nz/Group\?[^"\']+)["\']', page_html, flags=re.I)

    feature_titles: list[str] = []
    pools_section = text_between(page_html, r'id=["\']collapsepools["\']', [r'id=["\']collapsegym["\']', r'id=["\']collapsegroup-fitness["\']', r'id=["\']collapsevenue-hire["\']'])
    noisy_feature_words = ("pdf download", "terms and conditions", "safe use", "what level", "how to enrol")
    for raw in re.findall(r'class=["\'][^"\']*card-title[^"\']*["\'][^>]*>(.*?)</h[34]>', pools_section or page_html, flags=re.I | re.S):
        title = strip_tags(raw)
        title_l = title.lower()
        if any(word in title_l for word in noisy_feature_words):
            continue
        if title and title not in feature_titles and title.lower() != (name or "").lower():
            feature_titles.append(title)

    return {
        "name": name,
        "id": slug_text(name or ""),
        "council": "akl",
        "council_name": "Auckland",
        "source": "aucklandleisure",
        "source_url": final_url,
        "description": html.unescape(meta_m.group(1)).strip() if meta_m else None,
        "address": address,
        "operator": (card or {}).get("operator"),
        "status": (card or {}).get("status") or None,
        "hours": hours,
        "hours_summary": hours[0]["text"] if hours else None,
        "phone": phones[0] if phones else None,
        "email": emails[0] if emails else None,
        "features": feature_titles[:20],
        "resource_availability_url": availability_m.group(1) if availability_m else None,
        "group_fitness_url": html.unescape(group_fitness_m.group(1)) if group_fitness_m else None,
    }


def enrich_akl_hours(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def one(card: dict[str, Any]) -> dict[str, Any]:
        try:
            body, final_url, _ = fetch_text(card["source_url"], AKL_LEISURE_BASE)
            detail = parse_akl_detail(body, final_url, card)
            card["hours"] = detail.get("hours")
            card["hours_summary"] = detail.get("hours_summary")
            card["phone"] = detail.get("phone")
            card["email"] = detail.get("email")
            card["resource_availability_url"] = detail.get("resource_availability_url")
        except SystemExit as exc:
            card["detail_error"] = str(exc)
        return card

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(one, dict(card)): idx for idx, card in enumerate(cards)}
        out: list[dict[str, Any] | None] = [None] * len(cards)
        for future in concurrent.futures.as_completed(futures):
            out[futures[future]] = future.result()
    return [x for x in out if x is not None]


def fetch_wlg_facilities(kind: str) -> tuple[list[dict[str, Any]], str]:
    if kind == "pool":
        path = "/recreation/facilities-and-centres/swimming-pools"
        facility_type = "pool"
    elif kind == "leisure-centre":
        path = "/recreation/facilities-and-centres/recreation-centres"
        facility_type = "leisure-centre"
    else:
        return [], WLG_BASE
    body, final_url, _ = fetch_text(path, WLG_BASE)
    facilities: list[dict[str, Any]] = []
    for m in re.finditer(r"<a\b([^>]*)>(.*?)</a>", body, flags=re.I | re.S):
        tag, block = m.group(1), m.group(2)
        if "link-block" not in tag:
            continue
        title_m = re.search(r'<h2[^>]*class="[^"]*link-block__title[^"]*"[^>]*>(.*?)</h2>', block, flags=re.I | re.S)
        if not title_m:
            continue
        title = strip_tags(title_m.group(1))
        href = attr(tag, "href")
        if not title or not href:
            continue
        title_l = title.lower()
        if any(word in title_l for word in ("lessons", "classes", "rules", "membership")):
            continue
        if kind == "pool" and "pool" not in title_l and "aquatic centre" not in title_l:
            continue
        if kind == "leisure-centre" and "recreation centre" not in title_l:
            continue
        desc_m = re.search(r'<p[^>]*class="[^"]*link-block__content[^"]*"[^>]*>(.*?)</p>', block, flags=re.I | re.S)
        facilities.append(
            {
                "name": title,
                "id": slug_text(title),
                "type": facility_type,
                "council": "wlg",
                "council_name": "Wellington",
                "source": "wellington-city-council",
                "source_url": absolutize(href, WLG_BASE),
                "listing_source_url": final_url,
                "description": strip_tags(desc_m.group(1)) if desc_m else None,
                "hours": None,
                "hours_note": "Open times are published on the linked Wellington City Council detail page; v1 only lists WCC facilities.",
            }
        )
    return facilities, final_url


def fetch_rot_facilities(kind: str | None = "pool") -> tuple[list[dict[str, Any]], str]:
    facilities: list[dict[str, Any]] = []
    for facility in ROT_FACILITIES:
        if kind and kind not in facility.get("facility_types", []):
            continue
        facilities.append(dict(facility))
    return facilities, ROT_RECREATION_SOURCE_URL


def fetch_npl_facilities(kind: str) -> tuple[list[dict[str, Any]], str]:
    if kind != "pool":
        return [], NPL_COMMUNITY_POOLS_URL
    return [dict(item) for item in NPL_POOL_FACILITIES], NPL_COMMUNITY_POOLS_URL


def static_recreation_facilities(council: str, kind: str | None = None) -> tuple[list[dict[str, Any]], str]:
    source_url = {
        "npr": NPR_AQUATIC_SOURCE_URL,
        "has": HAS_SWIMMING_POOLS_URL,
        "nsn": NSN_POOL_LISTING_URL,
        "tdc": TDC_SWIMMING_LISTING_URL if kind == "pool" else TDC_RECREATION_LISTING_URL,
    }.get(council, "")
    facilities: list[dict[str, Any]] = []
    for item in STATIC_RECREATION_FACILITIES.get(council, []):
        item_types = set(item.get("facility_types") or item.get("types") or [item.get("type")])
        if kind == "pool" and not item_types.intersection({"pool", "water-park", "aquatic-centre"}):
            continue
        if kind and kind != "pool" and kind not in item_types:
            continue
        facility = dict(item)
        if council == "tdc" and kind != "pool":
            facility["listing_source_url"] = TDC_RECREATION_LISTING_URL
        facility["id"] = facility.get("id") or slug_text(str(facility.get("name") or ""))
        facilities.append(facility)
    return facilities, source_url


def fetch_dud_text(url_or_path: str, timeout: int = 30) -> tuple[str, str, int, str]:
    url = resolve_url(url_or_path, DUD_BASE)
    body, final_url, status, error = fetch_text_result(
        url,
        headers={"Accept": "text/html,application/xhtml+xml"},
        timeout=timeout,
        allow_http_error=True,
    )
    if body and (status is None or status < 400) and not is_bot_wall(body) and not is_missing_page(body):
        return body, final_url, status or 200, "direct"

    cdp_body = fetch_text_browser_or_cdp(final_url, cdp_timeout=18)
    method = "browser" if BROWSER_MODE else "cdp"
    if cdp_body and not is_bot_wall(cdp_body) and not is_missing_page(cdp_body):
        return cdp_body, final_url, 200, method
    if BROWSER_MODE:
        return "", final_url, status or 0, "browser_blocked"

    reason = error or ("bot-wall" if body and is_bot_wall(body) else "missing-page")
    fallback = "CloakBrowser --browser" if BROWSER_MODE else f"CDP fallback at {CDP_HTTP_BASE}"
    die(f"Dunedin page fetch failed for {final_url} ({reason}); {fallback} did not return usable HTML")


def dud_html_text_lines(page_html: str) -> list[str]:
    value = re.sub(r"<script\b.*?</script>", " ", page_html, flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"</(p|div|li|h[1-6]|tr|td|th|section|article)>", "\n", value, flags=re.I)
    value = re.sub(r"<(p|div|li|h[1-6]|tr|td|th|section|article)\b[^>]*>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value).replace("\xa0", " ")
    lines = []
    for raw in value.splitlines():
        line = re.sub(r"\s+", " ", raw).strip(" |;\t\r\n")
        if line:
            lines.append(line)
    return lines


def dud_content_lines(page_html: str) -> list[str]:
    lines = dud_html_text_lines(page_html)
    start = 0
    for idx, line in enumerate(lines):
        if line.startswith("Last updated:"):
            start = idx + 1
            break
    end = len(lines)
    for idx in range(start, len(lines)):
        if lines[idx].startswith("Still didn't find"):
            end = idx
            break
    return lines[start:end]


def dud_content_text(page_html: str) -> str:
    text = strip_tags(page_html, br=" ")
    lower = text.lower()
    start = lower.find("last updated:")
    if start != -1:
        text = text[start:]
    lower = text.lower()
    end = lower.find("still didn't find")
    if end != -1:
        text = text[:end]
    return re.sub(r"\s+", " ", text).strip()


def dud_clean_text(value: str | None, limit: int | None = None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip(" |;\t\r\n")
    cleaned = cleaned.replace("Area Open from Closes at ", "")
    cleaned = cleaned.replace("Day Time ", "")
    cleaned = cleaned.replace(" Scroll to view", "")
    cleaned = re.sub(r"^[–-]\s*Friday\s+", "", cleaned)
    if limit and len(cleaned) > limit:
        return cleaned[: limit - 3].rstrip() + "..."
    return cleaned


def dud_between(text: str, start_label: str, end_labels: list[str]) -> str | None:
    lower = text.lower()
    start = lower.find(start_label.lower())
    if start == -1:
        return None
    start += len(start_label)
    end = len(text)
    for label in end_labels:
        pos = lower.find(label.lower(), start)
        if pos != -1:
            end = min(end, pos)
    return dud_clean_text(text[start:end])


def dud_hours_summary(hours: list[dict[str, str]]) -> str | None:
    chunks = []
    for item in hours[:3]:
        text = dud_clean_text(item.get("text"), 120)
        if text:
            chunks.append(f"{item['label']}: {text}")
    return "; ".join(chunks) if chunks else None


def parse_dud_hours(name: str, detail_html: str, hours_html: str | None = None) -> tuple[list[dict[str, str]], str | None]:
    page_html = hours_html or detail_html
    text = dud_content_text(page_html)
    hours: list[dict[str, str]] = []
    if name == "Moana Pool":
        weekday = dud_between(text, "Monday - Friday", ["Saturday - Sunday"])
        weekend = dud_between(text, "Saturday - Sunday", ["Public holiday hours"])
        public = dud_between(text, "Public holiday hours", ["Contact us"])
        for label, value in (("Monday - Friday", weekday), ("Saturday - Sunday", weekend), ("Public holidays", public)):
            if value:
                hours.append({"label": label, "text": value})
    elif name == "Te Puna o Whakaehu":
        weekday = dud_between(text, "Monday - Friday", ["Saturday - Sunday"])
        weekend = dud_between(text, "Saturday - Sunday", ["Public holiday hours"])
        public = dud_between(text, "Public holiday hours", ["Kid"])
        for label, value in (("Monday - Friday", weekday), ("Saturday - Sunday", weekend), ("Public holidays", public)):
            if value:
                hours.append({"label": label, "text": value})
    elif name == "Port Chalmers Pool":
        season = dud_between(text, "Open hours", ["Hours (school terms 1 & 4)"])
        term = dud_between(text, "Hours (school terms 1 & 4)", ["Additional swimming times", "Hours (school holidays)"])
        extra = dud_between(text, "Additional swimming times - Monday", ["Hours (school holidays)"])
        holidays = dud_between(text, "Hours (school holidays)", ["Top of this page", "Identification and concession rate"])
        for label, value in (
            ("Season", season),
            ("School terms 1 & 4", term),
            ("Additional weekday times", extra),
            ("School holidays", holidays),
        ):
            if value:
                hours.append({"label": label, "text": value})
    elif name == "St Clair Hot Salt Water Pool":
        season = dud_between(text, "Open hours", ["Monday - Friday", "Day Time"])
        regular = dud_between(text, "Day Time", ["Identification and concession rate"])
        if not regular:
            regular = dud_between(text, "Open date:", ["Identification and concession rate"])
        for label, value in (("Season", season), ("Regular season hours", regular)):
            if value:
                hours.append({"label": label, "text": value})
    return hours, dud_hours_summary(hours)


def parse_dud_pool_details(page_html: str, default_pool_name: str) -> list[dict[str, str]]:
    lines = dud_content_lines(page_html)
    start = -1
    for idx, line in enumerate(lines):
        if line in {"About the pool", "About the pools", "Pools"}:
            start = idx + 1
            break
    if start == -1:
        return []

    stop_prefixes = (
        "Open hours",
        "Opening Hours",
        "Te Puna o Whakaehu timetable",
        "Kid",
        "Kid's stuff",
        "Identification and concession rate",
        "Contact us",
    )
    skip_lines = {
        "You can click on image to open a larger version of the layout.",
        "Information on pools available at Moana pool.",
    }
    pools: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    def finish_current() -> None:
        nonlocal current
        if current and any(k != "name" for k in current):
            pools.append(current)
        current = None

    for line in lines[start:]:
        if line.startswith(stop_prefixes):
            break
        if line in skip_lines or line.startswith("Image:"):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            normalized_key = key.strip().strip("*").lower()
            field = DUD_POOL_PROP_KEYS.get(normalized_key)
            if field:
                if current is None:
                    current = {"name": default_pool_name}
                current[field] = value.strip().lstrip("* ").strip()
            continue
        if len(line) <= 80:
            finish_current()
            current = {"name": line.strip("# ")}
    finish_current()
    return pools


def parse_dud_contact_and_address(name: str, page_html: str) -> tuple[str | None, str | None, str | None]:
    text = dud_content_text(page_html)
    full_text = strip_tags(page_html, br=" ")
    address = None
    phone = None
    location_m = re.search(r"Location:\s*([^.;]+(?:,\s*[^.;]+)?)\.\s*Phone\s*([+0-9 ()-]+)", text, flags=re.I)
    if location_m:
        address = dud_clean_text(location_m.group(1))
        phone = dud_clean_text(location_m.group(2))
    elif name == "Moana Pool":
        address_m = re.search(r"Moana Pool sits .*? at\s+([^.;]+)", text, flags=re.I)
        address = dud_clean_text(address_m.group(1)) if address_m else "60 Littlebourne Road, Dunedin"
    elif name == "Te Puna o Whakaehu":
        address_m = re.search(r"located at\s+([^.;]+)", text, flags=re.I)
        if address_m:
            street = re.split(r"\s+at the\s+", address_m.group(1), maxsplit=1, flags=re.I)[0]
            address = dud_clean_text(street + ", Mosgiel")
        else:
            address = "215 Gordon Road, Mosgiel"

    if not phone:
        phone_m = re.search(r"Phone\s+([+0-9][+0-9 ()-]+)", full_text, flags=re.I)
        phone = dud_clean_text(phone_m.group(1)) if phone_m else None

    emails = re.findall(r"[\w.+-]+@[\w.-]+\.\w+", full_text)
    preferred_email = next((e for e in emails if e.lower() != "dcc@dcc.govt.nz"), None)
    email = preferred_email or (emails[0] if emails else None)
    return address, phone, email


def parse_dud_description(name: str, page_html: str) -> str | None:
    text = dud_content_text(page_html)
    text = re.sub(r"^Last updated:\s*\d{2}\s+[A-Za-z]+\s+\d{4}\s+\d{1,2}:\d{2}[ap]m\s*", "", text, flags=re.I).strip()
    stops = [
        "Location of Moana Pool",
        "History of Te Puna o Whakaehu",
        "About the pool",
        "About the pools",
        "Open hours",
        "Te Puna o Whakaehu timetable",
        "list apps",
    ]
    end = len(text)
    lower = text.lower()
    for stop in stops:
        pos = lower.find(stop.lower())
        if pos != -1:
            end = min(end, pos)
    return dud_clean_text(text[:end], 500)


def dud_pool_links(index_html: str) -> dict[str, str]:
    links: dict[str, str] = {}
    for match in re.finditer(r"<a\b([^>]*)>(.*?)</a>", index_html, flags=re.I | re.S):
        name = strip_tags(match.group(2))
        if name not in DUD_POOL_PAGES:
            continue
        href = attr(match.group(1), "href")
        if href and "#" not in href:
            links[name] = absolutize(href, DUD_BASE) or DUD_POOL_PAGES[name]["url"]
    return links


def parse_dud_facility(name: str, meta: dict[str, Any], listing_source_url: str) -> dict[str, Any]:
    detail_html, final_url, _status, fetch_mode = fetch_dud_text(str(meta["url"]))
    hours_html = detail_html
    hours_url = final_url
    if meta.get("hours_url"):
        hours_html, hours_url, _hours_status, _hours_mode = fetch_dud_text(str(meta["hours_url"]))
    pool_html = detail_html
    pool_url = final_url
    if meta.get("pools_url"):
        pool_html, pool_url, _pool_status, _pool_mode = fetch_dud_text(str(meta["pools_url"]))

    address, phone, email = parse_dud_contact_and_address(name, detail_html)
    hours, hours_summary = parse_dud_hours(name, detail_html, hours_html)
    pool_details = parse_dud_pool_details(pool_html, name)
    features = [p["name"] for p in pool_details if p.get("name")]
    if name == "Moana Pool" and "Gym" not in features:
        features.append("Gym")
    aliases = list(meta.get("aliases") or [])
    source_urls = [final_url]
    for url in (hours_url, pool_url):
        if url and url not in source_urls:
            source_urls.append(url)
    facility = {
        "name": name,
        "id": slug_text(name),
        "aliases": aliases,
        "type": "pool",
        "council": "dud",
        "council_name": "Dunedin",
        "source": "dunedin-city-council",
        "source_url": final_url,
        "listing_source_url": listing_source_url,
        "source_urls": source_urls,
        "fetch_mode": fetch_mode,
        "description": parse_dud_description(name, detail_html),
        "address": address,
        "phone": phone,
        "email": email,
        "hours": hours,
        "hours_summary": hours_summary,
        "features": features,
        "pool_details": pool_details,
        "resource_availability_url": None,
    }
    if "Mosgiel Pool" in aliases:
        facility["former_name"] = "Mosgiel Pool"
    if name in {"Port Chalmers Pool", "St Clair Hot Salt Water Pool"}:
        facility["seasonal"] = True
    return facility


def fetch_dud_facilities(kind: str) -> tuple[list[dict[str, Any]], str]:
    if kind == "pool":
        index_html, listing_url, _status, _mode = fetch_dud_text(DUD_POOLS_URL)
        live_links = dud_pool_links(index_html)
        facilities = []
        for name, meta in DUD_POOL_PAGES.items():
            merged = dict(meta)
            if live_links.get(name):
                merged["url"] = live_links[name]
            facilities.append(parse_dud_facility(name, merged, listing_url))
        return facilities, listing_url

    if kind == "leisure-centre":
        review_html, final_url, _status, _mode = fetch_dud_text(DUD_SPORTS_REVIEW_URL)
        text = dud_content_text(review_html)
        facilities: list[dict[str, Any]] = []
        if "Edgar Centre" in text:
            owned_context = dud_between(text, "We own 85 sports facilities,", ["Information from this survey"])
            description = f"DCC says it owns 85 sports facilities, {owned_context}" if owned_context else None
            facilities.append(
                {
                    "name": "Edgar Centre",
                    "id": "edgar-centre",
                    "type": "leisure-centre",
                    "facility_type": "indoor-sports-venue",
                    "council": "dud",
                    "council_name": "Dunedin",
                    "source": "dunedin-city-council",
                    "source_url": final_url,
                    "listing_source_url": final_url,
                    "description": dud_clean_text(description, 400)
                    or "Dunedin City Council lists Edgar Centre as a DCC-owned indoor sports venue.",
                    "address": None,
                    "phone": "+64 3 477 4000",
                    "email": "dcc@dcc.govt.nz",
                    "hours": None,
                    "hours_summary": None,
                    "hours_note": "The DCC source lists ownership but does not publish venue hours on this page.",
                    "pool_details": [],
                }
            )
        return facilities, final_url

    return [], DUD_BASE


def fetch_whg_facilities(kind: str) -> tuple[list[dict[str, Any]], str, str | None]:
    if kind == "library":
        return [], WHG_WDC_BASE, "Libraries are outside this skill's recreation-focused v1 data source."
    facilities: list[dict[str, Any]] = []
    for item in WHG_FACILITIES:
        if kind in item.get("facility_types", []) or kind == item.get("type"):
            facilities.append(dict(item))
    note = WHG_POOL_NO_COMMUNITY_NOTE if kind == "pool" else None
    return facilities, WHG_RECREATION_URL, note


def chc_hours_from_timings(timings: dict[str, Any] | None) -> tuple[str | None, str | None, list[dict[str, str]]]:
    if not isinstance(timings, dict):
        return None, None, []
    status = strip_tags(str(timings.get("state") or ""))
    hours_text = strip_tags(str(timings.get("hoursText") or ""))
    parts = [x for x in (status, hours_text) if x]
    hours_summary = " | ".join(parts) if parts else None
    hours = [{"label": "Current opening status", "text": hours_summary}] if hours_summary else []
    return status or None, hours_summary, hours


def parse_chc_card(item: dict[str, Any], kind: str, listing_source_url: str) -> dict[str, Any] | None:
    name = strip_tags(str(item.get("title") or ""))
    href = item.get("url")
    if not name or not isinstance(href, str):
        return None
    status, hours_summary, hours = chc_hours_from_timings(item.get("timings"))
    facility_type = "pool" if kind == "pool" else "gym" if kind == "gym" else "leisure-centre"
    image = item.get("imageUrl") if isinstance(item.get("imageUrl"), str) else None
    return {
        "name": name,
        "id": slug_text(name),
        "type": facility_type,
        "types": [facility_type],
        "council": "chc",
        "council_name": "Christchurch",
        "source": "christchurch-recreation-and-sport",
        "source_url": absolutize(href, CHC_REC_BASE),
        "listing_source_url": listing_source_url,
        "address": strip_tags(str(item.get("subTitle") or "")) or None,
        "description": strip_tags(str(item.get("description") or "")) or None,
        "status": status,
        "hours": hours,
        "hours_summary": hours_summary,
        "phone": CHC_REC_PHONE,
        "image": absolutize(image, CHC_REC_BASE) if image else None,
        "ccc_id": item.get("id"),
    }


def fetch_chc_filter_cards(kind: str) -> tuple[list[dict[str, Any]], str]:
    config = CHC_FILTERS.get(kind)
    if not config:
        return [], CHC_REC_BASE
    source_url = urllib.parse.urljoin(CHC_REC_BASE, config["source_path"])
    data, final_url, _ = fetch_json_post(
        CHC_FILTER_ENDPOINT,
        config["payload"],
        headers={"Referer": source_url, "Origin": CHC_REC_BASE},
    )
    if not isinstance(data, dict):
        die("Christchurch recreation endpoint returned an unexpected JSON shape")
    cards: list[dict[str, Any]] = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        card = parse_chc_card(item, kind, source_url)
        if card:
            cards.append(card)
    return cards, final_url or source_url


def first_match(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text, flags=re.I | re.S)
    if not m:
        return None
    return strip_tags(m.group(1))


def trim_sentence(value: str | None, limit: int = 700) -> str | None:
    if not value:
        return None
    value = re.sub(r"\s+", " ", value).strip(" ;|")
    if len(value) <= limit:
        return value
    cut = value[:limit].rsplit(" ", 1)[0].strip()
    return cut + "..."


def fetch_he_puna_taimoana() -> dict[str, Any]:
    body, final_url, _ = fetch_text(CHC_HE_PUNA_BASE + "/")
    text = strip_tags(body)
    hours_summary = first_match(text, r"(Open\s+10am\s+.+?)\s+195 Marine Parade") or "Open 10am - 7.30pm, 7 days"
    feature_text = first_match(text, r"(What we offer\s+-\s+Five.+?)\s+Book your experience")
    if feature_text:
        feature_text = feature_text.replace("What we offer - ", "")
    else:
        feature_text = "Five hot pools, plunge pool, sauna, steam room, heated changing rooms and cafe."
    return {
        "name": "He Puna Taimoana",
        "id": "he-puna-taimoana",
        "type": "pool",
        "types": ["pool"],
        "council": "chc",
        "council_name": "Christchurch",
        "source": "he-puna-taimoana",
        "source_url": final_url,
        "listing_source_url": final_url,
        "address": "195 Marine Parade, New Brighton, Christchurch 8061",
        "description": "New Brighton hot pools by the sea.",
        "status": None,
        "hours": [{"label": "Opening hours", "text": hours_summary}],
        "hours_summary": hours_summary,
        "phone": "+64 3 941 7818",
        "email": "info@hepunataimoana.co.nz",
        "features": ["Hot pools", "Plunge pool", "Sauna", "Steam room", "Heated changing rooms", "Cafe"],
        "pool_details": [{"label": "Hot pools", "text": feature_text}],
        "gym_details": [],
        "public_swim_availability": {
            "source_url": final_url,
            "summary": "Bookings are essential for public hot-pool sessions; the site links to live session availability.",
        },
    }


def fetch_wharenui_pool() -> dict[str, Any]:
    body, final_url, _ = fetch_text("/swimming/", CHC_WHARENUI_BASE)
    contact_body, contact_url, _ = fetch_text("/contact/", CHC_WHARENUI_BASE)
    text = strip_tags(body)
    contact_text = strip_tags(contact_body)
    pool_details = first_match(text, r"(About our Pools\s+Our Main Pool.+?)\s+Prices")
    hours_summary = first_match(text, r"(Public Swimming Hours\s+.+?)\s+Pool Rules")
    if not hours_summary:
        hours_summary = first_match(contact_text, r"(Public Swimming Hours\s+.+?)\s+Contact Us")
    phone = first_match(contact_text, r"(03\s*348\s*6488)") or "03 348 6488"
    address = first_match(contact_text, r"(73 Elizabeth Street\s+Riccarton,\s+Christchurch,\s+New Zealand)") or "73 Elizabeth Street, Riccarton, Christchurch"
    return {
        "name": "Wharenui Swimming Pool & Sports Centre",
        "id": "wharenui-pool",
        "type": "pool",
        "types": ["pool"],
        "council": "chc",
        "council_name": "Christchurch",
        "source": "wharenui-sports-centre",
        "source_url": final_url,
        "listing_source_url": contact_url,
        "address": address,
        "description": "Riccarton sports centre with public lane swimming and heated indoor pools.",
        "status": None,
        "hours": [{"label": "Public swimming hours", "text": hours_summary}] if hours_summary else [],
        "hours_summary": hours_summary,
        "phone": phone,
        "features": ["Public lane swimming", "Main pool", "Teaching pool", "Toddlers pool", "Sports centre", "Basketball"],
        "pool_details": [{"label": "About our pools", "text": pool_details}] if pool_details else [],
        "gym_details": [],
        "public_swim_availability": {
            "source_url": final_url,
            "summary": hours_summary,
        } if hours_summary else None,
    }


def fetch_chc_supplemental_pools() -> list[dict[str, Any]]:
    pools: list[dict[str, Any]] = []
    for getter in (fetch_he_puna_taimoana, fetch_wharenui_pool):
        try:
            pools.append(getter())
        except SystemExit as exc:
            pools.append(
                {
                    "name": getter.__name__.replace("fetch_", "").replace("_", " ").title(),
                    "id": getter.__name__.replace("fetch_", "").replace("_", "-"),
                    "type": "pool",
                    "types": ["pool"],
                    "council": "chc",
                    "council_name": "Christchurch",
                    "source": "supplemental-public-page",
                    "source_url": None,
                    "address": None,
                    "hours": [],
                    "hours_summary": None,
                    "detail_error": str(exc),
                }
            )
    return pools


def chc_lane_availability_summaries() -> dict[str, dict[str, Any]]:
    body, final_url, _ = fetch_text("/swim/lane-availability/", CHC_REC_BASE)
    text = strip_tags(body)
    start = text.find("Review the sections below")
    content = text[start:] if start >= 0 else text
    names = [
        ("graham-condon", "Graham Condon"),
        ("jellie-park", "Jellie Park"),
        ("matatiki-hornby-centre", "Matatiki Hornby Centre"),
        ("parakiore", "Parakiore"),
        ("pioneer", "Pioneer"),
        ("taiora-qeii", "Taiora QEII"),
        ("te-pou-toetoe-linwood-pool", "Te Pou Toetoe Linwood Pool"),
    ]
    positions: list[tuple[int, str, str]] = []
    for facility_id, name in names:
        chosen = -1
        for match in re.finditer(re.escape(name), content):
            after = content[match.end() : match.end() + len(name) + 40].lstrip()
            if after.startswith(name) or after.startswith("has ") or after.startswith("is "):
                chosen = match.start()
                break
        if chosen < 0:
            chosen = content.find(name)
        if chosen >= 0:
            positions.append((chosen, facility_id, name))
    positions.sort()
    summaries: dict[str, dict[str, Any]] = {}
    for idx, (pos, facility_id, name) in enumerate(positions):
        end = positions[idx + 1][0] if idx + 1 < len(positions) else len(content)
        section = content[pos + len(name) : end]
        section = re.sub(r"\s+", " ", section).strip()
        for marker in ("Morning availability", "Afternoon availability", "Evening availability"):
            marker_pos = section.find(marker)
            if marker_pos > 0:
                section = section[:marker_pos]
                break
        section = trim_sentence(section, 900)
        if section:
            summaries[facility_id] = {
                "source_url": final_url,
                "summary": section,
                "contact_phone": CHC_LANE_PHONE,
                "contact_email": CHC_LANE_EMAIL,
            }
    return summaries


def main_html(page_html: str) -> str:
    m = re.search(r"<main\b[^>]*>(.*?)</main>", page_html, flags=re.I | re.S)
    return m.group(1) if m else page_html


def section_id(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", label)


def quick_link_features(page_html: str) -> list[str]:
    features: list[str] = []
    nav_m = re.search(r'<ul[^>]*class=["\'][^"\']*c-sticky-in-page-nav-links[^"\']*["\'][^>]*>(.*?)</ul>', page_html, flags=re.I | re.S)
    if not nav_m:
        return features
    for raw in re.findall(r"<span[^>]*>(.*?)</span>", nav_m.group(1), flags=re.I | re.S):
        text = strip_tags(raw)
        if text and text not in features and text.lower() != "quick links":
            features.append(text)
    return features


def extract_chc_html_section(page_html: str, heading: str) -> str | None:
    sid = section_id(heading)
    id_m = re.search(rf'id=["\']{re.escape(sid)}["\']', page_html, flags=re.I)
    if not id_m:
        return None
    next_m = re.search(r'<span[^>]*class=["\'][^"\']*c-content-heading[^"\']*["\'][^>]*id=["\']', page_html[id_m.end() :], flags=re.I)
    end = id_m.end() + next_m.start() if next_m else min(len(page_html), id_m.end() + 25000)
    block = page_html[id_m.start() : end]
    text_blocks = re.findall(r'<div[^>]*class=["\'][^"\']*c-text-block-main-text[^"\']*["\'][^>]*>(.*?)</div>', block, flags=re.I | re.S)
    if text_blocks:
        text = strip_tags(" ".join(text_blocks), br="; ")
    else:
        text = strip_tags(block, br="; ")
    text = re.sub(r"\s+", " ", text).strip(" ;|")
    if text.lower().startswith(heading.lower()):
        text = text[len(heading) :].strip(" ;|")
    return trim_sentence(text, 900) if len(text) >= 25 else None


def detail_text_for_facility(page_html: str, name: str | None) -> str:
    text = strip_tags(main_html(page_html))
    if name:
        start = text.find(f"{name} Quick Links")
        if start < 0:
            start = text.find(name)
        if start >= 0:
            text = text[start:]
    end = text.find("Contact us:")
    if end > 0:
        text = text[:end]
    return text


def extract_detail_section(detail_text: str, heading: str, stop_headings: list[str]) -> str | None:
    m = re.search(rf"(?:^|\s){re.escape(heading)}(?:\s|$)", detail_text, flags=re.I)
    if not m:
        return None
    start = m.end()
    end = len(detail_text)
    for stop in stop_headings:
        stop_m = re.search(rf"(?:^|\s){re.escape(stop)}(?:\s|$)", detail_text[start:], flags=re.I)
        if stop_m and stop_m.start() > 20:
            end = min(end, start + stop_m.start())
    text = detail_text[start:end]
    text = re.sub(r"\s+", " ", text).strip(" .;")
    if len(text) < 25:
        return None
    return trim_sentence(text, 900)


def parse_chc_detail(page_html: str, final_url: str, card: dict[str, Any]) -> dict[str, Any]:
    main = main_html(page_html)
    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", page_html, flags=re.I | re.S)
    meta_m = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)', page_html, flags=re.I)
    name = strip_tags(title_m.group(1)) if title_m else card.get("name")
    detail_text = detail_text_for_facility(main, name)
    phones = [html.unescape(x).strip() for x in re.findall(r'href=["\']tel:([^"\']+)', page_html, flags=re.I)]
    emails = [html.unescape(x).strip() for x in re.findall(r'href=["\']mailto:([^"?\']+)', page_html, flags=re.I)]
    feature_candidates = [
        "Pools",
        "Indoor pools",
        "Outdoor summer pools",
        "Hydroslides",
        "Hydroslide",
        "Learn to swim",
        "Gym",
        "Group fitness classes",
        "Indoor stadium",
        "Stadium/Courts",
        "Community Courts",
        "Rooms for hire",
        "Hydrotherapy Pool",
        "Sensory Centre",
        "Sensory Aqua Centre",
        "Spa",
        "Sauna",
        "Steam room",
        "Cafe",
    ]
    detail_lower = detail_text.lower()
    features = quick_link_features(main) or [feat for feat in feature_candidates if feat.lower() in detail_lower]
    stop_headings = feature_candidates + [
        "Centre amenities",
        "Plan your visit",
        "View Pricing",
        "Prices",
        "Travel by",
        "Accessibility",
        "The story of",
        "Parking",
        "Contact details",
        "Contact us",
    ]
    pool_details: list[dict[str, str]] = []
    for heading in ("Indoor pools", "Outdoor summer pools", "Pools", "Hydrotherapy Pool", "Hydroslides", "Sensory Aqua Centre"):
        section = extract_chc_html_section(main, heading)
        if section and all(section != item["text"] for item in pool_details):
            pool_details.append({"label": heading, "text": section})
    gym_details: list[dict[str, str]] = []
    for heading in ("Gym",):
        section = extract_chc_html_section(main, heading)
        if section and all(section != item["text"] for item in gym_details):
            gym_details.append({"label": heading, "text": section})

    enriched = dict(card)
    enriched.update(
        {
            "name": name,
            "id": slug_text(name or card.get("name", "")),
            "source_url": final_url,
            "description": html.unescape(meta_m.group(1)).strip() if meta_m else card.get("description"),
            "phone": card.get("phone") or CHC_REC_PHONE,
            "email": card.get("email"),
            "features": features,
            "pool_details": pool_details,
            "gym_details": gym_details,
        }
    )
    return enriched


def enrich_chc_details(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lane_summaries: dict[str, dict[str, Any]] = {}
    pool_ids = {card.get("id") for card in cards if card.get("type") == "pool"}
    if pool_ids:
        try:
            lane_summaries = chc_lane_availability_summaries()
        except SystemExit:
            lane_summaries = {}

    def one(card: dict[str, Any]) -> dict[str, Any]:
        if card.get("source") != "christchurch-recreation-and-sport" or not card.get("source_url"):
            return card
        try:
            body, final_url, _ = fetch_text(str(card["source_url"]), CHC_REC_BASE)
            detail = parse_chc_detail(body, final_url, card)
            if detail.get("id") in lane_summaries:
                detail["public_swim_availability"] = lane_summaries[detail["id"]]
            return detail
        except SystemExit as exc:
            card["detail_error"] = str(exc)
            return card

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(one, dict(card)): idx for idx, card in enumerate(cards)}
        out: list[dict[str, Any] | None] = [None] * len(cards)
        for future in concurrent.futures.as_completed(futures):
            out[futures[future]] = future.result()
    return [x for x in out if x is not None]


def unique_texts(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = re.sub(r"\s+", " ", value).strip(" ;,\t\r\n")
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def clean_tga_pool_detail_text(value: str) -> str | None:
    value = re.sub(r"\s+", " ", value).strip(" ;,\t\r\n")
    if not value:
        return None
    value = re.sub(r"\s*Click here for [^.]*?accessibility info\.?", "", value, flags=re.I).strip(" ;,")
    target_starts = (
        "Mount Hot Pools features three outdoor pools",
        "Memorial Pool was built",
        "The new Memorial Park Aquatic Centre",
        "Even if a new facility",
        "The existing pool would always have needed to close",
    )
    for phrase in target_starts:
        pos = value.find(phrase)
        if pos >= 0:
            value = value[pos:]
            break
    return value.strip(" ;,\t\r\n") or None


def parse_meta_description(page_html: str) -> str | None:
    meta_m = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)', page_html, flags=re.I)
    return html.unescape(meta_m.group(1)).strip() if meta_m else None


def clean_tga_hours_text(value: str) -> str | None:
    value = re.sub(r"\s+", " ", value).strip(" ;")
    if not value:
        return None
    stale_markers = (
        "Reduced hours from 15 July - 24 July",
        "Weekdays (15-22 July)",
        "Saturday & Sunday (16, 17 & 23 July)",
        "Sunday 24 July",
        "Thursday 23 June until Monday 4 July",
    )
    if any(marker in value for marker in stale_markers):
        if value.startswith("Clubfit Gym"):
            value = re.sub(r";?\s*Sunday 24 July:\s*CLOSED", "", value, flags=re.I)
        else:
            return None
    return value.strip(" ;") or None


def tga_hours_item(value: str) -> dict[str, str] | None:
    cleaned = clean_tga_hours_text(value)
    if not cleaned:
        return None
    label = "Opening hours"
    text = cleaned
    for prefix in ("Aquatic Centre", "Clubfit Gym", "Normal Hours"):
        if cleaned.lower().startswith(prefix.lower()):
            label = "Aquatic Centre" if prefix == "Normal Hours" else prefix
            text = cleaned[len(prefix) :].strip(" ;")
            break
    if not re.search(r"\d", text):
        return None
    return {"label": label, "text": text}


def tga_status_from_text(text: str) -> str | None:
    lowered = text.lower()
    if "permanently closed" in lowered:
        return "Permanently closed"
    if "closed until further notice" in lowered:
        return "Closed until further notice"
    if "currently closed" in lowered:
        return "Currently closed"
    return None


def parse_tga_location_cards(page_html: str, source_url: str, council_url: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for m in re.finditer(r'<section\b([^>]*)class="[^"]*cLocationWithText[^"]*"[^>]*>(.*?)</section>', page_html, flags=re.I | re.S):
        block = m.group(2)
        title_m = re.search(r"<h1[^>]*>(.*?)</h1>", block, flags=re.I | re.S)
        if not title_m:
            continue
        name = strip_tags(title_m.group(1))
        if not name:
            continue
        facility_id = slug_text(name)
        if facility_id not in TGA_KIND_HINTS:
            continue
        after_title = block[title_m.end() :]
        contact_html = after_title.split("<h2", 1)[0]
        contact_p = re.search(r"<p[^>]*>(.*?)</p>", contact_html, flags=re.I | re.S)
        contact_text = strip_tags(contact_p.group(1), br=", ") if contact_p else ""
        phone_m = re.search(r'href=["\']tel:([^"\']+)', contact_html, flags=re.I)
        phone = None
        if phone_m:
            digits = re.sub(r"\D+", "", html.unescape(phone_m.group(1)))
            if digits:
                phone = " ".join([digits[:2], digits[2:5], digits[5:]]) if digits.startswith("07") and len(digits) == 9 else digits
        address = contact_text
        if phone:
            address = re.sub(re.escape(phone), "", address)
            address = re.sub(r"\b0\d(?:[\s-]?\d){6,}\b", "", address)
        address = re.sub(r"\s*,\s*,+", ",", address).strip(" ,") or None

        hours: list[dict[str, str]] = []
        hours_m = re.search(r"<h2[^>]*>\s*Opening Hours\s*</h2>(.*?)(?:</div>\s*<p|</div>\s*</div>)", after_title, flags=re.I | re.S)
        if hours_m:
            for p in re.findall(r"<p[^>]*>(.*?)</p>", hours_m.group(1), flags=re.I | re.S):
                item = tga_hours_item(strip_tags(p, br="; "))
                if item:
                    hours.append(item)

        detail_url = TGA_POOL_DETAIL_URLS.get(facility_id)
        if not detail_url:
            link_m = re.search(r'<a\s+[^>]*href=["\']([^"\']+)["\']', block, flags=re.I)
            detail_url = absolutize(link_m.group(1), TGA_POOLS_BASE) if link_m else source_url

        cards.append(
            {
                "name": name,
                "id": facility_id,
                "type": "pool",
                "types": sorted(TGA_KIND_HINTS.get(facility_id, {"pool"})),
                "council": "tga",
                "council_name": "Tauranga",
                "source": "tauranga-pools-bayvenues",
                "source_url": detail_url,
                "listing_source_url": source_url,
                "council_source_url": council_url,
                "address": address,
                "operator": "Bay Venues",
                "phone": phone,
                "hours": hours,
                "hours_summary": hours[0]["text"] if hours else None,
            }
        )
    return cards


def extract_tga_pool_details(page_html: str) -> list[str]:
    facilities = text_between(
        page_html,
        r"<h3[^>]*>\s*(?:<strong>)?\s*Pool Facilities",
        [
            r"<h3[^>]*>\s*Regular Activities",
            r"<section\b[^>]*class=[\"'][^\"']*cTaurangaPoolTemp",
            r"<section\b[^>]*class=[\"'][^\"']*IconimagebuttonText",
            r"<section\b[^>]*class=[\"'][^\"']*cFullWithCta",
        ],
    )
    details: list[str] = []
    for item in re.findall(r"<li[^>]*>(.*?)</li>", facilities, flags=re.I | re.S):
        text = clean_tga_pool_detail_text(strip_tags(item, br="; "))
        if text:
            details.append(text)
    if details:
        return unique_texts(details)[:20]

    targeted_paragraphs = [
        strip_tags(paragraph, br="; ")
        for paragraph in re.findall(r"<p[^>]*>(.*?)</p>", page_html, flags=re.I | re.S)
    ]
    target_phrases = (
        "Mount Hot Pools features three outdoor pools",
        "three outdoor pools",
        "pools ranging from",
        "natural ocean water",
        "Memorial Pool was built",
        "new Memorial Park Aquatic Centre",
        "existing pool would always have needed to close",
    )
    for text in targeted_paragraphs:
        if any(phrase in text for phrase in target_phrases):
            cleaned = clean_tga_pool_detail_text(text)
            if cleaned:
                details.append(cleaned)
    return unique_texts(details)[:20]


def extract_tga_pool_temperatures(page_html: str) -> list[dict[str, str]]:
    temps: list[dict[str, str]] = []
    temp_section = text_between(page_html, r"<h2[^>]*>\s*Pool Temps", [r"</section>"])
    if not temp_section:
        temp_section = text_between(page_html, r"<h2[^>]*>\s*Pool Temperatures", [r"</section>"])
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", temp_section, flags=re.I | re.S):
        cells = [strip_tags(cell) for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.I | re.S)]
        if len(cells) >= 2 and cells[0] and cells[1]:
            temps.append({"pool": cells[0], "temperature": cells[1]})
    return temps


def extract_tga_status(page_html: str) -> tuple[str | None, str | None]:
    text = strip_tags(page_html, br="; ")
    status = tga_status_from_text(text)
    status_note = None
    if status:
        if "mauao landslides" in text.lower():
            status_note = "Mount Hot Pools is currently closed due to 2026 Mauao landslides."
        elif "Permanently closed" in text:
            status_note = "Permanently closed."
    return status, status_note


def parse_tga_detail(page_html: str, final_url: str, card: dict[str, Any]) -> dict[str, Any]:
    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", page_html, flags=re.I | re.S)
    name = strip_tags(title_m.group(1)) if title_m else card.get("name")
    if name and ("currently closed" in name.lower() or "closed until" in name.lower()):
        name = card.get("name")
    description = parse_meta_description(page_html)
    status, status_note = extract_tga_status(page_html)
    pool_details = extract_tga_pool_details(page_html)
    pool_temperatures = extract_tga_pool_temperatures(page_html)
    detail = dict(card)
    detail.update(
        {
            "name": name or card.get("name"),
            "id": card.get("id") or slug_text(name or ""),
            "source_url": final_url,
            "description": description,
            "status": status,
            "status_note": status_note,
            "pool_details": pool_details,
            "features": pool_details,
            "pool_temperatures": pool_temperatures,
        }
    )
    if status:
        detail["hours_summary"] = status
    return detail


def enrich_tga_facilities(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def one(card: dict[str, Any]) -> dict[str, Any]:
        try:
            body, final_url, _ = fetch_text_with_cdp(card["source_url"], timeout=30)
            detail = parse_tga_detail(body, final_url, card)
            info_url = TGA_POOL_INFO_URLS.get(detail.get("id", ""))
            if info_url:
                try:
                    info_body, info_final_url, _ = fetch_text_with_cdp(info_url, timeout=30)
                    extra_details = extract_tga_pool_details(info_body)
                    if extra_details:
                        detail["pool_details"] = unique_texts((detail.get("pool_details") or []) + extra_details)[:20]
                        detail["features"] = detail["pool_details"]
                    detail["pool_info_url"] = info_final_url
                except SystemExit:
                    pass
        except SystemExit as exc:
            detail = dict(card)
            detail["detail_error"] = str(exc)
        return detail

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(one, dict(card)): idx for idx, card in enumerate(cards)}
        out: list[dict[str, Any] | None] = [None] * len(cards)
        for future in concurrent.futures.as_completed(futures):
            out[futures[future]] = future.result()
    return [x for x in out if x is not None]


def fetch_chc_facilities(kind: str) -> tuple[list[dict[str, Any]], str]:
    if kind == "library":
        return [], CHC_REC_BASE
    cards, source_url = fetch_chc_filter_cards(kind)
    if kind == "pool":
        cards.extend(fetch_chc_supplemental_pools())
    return cards, source_url


def parse_pmn_pool_listing(page_html: str, source_url: str) -> list[dict[str, Any]]:
    starts = [m.start() for m in re.finditer(r'<div\s+class=["\'][^"\']*list-item-container[^"\']*small-panel', page_html, flags=re.I)]
    facilities: list[dict[str, Any]] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else min(len(page_html), start + 7000)
        block = page_html[start:end]
        link_m = re.search(r"<a\s+([^>]+)>", block, flags=re.I | re.S)
        title_m = re.search(r'<h2[^>]*class=["\'][^"\']*list-item-title[^"\']*["\'][^>]*>(.*?)</h2>', block, flags=re.I | re.S)
        desc_m = re.search(r"<p[^>]*>(.*?)</p>", block, flags=re.I | re.S)
        if not link_m or not title_m:
            continue
        href = attr(link_m.group(1), "href")
        name = strip_tags(title_m.group(1))
        if not href or not name:
            continue
        image_m = re.search(r"<img\s+([^>]+)>", block, flags=re.I | re.S)
        facilities.append(
            {
                "name": name,
                "id": slug_text(name),
                "type": "pool",
                "council": "pmn",
                "council_name": "Palmerston North",
                "source": "palmerston-north-city-council",
                "source_url": absolutize(href, PNCC_BASE),
                "listing_source_url": source_url,
                "description": strip_tags(desc_m.group(1)) if desc_m else None,
                "image": absolutize(attr(image_m.group(1), "src") or attr(image_m.group(1), "data-src"), PNCC_BASE) if image_m else None,
                "hours": None,
                "hours_summary": None,
                "hours_note": None,
            }
        )
    return facilities


def fetch_pmn_text(url_or_path: str, base: str = PNCC_BASE, timeout: int = 30) -> tuple[str, str, int]:
    url = resolve_url(url_or_path, base)
    body, final_url, status, method = try_fetch_live_page(url, use_cdp=True)
    if not body:
        die(f"could not fetch Palmerston North source {url}: {method}")
    canonical_url = meta_content(body, "og:url")
    if canonical_url:
        final_url = absolutize(canonical_url, final_url) or final_url
    return body, final_url, status or 0


def first_href(page_html: str, contains: str | None = None) -> str | None:
    for m in re.finditer(r"<a\s+([^>]+)>", page_html, flags=re.I | re.S):
        href = attr(m.group(1), "href")
        if not href:
            continue
        if contains and contains.lower() not in href.lower():
            continue
        return html.unescape(href)
    return None


def is_pmn_clm_page(page_html: str, final_url: str) -> bool:
    parsed = urllib.parse.urlparse(final_url)
    if parsed.netloc.endswith("clmnz.co.nz"):
        return True
    return (
        parsed.netloc.endswith("pncc.govt.nz")
        and not parsed.path.lower().startswith("/parks-recreation/swimming-pools/")
        and "clmnz.co.nz" in page_html.lower()
    )


def clm_page_base(page_html: str, final_url: str, slug: str | None = None) -> str:
    parsed = urllib.parse.urlparse(final_url)
    if parsed.netloc.endswith("clmnz.co.nz"):
        return final_url
    if parsed.netloc.endswith("pncc.govt.nz") and parsed.path and not parsed.path.lower().startswith("/parks-recreation/swimming-pools/"):
        return "https://www.clmnz.co.nz" + parsed.path
    if slug and re.search(rf"https://www\.clmnz\.co\.nz/{re.escape(slug)}/?", page_html, flags=re.I):
        return f"https://www.clmnz.co.nz/{slug}/"
    for m in re.finditer(r"https://www\.clmnz\.co\.nz/([a-z0-9-]+)/?", page_html, flags=re.I):
        segment = m.group(1).lower()
        if segment not in {"media", "assets"}:
            return f"https://www.clmnz.co.nz/{segment}/"
    return final_url


def pncc_side_section(page_html: str, title: str) -> str:
    pattern = rf'<h2[^>]*class=["\'][^"\']*side-box-title[^"\']*["\'][^>]*>\s*{re.escape(title)}\s*</h2>'
    return text_between(page_html, pattern, [r'<h2[^>]*class=["\'][^"\']*side-box-title', r'<div[^>]*class=["\'][^"\']*share-page-container'])


def parse_pmn_pncc_detail(page_html: str, final_url: str, card: dict[str, Any] | None = None) -> dict[str, Any]:
    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", page_html, flags=re.I | re.S)
    name = strip_tags(title_m.group(1)) if title_m else (card or {}).get("name")
    main_section = text_between(page_html, r"<!--normalTemplateStart-->", [r'<div[^>]*class=["\'][^"\']*share-page-container'])
    main_before_side = text_between(page_html, r"<!--normalTemplateStart-->", [r'<div[^>]*class=["\'][^"\']*col-xs-12 col-m-4', r'<div[^>]*class=["\'][^"\']*share-page-container'])

    description = meta_content(page_html, "description") or (card or {}).get("description")
    intro_m = re.search(r'<p[^>]*class=["\'][^"\']*introduction[^"\']*["\'][^>]*>(.*?)</p>', main_section, flags=re.I | re.S)
    if intro_m:
        description = strip_tags(intro_m.group(1)) or description

    features = [strip_tags(x) for x in re.findall(r"<li[^>]*>(.*?)</li>", main_before_side, flags=re.I | re.S)]
    if not features:
        features = [strip_tags(x) for x in re.findall(r"<h2[^>]*>(.*?)</h2>", main_before_side, flags=re.I | re.S)]
    features = dedupe_strings([f for f in features if f and f.lower() not in {"facilities", "services"}])

    location_section = pncc_side_section(page_html, "Location")
    address = (card or {}).get("address")
    address_m = re.search(r"<p[^>]*>(.*?)</p>", location_section, flags=re.I | re.S)
    if address_m:
        parsed_address = strip_tags(address_m.group(1), br=", ")
        if parsed_address and "location map" not in parsed_address.lower():
            address = parsed_address

    hours_section = pncc_side_section(page_html, "Opening hours and prices")
    hours_note = None
    hours_note_m = re.search(r"<p[^>]*>(.*?)</p>", hours_section, flags=re.I | re.S)
    if hours_note_m:
        hours_note = strip_tags(hours_note_m.group(1))
    if name and "paddling" in name.lower():
        hours_note = "Memorial Park pool and splash pad are open in summer from 10am to 9pm; Victoria Esplanade paddling pool opens November to March."

    phones = [html.unescape(x).strip() for x in re.findall(r'href=["\']tel:([^"\']+)', main_section, flags=re.I)]
    emails = [html.unescape(x).strip() for x in re.findall(r'href=["\']mailto:([^"?\']+)', main_section, flags=re.I)]
    opening_hours_url = first_href(hours_section, "contact") or first_href(hours_section)
    prices_url = first_href(hours_section, "prices")

    facility = {
        "name": name,
        "id": slug_text(name or ""),
        "type": "pool",
        "council": "pmn",
        "council_name": "Palmerston North",
        "source": "palmerston-north-city-council",
        "source_url": final_url,
        "listing_source_url": (card or {}).get("listing_source_url"),
        "description": description,
        "address": address,
        "operator": "Community Leisure Management" if "clmnz.co.nz" in hours_section.lower() else None,
        "status": None,
        "hours": None,
        "hours_summary": hours_note,
        "hours_note": hours_note,
        "phone": phones[0] if phones else None,
        "email": emails[0] if emails else None,
        "features": features[:20],
        "opening_hours_url": absolutize(opening_hours_url, final_url) if opening_hours_url else None,
        "prices_url": absolutize(prices_url, final_url) if prices_url else None,
        "image": (card or {}).get("image") or meta_content(page_html, "og:image"),
    }
    return facility


def parse_clm_contact(page_html: str, final_url: str) -> dict[str, Any]:
    phones = [html.unescape(x).strip() for x in re.findall(r'href=["\']tel:([^"\']+)', page_html, flags=re.I)]
    emails = [html.unescape(x).strip() for x in re.findall(r'href=["\']mailto:([^"?\']+)', page_html, flags=re.I)]
    address = None
    address_m = re.search(r'class=["\']contact-address__text["\'][^>]*>(.*?)</span>', page_html, flags=re.I | re.S)
    if address_m:
        address = strip_tags(address_m.group(1), br=", ")
        address = re.sub(r"\s*,\s*", ", ", address)

    starts = [m.start() for m in re.finditer(r'<div\s+class=["\']card__body["\']', page_html, flags=re.I)]
    hours: list[dict[str, str]] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else min(len(page_html), start + 3500)
        block = page_html[start:end]
        title_m = re.search(r'class=["\']card__title-text["\'][^>]*>(.*?)</span>', block, flags=re.I | re.S)
        text_m = re.search(r"<p[^>]*>(.*?)</p>", block, flags=re.I | re.S)
        if not title_m or not text_m:
            continue
        label = strip_tags(title_m.group(1))
        text = compact_text(strip_tags(text_m.group(1), br="; "))
        if label and text and any(word in label.lower() for word in ("hours", "hydroslides")):
            hours.append({"label": label, "text": text})

    pool_hours = next((h for h in hours if "pool" in h["label"].lower()), hours[0] if hours else None)
    return {
        "source_url": final_url,
        "phone": phones[0] if phones else None,
        "email": emails[0] if emails else None,
        "address": address,
        "hours": hours or None,
        "hours_summary": pool_hours["text"] if pool_hours else None,
    }


def parse_pmn_clm_detail(page_html: str, final_url: str, card: dict[str, Any] | None = None) -> dict[str, Any]:
    source_url = clm_page_base(page_html, final_url, str((card or {}).get("id") or ""))
    name = meta_content(page_html, "og:title") or (card or {}).get("name")
    description = meta_content(page_html, "description") or meta_content(page_html, "og:description") or (card or {}).get("description")
    contact_url = absolutize(first_href(page_html, "contact/"), source_url)
    features = [strip_tags(x) for x in re.findall(r'class=["\']navigation__link__text["\'][^>]*>\s*<span>(.*?)</span>', page_html, flags=re.I | re.S)]
    features = dedupe_strings([f for f in features if f and f.lower() not in {"business hours", "contact us", "prices", "news", "work with us"}])
    contact = parse_clm_contact(page_html, final_url)
    facility = {
        "name": name,
        "id": slug_text(name or ""),
        "type": "pool",
        "council": "pmn",
        "council_name": "Palmerston North",
        "source": "palmerston-north-city-council-linked-clm",
        "source_url": source_url,
        "listing_source_url": (card or {}).get("listing_source_url"),
        "description": description,
        "address": contact.get("address"),
        "operator": "Community Leisure Management",
        "status": None,
        "hours": contact.get("hours"),
        "hours_summary": contact.get("hours_summary"),
        "hours_note": None,
        "phone": contact.get("phone"),
        "email": contact.get("email"),
        "features": features[:20],
        "opening_hours_url": contact_url,
        "prices_url": absolutize(first_href(page_html, "prices/"), source_url),
        "image": (card or {}).get("image") or meta_content(page_html, "og:image"),
    }
    return facility


def enrich_pmn_facility(card: dict[str, Any]) -> dict[str, Any]:
    facility = dict(card)
    try:
        body, final_url, _ = fetch_pmn_text(card["source_url"], PNCC_BASE)
        if is_pmn_clm_page(body, final_url):
            facility.update(parse_pmn_clm_detail(body, final_url, card))
        else:
            facility.update(parse_pmn_pncc_detail(body, final_url, card))
        opening_hours_url = facility.get("opening_hours_url")
        if opening_hours_url and urllib.parse.urlparse(opening_hours_url).netloc.endswith("clmnz.co.nz"):
            contact_body, contact_final_url, _ = fetch_pmn_text(opening_hours_url, PNCC_BASE)
            contact = parse_clm_contact(contact_body, contact_final_url)
            facility["hours"] = contact.get("hours") or facility.get("hours")
            facility["hours_summary"] = contact.get("hours_summary") or facility.get("hours_summary")
            facility["hours_source_url"] = contact_final_url
            facility["phone"] = facility.get("phone") or contact.get("phone")
            facility["email"] = facility.get("email") or contact.get("email")
            facility["address"] = facility.get("address") or contact.get("address")
    except SystemExit:
        facility["detail_error"] = "Could not fetch facility detail page."
    return facility


def fetch_pmn_facilities(kind: str) -> tuple[list[dict[str, Any]], str]:
    if kind != "pool":
        return [], urllib.parse.urljoin(PNCC_BASE, PNCC_SWIMMING_PATH)
    body, final_url, _ = fetch_pmn_text(PNCC_SWIMMING_PATH, PNCC_BASE)
    facilities = parse_pmn_pool_listing(body, final_url)
    return [enrich_pmn_facility(card) for card in facilities], final_url


def fetch_tga_facilities(kind: str) -> tuple[list[dict[str, Any]], str]:
    if kind == "library":
        return [], TGA_RECREATION_POOLS_URL
    _, council_url, _ = fetch_text_with_cdp(TGA_RECREATION_POOLS_URL, timeout=30)
    body, final_url, _ = fetch_text_with_cdp(TGA_POOL_LOCATIONS_URL, timeout=30)
    cards = parse_tga_location_cards(body, final_url, council_url)
    cards = enrich_tga_facilities(cards)
    if kind == "pool":
        facilities = cards
    elif kind == "gym":
        facilities = [c for c in cards if "gym" in (c.get("types") or [])]
    elif kind == "leisure-centre":
        facilities = [c for c in cards if "leisure-centre" in (c.get("types") or [])]
    else:
        facilities = []
    for facility in facilities:
        facility["facility_type"] = kind
    return facilities, final_url


def clone_qldc_facility(item: dict[str, Any], requested_type: str | None = None) -> dict[str, Any]:
    facility = dict(item)
    for key in ("facility_types", "features"):
        if isinstance(facility.get(key), list):
            facility[key] = list(facility[key])
    if isinstance(facility.get("hours"), list):
        facility["hours"] = [dict(x) for x in facility["hours"]]
    if requested_type and requested_type in facility.get("facility_types", []):
        facility["type"] = requested_type
    return facility


def fetch_qldc_facilities(kind: str) -> tuple[list[dict[str, Any]], str, str | None]:
    if kind == "library":
        return [], QLDC_RECREATION_SOURCE, "Libraries are outside this skill's recreation-focused data source."
    source_url = QLDC_SWIM_SOURCE if kind == "pool" else QLDC_RECREATION_SOURCE
    facilities = [
        clone_qldc_facility(item, kind)
        for item in QLDC_FACILITIES
        if kind in item.get("facility_types", [])
    ]
    note = None
    if kind == "pool":
        note = "QLDC operates three aquatic facilities; community pools listed here are grant-assisted and community-operated."
    return facilities, source_url, note


def parse_time_label(value: str) -> dt.datetime | None:
    for fmt in ("%I:%M %p", "%I %p"):
        try:
            return dt.datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def add_minutes(label: str, minutes: int) -> str:
    parsed = parse_time_label(label)
    if not parsed:
        return label
    return (parsed + dt.timedelta(minutes=minutes)).strftime("%-I:%M %p")


def parse_akl_availability(url: str) -> dict[str, Any]:
    body, final_url, _ = fetch_text(url, AKL_LEISURE_BASE)
    items_m = re.search(r':items="([^"]+)"', body, flags=re.I | re.S)
    dates_m = re.search(r':date-strings="([^"]+)"', body, flags=re.I | re.S)
    if not items_m or not dates_m:
        return {"source_url": final_url, "date": None, "resources": [], "note": "No public availability payload found."}
    try:
        items = json.loads(html.unescape(items_m.group(1)))
        dates = json.loads(html.unescape(dates_m.group(1)))
    except json.JSONDecodeError as exc:
        return {"source_url": final_url, "date": None, "resources": [], "note": f"Could not parse availability payload: {exc}"}
    if not isinstance(items, dict) or not isinstance(dates, list) or not dates:
        return {"source_url": final_url, "date": None, "resources": [], "note": "Availability payload had an unexpected shape."}

    # The portal returns a rolling window with the local-current day first.
    date_index = 0
    date_value = dates[date_index]
    resources: list[dict[str, Any]] = []
    for resource_name, periods in items.items():
        slots: list[tuple[dt.datetime, str, int]] = []
        if not isinstance(periods, dict):
            continue
        for period_slots in periods.values():
            if not isinstance(period_slots, dict):
                continue
            for time_label, values in period_slots.items():
                if not isinstance(values, list) or date_index >= len(values):
                    continue
                lanes = values[date_index]
                if not isinstance(lanes, int) or lanes <= 0:
                    continue
                parsed_time = parse_time_label(time_label)
                if parsed_time:
                    slots.append((parsed_time, time_label, lanes))
        slots.sort(key=lambda x: x[0])
        intervals: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        previous_time: dt.datetime | None = None
        previous_label: str | None = None
        for parsed_time, label, lanes in slots:
            contiguous = previous_time is not None and parsed_time - previous_time == dt.timedelta(minutes=15)
            if current and contiguous and current["available_lanes"] == lanes:
                current["end"] = add_minutes(label, 15)
            else:
                if current:
                    intervals.append(current)
                current = {"start": label, "end": add_minutes(label, 15), "available_lanes": lanes}
            previous_time = parsed_time
            previous_label = label
        if current:
            intervals.append(current)
        resources.append({"name": resource_name, "intervals": intervals})
    retrieved_m = re.search(r'<time[^>]*datetime="([^"]+)"[^>]*>(.*?)</time>', body, flags=re.I | re.S)
    return {
        "source_url": final_url,
        "date": date_value,
        "retrieved": html.unescape(retrieved_m.group(1)) if retrieved_m else None,
        "resources": resources,
    }


def unique_text(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = strip_tags(value) if "<" in value else re.sub(r"\s+", " ", html.unescape(value)).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            out.append(cleaned)
    return out


def html_table_rows(table_html: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for row_m in re.finditer(r"<tr\b[^>]*>(.*?)</tr>", table_html, flags=re.I | re.S):
        cells: list[str] = []
        for cell_m in re.finditer(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", row_m.group(1), flags=re.I | re.S):
            text = strip_tags(cell_m.group(1), br="; ")
            cells.append(text)
        if any(cells):
            rows.append(cells)
    return rows


def table_after(page_html: str, start_pattern: str) -> str:
    start = re.search(start_pattern, page_html, flags=re.I | re.S)
    if not start:
        return ""
    table = re.search(r"<table\b[^>]*>.*?</table>", page_html[start.end() :], flags=re.I | re.S)
    return table.group(0) if table else ""


def parse_ham_hours_table(table_html: str) -> list[dict[str, str]]:
    rows = html_table_rows(table_html)
    if len(rows) < 2:
        return []
    headers = rows[0][1:] if len(rows[0]) > 1 else []
    hours: list[dict[str, str]] = []
    for row in rows[1:]:
        label = row[0]
        if headers and len(row) > 1:
            parts = []
            for idx, value in enumerate(row[1:]):
                if value:
                    heading = headers[idx] if idx < len(headers) else f"Column {idx + 1}"
                    parts.append(f"{heading}: {value}")
            text = "; ".join(parts)
        else:
            text = row[1] if len(row) > 1 else label
        if label and text:
            hours.append({"label": label, "text": text})
    return hours


def parse_ham_address(address_html: str) -> str | None:
    spans = [strip_tags(x) for x in re.findall(r"<span\b[^>]*>(.*?)</span>", address_html, flags=re.I | re.S)]
    parts = [x for x in spans if x and x.lower() not in ("waikato", "new zealand")]
    if not parts:
        text = strip_tags(address_html, br=", ")
        return text or None
    if len(parts) >= 3 and re.fullmatch(r"\d{4}", parts[-1]):
        return f"{parts[0]}, {parts[1]} {parts[-1]}"
    return ", ".join(parts)


def parse_ham_contact_page(page_html: str) -> tuple[dict[str, dict[str, str | None]], str | None]:
    email_m = re.search(r'href=["\']mailto:([^"?\']+)', page_html, flags=re.I)
    email = html.unescape(email_m.group(1)).strip() if email_m else None
    contacts: dict[str, dict[str, str | None]] = {}
    for block_m in re.finditer(r'<section\b[^>]*class=["\'][^"\']*\blocation\b[^"\']*["\'][^>]*>(.*?)</section>', page_html, flags=re.I | re.S):
        block = block_m.group(1)
        name_m = re.search(r"<h2\b[^>]*>(.*?)</h2>", block, flags=re.I | re.S)
        if not name_m:
            continue
        name = strip_tags(name_m.group(1))
        phone_m = re.search(r'href=["\']tel:([^"\']+)["\'][^>]*>(.*?)</a>', block, flags=re.I | re.S)
        address_m = re.search(r"<address\b[^>]*>(.*?)</address>", block, flags=re.I | re.S)
        contacts[slug_text(name)] = {
            "phone": strip_tags(phone_m.group(2)) if phone_m else None,
            "phone_href": html.unescape(phone_m.group(1)).strip() if phone_m else None,
            "address": parse_ham_address(address_m.group(1)) if address_m else None,
        }
    return contacts, email


def parse_ham_detail_contact(page_html: str) -> dict[str, str | None]:
    phone_m = re.search(r'href=["\']tel:([^"\']+)["\'][^>]*>(.*?)</a>', page_html, flags=re.I | re.S)
    address_m = re.search(r"<address\b[^>]*>(.*?)</address>", page_html, flags=re.I | re.S)
    return {
        "phone": strip_tags(phone_m.group(2)) if phone_m else None,
        "phone_href": html.unescape(phone_m.group(1)).strip() if phone_m else None,
        "address": parse_ham_address(address_m.group(1)) if address_m else None,
    }


def parse_ham_main_pool(page_html: str, final_url: str, contacts: dict[str, dict[str, str | None]], email: str | None) -> dict[str, Any]:
    title_m = re.search(r"<title\b[^>]*>(.*?)</title>", page_html, flags=re.I | re.S)
    name = strip_tags(title_m.group(1)).split("|")[0].strip() if title_m else None
    if not name:
        json_ld = json_ld_objects(page_html)
        name = next((str(o.get("name")) for o in json_ld if o.get("name")), "Hamilton pool")
    facility_id = slug_text(name)

    intro = text_between(page_html, r'<div\b[^>]*class=["\']intro-content["\'][^>]*>', [r'<section\b[^>]*class=["\']timetable__outer', r'<div\b[^>]*class=["\']hours__outer'])
    description = strip_tags(intro).lstrip("> ") or None
    opening_hours = parse_ham_hours_table(table_after(page_html, r"<h3\b[^>]*>\s*Opening hours\s*</h3>"))
    public_holiday_hours = parse_ham_hours_table(table_after(page_html, r'<div\b[^>]*class=["\']hours__outer'))
    disclaimer_m = re.search(r'<p\b[^>]*class=["\']disclaimer["\'][^>]*>(.*?)</p>', page_html, flags=re.I | re.S)

    features_section = text_between(
        page_html,
        r"<h2\b[^>]*>\s*Features\s*</h2>",
        [r"<h2\b[^>]*>\s*Visiting", r'<div\b[^>]*class=["\'][^"\']*blogpostselement'],
    )
    feature_headings = [strip_tags(x) for x in re.findall(r"<h3\b[^>]*>(.*?)</h3>", features_section, flags=re.I | re.S)]
    feature_items = [strip_tags(x) for x in re.findall(r"<li\b[^>]*>(.*?)</li>", features_section, flags=re.I | re.S)]
    pool_details = unique_text(feature_items)
    features = unique_text(feature_headings + pool_details)

    detail_contact = parse_ham_detail_contact(page_html)
    fallback_contact = contacts.get(facility_id, {})

    return {
        "name": name,
        "id": facility_id,
        "type": "pool",
        "council": "ham",
        "council_name": "Hamilton",
        "source": "hamilton-pools",
        "source_url": final_url,
        "description": description,
        "address": detail_contact.get("address") or fallback_contact.get("address"),
        "operator": "Hamilton City Council",
        "status": None,
        "hours": opening_hours,
        "hours_summary": opening_hours[0]["text"] if opening_hours else None,
        "public_holiday_hours": public_holiday_hours,
        "hours_note": strip_tags(disclaimer_m.group(1)) if disclaimer_m else None,
        "phone": detail_contact.get("phone") or fallback_contact.get("phone"),
        "email": email,
        "features": features,
        "pool_details": pool_details,
    }


def parse_ham_pricing_blocks(page_html: str) -> dict[str, list[dict[str, str]]]:
    pricing: dict[str, list[dict[str, str]]] = {}
    for block_m in re.finditer(r'<section\b[^>]*class=["\'][^"\']*\bgym-class__box\b[^"\']*["\'][^>]*>(.*?)</section>', page_html, flags=re.I | re.S):
        block = block_m.group(1)
        title_m = re.search(r"<h3\b[^>]*>(.*?)</h3>", block, flags=re.I | re.S)
        if not title_m:
            continue
        title = strip_tags(title_m.group(1))
        items: list[dict[str, str]] = []
        for item_m in re.finditer(r"<p\b[^>]*>(.*?)</p>\s*<span\b[^>]*>(.*?)</span>", block, flags=re.I | re.S):
            label = strip_tags(item_m.group(1))
            value = strip_tags(item_m.group(2))
            if label or value:
                items.append({"label": label, "value": value})
        if items:
            pricing[slug_text(title)] = items
    return pricing


def parse_ham_partner_pools(page_html: str, final_url: str, contacts: dict[str, dict[str, str | None]]) -> list[dict[str, Any]]:
    detail_html = text_between(page_html, r"Everything You Need to Know About Our Partner Pools", [r'<div\b[^>]*class=["\'][^"\']*dnadesign__elemental__models__elementcontent'])
    detail_text = strip_tags(detail_html)
    page_text = strip_tags(page_html)
    closed_m = re.search(r"all partner pools are closed for the season as of (\d{1,2}\s+[A-Za-z]+\s+\d{4})", page_text, flags=re.I)
    closed_status = f"Closed for the season as of {closed_m.group(1)}" if closed_m else "Closed for the season"
    pricing = parse_ham_pricing_blocks(page_html)
    partner_contact = contacts.get("partner-pools", {})

    markers = [
        ("Te Rapa Primary", "Te Rapa Primary School Pool"),
        ("Fairfield College", "Fairfield College Pool"),
        ("Hillcrest Normal School", "Hillcrest Normal School Pool"),
        ("Hamilton Boys High School", "Hamilton Boys High School Pool"),
    ]
    facilities: list[dict[str, Any]] = []
    for idx, (marker, name) in enumerate(markers):
        next_markers = [re.escape(m[0]) for m in markers[idx + 1 :]]
        end_pat = "|".join(next_markers) if next_markers else "$"
        block_m = re.search(rf"{re.escape(marker)}\s+(.*?)(?={end_pat})", detail_text, flags=re.I | re.S)
        block = block_m.group(1).strip() if block_m else ""
        season_m = re.search(r"Opening season\s*:?\s*(.*?)(?:\s+Address\s*:|\s+Address\b|$)", block, flags=re.I | re.S)
        address_m = re.search(r"Address\s*:?\s*(.*?)(?:\s+Stay connected|\s+Follow|\s+Closed for the season|\s+Information for|\s+Private hire|\s+Community group hire|$)", block, flags=re.I | re.S)
        email_m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", block)
        follow_m = re.search(r"(?:Stay connected!\s*)?(Follow .*?)(?:\s+Closed for the season|\s+Private hire|\s+Community group hire|$)", block, flags=re.I | re.S)
        hire_m = re.search(r"((?:Private hire|Community group hire):\s*.*?)(?:$)", block, flags=re.I | re.S)

        season = re.sub(r"\s+", " ", season_m.group(1)).strip() if season_m else None
        address = re.sub(r"\s+", " ", address_m.group(1)).strip(" .") if address_m else None
        contact_note = strip_tags(follow_m.group(1)).replace(" Key information below", "") if follow_m else None
        hire_note = strip_tags(hire_m.group(1)) if hire_m else None
        if contact_note and hire_note:
            contact_note = f"{contact_note}; {hire_note}"
        elif hire_note:
            contact_note = hire_note

        facility_id = slug_text(name)
        price_key = slug_text(marker)
        if marker == "Te Rapa Primary":
            price_key = "te-rapa-primary-school"
        fees = pricing.get(price_key, [])
        hours = [{"label": "Opening season", "text": season}] if season else []
        pool_details = ["Outdoor partner pool", "Seasonal community access"]
        facilities.append(
            {
                "name": name,
                "id": facility_id,
                "type": "pool",
                "council": "ham",
                "council_name": "Hamilton",
                "source": "hamilton-pools",
                "source_url": final_url,
                "listing_source_url": final_url,
                "description": "Hamilton City Council seasonal partner pool.",
                "address": address,
                "operator": "Hamilton City Council partner pool",
                "status": closed_status if "closed for the season" in block.lower() or closed_m else None,
                "hours": hours,
                "hours_summary": closed_status if closed_m else (season or None),
                "hours_note": "Information for the next summer season will be updated on the Hamilton Pools partner-pools page.",
                "phone": partner_contact.get("phone"),
                "email": email_m.group(0) if email_m else None,
                "contact_note": contact_note,
                "features": pool_details,
                "pool_details": pool_details,
                "fees": fees,
            }
        )
    return facilities


def fetch_ham_facilities(kind: str) -> tuple[list[dict[str, Any]], str]:
    if kind != "pool":
        return [], HAM_POOLS_BASE
    home, home_url, _ = fetch_text("/", HAM_POOLS_BASE)
    discovered_paths: list[str] = []
    for href in re.findall(r'href=["\']([^"\']+/facilities/[^"\']+|/facilities/[^"\']+)["\']', home, flags=re.I):
        path = urllib.parse.urlparse(html.unescape(href)).path
        if path in HAM_MAIN_POOL_PATHS and path not in discovered_paths:
            discovered_paths.append(path)
    if not discovered_paths:
        discovered_paths = list(HAM_MAIN_POOL_PATHS)

    contact_body, _, _ = fetch_text("/contact", HAM_POOLS_BASE)
    contacts, email = parse_ham_contact_page(contact_body)
    facilities: list[dict[str, Any]] = []
    for path in discovered_paths:
        body, final_url, _ = fetch_text(path, HAM_POOLS_BASE)
        facility = parse_ham_main_pool(body, final_url, contacts, email)
        facility["listing_source_url"] = home_url
        facilities.append(facility)

    partner_body, partner_url, _ = fetch_text(HAM_PARTNER_POOLS_PATH, HAM_POOLS_BASE)
    facilities.extend(parse_ham_partner_pools(partner_body, partner_url, contacts))
    return facilities, home_url


def find_facility(cards: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    needle = slug_text(query)
    if not needle:
        return None

    def keys(card: dict[str, Any]) -> list[str]:
        values = [card.get("id"), card.get("name")]
        values.extend(card.get("aliases") or [])
        values.extend([card.get("former_name")])
        return [slug_text(str(v)) for v in values if v]

    exact = [c for c in cards if needle in keys(c)]
    if exact:
        return exact[0]
    contains = [
        c
        for c in cards
        if any(needle in key or (len(key) > 3 and key in needle) for key in keys(c))
    ]
    return contains[0] if contains else None


def regional_pool_cards(council: str) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    if council not in REGIONAL_POOL_CATALOG:
        return [], "", {"ok": False, "method": "unsupported", "status": None, "url": None}
    source_url = REGIONAL_LISTING_URLS[council]
    probe = source_probe(source_url)
    cards = copy.deepcopy(REGIONAL_POOL_CATALOG[council])
    for card in cards:
        card["source_status"] = "live source checked" if probe["ok"] else "catalog fallback; source probe failed"
        card["source_probe"] = probe
    return cards, source_url, probe


def regional_pool_detail(card: dict[str, Any]) -> dict[str, Any]:
    facility = copy.deepcopy(card)
    probe = source_probe(str(card.get("source_url") or ""))
    facility["source_probe"] = probe
    facility["source_status"] = "live source checked" if probe["ok"] else "catalog fallback; source probe failed"
    return facility


def pool_detail_for_council(council: str, name: str) -> tuple[dict[str, Any] | None, str, list[str]]:
    if council == "akl":
        cards, listing_url = akl_location_listing("pool", None)
        card = find_facility(cards, name)
        if not card:
            return None, listing_url, [c["name"] for c in cards[:10]]
        body, final_url, _ = fetch_text(card["source_url"], AKL_LEISURE_BASE)
        facility = parse_akl_detail(body, final_url, card)
        availability = None
        if facility.get("resource_availability_url"):
            availability = parse_akl_availability(facility["resource_availability_url"])
        return {
            "facility": facility,
            "lane_availability_today": availability,
        }, listing_url, []
    if council == "wlg":
        cards, listing_url = fetch_wlg_facilities("pool")
        card = find_facility(cards, name)
        if not card:
            return None, listing_url, [c["name"] for c in cards[:10]]
        return {
            "facility": card,
            "lane_availability_today": None,
        }, listing_url, []
    if council == "rot":
        cards, listing_url = fetch_rot_facilities("pool")
        card = find_facility(cards, name)
        if not card:
            return None, listing_url, [c["name"] for c in cards[:10]]
        return {
            "facility": card,
            "lane_availability_today": None,
        }, listing_url, []
    if council == "npl":
        cards, listing_url = fetch_npl_facilities("pool")
        card = find_facility(cards, name)
        if not card:
            return None, listing_url, [c["name"] for c in cards[:10]]
        return {
            "facility": card,
            "lane_availability_today": None,
        }, listing_url, []
    if council == "pmn":
        cards, listing_url = fetch_pmn_facilities("pool")
        card = find_facility(cards, name)
        if not card:
            return None, listing_url, [c["name"] for c in cards[:10]]
        return {
            "facility": card,
            "lane_availability_today": None,
        }, listing_url, []
    if council == "tga":
        cards, listing_url = fetch_tga_facilities("pool")
        card = find_facility(cards, name)
        if not card:
            return None, listing_url, [c["name"] for c in cards[:10]]
        return {
            "facility": card,
            "lane_availability_today": None,
        }, listing_url, []
    if council in {"npr", "has", "nsn", "tdc"}:
        cards, listing_url = static_recreation_facilities(council, "pool")
        card = find_facility(cards, name)
        if not card:
            return None, listing_url, [c["name"] for c in cards[:10]]
        return {
            "facility": card,
            "lane_availability_today": None,
        }, listing_url, []
    if council == "qldc":
        cards, listing_url, _ = fetch_qldc_facilities("pool")
        card = find_facility(cards, name)
        if not card:
            return None, listing_url, [c["name"] for c in cards[:10]]
        return {
            "facility": clone_qldc_facility(card, "pool"),
            "lane_availability_today": None,
        }, listing_url, []
    if council == "ham":
        cards, listing_url = fetch_ham_facilities("pool")
        card = find_facility(cards, name)
        if not card:
            return None, listing_url, [c["name"] for c in cards[:10]]
        return {
            "facility": card,
            "lane_availability_today": None,
        }, listing_url, []
    if council == "dud":
        cards, listing_url = fetch_dud_facilities("pool")
        card = find_facility(cards, name)
        if not card:
            return None, listing_url, [c["name"] for c in cards[:10]]
        return {
            "facility": card,
            "lane_availability_today": None,
        }, listing_url, []
    if council in REGIONAL_POOL_CATALOG:
        cards, listing_url, _ = regional_pool_cards(council)
        card = find_facility(cards, name)
        if not card:
            return None, listing_url, [c["name"] for c in cards[:10]]
        return {
            "facility": regional_pool_detail(card),
            "lane_availability_today": None,
        }, listing_url, []
    if council == "whg":
        cards, listing_url, note = fetch_whg_facilities("pool")
        card = find_facility(cards, name)
        if not card:
            return None, listing_url, [c["name"] for c in cards[:10]]
        return {
            "facility": card,
            "lane_availability_today": None,
            "note": note,
        }, listing_url, []
    if council == "chc":
        cards, listing_url = fetch_chc_facilities("pool")
        cards = enrich_chc_details(cards)
        card = find_facility(cards, name)
        if not card:
            return None, listing_url, [c["name"] for c in cards[:12]]
        return {
            "facility": card,
            "lane_availability_today": card.get("public_swim_availability"),
        }, listing_url, []
    die(f"unsupported council {council!r}")


def cmd_pools(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    note = None
    if args.council == "akl":
        pools, source_url = akl_location_listing("pool", args.region)
        pools = pools[: args.limit]
        pools = enrich_akl_hours(pools)
    elif args.council == "wlg":
        pools, source_url = fetch_wlg_facilities("pool")
        if args.region:
            die("--region is only supported for Auckland pools")
        pools = pools[: args.limit]
    elif args.council == "rot":
        if args.region:
            die("--region is only supported for Auckland pools")
        pools, source_url = fetch_rot_facilities("pool")
        pools = pools[: args.limit]
    elif args.council == "npl":
        if args.region:
            die("--region is only supported for Auckland pools")
        pools, source_url = fetch_npl_facilities("pool")
        pools = pools[: args.limit]
    elif args.council in {"npr", "has", "nsn", "tdc"}:
        if args.region:
            die("--region is only supported for Auckland pools")
        pools, source_url = static_recreation_facilities(args.council, "pool")
        pools = pools[: args.limit]
    elif args.council == "ham":
        if args.region:
            die("--region is only supported for Auckland pools")
        pools, source_url = fetch_ham_facilities("pool")
        note = "Hamilton Pools currently lists Waterworld, Gallagher Aquatic Centre, and seasonal partner pools; Founders Memorial Theatre Pool is not listed as an active pool."
        pools = pools[: args.limit]
    elif args.council == "dud":
        if args.region:
            die("--region is only supported for Auckland pools")
        pools, source_url = fetch_dud_facilities("pool")
        pools = pools[: args.limit]
    elif args.council in REGIONAL_POOL_CATALOG:
        if args.region:
            die("--region is only supported for Auckland pools")
        pools, source_url, _ = regional_pool_cards(args.council)
        pools = pools[: args.limit]
    elif args.council == "whg":
        if args.region:
            die("--region is only supported for Auckland pools")
        pools, source_url, note = fetch_whg_facilities("pool")
    elif args.council == "pmn":
        pools, source_url = fetch_pmn_facilities("pool")
        if args.region:
            die("--region is only supported for Auckland pools")
        pools = pools[: args.limit]
    elif args.council == "tga":
        if args.region:
            die("--region is only supported for Auckland pools")
        pools, source_url = fetch_tga_facilities("pool")
        pools = pools[: args.limit]
    elif args.council == "qldc":
        if args.region:
            die("--region is only supported for Auckland pools")
        pools, source_url, note = fetch_qldc_facilities("pool")
        pools = pools[: args.limit]
    else:
        if args.region:
            die("--region is only supported for Auckland pools")
        pools, source_url = fetch_chc_facilities("pool")
        pools = pools[: args.limit]
        pools = enrich_chc_details(pools)

    data = {
        "query": {"council": args.council, "region": args.region, "limit": args.limit},
        "source_url": source_url,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "note": note,
        "pools": pools,
    }
    emit_facility_list(data, "pools", args.json)


def cmd_pool(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    councils = [args.council] if args.council else ["dud", "qldc", "whg", "npr", "has", "npl", "nsn", "tdc", "rot", "akl", "tga", "wlg", "ham", "hutt", "porirua", "uhutt", "kapiti", "chc", "pmn"]
    suggestions_by_council: list[str] = []
    for council in councils:
        detail, listing_url, suggestions = pool_detail_for_council(council, args.name)
        if detail:
            query = {"council": council, "name": args.name}
            if args.council is None:
                query["matched_by"] = "auto-council-search"
                query["searched_councils"] = councils
            data = {
                "query": query,
                "listing_source_url": listing_url,
                "elapsed_ms": round((time.perf_counter() - started) * 1000),
                "facility": detail["facility"],
                "lane_availability_today": detail["lane_availability_today"],
            }
            if detail.get("note"):
                data["note"] = detail["note"]
            emit_pool_detail(data, args.json)
            return
        if suggestions:
            suggestion_text = ", ".join(suggestions)
            if args.council is None:
                suggestion_text = f"{COUNCIL_NAMES.get(council, council)}: {suggestion_text}"
            suggestions_by_council.append(suggestion_text)
    searched = ", ".join(COUNCIL_NAMES.get(c, c) for c in councils)
    hint = "; ".join(suggestions_by_council[:3])
    if hint:
        die(f"no pool matched {args.name!r} in {searched}. Try one of: {hint}")
    die(f"no pool matched {args.name!r} in {searched}")


def cmd_facilities(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    if args.council == "akl":
        lookup_type = args.type
        cards, source_url = akl_location_listing(lookup_type if lookup_type in ("pool", "gym", "leisure-centre", "library") else None, args.region)
        facilities = cards[: args.limit]
        note = None
        if args.type == "library":
            note = "Auckland Leisure does not list libraries; v1 is scoped to recreation facilities."
    elif args.council == "wlg":
        if args.region:
            die("--region is only supported for Auckland facilities")
        if args.type == "gym":
            facilities, source_url = [], WLG_BASE
            note = "Wellington gym listings are not wired in v1."
        elif args.type == "library":
            facilities, source_url = [], WLG_BASE
            note = "Libraries are outside this skill's recreation-focused v1 data source."
        else:
            facilities, source_url = fetch_wlg_facilities(args.type)
            note = None
        facilities = facilities[: args.limit]
    elif args.council == "rot":
        if args.region:
            die("--region is only supported for Auckland facilities")
        if args.type == "library":
            facilities, source_url = [], ROT_RECREATION_SOURCE_URL
            note = "Libraries are outside this skill's recreation-focused v1 data source."
        else:
            facilities, source_url = fetch_rot_facilities(args.type)
            note = None
            if args.type == "gym":
                note = "Rotorua Aquatic Centre includes a gym; linked operator pages have current programme details."
        facilities = facilities[: args.limit]
    elif args.council in {"npr", "has", "nsn", "tdc"}:
        if args.region:
            die("--region is only supported for Auckland facilities")
        facilities, source_url = static_recreation_facilities(args.council, args.type)
        note = None
        if args.type == "library":
            note = "Libraries are outside this skill's recreation-focused data source."
        elif args.council in {"npr", "has"} and args.type != "pool":
            note = f"{COUNCIL_NAMES[args.council]} recreation support currently covers aquatic facilities only."
        facilities = facilities[: args.limit]
    elif args.council == "npl":
        if args.region:
            die("--region is only supported for Auckland facilities")
        if args.type == "pool":
            facilities, source_url = fetch_npl_facilities("pool")
            note = None
        else:
            facilities, source_url = [], NPL_COMMUNITY_POOLS_URL
            note = "New Plymouth recreation support is scoped to public pools in v1."
        facilities = facilities[: args.limit]
    elif args.council == "ham":
        if args.region:
            die("--region is only supported for Auckland facilities")
        if args.type == "pool":
            facilities, source_url = fetch_ham_facilities("pool")
            note = "Hamilton Pools currently lists Waterworld, Gallagher Aquatic Centre, and seasonal partner pools; Founders Memorial Theatre Pool is not listed as an active pool."
        elif args.type == "leisure-centre":
            facilities, source_url = fetch_ham_facilities("pool")
            note = "Hamilton Pools publishes aquatic recreation facilities; returned pool facilities for this recreation-centre-style query."
        elif args.type == "gym":
            facilities, source_url = [], HAM_POOLS_BASE
            note = "Hamilton gym listings are not wired; Hamilton Pools pages mention gym/fitness but this skill is scoped to pool facilities."
        else:
            facilities, source_url = [], HAM_POOLS_BASE
            note = "Libraries are outside this skill's recreation-focused data source."
        facilities = facilities[: args.limit]
    elif args.council == "dud":
        if args.region:
            die("--region is only supported for Auckland facilities")
        if args.type == "pool":
            facilities, source_url = fetch_dud_facilities("pool")
            note = None
        elif args.type == "leisure-centre":
            facilities, source_url = fetch_dud_facilities("leisure-centre")
            note = None
        elif args.type == "gym":
            facilities, source_url = [], DUD_BASE
            note = "Dunedin gym listings are not wired in v1; Moana Pool includes a gym on its pool detail."
        else:
            facilities, source_url = [], DUD_BASE
            note = "Libraries are outside this skill's recreation-focused v1 data source."
        facilities = facilities[: args.limit]
    elif args.council in REGIONAL_POOL_CATALOG:
        if args.region:
            die("--region is only supported for Auckland facilities")
        source_url = REGIONAL_LISTING_URLS[args.council]
        if args.type == "pool":
            facilities, source_url, _ = regional_pool_cards(args.council)
            facilities = facilities[: args.limit]
            note = None
        else:
            facilities = []
            note = f"{COUNCIL_NAMES.get(args.council, args.council)} recreation support is currently wired for public aquatic facilities only."
    elif args.council == "whg":
        if args.region:
            die("--region is only supported for Auckland facilities")
        facilities, source_url, note = fetch_whg_facilities(args.type)
    elif args.council == "pmn":
        if args.region:
            die("--region is only supported for Auckland facilities")
        if args.type == "pool":
            facilities, source_url = fetch_pmn_facilities("pool")
            note = None
        else:
            facilities, source_url = [], urllib.parse.urljoin(PNCC_BASE, PNCC_SWIMMING_PATH)
            note = "Palmerston North recreation is wired for council-listed swimming facilities only."
        facilities = facilities[: args.limit]
    elif args.council == "tga":
        if args.region:
            die("--region is only supported for Auckland facilities")
        if args.type == "library":
            facilities, source_url = [], TGA_RECREATION_POOLS_URL
            note = "Libraries are outside this skill's recreation-focused Tauranga pool source."
        else:
            facilities, source_url = fetch_tga_facilities(args.type)
            note = None
        facilities = facilities[: args.limit]
    elif args.council == "qldc":
        if args.region:
            die("--region is only supported for Auckland facilities")
        facilities, source_url, note = fetch_qldc_facilities(args.type)
        facilities = facilities[: args.limit]
    else:
        if args.region:
            die("--region is only supported for Auckland facilities")
        if args.type == "library":
            facilities, source_url = [], CHC_REC_BASE
            note = "Libraries are outside this skill's recreation-focused Christchurch data source."
        else:
            facilities, source_url = fetch_chc_facilities(args.type)
            facilities = facilities[: args.limit]
            facilities = enrich_chc_details(facilities)
            note = None

    data = {
        "query": {"council": args.council, "type": args.type, "region": args.region, "limit": args.limit},
        "source_url": source_url,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "note": note,
        "facilities": facilities,
    }
    emit_facility_list(data, "facilities", args.json)


def emit_event_list(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        return
    print(f"Events: showing {len(data['events'])} from {data['source']} ({data['elapsed_ms']} ms)")
    for source_url in data["source_urls"][:3]:
        print(f"Source: {source_url}")
    print()
    for item in data["events"]:
        print(item.get("title"))
        bits = [item.get("date_text") or item.get("start"), item.get("location"), item.get("category")]
        print("  " + " | ".join(str(x) for x in bits if x))
        if item.get("badges"):
            print("  " + "; ".join(item["badges"][:3]))
        print(f"  id: {item.get('id')}")
        print(f"  {item.get('url')}")
        print()


def emit_event_detail(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        return
    event = data["event"]
    print(event.get("title"))
    print(f"  {event.get('venue') or ''}")
    address = event.get("address") or {}
    address_text = ", ".join(str(x) for x in [address.get("street"), address.get("locality"), address.get("country")] if x)
    if address_text:
        print(f"  {address_text}")
    for session in event.get("sessions", [])[:8]:
        print(f"  {session.get('start')} - {session.get('end')}")
    if event.get("offers"):
        prices = [f"{o.get('name')}: ${o.get('price')}" for o in event["offers"][:5] if o.get("price")]
        if prices:
            print("  " + "; ".join(prices))
    print(f"  {event.get('url') or data.get('source_url')}")


def emit_facility_list(data: dict[str, Any], key: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        return
    rows = data[key]
    print(f"{key.title()}: showing {len(rows)} ({data['elapsed_ms']} ms)")
    print(f"Source: {data.get('source_url')}")
    if data.get("note"):
        print(f"Note: {data['note']}")
    print()
    for item in rows:
        print(item.get("name"))
        bits = [item.get("address"), item.get("hours_summary") or item.get("hours_note"), item.get("status")]
        for bit in bits:
            if bit:
                print(f"  {bit}")
        print(f"  {item.get('source_url')}")
        print()


def emit_pool_detail(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        return
    facility = data["facility"]
    print(facility.get("name"))
    for bit in [facility.get("address"), facility.get("hours_summary"), facility.get("phone"), facility.get("email")]:
        if bit:
            print(f"  {bit}")
    if facility.get("features"):
        print("  features: " + ", ".join(facility["features"][:10]))
    if facility.get("pool_details"):
        detail_names = [d.get("name") for d in facility["pool_details"][:5] if d.get("name")]
        if detail_names:
            print("  pools: " + ", ".join(detail_names))
    for detail_key in ("pool_details", "gym_details"):
        for detail in (facility.get(detail_key) or [])[:3]:
            if detail.get("label") and detail.get("text"):
                print(f"  {detail['label']}: {detail['text']}")
    availability = data.get("lane_availability_today")
    if availability and availability.get("resources"):
        print(f"  lane availability date: {availability.get('date')}")
        for resource in availability["resources"][:3]:
            intervals = resource.get("intervals") or []
            if intervals:
                first = intervals[0]
                print(f"  {resource['name']}: {first['start']}-{first['end']} ({first['available_lanes']} lanes)")
    elif availability and availability.get("summary"):
        print(f"  public swim: {availability.get('summary')}")
    print(f"  {facility.get('source_url')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only NZ council events, pools, and recreation facilities")
    sub = parser.add_subparsers(dest="command", required=True)

    events = sub.add_parser("events", help="list council-area public events")
    events.add_argument("--council", choices=sorted(COUNCIL_LOCATIONS), help="council area code")
    events.add_argument("--from", dest="date_from", help="start date filter, ISO yyyy-mm-dd")
    events.add_argument("--to", dest="date_to", help="end date filter, ISO yyyy-mm-dd")
    events.add_argument("--category", help="Eventfinda category slug, e.g. concerts-gig-guide")
    events.add_argument("--free", action="store_true", help="only include events with a visible free badge/text match")
    events.add_argument("--limit", type=int, default=10, help="maximum events to emit")
    events.add_argument("--json", action="store_true", help="emit JSON")
    events.add_argument("--browser", action="store_true", help="use optional CloakBrowser for public pages that direct HTTP cannot fetch")
    events.set_defaults(func=cmd_events)

    event = sub.add_parser("event", help="show one event detail from an Eventfinda URL/path id")
    event.add_argument("id_or_url", help="event id/path from events output, or a full Eventfinda event URL")
    event.add_argument("--json", action="store_true", help="emit JSON")
    event.add_argument("--browser", action="store_true", help="use optional CloakBrowser for public pages that direct HTTP cannot fetch")
    event.set_defaults(func=cmd_event)

    pools = sub.add_parser("pools", help="list public pools with available hours where supported")
    pools.add_argument("--council", choices=RECREATION_COUNCILS, default="akl", help="council recreation source")
    pools.add_argument("--region", choices=sorted(AKL_AREA_IDS), help="Auckland region filter")
    pools.add_argument("--limit", type=int, default=50, help="maximum pools to emit")
    pools.add_argument("--json", action="store_true", help="emit JSON")
    pools.add_argument("--browser", action="store_true", help="use optional CloakBrowser for public pages that direct HTTP cannot fetch")
    pools.set_defaults(func=cmd_pools)

    pool = sub.add_parser("pool", help="show one pool detail and lane availability where supported")
    pool.add_argument("name", help="pool name or slug, e.g. Tepid Baths")
    pool.add_argument("--council", choices=RECREATION_COUNCILS, help="council recreation source; searches supported councils when omitted")
    pool.add_argument("--json", action="store_true", help="emit JSON")
    pool.add_argument("--browser", action="store_true", help="use optional CloakBrowser for public pages that direct HTTP cannot fetch")
    pool.set_defaults(func=cmd_pool)

    facilities = sub.add_parser("facilities", help="list recreation facilities")
    facilities.add_argument("--council", choices=RECREATION_COUNCILS, default="akl", help="council recreation source")
    facilities.add_argument("--type", choices=["pool", "gym", "leisure-centre", "library"], default="pool", help="facility type")
    facilities.add_argument("--region", choices=sorted(AKL_AREA_IDS), help="Auckland region filter")
    facilities.add_argument("--limit", type=int, default=50, help="maximum facilities to emit")
    facilities.add_argument("--json", action="store_true", help="emit JSON")
    facilities.add_argument("--browser", action="store_true", help="use optional CloakBrowser for public pages that direct HTTP cannot fetch")
    facilities.set_defaults(func=cmd_facilities)

    return parser


def main() -> None:
    global BROWSER_MODE
    parser = build_parser()
    args = parser.parse_args()
    BROWSER_MODE = bool(getattr(args, "browser", False))
    if hasattr(args, "limit"):
        args.limit = min(max(1, args.limit), 100)
    try:
        if BROWSER_MODE:
            try:
                import cloakbrowser  # noqa: F401
            except Exception as exc:
                raise BrowserUnavailableError(
                    "cloakbrowser_not_installed: install CloakBrowser to use --browser for nz-council public pages."
                ) from exc
        args.func(args)
    except BrowserUnavailableError as exc:
        payload = {
            "error": "cloakbrowser_not_installed",
            "message": str(exc),
            "recommendation": "Recommend that the user installs CloakBrowser or reruns without --browser for direct public HTTP / legacy CDP fallback.",
        }
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"ERROR: {payload['message']}", file=sys.stderr)
            print(f"Recommendation: {payload['recommendation']}", file=sys.stderr)
        raise SystemExit(2)
    except BrowserBlockedError as exc:
        payload = {
            "error": "browser_blocked",
            "message": str(exc),
            "recommendation": "Rerun without --browser for direct public HTTP / legacy CDP fallback, or retry later; do not attempt to bypass CAPTCHA/challenge pages.",
        }
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"ERROR: {payload['message']}", file=sys.stderr)
            print(f"Recommendation: {payload['recommendation']}", file=sys.stderr)
        raise SystemExit(3)


if __name__ == "__main__":
    main()
