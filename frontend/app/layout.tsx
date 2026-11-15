import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const display = localFont({ src: "./fonts/big-shoulders-display-latin.woff2", variable: "--font-display", weight: "100 900" });
const body = localFont({ src: "./fonts/hanken-grotesk-latin.woff2", variable: "--font-body", weight: "100 900" });

export const metadata: Metadata = {
  title: "Waterline — Interior flood intelligence",
  description: "Waterline takes flood risk inside commercial buildings.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${display.variable} ${body.variable}`}>{children}</body>
    </html>
  );
}
