import { Container, FRICTION_LINE, Pill } from "./shared";
import { HeroCards } from "./HeroCards";

// Job: highlight + compel. Lever: show-don't-tell; the product's verdict is visible in
// the first viewport. Text is server-rendered and never hidden (fast LCP).
export function Hero() {
  return (
    <section aria-labelledby="hero-h" className="hero-stripes pt-32 pb-16 sm:pt-40 lg:pb-36">
      <Container className="grid items-center gap-12 lg:grid-cols-[1fr_520px] lg:gap-8">
        <div className="max-w-[460px]">
          <h1 id="hero-h" className="font-display text-[44px] leading-[1.1] tracking-[-0.05em] text-ink sm:text-[56px]">
            Apply to fewer jobs. Better ones.
          </h1>
          <p className="mt-6 text-lg leading-[1.4] tracking-[-0.03em] text-muted">
            Fitwise checks each job against what you&apos;ve really done, shows where you don&apos;t fit yet, and tailors your resume using only your own evidence.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Pill />
            <Pill tone="ghost" href="#how">See a sample</Pill>
          </div>
          <p className="mt-4 text-sm text-muted">{FRICTION_LINE}</p>
        </div>
        <HeroCards />
      </Container>
    </section>
  );
}
