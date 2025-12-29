import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Ensure Turbopack resolves modules from the frontend workspace (not the repo root)
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
