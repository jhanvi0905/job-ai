import { Nav } from "@/components/marketing/Nav";
import { Hero } from "@/components/marketing/Hero";
import { ProductBand } from "@/components/marketing/ProductBand";
import { PainScroll } from "@/components/marketing/PainScroll";
import { Steps } from "@/components/marketing/Steps";
import { FeatureTabs } from "@/components/marketing/FeatureTabs";
import { Different } from "@/components/marketing/Different";
import { Pricing } from "@/components/marketing/Pricing";
import { WhoFor } from "@/components/marketing/WhoFor";
import { FitwisePromise } from "@/components/marketing/FitwisePromise";
import { Faq } from "@/components/marketing/Faq";
import { FAQS } from "@/components/marketing/faqs";
import { FinalCta } from "@/components/marketing/FinalCta";
import { Footer } from "@/components/marketing/Footer";

const faqLd = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: FAQS.map((f) => ({
    "@type": "Question",
    name: f.q,
    acceptedAnswer: { "@type": "Answer", text: f.a },
  })),
};

// Section order follows docs/design/GROVIA_SPEC.md §2 (2.1 → 2.13).
export default function LandingPage() {
  return (
    <>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-full focus:bg-on-dark focus:px-3 focus:py-2">Skip to content</a>
      <Nav />
      <main id="main">
        <Hero />
        <ProductBand />
        <PainScroll />
        <Steps />
        <FeatureTabs />
        <Different />
        <Pricing />
        <WhoFor />
        <FitwisePromise />
        <Faq />
        <FinalCta />
      </main>
      <Footer />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqLd).replace(/</g, "\\u003c") }} />
    </>
  );
}
