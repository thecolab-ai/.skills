# Source notes

- Owner: New Zealand Parliament
- Application: https://journals.parliament.nz/
- Weekly search: `POST /api/data/search` with bounded `page` and `pageSize`
- Weekly detail: `GET /api/data/Journal/{id}`
- Authentication: none
- Last verified: 2026-09-12

The search API returns weekly Journal metadata. Detail objects include `PublishHtml`, the official rendered proceedings used by the parser. Parliament describes weekly Journals as drafts; Sessional Journals are the authoritative record. This skill does not download or parse Sessional Journal PDFs.

Extraction is deliberately conservative. A division must have the exact printed “votes were recorded as follows” question and the supported `jps-JVResultParty` / `jps-JVParty` style. Party rows preserve printed labels and counts. A supported bare singleton surname is retained as an explicitly printed person label, without identity, party, role, electorate, or membership enrichment. Counts must reconcile with the printed side total; otherwise that side's participant claims are discarded and warned. Missing abstentions remain `null`.

No resolution on the voices is represented as a division. Unsupported styles produce diagnostics rather than evidence of zero votes. An empty search page is distinct from a blocked or unavailable source. The CLI bounds each request to 10 seconds and 4 MiB and only permits `journals.parliament.nz`.
