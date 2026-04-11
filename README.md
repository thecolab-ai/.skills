# thecolab-ai/.skills

Community-contributed AI skills for useful New Zealand-specific data and workflows.

Point your agent at real NZ infrastructure, public datasets, market data, industry feeds, transport APIs, pricing sources, weather services, and other useful local information.

## What is this?

Think Folding@home, but for spare AI tokens. Instead of donating idle compute, the community contributes skills that make New Zealand-specific data actually usable by AI agents.

Every skill in this repo is a drop-in connector. Clone the repo, install the skill, and your agent gains access to real NZ-relevant data without you having to reverse-engineer the source.

## Try it in 30 seconds

```bash
git clone https://github.com/thecolab-ai/.skills
cd .skills && npm install

# NZ fuel prices, supply, and vessels
npx tsx skills/fuelclock-nz/scripts/cli.ts summary

# Latest NZ news
npx tsx skills/nz-news/scripts/cli.ts headlines

# Auckland Transport real-time (needs AT API key)
npx tsx skills/at-transport/scripts/cli.ts alerts
```

No auth needed for `fuelclock-nz`, `metservice-nz`, or `nz-news`. `at-transport` requires a free API key from [dev-portal.at.govt.nz](https://dev-portal.at.govt.nz).

## About this repository

This repo is intentionally structured like a proper skills library.

It includes:
- `skills/` for real contributed skills
- `spec/` for the Agent Skills spec link plus our repo stance
- `template/` for a basic manual starting point
- `templates/` for richer TypeScript-powered scaffold variants
- `scripts/` for repo tooling like generation and validation

We are borrowing the shape of the best public skills repos, but not copying their skill content.

## Available skills

| Skill | Source | Auth | Contributor |
|-------|--------|------|-------------|
| `at-transport` | dev-portal.at.govt.nz | API key required | [Adam Holt](https://github.com/adam91holt) |
| `fuelclock-nz` | fuelclock.nz (prices, supply, vessels, risk markets, headlines) | No auth | [Adam Holt](https://github.com/adam91holt) |
| `metservice-nz` | MetService / marine API | No auth | [Adam Holt](https://github.com/adam91holt) |
| `nz-news` | NZ RSS feeds | No auth | [Adam Holt](https://github.com/adam91holt) |

## Skill sets

- [./skills](./skills) - Real skills contributed to this repo
- [./spec](./spec/agent-skills-spec.md) - Agent Skills spec and repo-specific stance
- [./template](./template/SKILL.md) - Minimal starter template
- [./templates](./templates) - Opinionated scaffold variants for different skill types

## Contributing

We’ve made this repo opinionated on purpose.

Don’t freestyle the structure. Generate a scaffold, fill it in properly, then validate it before you open a PR. The repo tooling for this is TypeScript-based.

### Quick start

```bash
npm install
npm run new-skill -- my-nz-skill --variant minimal
npm run validate-skill -- skills/my-nz-skill
```

> **Note:** If `NODE_ENV=production` is set in your environment, `npm install` silently skips devDependencies, which breaks `npm run typecheck` and skill smoke tests. Fix this with `NODE_ENV=development npm install` or `npm install --include=dev`.

### Available scaffold variants

- `minimal` for narrow one-file skills
- `cli-workflow` for multi-step skills with `references/` and `scripts/`
- `tool-wrapper` for skills centered around a specific CLI or API client

### Canonical skill folder structure

```text
skills/
  my-nz-skill/
    SKILL.md
    references/
    scripts/
    assets/
```

Only create the directories the skill actually needs.

### Repo commands

```bash
npm run new-skill -- <name> --variant minimal
npm run validate-skill -- skills/<name>
npm run validate-skill -- skills
npm run typecheck
```

### Contribution rules

- Skills should target useful NZ-specific data or workflows
- Public and open data is great, but not the only valid source
- If auth is required, document it clearly in `SKILL.md`, including:
  - How to obtain access
  - Required environment variables
  - Whether there's a free tier
  - Example `.env` entry
- Skills that scrape public websites or consume open RSS feeds should note rate limits, caching expectations, and source stability concerns
- `description` must say what the skill does and when to use it
- Keep `SKILL.md` lean and operational
- Move deep detail into `references/`
- Put deterministic helpers in `scripts/`
- Do not add per-skill `README.md`, `CHANGELOG.md`, or junk notes

Full guide: [CONTRIBUTING.md](CONTRIBUTING.md)

## Good areas to cover

- Government and public datasets
- Transport and logistics feeds
- Weather, marine, and environmental data
- Retail and pricing data
- Property, mapping, and local infrastructure data
- Industry-specific NZ information sources
- Other useful NZ-centric APIs or data workflows

## Community

Built by the [TheColab](https://thecolab.ai) community, New Zealand's AI builders' collective.

Join us at the next weekly catchup.
