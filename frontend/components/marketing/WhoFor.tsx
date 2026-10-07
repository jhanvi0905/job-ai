import { AppearGroup, AppearItem, Appear } from "./motion";
import { Container, H2, Lead } from "./shared";

const g = { width: 44, height: 44, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
const Compass = () => <svg {...g}><circle cx="12" cy="12" r="9" /><path d="m15.5 8.5-2 5-5 2 2-5z" /></svg>;
const Swap = () => <svg {...g}><path d="M4 8h13l-3-3M20 16H7l3 3" /></svg>;
const Clock = () => <svg {...g}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>;
const Sunrise = () => <svg {...g}><path d="M4 18h16M7 18a5 5 0 0 1 10 0M12 4v3M5 9l1.5 1.5M19 9l-1.5 1.5" /></svg>;

const CARDS = [
  { title: "New to Canada", tag: "Eligibility filters", text: "Filters for where you can actually work, and maps your experience to local roles.", scene: "scene-1", Glyph: Compass },
  { title: "Switching careers", tag: "Transferable skills", text: "Shows which of your achievements carry over, and what's genuinely missing.", scene: "scene-2", Glyph: Swap },
  { title: "Experienced, short on time", tag: "A short list", text: "Skip the long list. See the few roles worth a tailored application.", scene: "scene-3", Glyph: Clock },
  { title: "Back after a break", tag: "No padding", text: "Rebuild a resume from what you've done, without padding the gap.", scene: "scene-4", Glyph: Sunrise },
];

// Job: compel. Lever: self-identification ("that's me"). Replaces Grovia's success
// stories: no logos, no clients, just the four situations we're built for.
export function WhoFor() {
  return (
    <section aria-labelledby="who-h" className="py-28 sm:py-40">
      <Container>
        <Appear className="mx-auto max-w-[620px] text-center">
          <H2 id="who-h">Who it&apos;s for</H2>
          <Lead className="mt-4">Built for people with real experience and a confusing market, whatever brought you here. Across 12 professional role families, from engineering and data to marketing, finance, operations and HR.</Lead>
        </Appear>
        <AppearGroup as="ul" className="mx-auto mt-14 grid max-w-[1000px] gap-2 rounded-panel bg-well p-2 sm:grid-cols-2">
          {CARDS.map((c) => (
            <AppearItem as="li" key={c.title} className="rounded-card bg-card p-2">
              <div className={`scene ${c.scene} flex h-[200px] items-center justify-center rounded-[14px] text-on-dark sm:h-[290px]`}>
                <span className="relative z-10 flex items-center gap-2 drop-shadow-sm">
                  <c.Glyph />
                </span>
                <span className="absolute bottom-3 right-3 z-10 rounded-full bg-ink/25 px-2.5 py-1 text-[12px] text-on-dark backdrop-blur-sm">{c.tag}</span>
              </div>
              <div className="px-4 pb-5 pt-5">
                <h3 className="font-display text-[22px] tracking-[-0.04em] text-ink">{c.title}</h3>
                <p className="mt-2 text-base leading-[1.45] text-muted">{c.text}</p>
              </div>
            </AppearItem>
          ))}
        </AppearGroup>
      </Container>
    </section>
  );
}
