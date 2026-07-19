# Source notes

- Owner: New Zealand Parliament
- Directory: https://www3.parliament.nz/en/mps-and-electorates/members-of-parliament/
- Access: server-rendered, read-only HTML
- Authentication: none
- Last verified: 2026-07-19

The current directory publishes one table row per MP with name, party, electorate or List status,
and a canonical profile. Profiles publish current and historical role tables plus official contact
details. The parser limits contact output to `@parliament.govt.nz` addresses and never enriches
private contact data. Current-role records retain their table kind, subject, role, start and end.

The directory is currently protected by a Radware challenge from this test network. The shared
HTTP layer reports that as `blocked` and the live smoke test skips; it does not turn the challenge
page into an empty or successful directory. Fixture assertions cover the source table and profile
schema deterministically.

Cross-member portfolio/committee search follows the directory's official profiles and inspects only
their labelled `Current Roles` tables. Results are marked current at retrieval. Absence is not
evidence that a person was never an MP, and former roles are not inferred from current pages.
