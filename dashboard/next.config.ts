import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        // Exclude /api/logs — handled natively by src/app/api/logs/route.ts (SSE streaming)
        source: "/api/:path((?!logs$).*)",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
