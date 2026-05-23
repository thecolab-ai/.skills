# NZ TV Guide API notes

This skill is an unofficial lightweight wrapper around public read-only TV guide surfaces for New Zealand.

## Source and auth

No username, password, account cookie, private token, browser storage, streaming entitlement, or recording state is required for the implemented commands.

Endpoint families used:

- Sky TV Guide: `https://tvguide.sky.co.nz/`
- Sky EPG GraphQL: `https://api.skyone.co.nz/exp/graph`
- Freeview TV Guide: `https://freeviewnz.tv/whats-on/tv-guide/`

## Sky NZ

The Sky TV Guide redirects from `https://www.sky.co.nz/tv-guide` to `https://tvguide.sky.co.nz/`. Browser traffic exposes a public GraphQL endpoint:

- `GET https://api.skyone.co.nz/exp/graph`

Useful operations:

- `getChannelGroups`: returns channel group ids and titles for `TV_GUIDE_WEB`
- `getChannelGroup($id: ID!)`: returns channels for a group
- `getChannelGroup($id: ID!, $date: LocalDate)`: returns channels plus `slotsForDay(date)` programme slots

Observed channel group ids:

| Group | Id |
|---|---|
| All Channels | `4b7LA20J4iHaThwky9iVqn` |
| Sports | `5P95WEpsEA6TcDMOsPmV19` |
| Movies | `23robtuSx9VbRD5j0iZslh` |
| Entertainment & Lifestyle | `LOXeZgvmRZ6T0b9geXwgy` |
| News & Documentaries | `2ZuubrhJhHFsY3RaH43QS2` |
| Kids | `2kHaAIbt50eqGIotu6Azew` |
| Music | `5M4HwW3cqjzeku0EfMazEV` |
| Pay-Per-View | `3RkCYpW5t7ZBmcgIZ0796i` |

Slot schema used by the CLI:

- Channel: `id`, `title`, `number`, `tileImage.uri`
- Slot: `id`, `startMs`, `endMs`, `live`
- Programme: `id`, `title`, `synopsis`, `__typename`
- Episode show metadata: `show.id`, `show.title`, `show.type`

`startMs` and `endMs` are Unix epoch milliseconds. The CLI converts them to `Pacific/Auckland` before rendering or returning simplified records.

Sky Sport channels observed in the Sports group include Sky Sport Select, Sky Sport 1-7, Sky Sport Premier League, Sky Sport 9, Sky Sport 4K UHD, ESPN, ESPN2, Sky Sport pop-up channels, Trackside 1/2, and Sky Arena. Sky Sport NOW streaming-specific account schedules were not implemented because the no-login Sky linear EPG already covers the core "what time and what channel?" workflow.

## Freeview

The Freeview website exposes a server-rendered public TV guide:

- `GET https://freeviewnz.tv/whats-on/tv-guide/?date={MM/DD/YYYY 00:00:00}&st=`

The page includes:

- A channel list in `ul.channel-nav`
- One `ul.schedule` per channel in page order
- Programme cards with title, time range, and hidden more-info description

The CLI parses only the public HTML already rendered by the page. It does not call playback, app, device, or HbbTV endpoints. `--provider tvnz` filters this Freeview schedule to TVNZ-branded linear channels such as TVNZ 1, TVNZ 2, and Duke.

Freeview time ranges are already local NZ guide times. The CLI attaches `Pacific/Auckland` and rolls an end time into the next day when a programme crosses midnight.

## Freshness and stability

- Sky and Freeview guide data are live website snapshots and can change during the day
- EPGs typically refresh at least daily; use small live checks before relying on a long schedule
- The Sky GraphQL and Freeview HTML shapes are website implementation details, not formal public APIs
- If a provider fails, re-sniff the public website traffic or inspect the current HTML before changing command behavior

## Intentionally omitted

- Streaming playback URLs and Sky Sport NOW account flows
- My Sky recording, reminders, purchases, PPV booking, subscriptions, login, or profile actions
- HAR files, JavaScript bundles, cookies, screenshots, or browser storage captures
- Bulk archival export or redistribution of EPG listings
