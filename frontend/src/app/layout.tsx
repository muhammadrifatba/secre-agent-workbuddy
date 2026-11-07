import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "SEKRE v3 Governance Console",
  description: "Approval, Limits, Permissions, Record",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="id">
      <body>{children}</body>
    </html>
  );
}

