# Security policy

## Reporting a vulnerability

Do not open a public issue for credentials, personal information, an exploitable
access-control weakness, or a vulnerability that has not been remediated.

Report it privately through GitHub Security Advisories for this repository, or
email `adam@thecolab.ai` with the subject `Security: .skills`. Include the
affected skill or file, impact, reproduction steps, and the least sensitive
evidence needed to verify the report. Do not include live credentials or
unredacted personal data.

We will acknowledge a good-faith report as soon as practical, coordinate a
remediation, and credit the reporter when requested and safe.

## Supported code

Security fixes target the current `main` branch. Skills call independent
upstream sources, so an upstream outage or schema change is not by itself a
repository vulnerability; report incorrect or unsafe handling through the
appropriate issue template.

## Credential and personal-data incident response

If a credential or personal record is committed:

1. Revoke or rotate the credential immediately. History rewriting is not a
   substitute for revocation.
2. Restrict further access and preserve the minimum audit evidence needed for
   response.
3. Remove the material from the current tree and open a private security
   advisory.
4. Identify every reachable commit, tag, release artifact, cache, fork, log,
   and generated catalogue that may contain it.
5. Coordinate a targeted history rewrite with repository owners when the data
   remains sensitive. Force-push only after maintainers agree the exact refs and
   contributor recovery instructions.
6. Invalidate affected caches and releases, notify impacted people or source
   operators when required, and document completion privately.
7. Add a regression check that detects the same exposure class without
   retaining the sensitive value.

Never copy a live secret into an issue, pull request, test fixture, smoke log,
or example. Tests must use synthetic credentials and synthetic personal data.

## Security boundaries

The repository access policy is documented in `README.md`, `CONTRIBUTING.md`,
and `docs/browser-assisted-skills.md`. User-configured proxies remain permitted
for the bounded public-source retry flow. CAPTCHA solving, authentication
bypass, protected-token forgery, account operation, checkout, booking, payment,
and transaction automation are outside the repository contract.
