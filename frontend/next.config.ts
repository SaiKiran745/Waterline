import type { NextConfig } from "next";
import { loadEnvConfig } from "@next/env";
import path from "node:path";

// Waterline keeps its shared .env in the repository root. Only NEXT_PUBLIC_ values
// are eligible for client bundling; the sponsor API credentials remain server-only.
loadEnvConfig(path.resolve(process.cwd(), ".."));

const nextConfig: NextConfig = {
  reactStrictMode: true,
  turbopack: {
    root: path.resolve(process.cwd(), ".."),
  },
  outputFileTracingRoot: path.resolve(process.cwd(), ".."),
};

export default nextConfig;
