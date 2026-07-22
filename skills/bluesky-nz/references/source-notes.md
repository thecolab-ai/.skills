# Source notes — Bluesky public AppView

- Primary owner: Bluesky Social (public AppView)
- Primary source: https://api.bsky.app/xrpc/app.bsky.feed.searchPosts
- Declared outbound hosts: api.bsky.app, bsky.app
- Access mode: public-api
- Authentication: none
- Last verified: 2026-07-22

## Endpoints

Unauthenticated XRPC on `api.bsky.app` (verified 2026-07-22):

- `app.bsky.feed.searchPosts?q=&sort=latest|top&since=&lang=&limit=` — public post search
- `app.bsky.feed.getAuthorFeed?actor=&limit=&filter=posts_no_replies` — public account feed
- `app.bsky.actor.getProfile?actor=` — public profile

Note: the documented "public" host `public.api.bsky.app` served `getAuthorFeed`/
`getProfile` but returned an edge 403 for `searchPosts` from this network, while
`api.bsky.app` served all three keylessly — so the skill uses `api.bsky.app`
throughout. `bsky.app` appears only in generated web links, never fetched.

## Behaviour and limits

- API errors arrive as HTTP 400 with `{"error": ..., "message": ...}` JSON;
  the CLI maps invalid/not-found errors to exit 2 and others to exit 5.
- Timestamps are UTC; `record.createdAt` is author-asserted and can be spoofed
  or clock-skewed — treat ordering as approximate.
- Handles are self-registered; only domain handles (e.g. `*.govt.nz`) imply
  control of that domain. The SKILL.md instructs verifying accounts via
  `profile` before treating them as official.
- Unauthenticated rate limits are generous but unpublished; the CLI bounds
  `--limit` at 100 (the API cap) and makes one request per command.
- Reuse: posts are public user content — quote with attribution (handle + URL),
  do not bulk-republish, and treat as unverified crowd signal.
