# CourseViewerPlatform Publishing Workflow

Use this when the task goes beyond local authoring and the course must appear on a live tenant such as `https://forgood.mycourse.work`.

## Authoring Standard

Course lessons should contain the research and teaching material directly:

- Put core findings, tables, calculations, caveats, and examples in the lesson body.
- Keep external links as bottom `### References` lists unless the link itself is the lesson object.
- Prefer charts, widgets, diagrams, and generated educational images that explain a concept or data relationship.
- Avoid standalone "read this GitHub finding" lessons; learners should not need to leave the course to understand the argument.
- Use NZ English in learner-facing text.

## Tenant Repo Flow

1. Find or clone the tenant content repo, usually `mycourse-work/<tenant>`.
2. Make course changes in the tenant repo structure:
   - `courses/<course-id>/course.json`
   - `courses/<course-id>/welcome.md`
   - `courses/<course-id>/assets/*`
   - `modules/<module-id>/manifest.json`
   - `modules/<module-id>/*.md`
   - `widgets/*.html`
3. Remove joke, test, or superseded courses from the tenant repo if they must disappear from public listing.
4. Commit and push according to the tenant repo's branch/main policy.
5. Watch the tenant sync workflow. It should upload changed files to R2 and register content in D1.

Typical checks:

```bash
gh run list --repo mycourse-work/<tenant> --limit 5 \
  --json databaseId,workflowName,status,conclusion,headSha,url,createdAt

gh run watch <run-id> --repo mycourse-work/<tenant> --exit-status
```

## Validation Commands

Validate a full tenant root when widgets or multiple courses changed:

```bash
python3 skills/colab-course-publisher/scripts/cli.py validate /path/to/tenant-root
```

Validate a single course when changing one course. This also validates referenced modules:

```bash
python3 skills/colab-course-publisher/scripts/cli.py validate /path/to/tenant-root/courses/<course-id>
```

Use `--strict` before opening a PR or publishing if warnings should block the release.

## Live Verification

After sync, check the live API with cache-busting:

```bash
curl -fsS -H 'Cache-Control: no-cache' \
  "https://<tenant-domain>/api/content/<course-id>/manifest.json?verify=$(date +%s)"

curl -fsS -H 'Cache-Control: no-cache' \
  "https://<tenant-domain>/api/content/<course-id>/@modules/<module-id>/<lesson>.md?verify=$(date +%s)"
```

Verify at least:

- `/api/courses` lists the intended public courses and omits removed courses.
- The resolved manifest contains the expected modules and lesson paths.
- One or two changed lesson endpoints return the new text, tables, widgets, or references.
- Referenced widgets and media load through their API paths if changed.

## Platform Renderer Issues

If the course content is correct but display is poor, fix CourseViewerPlatform separately. Examples:

- External source links render too large.
- Widgets fail to resize in iframes.
- Tables overflow on mobile.
- Generated images are cropped or unreadable.

Content repo sync and platform deploy are different release paths; verify both when both changed.
