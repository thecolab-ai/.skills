# Source notes

- Primary owner: {{SOURCE_OWNER}}
- Primary source: {{SOURCE_URL}}
- Data licence: {{SOURCE_LICENCE}}
- Declared outbound hosts: {{ALLOWED_DOMAINS}}
- Access mode: {{ACCESS_MODE}}
- Authentication: {{AUTH}}
- Last verified: {{LAST_VERIFIED}}

Replace this scaffold note with endpoint/export discovery, reuse conditions,
update cadence, parser assumptions, and source-owner expectations before the
skill is marked healthy. Keep blocked and unavailable states explicit.

Every data command uses `scripts/provenance.py` for a `meta`/`results` JSON
envelope, or places the same provenance fields on existing records. Set
`latest_data` only from a source-stated date, period or update timestamp and
document what it means. Keep original retrieval times for cached records.
Return failures with `error_envelope`, JSON on stdout and the matching exit code.
Update `DATA_COMMAND` in `scripts/test_contract.py` to a deterministic data
invocation when replacing the scaffold status command; mock retrieval or use a
fixture so the contract test stays offline.

For spatial commands, use `add_spatial_arguments` only after implementing the
bounding-box filter and WGS84 GeoJSON features. Document intersection versus
containment and upstream versus local filtering. Emit `geojson_envelope` when
`--format geojson` is requested, even without `--json`.
