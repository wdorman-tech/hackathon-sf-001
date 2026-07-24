import crypto from "crypto";

const SECRET =
  process.env.SESSION_SECRET ?? "dev-insecure-secret-change-in-production";

/**
 * Sign a JSON payload into a tamper-proof token (base64url(payload).base64url(hmac)).
 * Used to bind a served pair to the vote that comes back — so a client can't
 * forge arbitrary (promptId, genA, genB) combinations or flip which side of an
 * attention check was correct.
 */
export function sign<T>(payload: T): string {
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const sig = crypto
    .createHmac("sha256", SECRET)
    .update(body)
    .digest("base64url");
  return `${body}.${sig}`;
}

export function verify<T>(token: string): T | null {
  const [body, sig] = token.split(".");
  if (!body || !sig) return null;
  const expected = crypto
    .createHmac("sha256", SECRET)
    .update(body)
    .digest("base64url");
  // Constant-time compare.
  if (
    sig.length !== expected.length ||
    !crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected))
  ) {
    return null;
  }
  try {
    return JSON.parse(Buffer.from(body, "base64url").toString()) as T;
  } catch {
    return null;
  }
}
