# Trust-based distribution packs

Skills remain implemented once under `skills/`. Generated pack manifests select
those folders without copying source code.

| Pack | Trust model |
|---|---|
| `nz-public-data` | Public data and public-interest read surfaces. No personal data or repository-specific publishing workflow. |
| `nz-commercial-web` | Read-only public commercial websites and market surfaces. Terms, freshness, and source availability vary by operator. |
| `nz-personal-data` | User-authorised personal data. Credentials are supplied at runtime and live personal records are never used in CI. |
| `thecolab-internal` | TheColab-specific documentation and operational workflows. May include explicitly declared write operations. |
| `artifact-tools` | Local artifact creation or editing; filesystem writes are part of the declared contract. |
| `paid-data-connectors` | Providers whose calls require paid credentials or consume credits. |

The default installation is `nz-public-data`. It excludes personal-data skills,
internal workflows, artifact writers, paid connectors, and commercial-web
connectors. The legacy `nz-skills` plugin name remains as an all-packs
compatibility aggregate during migration.

Preview and install a pack into an explicit destination:

```bash
python3 scripts/install_pack.py nz-public-data --target /absolute/path/to/skills --dry-run
python3 scripts/install_pack.py nz-public-data --target /absolute/path/to/skills
```

Existing folders are never replaced unless the operator deliberately passes
`--force`. Pack installation copies the canonical skill folders selected by the
manifest; implementations are not duplicated in this repository.

`scripts/generate_catalogue.py` derives the catalogue and pack manifests from
SKILL.md metadata. The legacy aggregate plugin descriptor is static compatibility
metadata. Generated catalogue and pack files must not be edited by hand.
