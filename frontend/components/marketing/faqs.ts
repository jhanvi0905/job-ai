// Objection-first order (spec §2.11). Answers are plain claims the shipped product keeps.
// Plain module (no "use client") so the page can also emit FAQPage JSON-LD on the server.
export const FAQS = [
  { q: "Is it really free?", a: "Yes. The free plan needs no card and has daily limits on screening and tailoring. Pro pricing isn't set yet; waitlist members hear first, and nothing changes on your free plan unless you choose it." },
  { q: "Will it make things up?", a: "No. Suggestions only reword achievements you've already checked, and each one shows its source. If there is no evidence for a line, the line is dropped. You accept or reject every change." },
  { q: "Does it apply for me?", a: "No. Never. You press apply on the employer's own site. Fitwise helps you decide where to aim and what to say." },
  { q: "Do you sell my data?", a: "No. We never sell your resume, your achievements, your matches or any job data." },
  { q: "Does it work outside tech?", a: "Yes, for 12 common professional role families: software engineering, data and analytics, AI and ML, product management, design, marketing, sales, customer success and support, operations and project management, finance and accounting, people and HR, and IT and security. Matching is strongest where job requirements are concrete (named tools, certifications, measurable outcomes) and rougher where postings are vague. Trades, healthcare and other licensed roles aren't covered yet." },
  { q: "Can I delete everything?", a: "Yes. Settings has a Delete account button. It permanently removes your resume, achievements, matches and tracker." },
];
