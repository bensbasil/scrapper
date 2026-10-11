import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // All /api/* traffic is securely handled by src/app/api/[[...path]]/route.ts,
  // which dynamically routes to API_INTERNAL_URL and injects API_AUTH_TOKEN server-side.
};

export default nextConfig;
