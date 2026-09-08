export const RATE_LIMIT = 10;
export const RATE_WINDOW_MS = 24 * 60 * 60 * 1000;

export function consumeRateLimit(attempts, now) {
  const active = attempts.filter((at) => at > now - RATE_WINDOW_MS);
  if (active.length >= RATE_LIMIT) {
    return {
      allowed: false,
      retryAfter: Math.max(1, Math.ceil((Math.min(...active) + RATE_WINDOW_MS - now) / 1000)),
      attempts: active,
    };
  }
  return { allowed: true, retryAfter: null, attempts: [...active, now] };
}

export async function consumeTokenAndIp(tokenLimiter, ipLimiter) {
  try {
    const token = await tokenLimiter.checkAndConsume();
    if (!token.allowed) return token;
    return await ipLimiter.checkAndConsume();
  } catch {
    return { allowed: false, unavailable: true, retryAfter: null };
  }
}
