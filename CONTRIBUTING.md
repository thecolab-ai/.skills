# Contributing Skills

This repo should be easy to extend and hard to mess up.

The standard is simple: narrow skills, strong trigger descriptions, lean `SKILL.md` files, and measurable validation.

## Quick start

```bash
npm install
npm run new-skill -- my-skill --variant minimal
npm run validate-skill -- skills/my-skill
```

## Core stance

- Prefer narrow, composable skills over giant umbrella skills
- Make the `description` field do the retrieval work
- Keep `SKILL.md` operational, not essay-like
- Move deep reference material into `references/`
- Put deterministic operations into `scripts/`
- Avoid per-skill doc clutter

## Definition of done

A contribution is only ready when it passes all of these:

- `name` is specific, stable, and hyphenated
- `description` says what the skill does and when to use it
- `SKILL.md` is short enough to scan quickly
- The workflow is explicit
- Any referenced local files exist
- Any bundled scripts were actually run
- No placeholder text remains
- No duplicate guidance is split across `SKILL.md` and `references/`

## Repo rules

### 1. Build useful NZ-specific skills

The bar is not "must be government". The bar is "genuinely useful for New Zealand-specific tasks".

Good sources include:
- public and open datasets
- government APIs
- transport feeds
- pricing sources
- logistics or supply-chain data
- industry-specific NZ data sources
- other lawful, stable, agent-useful local data workflows

If the skill is useful, NZ-specific, and the source is legitimate, it belongs in scope.

### 2. Write narrow skills

Good:
- `auckland-transport-departures`
- `stats-nz-census`
- `linz-property-search`

Bad:
- `nz-data-helper`
- `tooling`
- `everything`

If a skill wants to teach three different jobs, split it.

### 3. Treat frontmatter as the trigger surface

The `description` is not marketing copy. It is routing logic in plain English.

Good:

```yaml
---
name: auckland-transport-departures
description: Query Auckland Transport real-time departures and stop data. Use when the task involves live bus or train departures, stop lookups, route timing, or GTFS-realtime transport data.
---
```

Bad:

```yaml
---
name: helper
description: Helps with NZ data.
---
```

### 4. Keep `SKILL.md` lean

Put the workflow, decision points, and non-obvious rules in `SKILL.md`.
Do not dump background theory, changelogs, setup diaries, or generic tutorials in there.

### 5. Keep one source of truth per concern

- Trigger logic lives in frontmatter
- Execution guidance lives in `SKILL.md`
- Deep detail lives in `references/`
- Reusable deterministic logic lives in `scripts/`
- Output resources or starter files live in `assets/`

Do not duplicate the same instructions in multiple places.

### 6. Ban clutter files inside skill folders

Do not add these unless they are runtime-critical:

- `README.md`
- `CHANGELOG.md`
- `NOTES.md`
- `IDEAS.md`

One clean central contribution guide beats a graveyard of side docs.

### 7. Make examples realistic

Good:
- `Fetch the latest departures for Britomart platform 2 and show them as JSON.`
- `Build a LINZ skill that can search parcels by title reference.`
- `Show me the latest NZ fuel summary and only flagged incoming diesel vessels.`

Bad:
- `Use this amazing skill to improve your project.`

### 8. If you ship a script, mention how to use it

A script with no invocation guidance is dead weight.
Reference the script from `SKILL.md` or a linked reference doc.

## Template variants

Use the scaffold that matches the job:

- `minimal` for narrow one-file skills
- `cli-workflow` for multi-step skills with references and scripts
- `tool-wrapper` for skills centered around a specific external CLI or API client

## Review checklist

- [ ] Skill name is specific and hyphenated
- [ ] Description includes clear triggers and boundaries
- [ ] `SKILL.md` is operational, not bloated
- [ ] References are linked directly from `SKILL.md`
- [ ] Script usage is documented
- [ ] No placeholder text remains
- [ ] No forbidden clutter files exist
- [ ] Validator passes cleanly

## Bottom line

Be opinionated in structure, strict in validation, and sparse in prose.
If the skill is hard to scan, vague to trigger, or padded with junk, it is not ready.
