/**
 * Dev frontend proxies all /api/* requests to the turing backend so the
 * browser never hits the backend cross-origin (no CORS setup needed).
 * Override the backend location with TURING_API_URL.
 */
const TURING_API_URL = process.env.TURING_API_URL || "http://localhost:8005";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${TURING_API_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
