# Source notes

- Primary owner: Trade Me
- Primary source: https://www.trademe.co.nz
- Declared outbound hosts: api.trademe.co.nz,www.trademe.co.nz
- Access mode: public-api-and-browser-authenticated-personal
- Authentication: mixed
- Last verified: 2026-07-24

Public search is read-only. Seller commands plan work on the ordinary website;
the Browser skill reuses a user-completed website sign-in without inspecting or
exporting browser authentication data. Seller inventory and complete listing
forms are private. Seller mutations are declared in `SKILL.md` and require a
separate action-time confirmation on the website's final review screen. Live
results must retain source and retrieval-time context. A blocked, unavailable,
or changed source is an explicit failure state, never an empty successful
dataset.
