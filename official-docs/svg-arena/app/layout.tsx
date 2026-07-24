import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "SVG Arena",
  description:
    "Blind, head-to-head comparison of AI-generated SVG illustrations. Vote on which is better and help build an open preference dataset.",
};

import Link from "next/link";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-neutral-50 text-neutral-900">
        <header className="border-b border-neutral-200 bg-white">
          <nav className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
            <Link href="/" className="font-semibold tracking-tight">
              🎨 SVG Arena
            </Link>
            <div className="flex gap-5 text-sm text-neutral-600">
              <Link href="/" className="hover:text-neutral-900">
                Arena
              </Link>
              <Link href="/leaderboard" className="hover:text-neutral-900">
                Leaderboard
              </Link>
              <Link href="/about" className="hover:text-neutral-900">
                About
              </Link>
            </div>
          </nav>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
