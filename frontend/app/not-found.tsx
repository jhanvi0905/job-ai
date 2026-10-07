import type { Metadata } from "next";
import Link from "next/link";
import { LogoMark } from "@/components/marketing/Nav";
import { pillClass, ArrowChip } from "@/components/marketing/shared";

export const metadata: Metadata = { title: "Page not found", robots: { index: false } };

export default function NotFound() {
  return (
    <main className="hero-stripes flex min-h-screen flex-col items-center justify-center px-4 py-16 text-center">
      <Link href="/" className="mb-10 inline-flex items-center gap-2 text-ink">
        <LogoMark /><span className="font-display text-[22px] tracking-[-0.04em]">Fitwise</span>
      </Link>
      <p className="font-display text-[96px] leading-none tracking-[-0.06em] text-faint sm:text-[128px]">404</p>
      <h1 className="mt-4 font-display text-[32px] leading-[1.15] tracking-[-0.05em] text-ink sm:text-[40px]">
        This page isn&apos;t a fit.
      </h1>
      <p className="mt-4 max-w-[440px] text-lg leading-[1.45] text-muted">
        The link may be old, or the page has moved. Nothing is wrong with your account.
      </p>
      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <Link href="/" className={pillClass("black")}>Go to home<ArrowChip /></Link>
        <Link href="/feed" className={pillClass("ghost")}>Open my feed</Link>
      </div>
    </main>
  );
}
