import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { MobileNav } from "@/components/MobileNav";
import "@/lib/i18n";

export const metadata: Metadata = {
  title: "Physical AI Safety Agent",
  description:
    "Safety-first experiment copilot for physical-AI teams. Run control / treatment policy experiments, evaluate, and gate hardware deployment.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <div className="mx-auto flex max-w-[1480px] gap-8 px-4 py-6 md:px-6 md:py-8">
          <Sidebar />
          <main className="min-w-0 flex-1">
            {/* On mobile the sidebar is hidden; show a compact nav instead. */}
            <MobileNav />
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
