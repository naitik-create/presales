import type { Metadata } from "next";
import { ReactNode } from "react";
import { SessionProvider } from "@/lib/session";
import "./globals.css";

export const metadata: Metadata = {
  title: "Presales Intelligence",
  description: "Motadata Presales Intelligence Platform",
  icons: { icon: "/api/branding/logomark" },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  );
}
