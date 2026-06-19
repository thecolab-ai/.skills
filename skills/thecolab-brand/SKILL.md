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

Use the live `thecolab.ai` website as the brand source of truth. The look is editorial, premium, warm, and sparse — not neon SaaS sludge.

### Site-Derived Palette

Use these as defaults unless a client brand overrides them:

- **Ink / near black:** `#171412` — headings, primary CTAs, footer/dark sections.
- **Warm off-white:** `#F8F7F4` — main canvas/background.
- **White card:** `#FFFFFF` — cards and content panels.
- **Deep navy:** `#31465F` — large stat cards and trust/depth blocks.
- **Colab blue:** `#1688C7` — headline emphasis, links, metric accents.
- **Bright blue:** `#19A7E0` — gradient/high-energy accents.
- **Kea orange:** `#C94A0A` — sparing metric emphasis/warnings.
- **Charcoal body:** `#4F4943` — paragraph copy.
- **Muted stone:** `#6E6861` — captions/supporting text.
- **Soft border:** `#DDD8D0` — card outlines.

Recommended balance: 65–75% warm off-white/white, 15–20% ink/navy, 5–10% blue, tiny orange accents.

### Type & Components

- Headings feel like editorial serif: Georgia / Times-style, heavy, tight tracking.
- Body copy is clean sans-serif: Inter/system sans, generous line height.
- Primary CTAs are black rounded rectangles with white text.
- Cards are rounded white panels with soft borders/shadows.
- Metrics use big bold sans numerals with blue/orange accents.
- Dark community/event sections use near-black backgrounds with white text and blue accents.

## Deck Rules

When creating HTML→PDF decks, proposals, or presentation-style outputs:

1. Start with the story: audience, decision, one-line takeaway, slide spine.
2. Use the thecolab.ai visual system: warm canvas, black serif headlines, blue emphasis, rounded cards, restrained orange.
3. Every slide should have a visual structure: cards, timeline, callout, process flow, comparison, quote block, or metric panel.
4. Keep text tight: one idea per slide, 3–5 bullets max, no paragraph sludge.
5. Include proof/receipts when making claims: metric, example, source, or operational implication.
6. Treat first-pass decks as editable working drafts unless the user asks for polished final art.

## Layout Motifs

- Website-style hero: centered editorial serif headline with blue emphasis word.
- Cream content slides with rounded white cards and sparse blue accents.
- Navy-to-blue metric panels for headline statistics.
- Before/after columns for transformation stories.
- Three-card operating model: **Discover → Build → Operate**.
- Timeline/process flows for pilots and implementation plans.
- Dark near-black community/CTA sections with white text and blue CTA accent.

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
