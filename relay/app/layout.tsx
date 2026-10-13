import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Codaki Mini Codex 0.2.4 — phone & PC",
  description: "A personal agent for phone control and compressed task memory.",
  other: {
    "codex-preview": "development",
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
