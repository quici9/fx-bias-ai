import type { NextConfig } from "next";

// GitHub Pages deploys under a sub-path: https://quici9.github.io/fx-bias-ai/
// In local dev, NEXT_PUBLIC_BASE_PATH is unset (empty string = root).
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  basePath: BASE_PATH,
  assetPrefix: BASE_PATH || undefined,
  images: {
    unoptimized: true, // Required for static export
  },
};

export default nextConfig;
