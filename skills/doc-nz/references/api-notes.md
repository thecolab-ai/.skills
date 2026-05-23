# DOC NZ API notes

This skill is an unofficial lightweight wrapper around public Department of Conservation (DOC) New Zealand web endpoints used by `bookings.doc.govt.nz` and `doc.govt.nz`.

## Source and auth

- Booking website: `https://bookings.doc.govt.nz/Web/`
- Booking API base observed from the web app: `https://prod-nz-rdr.recreation-management.tylerapp.com/nzrdr/rdr/`
- DOC website: `https://www.doc.govt.nz`
- DOC alerts API base observed from the frontend bundle: `https://www.doc.govt.nz/api/`
- Auth model for this skill: none for implemented read-only operations

No username, password, payment data, account cookie, private token, browser profile, or session storage is required.

## Endpoint families used

### Great Walks and booking availability

- `GET /search/getgreatwalkplaces/false/isCashier`
  - Lists DOC Great Walk booking places.
  - Response includes `FutureBookingStartDate`, `FutureBookingEndDate`, and `GWPlaceData[]`.
  - Useful keys in `GWPlaceData[]`: `PlaceId`, `Name`, `Description`, `AllowWebBooking`, `IsWebViewable`, `IsAvailableForGreatwalk`, `IsAvailableForFixedgreatwalk`, `FixedGWMinNight`, `FixedGWMaxNight`, `Latitude`, `Longitude`.

- `GET /search/getgreatwalksearchdata/placeId/{placeId}`
  - Returns per-Great-Walk search metadata.
  - Useful keys: `MinNoofNights`, `MaxNoofNights`, `MinNoofPeople`, `MaxNoofPeople`, `IsAvailableForFixedGreatWalk`, `IsAccomodationVisible`, `IsDirectionVisible`, `GWAccomodationData[]`, `GWPlaceDirection[]`, `PlaceDescription`.
  - DOC's JSON uses the misspelled `Accomodation` spelling; the CLI preserves that only in upstream request parsing.

- `POST /search/greatwalkplacefacility`
  - Public Great Walk availability grid.
  - Request body uses `accomodation` as the accommodation name, not the accommodation id.
  - Minimal body:
    ```json
    {
      "accomodation": "Hut",
      "placeId": 874,
      "customerClassificationId": 0,
      "arrivalDate": "2026-11-01",
      "startDate": "2026-11-01",
      "nights": 1,
      "direction": 31
    }
    ```
  - Response includes `GreatWalkFacilityHeaderData[]` and `GreatWalkFacilityData[]`.
  - Facility keys include `FacilityId`, `FacilityName`, `FacilityCategory`, `MasterMaxOccupancy`, and `GreatWalkFacilityDateData[]`.
  - Date keys include `ArrivalDate`, `TotalAvailable`, `IsAvailable`, `IsSeasonAvailable`, `AllocationSeats`, `AllocatedSeatsReservationCount`.

### Booking place listings

- `GET /search/popular/places/`
  - Public listing of popular bookable DOC places, including huts, campsites, and circuits.
  - Used for lightweight `huts` discovery and client-side filtering.
  - Useful keys include `PlaceId`, `PlaceName`, `PlaceDescription`, `CityParkId`, `EntityType`, `AvailableUnitCount`, and `ReservationCount` where present.

Generic booking detail endpoint `GET /search/details/{placeId}/startdate/{date}/nights/{nights}/{customerId}/{customerClassificationId}` returned HTTP 500 during discovery for several public place ids, so it is intentionally not exposed.

### Alerts and track pages

- Alerts index page: `GET https://www.doc.govt.nz/parks-and-recreation/know-before-you-go/alerts/`
  - The CLI scrapes public `doc-standard-product-card`/`doc-summary-card` region links.

- Region page HTML, for example `GET https://www.doc.govt.nz/parks-and-recreation/places-to-go/fiordland/alerts/`
  - Contains a `doc-alerts` component with a public GUID.

- `GET /api/alerts/alertregionsummary/{guid}`
  - Current regional alert groups.
  - Response groups alerts by DOC place, hut, campsite, track, or general region entry.
  - Group keys include `name`, `staticLink`, `isGeneral`, `alerts[]`.
  - Alert keys include `summary`, `description`, `subText`, `sortDate`, `displayDate`, `associatedBookingIDs`.

- `GET /api/alerts/alertsummary/{guid}`
  - Summary alert groups for DOC pages that use `type="summary"`.

- `GET /api/alerts/guid/{guid}`
  - Page-specific alert list for DOC pages that use a unique alert component.

The `track` command resolves Great Walk DOC links from booking metadata when available, then fetches the public DOC page title, meta description, first content paragraphs, and any page alert component.

## Headers

The booking API returned an AWS WAF challenge without browser-like request headers. The CLI sends:

- `Accept: application/json, text/plain, */*`
- `Origin: https://bookings.doc.govt.nz`
- `Referer: https://bookings.doc.govt.nz/Web/`
- a common browser `User-Agent`

The DOC website API uses normal public GET requests with `Accept: application/json, text/plain, */*`.

## Refresh cadence

- Great Walk booking availability changes live as users book or cancel.
- DOC alerts are current public site data and may change at any time during weather, track, pest-control, or maintenance events.
- Track page descriptions and alert components should be treated as live website snapshots.

Use narrow date windows and small limits for normal agent workflows.

## Safety and stability

- Read-only only: no booking holds, cart actions, payments, login, cancellation, or account access.
- Availability does not guarantee that a space can be booked; always confirm on DOC before travel.
- Endpoint names and response schemas are not a formal public API contract and can change without notice.
- Do not commit HAR files, raw browser bundles, cookies, credentials, screenshots with private data, or large scraped datasets.
