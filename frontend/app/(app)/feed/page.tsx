import type { Metadata } from "next";
import { Feed } from "@/components/app/Feed";

export const metadata: Metadata = { title: "Feed" };
export default function FeedPage() {
  return <Feed />;
}
