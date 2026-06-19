---
name: thecolab-brand
description: Use when creating TheColab.ai branded outputs: decks, proposals, one-pagers, event collateral, social images, reports, or WhatsApp bot responses that need The Colab's voice, positioning, colours, and visual style.
---

# TheColab.ai Brand Skill

Use this with `pptx` whenever a deck, presentation, workshop pack, pitch deck, proposal, event recap, or client-facing visual should look and sound like The Colab.

## Brand Snapshot

The Colab is a New Zealand AI consultancy and community helping businesses move from AI demos to operational capability.

- **Positioning:** practical AI operators, not ivory-tower consultants.
- **Core promise:** model-agnostic AI strategy + implementation that turns pilots into production workflows.
- **Audience:** NZ business leaders, founders, operators, councils, associations, and technical teams.
- **Founders:** Simon Conroy (strategy/commercial) and Adam Holt (technical/agentic systems).
- **Community:** Claude Code Meetups NZ and hands-on AI education/events.

## Voice

- Direct, useful, sharp, warm.
- Confident without corporate theatre.
- Prefer concrete verbs: build, ship, automate, measure, integrate, operate.
- Use light NZ flavour when appropriate; do not overdo slang.
- Avoid generic AI waffle: "unlock potential", "leverage synergies", "future-proof your business", "cutting-edge solutions".

## Message Pillars

1. **AI that works in the business** — not another strategy PDF that dies in SharePoint.
2. **Humans + agents together** — the practical operating model is collaboration, not magic replacement.
3. **Fast pilots, real constraints** — prove value quickly, with privacy, integrations, and workflow ownership considered early.
4. **Model-agnostic by design** — OpenAI, Anthropic, Google, and open-source models are tools, not religions.
5. **Community-backed learning** — meetups, demos, and shared practice keep the work grounded.

## Visual Direction

Use a modern consultancy/community aesthetic: premium but approachable, useful not sterile.

### Palette

Use these as defaults unless a client brand overrides them:

- **Ink / deep charcoal:** `#1C1917` — title slides, strong text, premium dark sections.
- **Colab blue-grey:** `#2E4057` — section blocks, trust, depth.
- **Electric cyan:** `#0EA5E9` — highlights, connectors, progress, active AI/agent cues.
- **Cyan dark:** `#0284C7` — secondary accent.
- **Kea orange:** `#C2410C` — sparing emphasis, warnings, key moments.
- **Warm cream:** `#FBF9F6` — light slide backgrounds.
- **Stone text:** `#44403C` — body copy.
- **Muted stone:** `#78716C` — captions, footers.
- **White:** `#FFFFFF`.

Recommended balance: 60–70% ink/cream base, 20–30% blue-grey, 5–10% cyan/orange accents.

## Deck Rules

When paired with `pptx`:

1. Start with the story: audience, decision, one-line takeaway, slide spine.
2. Use a dark title slide, light content slides, and a dark closing/section slide where useful.
3. Every slide should have a visual structure: cards, timeline, callout, process flow, comparison, or quote block.
4. Keep text tight: one idea per slide, 3–5 bullets max, no paragraph sludge.
5. Include proof/receipts when making claims: metric, example, source, or operational implication.
6. Treat first-pass decks as editable working drafts unless the user asks for polished final art.

## Layout Motifs

- Dark title slide with a bold left-aligned title and cyan/orange accent block.
- Cream content slides with rounded white cards and sparse accent dots/lines.
- Big-number callouts for quantified impact.
- Before/after columns for transformation stories.
- Three-card operating model: **Discover → Build → Operate**.
- Timeline/process flows for pilots and implementation plans.

## Slide Copy Patterns

Use these phrases as anchors, not mandatory copy:

- "From demo to operating rhythm"
- "Practical AI capability, built with your team"
- "Pilot fast, integrate deliberately"
- "Agents where they help; humans where judgment matters"
- "The model is not the strategy — the workflow is"

## Clawd / Community Mascot

For community and playful outputs, Clawd is a mischievous kea: curious, clever, occasionally chaotic, stealing unattended API tokens and pecking at bad prompts. Use him for warm humour, not for serious enterprise collateral unless the brief invites it.

## Files & Validation

This is a documentation/brand skill. Use `scripts/cli.py palette --json` for machine-readable colours or `scripts/cli.py skill` for the full guide. The `scripts/smoke_test.py` file validates that the brand guidance remains present for CI.
