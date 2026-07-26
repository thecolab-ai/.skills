# Trade Me browser-backed seller workflow

Read this file completely before seller work.

## Boundary

Use the ordinary Trade Me website in a supported Codex-controlled browser.
Do not use OAuth, developer credentials, member APIs, replayed requests, or a
standalone HTTP client for seller work.

The browser may already have a signed-in session. Reuse it only through visible
website navigation and page interaction. Never inspect, copy, export, log,
persist, or transmit cookies, local/session storage, request authorization
headers, bearer tokens, browser profiles, or passwords.

The Python CLI is a task planner. Run the requested seller command with `--json`
and use its URL and target details. The CLI never drives or authenticates the
browser and never submits a seller action.

## Sign-in and verification handoff

1. Open the CLI plan's URL in the browser selected for that Trade Me URL.
2. Check the current URL and a fresh DOM snapshot.
3. Treat a redirect to a login/sign-in route, a visible sign-in form, or an
   email/2FA verification screen as a user handoff.
4. Keep the same browser and tab available. Ask the user to complete sign-in,
   email confirmation, CAPTCHA, or 2FA directly in that browser and tell you
   when it is ready.
5. Do not ask the user to paste a password or verification code into chat. Do
   not retrieve a code from email on their behalf unless they separately ask
   for that different workflow.
6. After the user says it is ready, re-check the same tab. Continue only when
   the seller page is visibly loaded.

## Verified seller routes

| Task | Website route |
| --- | --- |
| Seller home/summary | `/a/my-trade-me/sell` |
| Selling | `/a/my-trade-me/sell/selling` |
| Sold | `/a/my-trade-me/sell/sold` |
| Unsold | `/a/my-trade-me/sell/unsold` |
| Start a listing | `/a/list` |
| Listing detail | `/a/listing/{listing_id}` |
| Edit an active marketplace listing | `/a/marketplace/edit/{listing_id}?reloadDraft=1` |

Use direct navigation only for these verified starting routes. For withdraw,
relist, promotion, or category-specific steps, use controls visibly present on
the loaded page. Do not guess action URLs.

## Reading inventory

Take a fresh DOM snapshot after navigation and after any loading placeholders
clear. Scope reads to the main seller region.

- Selling is headed `Selling` and exposes a visible listing count. Listing
  links contain `/listing/{id}` and their accessible text includes the title,
  closing time, watcher/bid/view counts, reserve state, and current price when
  available.
- Sold is headed `Sold`; an empty state is `No sold listings`. The page may
  expose a visible time-range filter such as `Closed last 45 days`.
- Unsold is headed `Unsold`; an empty state is `No unsold listings`. The page
  may initially show `Listing is loading`, so wait briefly for that explicit
  state to clear before reading.

Return only information visible in the scoped seller region. Do not read buyer
addresses, messages, payment details, or unrelated account data. When a listing
id is supplied, match that exact id in the visible link URL before reporting or
acting.

## Creating and editing

Use a user-supplied listing JSON file only as structured input for visible form
fields. It may include title, description, category, prices, shipping, pickup,
payment methods, duration, and photo paths. Do not treat API-shaped fixture
fields as authority over the live website form.

1. Navigate to the CLI plan's URL.
2. Inspect the visible form and map only fields supported by the current page.
3. Fill only requested values. Do not change promotions, shipping, payment, or
   reserve settings unless the user supplied them.
4. If a photo upload is requested, follow the Browser skill's file-upload
   instructions and confirm the exact files before upload when required.
5. Continue through validation until Trade Me shows its final review, fee, or
   confirmation step.
6. Stop before the control that creates or saves the listing.

For edits, verify the page visibly identifies the exact listing id or expected
title before changing anything. If the listing has bids or Trade Me restricts
an edit, report the visible restriction rather than trying another route.

## Withdraw and relist

For withdrawal, start from the verified edit page or Selling inventory and use
the visible withdraw action. Confirm whether the item was sold, the exact sale
price when applicable, and the reason. Never infer these values.

For relisting, start from Unsold, match the exact listing id, and use the visible
relist action. Review all carried-forward listing values and promotions because
the website may default them differently.

## Required action-time confirmation

Creating, saving an edit, withdrawing, and relisting are external side effects.
Preparation and earlier approval do not authorize the final click.

Immediately before the final submit:

1. Take a fresh DOM snapshot.
2. Report the exact listing id/title, action, changed values, withdrawal
   disposition or relist terms, and every fee visible on the page.
3. Ask the user to confirm that exact action.
4. If confirmed, re-check that the same final control and values are present.
5. Click the unique final control once.
6. Verify a visible success message or resulting seller state.

If the final target, values, or fees differ after confirmation, stop and ask
again. Never create, edit, withdraw, or relist merely because the CLI plan was
generated.

## Failure handling

- If no supported browser control surface is available, report that seller work
  requires the Browser skill; do not fall back to OAuth or credential capture.
- If Trade Me changes labels or layout, rebuild locators from a fresh DOM
  snapshot. Do not guess selectors.
- If login expires, return to the sign-in handoff.
- If the result is ambiguous, make no change and report the visible state.
