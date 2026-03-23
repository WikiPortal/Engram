import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Engram — Memory Layer",
  description: "Private, self-hosted AI memory",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
