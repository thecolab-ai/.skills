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
import html
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

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
CDP_HTTP_BASE = "http://127.0.0.1:5100"

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
}

RECREATION_COUNCILS = ("akl", "wlg", "chc", "rot", "npl", "npr", "has", "ham", "hutt", "porirua", "uhutt", "kapiti")

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
}

HAM_MAIN_POOL_PATHS = (
    "/facilities/waterworld",
    "/facilities/gallagher-aquatic-centre",
)

HAM_PARTNER_POOLS_PATH = "/facilities/partner-pools"

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
) -> tuple[str | None, str, int | None, str | None]:
    url = resolve_url(url_or_path, base)

    req_headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/json",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            return body, resp.geturl(), resp.status, None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        message = strip_tags(raw)[:240] or e.reason
        return raw, url, e.code, f"HTTP {e.code} from {url}: {message}"
    except urllib.error.URLError as e:
        return None, url, None, f"network error calling {url}: {e.reason}"


def fetch_text(url_or_path: str, base: str = "", headers: dict[str, str] | None = None, timeout: int = 30) -> tuple[str, str, int]:
    body, final_url, status, error = fetch_text_result(url_or_path, base, headers, timeout)
    if error:
        die(error)
    return body or "", final_url, status or 0


def strip_tags(value: str, br: str = " ") -> str:
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<br\s*/?>", br, value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip(" |;\t\r\n")


def attr(tag: str, name: str) -> str | None:
    m = re.search(rf"\b{name}=['\"]([^'\"]+)['\"]", tag, flags=re.I)
    return html.unescape(m.group(1)) if m else None


def absolutize(url: str | None, base: str) -> str | None:
    if not url:
        return None
    return urllib.parse.urljoin(base, html.unescape(url))


def slug_text(value: str) -> str:
    value = html.unescape(value).lower()
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
        deadline = time.time() + timeout
        best_html = None
        while time.time() < deadline:
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
                if not is_bot_wall(value) and not is_missing_page(value):
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
        cdp_body = fetch_text_via_cdp(final_url)
        if cdp_body and not is_bot_wall(cdp_body) and not is_missing_page(cdp_body):
            return cdp_body, final_url, 200, "cdp"
    if error:
        return None, final_url, status, error
    if body and is_bot_wall(body):
        return None, final_url, status, "bot-wall"
    return None, final_url, status, "missing-page"


def source_probe(url: str) -> dict[str, Any]:
    _, final_url, status, method = try_fetch_live_page(url)
    ok = method in {"direct", "cdp"}
    return {"ok": ok, "method": method, "status": status, "url": final_url}


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
    source_url = {"npr": NPR_AQUATIC_SOURCE_URL, "has": HAS_SWIMMING_POOLS_URL}.get(council, "")
    facilities: list[dict[str, Any]] = []
    for item in STATIC_RECREATION_FACILITIES.get(council, []):
        item_type = item.get("type")
        if kind == "pool" and item_type not in {"pool", "water-park", "aquatic-centre"}:
            continue
        if kind and kind != "pool" and item_type != kind:
            continue
        facility = dict(item)
        facility["id"] = facility.get("id") or slug_text(str(facility.get("name") or ""))
        facilities.append(facility)
    return facilities, source_url


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
    if council in {"npr", "has"}:
        cards, listing_url = static_recreation_facilities(council, "pool")
        card = find_facility(cards, name)
        if not card:
            return None, listing_url, [c["name"] for c in cards[:10]]
        return {
            "facility": card,
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
    if council in REGIONAL_POOL_CATALOG:
        cards, listing_url, _ = regional_pool_cards(council)
        card = find_facility(cards, name)
        if not card:
            return None, listing_url, [c["name"] for c in cards[:10]]
        return {
            "facility": regional_pool_detail(card),
            "lane_availability_today": None,
        }, listing_url, []
    die("Christchurch pool detail is not wired in v1")


def cmd_pools(args: argparse.Namespace) -> None:
    started = time.perf_counter()
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
    elif args.council in {"npr", "has"}:
        if args.region:
            die("--region is only supported for Auckland pools")
        pools, source_url = static_recreation_facilities(args.council, "pool")
        pools = pools[: args.limit]
    elif args.council == "ham":
        if args.region:
            die("--region is only supported for Auckland pools")
        pools, source_url = fetch_ham_facilities("pool")
        pools = pools[: args.limit]
    elif args.council in REGIONAL_POOL_CATALOG:
        if args.region:
            die("--region is only supported for Auckland pools")
        pools, source_url, _ = regional_pool_cards(args.council)
        pools = pools[: args.limit]
    else:
        die("Christchurch pools are not wired in v1 because the public council recreation source is JS/vendor-backed")

    data = {
        "query": {"council": args.council, "region": args.region, "limit": args.limit},
        "source_url": source_url,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "note": "Hamilton Pools currently lists Waterworld, Gallagher Aquatic Centre, and seasonal partner pools; Founders Memorial Theatre Pool is not listed as an active pool." if args.council == "ham" else None,
        "pools": pools,
    }
    emit_facility_list(data, "pools", args.json)


def cmd_pool(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    councils = [args.council] if args.council else ["npr", "has", "npl", "rot", "akl", "wlg", "ham", "hutt", "porirua", "uhutt", "kapiti"]
    suggestions_by_council: list[str] = []
    for council in councils:
        detail, listing_url, suggestions = pool_detail_for_council(council, args.name)
        if detail:
            data = {
                "query": {"council": council, "name": args.name},
                "listing_source_url": listing_url,
                "elapsed_ms": round((time.perf_counter() - started) * 1000),
                "facility": detail["facility"],
                "lane_availability_today": detail["lane_availability_today"],
            }
            emit_pool_detail(data, args.json)
            return
        if suggestions:
            suggestions_by_council.append(f"{COUNCIL_NAMES.get(council, council)}: {', '.join(suggestions)}")
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
    elif args.council in {"npr", "has"}:
        if args.region:
            die("--region is only supported for Auckland facilities")
        facilities, source_url = static_recreation_facilities(args.council, args.type)
        note = None
        if args.type != "pool":
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
    else:
        facilities, source_url = [], "https://recandsport.ccc.govt.nz/"
        note = "Christchurch recreation uses a vendor-backed source that is documented in references but not wired in v1."

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
    availability = data.get("lane_availability_today")
    if availability and availability.get("resources"):
        print(f"  lane availability date: {availability.get('date')}")
        for resource in availability["resources"][:3]:
            intervals = resource.get("intervals") or []
            if intervals:
                first = intervals[0]
                print(f"  {resource['name']}: {first['start']}-{first['end']} ({first['available_lanes']} lanes)")
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
    events.set_defaults(func=cmd_events)

    event = sub.add_parser("event", help="show one event detail from an Eventfinda URL/path id")
    event.add_argument("id_or_url", help="event id/path from events output, or a full Eventfinda event URL")
    event.add_argument("--json", action="store_true", help="emit JSON")
    event.set_defaults(func=cmd_event)

    pools = sub.add_parser("pools", help="list public pools with available hours where supported")
    pools.add_argument("--council", choices=RECREATION_COUNCILS, default="akl", help="council recreation source")
    pools.add_argument("--region", choices=sorted(AKL_AREA_IDS), help="Auckland region filter")
    pools.add_argument("--limit", type=int, default=50, help="maximum pools to emit")
    pools.add_argument("--json", action="store_true", help="emit JSON")
    pools.set_defaults(func=cmd_pools)

    pool = sub.add_parser("pool", help="show one pool detail and lane availability where supported")
    pool.add_argument("name", help="pool name or slug, e.g. Tepid Baths")
    pool.add_argument("--council", choices=RECREATION_COUNCILS, help="council recreation source; searches supported councils when omitted")
    pool.add_argument("--json", action="store_true", help="emit JSON")
    pool.set_defaults(func=cmd_pool)

    facilities = sub.add_parser("facilities", help="list recreation facilities")
    facilities.add_argument("--council", choices=RECREATION_COUNCILS, default="akl", help="council recreation source")
    facilities.add_argument("--type", choices=["pool", "gym", "leisure-centre", "library"], default="pool", help="facility type")
    facilities.add_argument("--region", choices=sorted(AKL_AREA_IDS), help="Auckland region filter")
    facilities.add_argument("--limit", type=int, default=50, help="maximum facilities to emit")
    facilities.add_argument("--json", action="store_true", help="emit JSON")
    facilities.set_defaults(func=cmd_facilities)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "limit"):
        args.limit = min(max(1, args.limit), 100)
    args.func(args)


if __name__ == "__main__":
    main()
