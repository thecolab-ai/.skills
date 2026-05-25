# Complaints and Takedowns

This file is for businesses, operators, and individuals who have a concern about a skill in this repository. It explains what we'll action, how to ask, and how quickly we'll respond.

## If you operate a service one of our skills connects to

Email **adam@thecolab.ai** with:

- The skill name (e.g. `petrolmate-nz-au`)
- Your role at the affected service (we action requests from the operator, not from third parties)
- A brief reason. You don't need to justify it in detail, but "we don't want this skill to exist" is enough

We action good-faith requests from the affected operator promptly, usually within 5 working days. We may ask a clarifying question, but we won't argue the point.

If the request is straightforward, we will:
1. Remove the skill from the repository
2. Tag the removal commit so it's permanent in git history
3. Reply to confirm

If the request is more nuanced (e.g. you'd prefer rate-limiting, attribution, or a specific change rather than full removal), we'll work with you on that instead.

## Other types of complaint

| If you're reporting... | Send it to | What we do |
|---|---|---|
| A skill returning wrong data | [GitHub issue](https://github.com/thecolab-ai/.skills/issues/new) | Fix or remove |
| A privacy concern about personal info exposed by a skill | adam@thecolab.ai | Same SLA as above |
| Misuse of a skill by a third party | adam@thecolab.ai | We can't police end users, but we'll review whether the skill itself should change |
| A general question or feedback | adam@thecolab.ai | Conversation |
| A legal matter | adam@thecolab.ai | Routed to a lawyer if needed |

## What this file is not for

- End-user support for products built on our skills. Talk to whoever built the product.
- General GitHub issues with the repo. Use the [issue tracker](https://github.com/thecolab-ai/.skills/issues).

## Our position

We build skills against endpoints that respond to unauthenticated public requests. We don't bypass authentication or circumvent technical access controls. Users of these skills are responsible for complying with the terms of service of the underlying provider.

We'd rather work with businesses than around them. If you'd prefer a more controlled way for AI agents to access your data, see the "For businesses whose APIs we touch" section in the [README](README.md). Email **adam@thecolab.ai** or open an issue.

---

*Last updated: 2026-05-25*
