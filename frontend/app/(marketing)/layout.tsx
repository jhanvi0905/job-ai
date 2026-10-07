import type { Metadata } from "next";

const title = "Fitwise: apply to fewer jobs, with a resume that's true";
const description =
  "See honestly which jobs fit you, and tailor your resume for each one using only your own evidence. We never auto-apply and never invent experience.";

export const metadata: Metadata = {
  title: { absolute: title },
  description,
  openGraph: { title, description, type: "website", siteName: "Fitwise" },
  twitter: { card: "summary_large_image", title, description },
  alternates: { canonical: "/" },
};

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-canvas">{children}</div>;
}
