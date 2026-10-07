// DRAFT — review with a lawyer before launch. Plain-language terms; governing law and
// the legal entity name are placeholders until incorporation details are final.
import type { Metadata } from "next";
import Link from "next/link";
import { LegalEmail, LegalList, LegalPage, type LegalSection } from "@/components/marketing/LegalPage";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: "The rules for using Fitwise, in plain language.",
  alternates: { canonical: "/terms" },
};

const UPDATED = "October 7, 2026";

const sections: LegalSection[] = [
  {
    id: "agreement",
    title: "Agreeing to these terms",
    body: (
      <p>
        By creating an account or using Fitwise you agree to these terms and to our{" "}
        <Link href="/privacy" className="font-medium underline underline-offset-4">Privacy Policy</Link>. If you don&apos;t agree,
        please don&apos;t use the service. You need to be at least 16 to use Fitwise.
      </p>
    ),
  },
  {
    id: "service",
    title: "What Fitwise does, and doesn't do",
    body: (
      <>
        <p>
          Fitwise finds job postings, checks how your experience covers each one, and suggests resume changes based only on
          achievements you&apos;ve reviewed. It&apos;s a decision aid.
        </p>
        <LegalList items={[
          <><strong>No auto-apply.</strong> Fitwise never applies to jobs, contacts employers, or sends your resume anywhere. You decide where to apply and you apply yourself.</>,
          <><strong>No guarantees.</strong> Fit results are an informed estimate, not a promise of an interview or offer. Employers make their own decisions.</>,
          <><strong>Postings belong to employers.</strong> We show public job postings as we find them. They may be out of date or inaccurate; always check the employer&apos;s site.</>,
          <><strong>Coverage is limited.</strong> Matching works across 12 common professional role families and is strongest where job requirements are concrete.</>,
        ]} />
      </>
    ),
  },
  {
    id: "you",
    title: "Your responsibilities",
    body: (
      <LegalList items={[
        "Give accurate information about yourself, and only upload a resume that's yours.",
        "Review every suggestion before you use it. You're responsible for what you send to employers, so only use bullets you can stand behind in an interview.",
        "Keep your sign-in details secure and tell us if you think your account has been misused.",
        "Don't misuse the service: no scraping, reverse engineering, overloading the API, getting around plan limits, or using Fitwise to break the law or anyone's rights.",
      ]} />
    ),
  },
  {
    id: "content",
    title: "Your content",
    body: (
      <p>
        You own your resume, your achievements and everything you write in Fitwise. You give us permission to store and
        process it only to run the service for you, including sending it to the providers listed in our Privacy Policy.
        That permission ends when you delete the content or your account. We don&apos;t sell it and don&apos;t use it to train our own models.
      </p>
    ),
  },
  {
    id: "ai",
    title: "AI-generated suggestions",
    body: (
      <p>
        Suggestions are produced by a language model working from your own evidence. They can still be wrong, awkward, or
        miss context. Anything without supporting evidence is dropped, but you should read each line before accepting it.
      </p>
    ),
  },
  {
    id: "plans",
    title: "Plans, limits and changes",
    body: (
      <>
        <p>
          The free plan has daily limits on screening, analysis and tailoring, which may change as we learn what&apos;s fair and
          sustainable. Paid plans aren&apos;t on sale yet; when they are, their price and terms will be shown before you pay, and
          nothing on your free plan changes unless you choose to upgrade.
        </p>
        <p>We may add, change or remove features. If a change materially reduces what you get, we&apos;ll tell you in advance.</p>
      </>
    ),
  },
  {
    id: "ending",
    title: "Ending your account",
    body: (
      <p>
        You can stop using Fitwise and delete your account at any time from{" "}
        <Link href="/settings" className="font-medium underline underline-offset-4">Settings</Link>; this erases your data as described
        in our Privacy Policy. We may suspend or close accounts that break these terms or put the service or other users at risk,
        and we&apos;ll tell you why unless the law or safety prevents it.
      </p>
    ),
  },
  {
    id: "liability",
    title: "Disclaimers and liability",
    body: (
      <>
        <p>
          Fitwise is provided &ldquo;as is&rdquo;. To the extent the law allows, we don&apos;t promise it will be uninterrupted or
          error-free, and we aren&apos;t liable for indirect losses such as lost job opportunities, or for decisions made by employers.
        </p>
        <p>Nothing in these terms limits rights you have under consumer protection laws that can&apos;t be waived.</p>
      </>
    ),
  },
  {
    id: "law",
    title: "Governing law",
    body: <p>These terms are governed by the laws of the province of Ontario and the federal laws of Canada that apply there (to be confirmed).</p>,
  },
  {
    id: "contact",
    title: "Changes and contact",
    body: (
      <p>
        If we change these terms in a way that matters, we&apos;ll email you before the change takes effect. Continuing to use
        Fitwise after that means you accept the new terms. Questions: <LegalEmail />.
      </p>
    ),
  },
];

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms of Service"
      updated={UPDATED}
      intro={
        <p>
          Fitwise helps you find jobs worth applying to and tailor your resume with your own evidence. These terms explain what
          you can expect from us and what we expect from you. We&apos;ve kept them short and plain.
        </p>
      }
      sections={sections}
    />
  );
}
