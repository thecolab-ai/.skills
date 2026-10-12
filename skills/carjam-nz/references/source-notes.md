# Source notes

- Primary owner: CarJam
- Primary source: https://www.carjam.co.nz
- Declared outbound hosts: www.carjam.co.nz
- Access mode: access-restricted
- Authentication: none
- Last verified: 2026-10-12

Live vehicle retrieval is access restricted pending a permitted CarJam API or provider agreement. This skill is not a dependable keyless connector. `lookup` and `batch` return exit code 4, error type `blocked`, and an empty result list. They do not open a network connection.

The previous HTML path under `/car/` is not a supported operation. CarJam robots.txt disallows `/car/` for all user agents. Public terms restrict automated collection, including screen scraping, and the Developer Connection API requires the provider's agreement. On 12 October 2026 the skill smoke failed with `no public vehicle fields found for plate 'PSP532'` after earlier runs had passed. A separate direct response on that path was an HTTP 403 challenge. This skill does not solve challenges, use a browser, send another `/car/` request, or turn that failure into a successful vehicle.

Offline parser fixtures still cover a synthetic public HTML row, an anti-bot interstitial, and a CarJam shell with no public fields. The shell-without-fields case remains a hard parser failure with that same `no public vehicle fields found` message. Fixtures do not contact CarJam.

The skill is read-only. It does not purchase reports, log in, or collect owner information. A blocked result is an explicit failure, never an empty successful dataset. No vehicle payload is cached.
