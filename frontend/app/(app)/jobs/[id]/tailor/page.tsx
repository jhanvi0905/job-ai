import type { Metadata } from "next";
import { TailorView } from "@/components/app/Tailor";

export const metadata: Metadata = { title: "Tailor resume" };
export default function TailorPage() {
  return <TailorView />;
}
