---
name: colab-course-publisher
description: Use when Codex needs to create, edit, publish, package, or validate The Colab CourseViewerPlatform course content, including tenant course repos, course.json, blueprint.json, module manifests, markdown lessons, quizzes, generated educational images, HTML widgets, and live CourseViewerPlatform content checks.
---

# Colab Course Publisher

## Goal

Build CourseViewerPlatform-compatible course packages, validate their modules, and verify tenant-published content after deployment.

## Quick triage

Use this when:
- Creating a new tenant course under `courses/` plus reusable modules under `modules/`.
- Adding or editing lessons, quizzes, images, videos, markdown HTML, or widget HTML.
- Publishing tenant content repos such as `mycourse-work/<tenant>` and checking live course endpoints.
- Validating a course root, a single course, a single module, or a tenant content root before upload/deploy.

Do not use this for:
- General LMS, SCORM, Moodle, or unrelated course-authoring formats.
- Course strategy only, unless the output must become CourseViewerPlatform files.
- General platform renderer bugs, unless course content changes or live content verification is part of the task.

## Core workflow

1. Prefer the module-first format: `courses/<courseId>/course.json` or `blueprint.json` plus sibling `modules/<moduleId>/manifest.json`.
2. Read `references/course-format.md` before creating or reshaping course files.
3. Keep module lessons flat at the module root, with module-local assets in `assets/`.
4. Use markdown for lessons, JSON for quizzes, and `widgets/<name>.html` plus `:::widget name` for reusable HTML artifacts.
5. Put research findings, tables, caveats, and practical examples in the lesson body. Use links as bottom references, not as a substitute for course substance.
6. Run the validator after every structural change:

```bash
python3 skills/colab-course-publisher/scripts/cli.py validate /path/to/content-root
```

For a single course directory, validation also follows referenced modules. Validate the tenant root when changing shared widgets or multiple courses.

## Checks

- IDs are stable, unique, and safe for URLs.
- Course manifests reference modules that exist.
- Module manifests reference lesson and quiz files that exist.
- Quizzes use supported question types and `correct`, not `isCorrect`.
- Markdown and inline HTML reference existing local images, videos, PDFs, HTML files, or widgets.
- Widget HTML posts `widget-ready` and `widget-resize` messages.
- External links are intentional; local publishing-critical files are local and validated.
- Course lessons contain the useful explanation directly; references are mostly grouped under `### References`.
- Generated images and charts teach a concept, show a process, or visualise data; they are not decorative filler.
- Live verification uses cache-busted `/api/content/...` and `/manifest.json` endpoints after tenant sync.

## Resources

- Course format guide: `references/course-format.md`
- Publishing workflow: `references/publishing-workflow.md`
- Validator and outline CLI: `scripts/cli.py`
- CI smoke test: `scripts/smoke_test.py`

## CLI

Use `outline` to print the supported structure:

```bash
python3 skills/colab-course-publisher/scripts/cli.py outline
python3 skills/colab-course-publisher/scripts/cli.py outline --json
```

Use `validate` for content:

```bash
python3 skills/colab-course-publisher/scripts/cli.py validate ~/CourseViewerPlatform/content/thecolab
python3 skills/colab-course-publisher/scripts/cli.py validate ~/CourseViewerPlatform/content/thecolab/courses/ai-for-small-business
python3 skills/colab-course-publisher/scripts/cli.py validate ~/CourseViewerPlatform/content/thecolab/modules/afsb-ai-tools --json
```

Use `--strict` when warnings should fail the command.

## Publishing quick path

1. Work in the tenant content repo when one exists, for example `/tmp/<tenant>-course-repo` or a clone of `mycourse-work/<tenant>`.
2. Validate the changed course or tenant root.
3. Commit and push the tenant repo branch/main according to that repo's workflow.
4. Watch the tenant sync workflow upload to R2 and register D1 content.
5. Fetch live cache-busted lesson and manifest endpoints to prove the viewer will receive the new content.

See `references/publishing-workflow.md` for endpoint examples and deployment checks.
