/** The browser only talks to Next.js; /api is proxied to FastAPI so cookies stay same-origin. */
// Read at build time: rebuild after changing BACKEND_URL.
const backend = process.env.BACKEND_URL || "http://127.0.0.1:8010";

export default {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  experimental: { proxyTimeout: 600000 },
};
