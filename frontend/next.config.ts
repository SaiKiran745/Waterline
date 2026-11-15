import type { NextConfig } from "next";
import { loadEnvConfig } from "@next/env";
import path from "node:path";

// Waterline keeps its shared .env in the repository root. Only NEXT_PUBLIC_ values
// are eligible for client bundling; the sponsor API credentials remain server-only.
loadEnvConfig(
  path.resolve(process.cwd(), ".."),
  process.env.NODE_ENV !== "production",
  console,
  true,
);

const nextConfig: NextConfig = {
  // NEXT_DIST_DIR lets a check build run without replacing the .next/ that a running `next start` serves.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  reactStrictMode: true,
  devIndicators: false,
  turbopack: {
    root: path.resolve(process.cwd(), ".."),
  },
  outputFileTracingRoot: path.resolve(process.cwd(), ".."),
};

export default nextConfig;
