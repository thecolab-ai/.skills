# thecolab-ai/.skills

Community-contributed AI skills for useful New Zealand-specific data and workflows.

Point your agent at real NZ infrastructure, public datasets, market data, industry feeds, transport APIs, pricing sources, and other useful local information.

## What is this?

Think Folding@home, but for spare AI tokens. Instead of donating idle compute, the community contributes skills that make New Zealand-specific data actually usable by AI agents.

Every skill in this repo is a drop-in connector. Clone the repo, install the skill, and your agent gains access to real NZ-relevant data without you having to reverse-engineer the source.

## About this repository

This repo is intentionally structured like a proper skills library.

It includes:
- `skills/` for real contributed skills
- `spec/` for the Agent Skills spec link plus our repo stance
- `template/` for a basic manual starting point
- `templates/` for richer TypeScript-powered scaffold variants
- `scripts/` for repo tooling like generation and validation

We are borrowing the shape of the best public skills repos, but not copying their skill content.

## Authentication

Skills that call external APIs may need an API key. Follow these rules:

- **Never hardcode API keys** in skill scripts — environment variables only, no fallback to a raw key
- Store keys in `~/.env` or the workspace `.env` (e.g. `/home/adam/agents/kev/.env`)
- Pattern to use in TypeScript:
  ```typescript
  const API_KEY = process.env.MY_API_KEY;
  if (!API_KEY) throw new Error('MY_API_KEY env var not set. Get a key at https://example.com and add it to your .env');
  ```
- Each skill that requires a key must document in its `SKILL.md`:
  - What the env var is called
  - Where to get the API key (URL)
  - Whether there's a free tier
  - Example `.env` entry

Skills that scrape public websites or consume open RSS feeds generally need no key — check each skill's **Setup** section.

## Available skills

| Skill | Source | Auth | Contributor |
|-------|--------|------|-------------|
| `fuelclock-nz` | fuelclock.nz | None | [Adam Holt](https://github.com/adam91holt) |
| `metservice-nz` | MetOcean API | `METOCEAN_API_KEY` | [Adam Holt](https://github.com/adam91holt) |
| `nz-news` | NZ RSS feeds | None | [Adam Holt](https://github.com/adam91holt) |

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
