# Source notes

- Owner: Electoral Commission
- Primary source: https://elections.nz/stats-and-research/
- Authentication: none
- Last verified: 2026-09-12
- Result exports: `https://electionresults.govt.nz/electionresults_YEAR/statistics/`
- Finance publications: `https://elections.nz/`
- Allowed hosts: `elections.nz`, `www.elections.nz`, `electionresults.govt.nz`, `www.electionresults.govt.nz`
- Access: public and read-only

The results website publishes final-election CSV tables including overall party results, electorate turnout and winning electorate candidates. Each export has an explicit parser and stable typed fields; banner/header rows never become data. Electorate lookup combines the exact turnout row and winning-candidate record. Candidate lookup accepts published surname-first and natural-order names with Māori diacritics. General-election years 2005–2023 are accepted; a missing or changed legacy export fails explicitly.

Candidate expense and party donation commands return matching first-party PDF/CSV/XLSX publications, not inferred totals. The aggregate command separately parses only the exact party-summary table layouts on the annual donation/loan page and supported election-expense pages. It uses decimal strings, distinguishes explicit `Nil` from missing values, keeps each metric separate, and fails closed on malformed amounts, duplicate party-year metrics or layout drift. It does not follow return links or expose donor/contributor names, addresses or rows.

Annual aggregates currently support the Commission's accordion year tables that expose aggregate donation and loan totals; a requested historical section with only donor-level or another unsupported layout fails explicitly instead of returning empty data. Election-expense aggregates currently support the 2023 General Election page and retain its published regulated period (14 July–13 October 2023); unsupported years fail as invalid input. Reporting-rule output uses accordion or page-level election context ahead of filing-deadline dates, and retains exact paragraph/list wording, mentioned amounts and explicit reporting-year scope. Observation time is not an effective date, so `effective_from` and `effective_to` stay null unless an official source explicitly supplies them. This is source retrieval, not legal advice.

The main Elections site can present an automated-access challenge on some networks. The connector reports `blocked` rather than returning an empty success. Each finance invocation makes one bounded request with a 20-second timeout through the repository's common fetch layer.
