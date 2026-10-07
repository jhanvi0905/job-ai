import type { Metadata, Viewport } from "next";
import { Albert_Sans, Geist } from "next/font/google";
import "./globals.css";

// Display: Albert Sans, used at weight 400 (hierarchy from size, not boldness).
const display = Albert_Sans({
  subsets: ["latin"],
  variable: "--font-albert",
  display: "swap",
});
// UI and body: Geist.
const body = Geist({
  subsets: ["latin"],
  variable: "--font-geist",
  display: "swap",
});

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#f4f2ee",
};

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: { default: "Fitwise", template: "%s | Fitwise" },
  description:
    "See which jobs actually match your work, and tailor a resume per job description without inventing experience.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`}>
      <body className="min-h-screen bg-canvas text-ink antialiased">{children}</body>
    </html>
  );
}
