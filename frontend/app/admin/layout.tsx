import type { Metadata } from "next";
import { AdminNav } from "@/components/AdminNav";

export const metadata: Metadata = {
  title: "Job Agent Control Panel",
  robots: { index: false, follow: false },
};

// Ops dashboard. Intentionally unlinked from the customer app.
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <AdminNav />
      <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
    </div>
  );
}
