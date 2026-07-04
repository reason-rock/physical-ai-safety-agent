/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // In dev, the FastAPI backend runs on :8000. Proxy /api/* and /sse/*
  // so the browser only talks to :3000.
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/sse/:path*", destination: `${backend}/sse/:path*` },
    ];
  },
};

export default nextConfig;
