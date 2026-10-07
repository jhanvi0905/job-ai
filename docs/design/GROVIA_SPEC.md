# Fitwise × Grovia design spec

Measured from the live free template https://grovia.framer.ai (2026-10-07). We recreate the **look and section patterns** in our own code. We do not copy Grovia's code, images or copy, and we drop its invented proof (ratings, customer counts, testimonials, client logos).

Every section states its **job** (understand / highlight / compel) and its **psychology lever**. Decoration with no job is cut.

---

## 1. Tokens

### Colour
| Token | Value | Use |
|---|---|---|
| `--canvas` | `#F4F2EE` | page background |
| `--surface-quiet` | `#F0ECE6` | segmented tab bar, footer panel, inactive fills |
| `--card` | `rgba(255,255,255,0.9)` | step cards, floating UI cards |
| `--card-glass` | `rgba(255,255,255,0.4)` | FAQ items |
| `--ink` | `#000000` | headings, primary button fill |
| `--ink-2` | `#1A1A1A` | strong body |
| `--muted` | `#605F5F` | body copy, subtitles |
| `--faint` | `#AEAEAE` | inactive tab text, placeholders |
| `--highlight` | `#FEF7AF` | highlighted row (e.g. "Strong fit" job in the list) |
| `--accent` | `#FECD1A` | yellow pill CTA on dark bands, small badges |
| `--chart-cyan` | `#84E6F6` | evidence: direct |
| `--chart-salmon` | `#F7A49E` | evidence: none / gap |
| `--chart-yellow` | `#FECD1A` | evidence: adjacent |
| `--alert` | `#E83043` | tiny deltas only |
| `--band-dark` | `#2E3A40` base + blurred warm radial gradients (red/orange/green, see §7) | pricing and final CTA bands |

Fit semantics in the app: strong = cyan-tinted chip, plausible = yellow, weak = salmon, no = faint. Never colour alone: always a text label.

Marketing is **light only** (as Grovia). The app may keep dark mode if it costs nothing; light is the reference.

### Type
- Display: **Albert Sans 400** (Google Fonts via `next/font/google`). H1 `56px / 1.1 / -0.05em` (Grovia: 56px, -2.8px). H2 `40px / 1.15 / -0.05em` (40px, -2px). H3 `28px / -0.04em`.
- UI and body: **Geist** (`next/font/google`). Body 18px subtitle / 16px body, `-0.03em`; labels and nav 16px **500**.
- Headings are deliberately *light weight* (400). Hierarchy comes from size and space, not boldness.
- Replace Fraunces / Hanken Grotesk everywhere.

### Shape, depth, spacing
| Element | Radius | Shadow | Padding |
|---|---|---|---|
| Floating nav pill | 58px | `0 1px 20px rgba(224,215,198,.5)` (warm) | 8px 12px, h 60, w ~620 desktop |
| Primary button (black pill) | 32px | `0 5px 15px rgba(0,0,0,.2)` | 8px 8px 8px 16px, h 44 |
| Arrow chip inside buttons | 50% | none | 28px circle, white on black buttons, black on yellow |
| Ghost button | 32px | none | 1px `--ink` border |
| Step / feature cards | 20px | `0 8px 20px rgba(0,0,0,.1)` | 24px |
| Floating UI mock cards | 20–24px | `5px 8px 15px rgba(0,0,0,.15)` | 16–24px |
| Segmented tab bar | 40px | none | 8px, bg `--surface-quiet`, active tab white pill 32px |
| Plan list item (on dark) | 16px | `5px 8px 15px rgba(0,0,0,.15)` | 16px 20px, bg `rgba(255,255,255,.1)` |
| FAQ item | 20px | none | 32px, bg `--card-glass` |
| Dark bands | 32px (inset 16px from viewport edges) | none | 80–96px vertical |
| Footer panel | 32px | none | bg `--surface-quiet` |

Content width 1040px. Section vertical rhythm 120–160px desktop, 80px mobile. Hero background: very soft vertical light-beige stripes (CSS repeating linear-gradient at 3–4% contrast), no images.

### Motion (Framer-style)
- **Appear:** opacity 0→1, y 24→0, blur 6px→0, 0.7s, ease `[0.22,1,0.36,1]`, once, stagger 0.08s within a group. Triggered at ~15% in view.
- **Hero mock cards:** float in from y 40 with a 0.15s offset between the list card and the overlapping chart card.
- **Step cards:** active card expands (flex-grow), springs `stiffness 260, damping 30`; auto-advance every 5s, pauses on hover/focus; click/keyboard selects.
- **Tab panel:** crossfade + 8px slide, 0.35s.
- **FAQ:** height auto animate 0.3s; `+` rotates 45° to `×`.
- **Nav:** stays a floating pill; gains slightly stronger shadow after 40px scroll.
- `prefers-reduced-motion`: no transforms, no blur, no auto-advance; final states rendered.

---

## 2. Sections, top to bottom

### 2.1 Floating pill nav
Grovia: centered white pill, logo left, 3 links, black "Contact us" pill with arrow chip.
**Fitwise:** logo mark + "Fitwise" · links *How it works · Why it's different · Pricing* · black pill **"Get my free fit check →"**. Sticky at top 16px. Mobile: logo + CTA pill, links in a sheet.
Job: compel. Lever: the next step is always one tap away.

### 2.2 Hero (two columns)
Grovia: left H1 three lines, muted subtitle, black + ghost buttons; right two overlapping floating cards (customer list with a yellow-highlighted row; "Daily Average" stacked-bar card).
**Fitwise left:**
- H1: "Apply to fewer jobs. Better ones." (2–3 lines at 56px).
- Subtitle: "Fitwise checks each job against what you've really done, shows where you don't fit yet, and tailors your resume using only your own evidence."
- Buttons: black **Get my free fit check →**, ghost **See a sample**.
- Friction line under buttons, 14px muted: "Free to start · No card · We never apply for you".
**Fitwise right (Sample tag on the card):**
- Card A "Your matches · Sort by best fit": 3 job rows (title, company, location), the top row highlighted `--highlight` with a "Strong fit" chip and row actions (save / tailor icons).
- Card B overlapping bottom-right, "Why it fits": odometer score count-up (e.g. 78 → labelled "Sample fit"), one stacked bar per requirement coloured direct / adjacent / gap (cyan / yellow / salmon), legend underneath. Mirrors Grovia's stacked-bar chart but each bar *means* something.
Job: highlight + compel. Lever: show-don't-tell; the product's verdict is visible in the first viewport.

### 2.3 Product band
Grovia: a full app screenshot (kanban) sliding up under the hero.
**Fitwise:** an HTML/CSS mock of the **tracker** (columns Saved / Tailored / Applied / Interview, cards with company, fit chip, "Follow up?" nudge on one Applied card) inside a rounded white frame with a small left sidebar (Feed, Tracker, Evidence, Settings). Sample tag. Partially overlapped by the step cards like Grovia.
Job: understand. Lever: concreteness, "this is the place I'll work in".

### 2.4 Pain statement (scroll-synced, ours)
Not in Grovia, kept because it carries the narrative. Centered, Albert Sans 40px, max 820px. Words go from `--faint` to `--ink` as the section scrolls through: "You've sent dozens of applications. Most never got a reply. Not because you're not good, but because nobody told you which jobs were worth it, or how to show what you've actually done."
Job: highlight. Lever: resonance before any product is shown.

### 2.5 Expanding step cards (3)
Grovia: three cards in a row, active one ~2× wider with a UI visual on its right; number "01" top-left; title + text bottom-left.
**Fitwise:**
- 01 **Upload your resume.** "We pull out your real achievements. You review and edit every one." Visual: extracted achievement list with edit pencils.
- 02 **See an honest fit.** "Every requirement checked against your evidence, with gaps named, not hidden." Visual: requirement checklist, one row marked Gap.
- 03 **Tailor with proof.** "Rewrite bullets for this job using only what you've done. Accept what you like." Visual: bullet with evidence chip.
Job: understand. Lever: effort minimisation (3 steps feel small) + IKEA effect (step 1 says *you* edit).

### 2.6 Feature tabs: "Built to be honest"
Grovia: centered H2 + subtitle; segmented tab bar with icons; panel = UI image left, yellow small-caps badge + H3 + text right.
**Fitwise tabs:** Fit check · Evidence bank · Tailoring · Tracker. Each panel: left a UI mock; right badge (e.g. `FIT CHECK`), H3, 2 lines of copy, and one "how it's different" line.
- Fit check: "A reason for every score." / Others give a number; we show which requirements you meet.
- Evidence bank: "Your experience, structured and yours to edit."
- Tailoring: "Bullets you can defend in an interview." / Anything without evidence is dropped.
- Tracker: "Know what's next." / Follow-up reminders after 7 days.
Job: understand. Lever: show-don't-tell, depth on demand.

### 2.7 "How we're different" (Grovia's integrations layout)
Grovia: left-aligned H2, text, black pill CTA, then a numbered list with black circular numerals.
**Fitwise:** H2 "Most job tools optimise for volume. We optimise for fit." + CTA. Numbered list, each line "Other tools → Fitwise":
1. Keyword scanners give you a score → we give you the reasons and the gaps.
2. Auto-apply bots send hundreds of applications → you send fewer, better ones, and you press apply.
3. AI resume writers make things up → every bullet cites your own evidence, or it's dropped.
Job: highlight the wedge. Lever: contrast and anchoring against the category the reader already knows. Never name companies.

### 2.8 Pricing (dark band)
Grovia: dark rounded band with a blurred painterly background; left H2 white + selectable plan list; right glass detail card (icon, price, description, yellow pill CTA, checklist); below the list, avatars + "4.9/5 Rated".
**Fitwise:** plan list *Free* / *Pro* (Pro row: "Announced soon"). Detail card for Free: "$0", what's included (daily screening cap, one resume parse, one tailor, tracker), yellow pill **Start free →**. Pro detail: "Price announced soon" + included list + **Join the waitlist** with inline email field. Replace the rating block with three honest trust lines with check icons: *No card required · You approve every change · Delete your data anytime.*
Background: `--band-dark` with 3 large blurred radial gradients (`#E8604C`, `#F2A541`, `#4E8B6A`, blur 80px, 35% opacity), plus subtle noise.
Job: compel. Lever: anchoring (Free shown with Pro), risk removal.

### 2.9 "Who it's for" (replaces Success stories)
Grovia: 2×2 cards with colourful photographic scenes, logo overlay, year pill, name, one-line description.
**Fitwise:** 2×2 cards with CSS-only colour scenes in Grovia's palette (teal/orange split, peach, pink, mustard) and a large simple glyph instead of a logo. Pill tag replaces year. Cards:
- **New to Canada** · "Filters for where you can actually work, and maps your experience to local roles."
- **Switching careers** · "Shows which of your achievements carry over, and what's genuinely missing."
- **Experienced, short on time** · "Skip the long list. See the few roles worth a tailored application."
- **Back after a break** · "Rebuild a resume from what you've done, without padding the gap."
Job: compel. Lever: self-identification ("that's me").

### 2.10 The Fitwise promise (replaces testimonials)
Grovia: three quote cards with names and roles.
**Fitwise:** three cards in the same style, written as commitments, signed "— The Fitwise promise": "We will never apply on your behalf." / "We will never add experience you don't have." / "We will never sell your data or your resume." No fake people.
Job: highlight trust. Lever: honesty as the brand; reverses the reader's main fear about AI tools.

### 2.11 FAQ (two columns)
Grovia: left H2 "Your questions, answered" + text + ghost pill; right accordion items on glass.
**Fitwise:** same layout, objection-first order: Is it really free? · Will it make things up? · Does it apply for me? · Do you sell my data? · Does it work outside tech? (honest: strongest for tech and data roles today) · Can I delete everything?
Job: compel. Lever: objection handling right before the ask.

### 2.12 Final CTA (dark band)
Grovia: "Start your journey" + glass contact form.
**Fitwise:** left H2 white "Find the jobs worth your time." + one line; right glass card with email field + yellow pill **Get my free fit check →** (signup) and a text link "or join the waitlist". Under the left text: the same three trust lines.
Job: compel. Lever: final low-friction ask.

### 2.13 Footer panel
Grovia: rounded quiet panel, newsletter left, links right, giant email wordmark bottom-left.
**Fitwise:** waitlist email field left, links right (How it works, Pricing, FAQ, Privacy, Log in), giant "fitwise" wordmark in Albert Sans bottom-left, small "© Fitwise" right.

---

## 3. App surfaces (same system)
- App header becomes the floating pill (logo, Feed · Tracker · Settings, account menu).
- Cards: `--card`, 20px radius, card shadow. Primary actions: black pill with arrow chip; secondary: ghost pill.
- Feed card: top-ranked unseen strong fit row uses `--highlight` like the hero list.
- FitMeter: requirement-coloured stacked bar (cyan / yellow / salmon) + text label; category stays primary (the API returns categories only; no invented percentage).
- Retention surfaces (from GO_TO_MARKET §6c), styled as Grovia mini-cards: new-match count in the feed header, "This week" card styled like Grovia's "Daily Average" card (reviewed / tailored / applied / awaiting reply), profile completeness meter, tracker follow-up nudge.

## 4. Acceptance
- Side-by-side screenshots of Fitwise and Grovia at desktop show the same visual language: canvas colour, pill nav, light display type, black pill buttons with arrow chips, floating overlapping cards, segmented tabs, dark painterly pricing band, quiet footer panel.
- No fabricated ratings, counts, testimonials or logos; sample UIs carry a "Sample" tag.
- 390px mobile: no horizontal scroll, nav collapses, step cards stack, hero mock cards stack under the text.
- AA contrast (check muted `#605F5F` on `#F4F2EE`: passes for body), 44px targets, keyboard-operable tabs, steps and accordion.
- `npx tsc --noEmit`, `npm run lint`, `npm run build` pass.
