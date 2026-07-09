# CourseViewerPlatform Course Format

Use this reference when creating or editing content for `~/CourseViewerPlatform`.

## Recommended Shape

Prefer module-first content roots:

```text
content/<tenant>/
  courses/<course-id>/
    course.json
    welcome.md
    assets/cover.png
  modules/<module-id>/
    manifest.json
    intro.md
    practical-example.md
    quiz.json
    assets/diagram.webp
    assets/intro.mp4
  widgets/<widget-name>.html
```

The edge router resolves `course.json` or `blueprint.json` into the runtime `manifest.json` consumed by the player. Legacy monolithic `courses/<course-id>/manifest.json` courses are still supported, but new courses should use module-first packaging.

## Course Files

Simple course file:

```json
{
  "id": "ai-for-small-business",
  "title": "AI for Small Business",
  "description": "Practical AI training for small-business operators.",
  "estimatedDuration": "3-4 hours",
  "coverImage": "cover.png",
  "welcomePath": "welcome.md",
  "modules": [
    "afsb-understanding-ai",
    "afsb-ai-readiness"
  ]
}
```

Rules:
- Folder name should match `id`.
- `modules` is an ordered array of module IDs, not objects.
- `welcomePath` is course-relative and should point to markdown in the course folder.
- `coverImage` should normally be stored in `courses/<course-id>/assets/`. Use `cover.png` or `assets/cover.png`, not an unrelated path.

Use full `blueprint.json` only when electives or slot-level rules are needed:

```json
{
  "id": "workplace-safety",
  "title": "Workplace Safety",
  "description": "Core safety training with electives.",
  "coverImage": "cover.png",
  "welcomePath": "welcome.md",
  "coreModules": [
    { "slotId": "core-01", "moduleId": "hazard-identification" }
  ],
  "electiveGroups": [
    {
      "groupId": "role-track",
      "title": "Role Track",
      "minSelections": 1,
      "maxSelections": 1,
      "options": [
        { "slotId": "opt-01", "moduleId": "contractor-safety" }
      ]
    }
  ],
  "rules": {
    "selectionLockedAfterStart": true,
    "completionPolicy": "core_plus_selected_electives",
    "certificatePolicy": "core_plus_selected_electives"
  }
}
```

Keep `slotId` stable after publishing because learner progress and elective selections can depend on it.

## Module Files

Module manifest:

```json
{
  "id": "afsb-understanding-ai",
  "title": "Understanding AI",
  "description": "Core AI concepts for operators.",
  "tags": ["ai", "small-business"],
  "lessons": [
    { "id": "intro", "title": "Introduction", "type": "content", "markdownPath": "intro.md" },
    { "id": "tools-in-practice", "title": "Tools in Practice", "type": "content", "markdownPath": "tools-in-practice.md" },
    { "id": "quiz", "title": "Understanding AI Quiz", "type": "quiz", "quizPath": "quiz.json" }
  ]
}
```

Rules:
- Folder name should match `id`.
- Keep lesson IDs stable after publishing.
- Supported lesson types are `content`, `quiz`, and `section`.
- `markdownPath` and `quizPath` are module-relative, never absolute, never URLs.
- Keep lesson markdown and quiz JSON flat at the module root unless the platform code is changed.
- Put module-local images, PDFs, videos, and other media in `assets/`.

## Lesson Markdown

Each content lesson should:
- Start with a single `# Lesson Title`.
- Include concrete learning objectives and practical examples.
- Carry the substantive teaching content directly in the lesson body: findings, tables, calculations, caveats, and public-interest interpretation should not live only behind external links.
- Group source links under a bottom `### References` section when they are supporting evidence rather than the primary lesson content.
- Use normal markdown for headings, lists, tables, callouts, code blocks, and links.
- Use fenced `mermaid` only when a diagram is easier than HTML; the player renders Mermaid client-side.
- Use inline HTML sparingly for richer diagrams. Scripts and event handlers are stripped or unsafe in lesson markdown.

Images:

Use markdown image syntax with descriptive alt text. Typical paths are `./assets/process-diagram.webp` for module-local assets and `../assets/overview.png` for course-level legacy assets.

Videos:

```html
<video controls playsinline preload="metadata" style="width: 100%; max-width: 800px; border-radius: 12px; margin: 1.5rem auto; display: block;">
  <source src="./assets/intro.mp4" type="video/mp4">
</video>
```

External video embeds:

```markdown
[Watch the demo](https://player.vimeo.com/video/123456789)
```

Iframe directive:

```markdown
:::iframe
https://player.vimeo.com/video/123456789
:::
```

## Widgets And HTML Artifacts

Use widgets for interactive HTML artifacts that need JavaScript.

Place reusable widget files in:

```text
widgets/<widget-name>.html
```

Reference a widget from lesson markdown:

```markdown
:::widget readiness-calculator
title: Readiness calculator
level: beginner
:::
```

Widget requirements:
- The filename is `<widget-name>.html`.
- The widget must work inside an iframe sandbox with scripts and same-origin.
- Post `widget-ready` when initialised.
- Post `widget-resize` with a numeric `height` whenever the content size changes.
- Read optional props from the `props` query string and theme from `theme`, `primary`, and `font` query params.

Minimum widget script:

```html
<script>
  function notifyReady() {
    parent.postMessage({ type: 'widget-ready' }, '*');
    parent.postMessage({ type: 'widget-resize', height: document.body.scrollHeight }, '*');
  }
  window.addEventListener('load', notifyReady);
</script>
```

## Quiz Format

Quiz file:

```json
{
  "title": "Understanding AI Quiz",
  "type": "quiz",
  "passingScore": 70,
  "questions": [
    {
      "id": "q1",
      "questionNumber": 1,
      "type": "MULTIPLE_CHOICE",
      "question": "Which statement is most accurate?",
      "answers": [
        { "id": "q1_a", "text": "Option A", "correct": false },
        { "id": "q1_b", "text": "Option B", "correct": true }
      ],
      "feedback": "Option B is correct because..."
    }
  ]
}
```

Rules:
- `type` must be `quiz`.
- `passingScore` should be a number from 0 to 100.
- Supported question types are `MULTIPLE_CHOICE`, `MULTIPLE_RESPONSE`, and `MATCHING`.
- Use `correct`, never `isCorrect`.
- `MULTIPLE_CHOICE` needs exactly one correct answer.
- `MULTIPLE_RESPONSE` needs at least one correct answer.
- `MATCHING` needs `matchText` on every answer.

## Validation

Run:

```bash
python3 skills/colab-course-publisher/scripts/cli.py validate <path>
```

Valid targets:
- Tenant/root content directory containing `courses/`, `modules/`, and optionally `widgets/`.
- Single `courses/<course-id>` directory.
- Single `modules/<module-id>` directory.
- Legacy monolithic course directory containing runtime `manifest.json`.

Use `--json` for machine-readable results and `--strict` to fail on warnings.

When validating a single module-first course directory, the validator follows the course's referenced modules. Validate the full tenant root when shared widgets, shared modules, or multiple courses changed.
