import { AppearGroup, AppearItem, Appear } from "./motion";
import { Container, H2, Lead } from "./shared";

const PROMISES = [
  { text: "We will never apply on your behalf.", sub: "You press apply, on the employer's own site.", tile: "scene-1" },
  { text: "We will never add experience you don't have.", sub: "Every bullet cites your own evidence.", tile: "scene-3" },
  { text: "We will never sell your data or your resume.", sub: "And you can delete all of it, anytime.", tile: "scene-4" },
];
const offset = ["md:mt-0", "md:mt-10", "md:mt-20"];

// Job: highlight trust. Lever: honesty as the brand; reverses the reader's main fear
// about AI tools. Commitments in Grovia's testimonial layout, with no invented people.
export function FitwisePromise() {
  return (
    <section aria-labelledby="promise-h" className="pb-28 sm:pb-40">
      <Container>
        <Appear className="mx-auto max-w-[620px] text-center">
          <H2 id="promise-h">The Fitwise promise</H2>
          <Lead className="mt-4">Three things we won&apos;t do, written down so you can hold us to them.</Lead>
        </Appear>
        <AppearGroup as="ul" className="mt-14 grid items-start gap-4 md:grid-cols-3">
          {PROMISES.map((p, i) => (
            <AppearItem as="li" key={p.text} className={`flex min-h-[300px] flex-col rounded-card bg-glass p-6 ${offset[i]}`}>
              <span aria-hidden="true" className="font-display text-[56px] leading-[0.6] text-faint">&rdquo;</span>
              <blockquote className="mt-4 font-display text-[22px] leading-[1.3] tracking-[-0.04em] text-ink">{p.text}</blockquote>
              <p className="mt-3 text-base text-muted">{p.sub}</p>
              <div className="mt-auto flex items-end justify-between gap-4 pt-8">
                <p className="text-[15px] text-ink">&mdash; The Fitwise promise</p>
                <span aria-hidden="true" className={`scene ${p.tile} h-16 w-16 shrink-0 rounded-[12px]`} />
              </div>
            </AppearItem>
          ))}
        </AppearGroup>
      </Container>
    </section>
  );
}
