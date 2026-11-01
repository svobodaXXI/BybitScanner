/**
 * Separate Telegram Terminal ingress. The public Worker is NOT authentication.
 * Its only upstream is the existing protected VPS HTTPS ingress.
 * Never route to :8080, :8081, :8091, or :8765 from the public internet.
 *
 * Deliberately keep upstream redirects manual, preserve host-only __Host-terminal
 * cookies and WebSocket upgrades, and never create a fallback to an unguarded API.
 */
const ORIGIN = "https://83.217.213.181";
const ALLOWED_METHODS = new Set(["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]);
const BLOCKED_PATHS = new Set(["/_auth"]);
const REQUEST_TIMEOUT_MS = 12000;

function permitted(pathname) {
  if (BLOCKED_PATHS.has(pathname)) return false;
  if (pathname.includes("\\") || pathname.includes("\0")) return false;
  // Protected nginx handles auth on every other route; no Worker route
  // bypasses that listener. Keep login/bootstrap and static/WS URLs intact.
  return pathname.startsWith("/");
}

export default {
  async fetch(request) {
    const incoming = new URL(request.url);
    if (incoming.protocol !== "https:") return new Response("HTTPS required", { status: 400 });
    if (!ALLOWED_METHODS.has(request.method) || !permitted(incoming.pathname)) {
      return new Response("Not found", { status: 404 });
    }

    const upstream = new URL(ORIGIN);
    upstream.pathname = incoming.pathname;
    upstream.search = incoming.search;

    const headers = new Headers(request.headers);
    // The Worker is an external public edge, never a source of trusted
    // identity. Do not allow callers to inject origin routing metadata.
    headers.delete("x-forwarded-host");
    headers.delete("x-forwarded-proto");
    headers.delete("x-forwarded-for");
    headers.delete("x-real-ip");
    headers.delete("cf-connecting-ip");
    headers.delete("cf-ray");
    // Nginx and auth-sidecar enforce the actual Telegram cookie/Origin.
    const upstreamRequest = new Request(upstream.toString(), {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
      redirect: "manual",
    });
    const controller = new AbortController();
    // Do not impose an artificial 12s timeout on long-lived WebSocket/SSE.
    const isUpgrade = request.headers.get("upgrade")?.toLowerCase() === "websocket";
    const isStream = request.headers.get("accept")?.includes("text/event-stream");
    const timer = isUpgrade || isStream ? null : setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(upstreamRequest, { redirect: "manual", signal: controller.signal });
      // Do not follow upstream redirects, which could carry session cookies
      // to another origin. Cross-origin redirects must not be exposed.
      const location = response.headers.get("location");
      if (response.status >= 300 && response.status < 400 && location) {
        const destination = new URL(location, upstream);
        if (destination.origin !== upstream.origin) return new Response("Bad upstream redirect", { status: 502 });
        const mapped = new URL(request.url);
        mapped.pathname = destination.pathname;
        mapped.search = destination.search;
        const resultHeaders = new Headers(response.headers);
        resultHeaders.set("location", mapped.toString());
        return new Response(response.body, { status: response.status, headers: resultHeaders });
      }
      // Response preserves Set-Cookie, access control and (for 101) WebSocket.
      return response;
    } catch (_) {
      return new Response("Protected terminal upstream unavailable", { status: 502 });
    } finally {
      if (timer !== null) clearTimeout(timer);
    }
  },
};
