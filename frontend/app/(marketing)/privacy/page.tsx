// DRAFT — review with a lawyer before launch. Plain-language summary of current practice;
// keep in sync with the backend (DELETE /me, LLM routing, subprocessors).
import type { Metadata } from "next";
import Link from "next/link";
import { LegalEmail, LegalList, LegalPage, type LegalSection } from "@/components/marketing/LegalPage";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "What Fitwise collects, why, who processes it, how long we keep it, and how to delete it.",
  alternates: { canonical: "/privacy" },
};

const UPDATED = "October 7, 2026";

const SUBPROCESSORS: Array<[string, string]> = [
  ["LLM provider — to be confirmed", "Reads your resume text and job descriptions to extract achievements, check fit and suggest tailored bullets."],
  ["Supabase", "Sign-in, database and private file storage for your resume."],
  ["Vercel", "Hosts this website."],
  ["Fly.io", "Runs the Fitwise API that does the matching."],
  ["Sentry", "Error reports so we can fix crashes. We strip request bodies, auth headers and personal details before sending."],
];

const sections: LegalSection[] = [
  {
    id: "collect",
    title: "What we collect",
    body: (
      <>
        <p>Only what the product needs to work:</p>
        <LegalList items={[
          <><strong>Account details:</strong> your email address and sign-in method (password, magic link or Google). Passwords are handled by our sign-in provider; we never see them.</>,
          <><strong>Your resume:</strong> the file you upload, the text we extract from it, and the achievements we pull out, including any edits you make.</>,
          <><strong>Your search preferences:</strong> countries, workplace types, role families, years of experience and similar settings.</>,
          <><strong>Your activity in Fitwise:</strong> jobs we matched for you, fit results, tailored bullets you accepted, and your tracker (statuses and notes).</>,
          <><strong>Usage records:</strong> counts of screenings, analyses and tailorings so we can apply plan limits, plus basic technical logs (time, request path, error codes).</>,
          <><strong>Waitlist:</strong> if you join the waitlist, your email and where you signed up from.</>,
        ]} />
        <p>We don&apos;t ask for your date of birth, address, immigration status, or government ID, and we&apos;d ask you not to put them in your resume upload.</p>
      </>
    ),
  },
  {
    id: "why",
    title: "Why we use it",
    body: (
      <LegalList items={[
        "To run the service you asked for: find jobs, check how your experience covers each one, and suggest resume changes you approve.",
        "To keep your account secure and apply fair-use and plan limits.",
        "To fix bugs and keep the service reliable.",
        "To email you about your account, and about Pro if you joined the waitlist. You can opt out of non-essential emails at any time.",
      ]} />
    ),
  },
  {
    id: "never",
    title: "What we never do",
    body: (
      <LegalList items={[
        <><strong>We never sell your data</strong>, your resume, or anything derived from it. We don&apos;t share it with advertisers or data brokers.</>,
        <><strong>We never apply to jobs for you.</strong> Fitwise has no auto-apply. You press apply on the employer&apos;s own site.</>,
        <><strong>We never send your resume to employers.</strong> Nothing leaves Fitwise unless you download it and send it yourself.</>,
        <>We don&apos;t use your resume to train our own AI models.</>,
      ]} />
    ),
  },
  {
    id: "ai",
    title: "How AI processes your data",
    body: (
      <>
        <p>
          Fitwise uses a large language model (LLM) to read your resume, compare it with job descriptions, and draft
          tailored bullets. To do that, your resume text, achievements and the job description are sent to our LLM provider
          for processing. We only use providers that contractually agree not to train their models on data sent through their
          API and to delete it after a short retention window. Every suggestion is shown to you and nothing is applied without your approval.
        </p>
      </>
    ),
  },
  {
    id: "subprocessors",
    title: "Who processes it for us",
    body: (
      <>
        <p>These service providers process data on our behalf, under contract, only to run Fitwise:</p>
        <div className="overflow-hidden rounded-card bg-glass">
          <table className="w-full text-left text-[15px]">
            <thead><tr className="border-b border-line"><th scope="col" className="p-4 font-medium">Provider</th><th scope="col" className="p-4 font-medium">What for</th></tr></thead>
            <tbody>
              {SUBPROCESSORS.map(([name, why]) => (
                <tr key={name} className="border-b border-line last:border-0 align-top">
                  <td className="p-4 font-medium">{name}</td><td className="p-4 text-muted">{why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          Some of these providers store or process data outside Canada, including in the United States. When that happens your
          information is subject to the laws of that country. We&apos;ll update this list before adding a new provider.
        </p>
      </>
    ),
  },
  {
    id: "cookies",
    title: "Cookies and local storage",
    body: (
      <p>
        We use cookies only to keep you signed in. We also keep small, non-identifying notes in your browser (for example,
        when you last visited your feed, or a background task in progress) so the app can pick up where you left off. We don&apos;t
        use advertising or cross-site tracking cookies.
      </p>
    ),
  },
  {
    id: "retention",
    title: "How long we keep it, and deleting it",
    body: (
      <>
        <p>We keep your data while your account is open. You can delete it at any time:</p>
        <LegalList items={[
          <>Go to <Link href="/settings" className="font-medium underline underline-offset-4">Settings</Link> and choose <strong>Delete my account</strong>. This permanently erases your account, resume files, achievements, preferences, matches, tailored resumes, tracker and waitlist entry from our live systems straight away.</>,
          "You can also delete individual achievements, or replace your resume, whenever you like.",
          "Copies in our encrypted backups roll off automatically within 30 days. We don't restore deleted accounts from backups.",
          "Error reports and technical logs, which don't contain your resume, expire within 90 days.",
        ]} />
      </>
    ),
  },
  {
    id: "rights",
    title: "Your rights (PIPEDA)",
    body: (
      <>
        <p>
          Fitwise is built in Canada and follows the Personal Information Protection and Electronic Documents Act (PIPEDA).
          You have the right to:
        </p>
        <LegalList items={[
          "Know what personal information we hold about you and how it's used.",
          "Get a copy of it, and ask us to correct anything that's wrong.",
          "Withdraw consent and have your information deleted (see above).",
          "Complain to us, and if you're not satisfied, to the Office of the Privacy Commissioner of Canada (priv.gc.ca).",
        ]} />
        <p>To make a request, email <LegalEmail />. We&apos;ll reply within 30 days. If you live outside Canada you may have similar rights under your local law; ask and we&apos;ll help.</p>
      </>
    ),
  },
  {
    id: "security",
    title: "Security",
    body: (
      <p>
        Data is encrypted in transit and at rest. Resume files are kept in private storage that only our API can read, and every
        request is checked against your account. No system is perfectly secure; if a breach affects your information we&apos;ll tell
        you and the Privacy Commissioner as the law requires.
      </p>
    ),
  },
  {
    id: "children",
    title: "Age",
    body: <p>Fitwise is for people looking for professional work. It isn&apos;t meant for anyone under 16.</p>,
  },
  {
    id: "changes",
    title: "Changes and contact",
    body: (
      <p>
        If we change this policy in a way that matters, we&apos;ll email you before it takes effect. Questions about privacy go to
        our privacy officer at <LegalEmail />. See also our <Link href="/terms" className="font-medium underline underline-offset-4">Terms of Service</Link>.
      </p>
    ),
  },
];

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy Policy"
      updated={UPDATED}
      intro={
        <p>
          The short version: we use your resume and preferences only to find and explain jobs for you. We never sell your
          data, never apply on your behalf, and you can delete everything from Settings at any time.
        </p>
      }
      sections={sections}
    />
  );
}
