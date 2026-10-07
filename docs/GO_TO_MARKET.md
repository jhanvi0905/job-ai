# Go-to-market

Working assumptions, not validated facts. Everything marked **Test** should be checked with real users before money is spent on it.

## 1. The one idea
Job seekers do not lack tools that *apply* for them. They lack a way to know **which jobs are worth the effort** and a resume that is **true and still persuasive**.

> **Apply to fewer jobs. Better ones. With a resume that's true.**

Sell the exact pain, then the exact fix. Never lead with "AI".

## 1b. How we stand apart
The market already has three kinds of tools. We are positioned against the category, never by naming companies.

| Category | What it optimises | The cost to the seeker | Our counter |
|---|---|---|---|
| Keyword-match resume scanners | A match score | Keyword stuffing; a number with no reasons | Fit per requirement, with the gaps named |
| Auto-apply bots | Application volume | Spam, employer distrust, no control | Fewer, better applications; you press apply |
| AI resume writers | Fluent text | Invented experience you can't defend in interview | Every bullet cites your own evidence or is dropped |

Positioning line: **the job tool that tells you where you *don't* fit.** (Avoid "the only" in public copy unless verified.) Honesty is the feature competitors structurally can't copy without breaking their own growth model, since they gain from volume and inflated claims.

## 2. Pain → promise map
| Pain the seeker feels | What we say | What the product does |
|---|---|---|
| Dozens of applications, silence | "Stop sending applications into the void." | Fit band per job, so effort goes to jobs that can say yes |
| "Is this job even for me?" | "Know before you apply." | Why it fits + honest gaps, requirement by requirement |
| Rewriting the resume every time | "One honest resume, tailored in minutes." | Bullet rewrites drawn only from your own achievements |
| Fear of exaggerating, imposter feelings | "Nothing in your resume you can't defend in an interview." | Every bullet cites its evidence; unsupported bullets are dropped |
| Newcomers unsure of eligibility | "Filtered for where you can actually work." | Per-user country, remote and seniority filters |
| Distrust of AI tools that spam or invent | "We never auto-apply. You press the button." | No auto-apply, no scraping, delete anytime |

## 3. Who it is for (in order of pull)
1. **Newcomers to Canada** with real experience and a confusing market (first beta group; dogfood).
2. **Career switchers** who need their existing experience mapped to a new role.
3. **Experienced professionals** who want fewer, better applications.

Wide enough to feel mainstream, specific enough to speak to. Landing copy addresses the pain, not the persona label.

## 4. Psychology levers, and the line we do not cross
| Lever | Use | Do not |
|---|---|---|
| Resonance | Open with the feeling ("Sound familiar?") | Mock or shame the reader |
| Show, don't tell | Live sample demo of a fit check | Show fake results as real |
| Effort minimisation | One dominant CTA, first value in minutes | Long forms before value |
| IKEA effect | User reviews and edits their achievements | Hide the evidence bank |
| Loss framing | "Every generic application is a missed chance" (gentle) | Fake scarcity, countdowns |
| Social proof | Real beta quotes only, once they exist | Invented testimonials, user counts, logos |
| Anchoring | Free vs Pro side by side | Invent prices before they are decided |
| Honesty as brand | "What we won't do" section | Overclaim outcomes (no "get hired faster") |

We make **no outcome promises** (interviews, offers). We promise clarity, evidence and saved time.

## 5. Offer and pricing (to be decided)
- **Free:** limited daily screening, one resume parse, one tailor. Enough to feel the product work.
- **Pro:** daily refresh, more tailors, more countries. **Price: undecided.** Test two price points with waitlist users before launch.
- **Credits:** pay-per-tailor overage, priced from real token cost plus margin.
- Never sell candidate or job data.

## 6. Acquisition
| Channel | Content | Why |
|---|---|---|
| LinkedIn + Reddit (r/cscareerquestions, r/ImmigrationCanada, r/ExperiencedDevs) | Before/after tailored bullet with its evidence | Concrete and shareable |
| Newcomer communities (Toronto/Vancouver Discords and Slack, settlement-agency groups) | "Which Canadian remote roles fit you" guides | Trust-first, high-pain audience |
| Product Hunt | Honest-fit angle, not "AI agent" | One-day spike for the waitlist |
| SEO later | "{role} jobs in Canada you actually qualify for" | Long-tail, programmatic once catalog is real |
| Free fit check (**Test**) | Paste a JD + resume → instant fit and gaps | The Motion/Framer pattern: a free tool as the hook. Needs a rate-limited public endpoint and a hard LLM budget cap before launch |

## 6b. Funnel and what to measure
Visit → waitlist/signup → resume uploaded → first feed → first tailor accepted → application tracked → week-2 return.
Watch the **activation rate (resume uploaded)** and **time to first match** first; everything else depends on them.

## 6c. Retention: why someone comes back
A job search is episodic and stressful, so retention must be *useful*, never manipulative. The loop is: **trigger → action → reward → investment**.

| Stage | Mechanism | Surface (UI-only pass) | Needs backend later |
|---|---|---|---|
| Trigger (external) | "N new matches since your last visit" | New-match badge and count in the feed header | Weekly email digest (mail provider + worker) |
| Trigger (internal) | The recurring "what should I apply to today?" | Feed opens on "Today's best fits" | Saved-search alerts |
| Action | One-click next step | "Tailor this" from the card; follow-up nudge on the tracker | None |
| Reward (variable, honest) | Fresh matches vary daily; a strong fit is a real win | Fit meter, short celebration on a strong match | None |
| Investment (IKEA effect) | The user's edited achievements make every later result better | Profile completeness meter ("3 more achievements sharpen your matches") | None |
| Progress | Visible momentum without streak guilt | "This week" card: reviewed, tailored, applied, awaiting reply | Weekly stats endpoint |
| Follow-up | Replies are slow; remind kindly | "Applied 7 days ago. Follow up?" on tracker cards | Reminder emails |

Rules: no streaks that punish a break (job seekers stop when they get hired, and that is success); no fake urgency; every nudge can be turned off; celebrate the user's evidence, not our product. Success measures: week-2 return rate, tailors accepted per active user, and applications tracked per active user.

## 7. Launch sequence
1. Dogfood on Canada prefs (you). Fix the feed quality before anyone else sees it.
2. 10 beta users from newcomer groups; collect quotes **with permission**.
3. Waitlist landing live; publish 3 before/after posts.
4. Open Free tier; Product Hunt.
5. Introduce Pro after observing which actions users hit the cap on.

## 8. Risks
- **Feed quality** is the product. A weak match list ends trust faster than any copy can build it.
- **Cost per free user.** Per-user daily caps and the dollar guard exist; verify with real provider pricing.
- **Claims discipline.** Every public claim must be true of the shipped product.
- **Role coverage.** Filters are still AI/ML-centric; broad "mass" positioning outruns the product until taxonomies are per-user.
