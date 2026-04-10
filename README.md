# thecolab-ai/.skills

Community-contributed AI skills for New Zealand public data.

Point your agent at real NZ infrastructure — LINZ, Stats NZ, Auckland Transport, weather, census data, and more.

## What is this?

Think Folding@home, but for spare AI tokens. Instead of donating idle compute, the community contributes skills that make New Zealand's public data actually usable by AI agents.

Every skill in this repo is a drop-in connector. Clone the repo, install the skill, and your agent gains access to real NZ data without you having to figure out the APIs yourself.

## Available Skills

| Skill | Data Source | Contributor |
|-------|-------------|-------------|
| *(coming soon)* | | |

## Contributing

1. Fork this repo
2. Create a folder: `skills/<your-skill-name>/`
3. Add a `SKILL.md` describing what it does, what data it hits, and how to use it
4. Add your implementation (Python, JS, shell — whatever works)
5. Open a PR

### Skill folder structure

```
skills/
  auckland-transport/
    SKILL.md          # Description, usage, examples
    skill.py          # Implementation
    requirements.txt  # Dependencies (if any)
  stats-nz/
    SKILL.md
    skill.py
```

### What makes a good skill?

- Hits a **publicly available NZ dataset** (no auth required is ideal)
- Returns data in a format agents can reason about (JSON, markdown, plain text)
- Has clear usage docs in `SKILL.md`
- Works without needing paid API keys

## Data sources to cover

- [LINZ Data Service](https://data.linz.govt.nz/) — land, property, cadastral
- [Stats NZ](https://www.stats.govt.nz/large-datasets/csv-files-for-download/) — census, population, economic data
- [Auckland Transport](https://dev-portal.at.govt.nz/) — real-time transport, GTFS feeds
- [MetService / NIWA](https://developer.metservice.com/) — weather data
- [data.govt.nz](https://www.data.govt.nz/) — NZ government open data portal
- [MfE Environmental Data](https://data.mfe.govt.nz/) — environment, climate
- [NZTA](https://opendata-nzta.opendata.arcgis.com/) — roads, traffic

## Community

Built by the [TheColab](https://thecolab.ai) community — New Zealand's AI builders' collective.

Join us at the next weekly catchup.
