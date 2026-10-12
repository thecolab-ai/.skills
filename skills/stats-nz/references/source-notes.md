# Source notes

- Primary owner: Stats NZ
- Primary source: https://www.stats.govt.nz
- Declared outbound hosts: tools.summaries.stats.govt.nz,www.stats.govt.nz
- Access mode: public-api
- Authentication: none
- Last verified: 2026-10-11

The skill is read-only unless its SKILL.md metadata explicitly declares mutations. Live results must retain source and retrieval-time context. A blocked, unavailable, or changed source is an explicit failure state, never an empty successful dataset.

## Place-summary travel to work

Verified on 2026-10-11 from `https://tools.summaries.stats.govt.nz/places/UR/auckland` and `https://www.stats.govt.nz/about-us/copyright/`.

The place page footer, and the same sentence on the copyright page, says: unless noted otherwise, all content on stats.govt.nz is licensed under the Creative Commons 4.0 International Licence. The footer attribution mark links to `https://creativecommons.org/licenses/by/4.0/`. Attribute Stats NZ. Omit material the page marks as excepted. This command does not call Figure.NZ or any other republisher.

`place-travel` requests one place URL, with a 15-second timeout and a 2,000,000 byte cap. `nzfetch` sends its named Chrome User-Agent and rejects redirects that leave `tools.summaries.stats.govt.nz` or land on a different place path. The command reads `Main means of travel to work` for `--address usual` (usual residence) or `--address workplace`. It does not read travel to education, the Māori ethnic-group cut, or New Zealand comparison rows.

`value` is the published percent (`value_label` `percent`). `count_value` is people. `period` for the Auckland usual-residence rows checked on this date was `2023`, collection `Census`. `confidentiality_indicator` is copied when Stats NZ publishes one (`..` and `S` both occur on this place page for other concepts). A suppressed row keeps that indicator and null measures. An empty travel section, truncated page, or non-JSON `__NEXT_DATA__` block is a failure.

`population --region` is unchanged. It still reads estimated resident population (`variable1_code` `ERP`) from `places/RC` only.

The fixture `tests/fixtures/place-travel-auckland.html` is a reduced excerpt of the Auckland usual-residence rows, including drive a private car, truck or van at 55.4 percent and count 408939. One suppressed row in that fixture is synthetic. Live smoke accepts a revised Stats NZ percent as long as a mode still has a numeric percent and count.
