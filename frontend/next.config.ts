import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Ensure Turbopack and output file tracing use the same root directory
  turbopack: {
    root: __dirname,
  },
  outputFileTracingRoot: __dirname,
};

export default nextConfig;
