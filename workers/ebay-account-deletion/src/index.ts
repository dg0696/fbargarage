/**
 * eBay Marketplace Account Deletion / Closure endpoint.
 * Required to unlock a Production keyset.
 *
 * GET  ?challenge_code=…  → { challengeResponse: sha256(code + token + endpoint) }
 * POST                    → 200 ack (this app does not store other users' PII)
 */

const MAX_BODY_BYTES = 64 * 1024;

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== "/ebay/account-deletion") {
      return json({ ok: false, error: "not_found" }, 404);
    }

    if (request.method === "GET") {
      return handleChallenge(url, env);
    }
    if (request.method === "POST") {
      return handleNotification(request, ctx);
    }
    return json({ ok: false, error: "method_not_allowed" }, 405);
  },
};

async function handleChallenge(url: URL, env: Env): Promise<Response> {
  const challengeCode = url.searchParams.get("challenge_code") || "";
  const token = env.EBAY_VERIFICATION_TOKEN || "";
  if (!challengeCode || !token) {
    return json({ ok: false, error: "missing_challenge_or_token" }, 400);
  }

  const endpoint = env.EBAY_ENDPOINT_URL || `${url.origin}${url.pathname}`;
  const challengeResponse = await sha256Hex(challengeCode + token + endpoint);
  return json({ challengeResponse }, 200);
}

async function handleNotification(request: Request, ctx: ExecutionContext): Promise<Response> {
  const length = Number(request.headers.get("content-length") || "0");
  if (length > MAX_BODY_BYTES) {
    return json({ ok: false, error: "payload_too_large" }, 413);
  }
  ctx.waitUntil(logNotification(request));
  return new Response(null, { status: 204 });
}

async function logNotification(request: Request): Promise<void> {
  const raw = await request.text();
  if (raw.length > MAX_BODY_BYTES) {
    console.log(JSON.stringify({ event: "ebay_account_deletion", skipped: "too_large" }));
    return;
  }
  console.log(
    JSON.stringify({
      event: "ebay_account_deletion",
      received_at: new Date().toISOString(),
      bytes: raw.length,
    }),
  );
}

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
