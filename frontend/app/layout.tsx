import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Waterline — Interior flood intelligence",
  description: "Waterline takes flood risk inside commercial buildings.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
