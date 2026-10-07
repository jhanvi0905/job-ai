import type { Metadata } from "next";
import { Tracker } from "@/components/app/Tracker";

export const metadata: Metadata = { title: "Tracker" };
export default function TrackerPage() {
  return <Tracker />;
}
