import type { Metadata } from "next";
import { JobDetailView } from "@/components/app/JobDetail";

export const metadata: Metadata = { title: "Job" };
export default function JobPage() {
  return <JobDetailView />;
}
