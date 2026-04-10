# thecolab-ai/.skills

Community-contributed AI skills for New Zealand public data.

Point your agent at real NZ infrastructure, LINZ, Stats NZ, Auckland Transport, weather, census data, and more.

## What is this?

Think Folding@home, but for spare AI tokens. Instead of donating idle compute, the community contributes skills that make New Zealand's public data actually usable by AI agents.

Every skill in this repo is a drop-in connector. Clone the repo, install the skill, and your agent gains access to real NZ data without you having to reverse-engineer the APIs yourself.

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

| Skill | Data Source | Contributor |
|-------|-------------|-------------|
| *(coming soon)* | | |

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
npm run new-skill -- auckland-transport-departures --variant minimal
npm run validate-skill -- skills/auckland-transport-departures
```

### Available scaffold variants

- `minimal` for narrow one-file skills
- `cli-workflow` for multi-step skills with `references/` and `scripts/`
- `tool-wrapper` for skills centered around a specific CLI or API client

### Canonical skill folder structure

```text
skills/
  auckland-transport-departures/
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

- Skills must target real, useful NZ public data workflows
- `description` must say what the skill does and when to use it
- Keep `SKILL.md` lean and operational
- Move deep detail into `references/`
- Put deterministic helpers in `scripts/`
- Do not add per-skill `README.md`, `CHANGELOG.md`, or junk notes

Full guide: [CONTRIBUTING.md](CONTRIBUTING.md)

## Data sources to cover

- [LINZ Data Service](https://data.linz.govt.nz/) - land, property, cadastral
- [Stats NZ](https://www.stats.govt.nz/large-datasets/csv-files-for-download/) - census, population, economic data
- [Auckland Transport](https://dev-portal.at.govt.nz/) - real-time transport, GTFS feeds
- [MetService / NIWA](https://developer.metservice.com/) - weather data
- [data.govt.nz](https://www.data.govt.nz/) - NZ government open data portal
- [MfE Environmental Data](https://data.mfe.govt.nz/) - environment, climate
- [NZTA](https://opendata-nzta.opendata.arcgis.com/) - roads, traffic

## Community

Built by the [TheColab](https://thecolab.ai) community, New Zealand's AI builders' collective.

Join us at the next weekly catchup.
