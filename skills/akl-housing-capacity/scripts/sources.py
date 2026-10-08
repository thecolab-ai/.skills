"""Verified public source registry; inventory entries are not fetched observations."""
COUNCIL = "Auckland Council"
HUD = "Ministry for Cities, Environment, Regions and Transport (formerly HUD)"
HOUSING_PAGE = "https://knowledgeauckland.org.nz/publications/auckland-monthly-housing-update-datasheet/"
CAPACITY_PAGE = "https://knowledgeauckland.org.nz/publications/auckland-council-capacity-for-growth-study-20222023-data-housing/"
HUD_PAGE = "https://www.hud.govt.nz/stats-and-insights/the-government-housing-dashboard/further-information"
CAPACITY_URL = "https://knowledgeauckland.org.nz/media/gzyj4pvk/auckland-council-hba-2023-pc78-outputs-from-housing-and-housing-hba-models-october-2023-v2-unlinked.xlsx"
FEASIBILITY_URL = "https://knowledgeauckland.org.nz/media/2xdluxge/auckland-council-hba-2023-feasibilitysummary_by_lb.xlsx"
BUSINESS_URL = "https://knowledgeauckland.org.nz/media/hv2j4xcw/pec-business.zip"
DEMOLITIONS_URL = "https://www.kaingaora.govt.nz/assets/Publications/OIAs-Official-Information-Requests/August-2025/26-August-2025-Demolished-Social-Housing-Statistcs.pdf?v=e3bf5397c490918b2b6b4d7d0743bd9abb1a3152"
HOSTS = {"knowledgeauckland.org.nz", "www.knowledgeauckland.org.nz", "www.hud.govt.nz", "www.kaingaora.govt.nz"}

SOURCES = [
    {"id": "housing-update", "publisher": COUNCIL, "source_url": HOUSING_PAGE,
     "download_url": "https://knowledgeauckland.org.nz/media/rayokdv3/auckland-monthly-housing-update-datasheet-09september-2026.xlsx",
     "format": "XLSX", "command": "housing-update", "status": "supported", "latest_data": "2026-08",
     "note": "Discovers the current datasheet link at runtime; different series have different observation months."},
    {"id": "capacity", "publisher": COUNCIL, "source_url": CAPACITY_URL,
     "landing_page": CAPACITY_PAGE, "format": "XLSX", "latest_data": "October 2023",
     "command": "capacity", "status": "supported",
     "note": "PC78 model local-board totals; no zoning polygons or site-level records."},
    {"id": "feasibility", "publisher": COUNCIL, "source_url": FEASIBILITY_URL,
     "landing_page": CAPACITY_PAGE, "format": "XLSX", "latest_data": "2023",
     "command": "capacity --detail typology", "status": "supported",
     "note": "Max_Profit and MinDUPrice are alternative selections; do not sum them."},
    {"id": "residential-geodatabases", "publisher": COUNCIL,
     "source_url": "https://knowledgeauckland.org.nz/publications/auckland-council-capacity-for-growth-study-20222023-data-residential-capacity-part-1/",
     "download_url": "https://knowledgeauckland.org.nz/media/42kl1kwk/pec-residential-part1.zip",
     "format": "File Geodatabase ZIP", "latest_data": "2023", "status": "GIS software required",
     "note": "Landing page and 43,333,422-byte keyless download headers verified. Large residential archive not parsed here."},
    {"id": "residential-geodatabases-part2", "publisher": COUNCIL,
     "source_url": "https://knowledgeauckland.org.nz/publications/auckland-council-capacity-for-growth-study-20222023-data-residential-capacity-part-2/",
     "download_url": "https://knowledgeauckland.org.nz/media/ynch3j4d/pec-residential-part2.zip",
     "format": "File Geodatabase ZIP", "latest_data": "2023", "status": "GIS software required",
     "note": "Official publication links the keyless part 2 archive; site-level records require GIS software."},
    {"id": "business-capacity", "publisher": COUNCIL, "source_url": BUSINESS_URL,
     "format": "File Geodatabase ZIP", "latest_data": "2023", "status": "archive inventory only",
     "command": "capacity --dataset business",
     "note": "Keyless ZIP verified; feature counts and area/zone filtering require a File Geodatabase reader."},
    {"id": "hud-delivery", "publisher": HUD, "source_url": HUD_PAGE,
     "download_url": "https://www.hud.govt.nz/assets/Housing-dashboard-data-download-August-2026.xlsx?m=501cb74296a5aef93adff4b078d2e0014ceb7bcb",
     "format": "XLSX", "latest_data": "2026-08", "licence": "CC BY 4.0, except identified third-party material",
     "command": "housing-update --source hud", "status": "supported",
     "note": "Social housing Delivery rows; includes acquisitions, leases, transfers and stock removals, not only new builds."},
    {"id": "demolitions", "publisher": "Kāinga Ora — Homes and Communities", "source_url": DEMOLITIONS_URL,
     "format": "PDF OIA release", "latest_data": "2025", "command": "demolitions",
     "status": "PDF only; live access blocked on verification network",
     "note": "No structured keyless site extract verified; command reports unsupported_operation rather than fabricated demolition records."},
]
