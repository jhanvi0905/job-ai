# Design references (Framer free marketplace)

Research only. Observed Oct 2026. These are Framer projects: we RECREATE patterns in our own Next.js; never copy code, assets, imagery or copy. Marketplace license shows "Limited" (terms not read); treat everything as inspiration, not source.
Caveat: live previews hide content until scroll-triggered reveals fire, so some sections were read from page text, not seen rendered. Most free templates are dark/neon; only a few fit cream + forest green.

## Templates

### 1. Grovia (best brand fit) - https://www.framer.com/marketplace/templates/grovia/ (preview grovia.framer.ai)
- Free: yes (title "Free Website Template"; a Figma file is sold separately).
- Emulate: warm beige page, sans headline, floating pill nav with one dark CTA. "01 Easy setup / 02 Collaborate / 03 Track growth" as three cards where the active card widens and shows a mini UI. Pricing as a left list of plans selecting a detail card on the right.
- Avoid: "4.9 / 5, 9.2k customers" and named customer quotes (fake for us). Dark pricing slab clashes with calm. Blurry hero until reveal.
- Maps to: hero + nav, how-it-works, Free vs Pro.
- Lever: effort minimisation (3 steps), anchoring (plans side by side).

### 2. Alytics - https://www.framer.com/marketplace/templates/alytics/ (preview alytics.framer.website)
- Free: yes.
- Emulate (from page text; most sections rendered blank in my scroll): section order Features, Benefits, 3-step "How it works", Pricing (monthly/yearly toggle), then a two-column "Other tools vs Alytics" list of pains against fixes, then FAQ. The pain-vs-fix list is the pattern to take.
- Avoid: "Trusted by 1M+ users", logo strip, invented testimonials, invented stats. Blue SaaS styling.
- Maps to: pain-to-fix section, FAQ, pricing.
- Lever: pain resonance, show-don't-tell.

### 3. Aoutive Website - https://www.framer.com/marketplace/templates/aoutive-website/ (preview aoutive.framer.website)
- Free: yes. Light, grid-line aesthetic.
- Emulate: tabbed feature block, a text list on the left (active item highlighted) swapping the visual on the right. Headline whose words darken progressively as you scroll. Stat counters that count up. Use-case cards that fan out/stack.
- Avoid: counters with made-up numbers ("840+ workflows", "84% uptime"). Isometric tech illustrations. Large empty gaps while reveals load; keep our content visible without JS.
- Maps to: "what it checks" feature tabs (fit / gaps / evidence / bullets), scroll headline.
- Lever: show-don't-tell.

### 4. Verity - https://www.framer.com/marketplace/templates/verity/ (preview verity-template.framer.website)
- Free: yes. Only the marketplace description was read; the preview was not scrolled.
- Emulate: section inventory only: use-case tabs showing real product screens, comparison table, pricing toggle, FAQ, final CTA repeated.
- Avoid: black cinematic theme, glow visuals.
- Maps to: page skeleton / CTA repetition.
- Lever: show-don't-tell, repeated single CTA.

### Rejected after looking
- Hedvig: dark, large blank scroll stretches, "Notify me" waitlist framing.
- WaitlistKit: single "Coming soon" screen, nothing to learn for a full page.
- Not opened (thumbnails only): Atoks, Dreelio, Omrix, AuraFlowX, Auraform, Enrolment, Qarin.

## Components (all open via "Copy" button; free per marketplace title)

| Component | URL | Free | Emulate | Avoid | Maps to | Lever |
|---|---|---|---|---|---|---|
| Expanding Step Cards (Pixels71) | /marketplace/components/expanding-step-cards/ | yes (license Limited) | Row of numbered cards, hovered/focused card expands to show its visual, others collapse to slim text; stacks on mobile; keyboard focus opens it. | Hover-only meaning; make it tap/focus friendly. | How it works (Upload, Review fit, Tailor, Apply yourself) | effort minimisation |
| Image comparison (Hugo Marques) | /marketplace/components/image-comparison/ | yes | Draggable before/after slider, touch ok, settable start position. | Image-only; ours should swap real text (generic bullet vs evidence-backed bullet). | Before/after bullet demo | show-don't-tell |
| Split Image Compare (Utkarsh Arya) | /marketplace/components/split-image-compare/ | yes | Same pattern, alternate implementation. | Same. | Same | show-don't-tell |
| Odometer Counter FX (Ali Themes) | /marketplace/components/odometer-counter-fx/ | yes | Each digit rolls as its own wheel from a start to end value. Use for a fit-score reveal (e.g. 0 to 72) in the sample demo. | Never for fake user counts or outcomes. Respect reduced-motion. | Fit meter in demo | show-don't-tell |
| Progress Steps (Beth) | /marketplace/components/progress-steps/ | yes | Horizontal step cards with a sliding progress bar on scroll; gives a sense of journey. | Over-long step copy. | Timeline of the flow / onboarding progress | effort minimisation, IKEA effect |
| ScrollSyncedText | /marketplace/components/scrollsyncedtext/ | yes | Words light up in sync with scroll through a pain paragraph. | Slow scrub that blocks reading; keep text readable if unscrolled. | "Sound familiar?" pain block | pain resonance |
| Text Reveal | /marketplace/components/text-reveal/ | yes | Scroll text reveal that keeps global text styles (stated in its description). | Gimmicky on every heading; use once. | Hero subline or pain block | pain resonance |
| FAQ Fold | /marketplace/components/faq-fold/ | yes | Smooth animated accordion, one open at a time. (Basic FAQ Accordion by Jan S also listed free; only its title was checked.) | Marketing-speak answers. | FAQ ("Will it apply for me?" "Do you invent bullets?") | trust |
| Floating Pill Nav (Omer Mirza) | /marketplace/components/floating-pill-nav/ | yes (listing) | Rounded floating nav with a single accent CTA, as seen in Grovia. Description text not read. | Cramming links. | Sticky nav + CTA | effort minimisation |

## Recommended build order (by expected conversion impact)
1. Hero + one dominant CTA, then repeat that same CTA after pain, demo, pricing, FAQ (Grovia nav, Verity skeleton).
2. Live sample fit check with animated score and gaps (odometer idea + Aoutive tabs); uses sample data, labelled as a sample.
3. Before/after bullet slider with evidence line under the improved bullet (image-comparison idea). This is the "true and persuasive" proof.
4. Pain-vs-fix two-column section (Alytics) plus "What we won't do" honesty block; scroll-synced pain paragraph as the opener.
5. Three/four-step "how it works" with expanding cards, then Free vs Pro side by side (no prices until decided) and FAQ accordion.

## Not verified
- License terms: the marketplace shows "Limited"; full text not read. Do not reuse any assets.
- Not searched or found: comparison-table, pricing-toggle, announcement-bar, logo/testimonial marquee, bento grid, onboarding checklist and empty-state components. Alytics and Verity show toggle/table patterns at template level only.
- Template previews were not scrolled fully rendered; Alytics, Verity and Aoutive details beyond what is stated come from page text or description.
- Motion quality, performance and mobile behaviour were not tested.
