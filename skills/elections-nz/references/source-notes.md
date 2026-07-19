# Source notes

- Owner: Electoral Commission
- Primary source: https://elections.nz/stats-and-research/
- Authentication: none
- Last verified: 2026-07-19
- Result exports: `https://electionresults.govt.nz/electionresults_YEAR/statistics/`
- Finance publications: `https://elections.nz/`
- Allowed hosts: `elections.nz`, `www.elections.nz`, `electionresults.govt.nz`, `www.electionresults.govt.nz`
- Access: public and read-only

The results website publishes final-election CSV tables including overall party results, electorate turnout and winning electorate candidates. Each export has an explicit parser and stable typed fields; banner/header rows never become data. Electorate lookup combines the exact turnout row and winning-candidate record. Candidate lookup accepts published surname-first and natural-order names with Māori diacritics. General-election years 2005–2023 are accepted; a missing or changed legacy export fails explicitly.

Candidate expense and party donation commands return matching first-party PDF/CSV/XLSX publications, not inferred totals. Finance interpretation must retain the document reporting period and the disclosure thresholds that applied. The main Elections site currently presents an automated-access challenge from some networks; the connector reports `blocked` and continues to support user-configured proxy routing through the common fetch layer.
