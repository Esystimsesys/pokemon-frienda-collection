import test from "node:test";
import assert from "node:assert/strict";
import { consumeRateLimit, consumeTokenAndIp, RATE_WINDOW_MS } from "../src/rate-limit-core.mjs";
import { DatabaseSync } from "node:sqlite";
import { checkAndConsumeSql, initializeRateLimitSql } from "../src/rate-limit-storage.mjs";

test("allows ten attempts and denies the eleventh", () => {
  const now = 1_000_000;
  let attempts = [];
  for (let i = 0; i < 10; i += 1) {
    const result = consumeRateLimit(attempts, now + i);
    assert.equal(result.allowed, true);
    attempts = result.attempts;
  }
  assert.equal(consumeRateLimit(attempts, now + 10).allowed, false);
});

test("uses the persistent SQLite table and does not write after denial", () => {
  const db = new DatabaseSync(":memory:");
  const sql = {
    exec(query, ...args) {
      const statement = db.prepare(query);
      if (/^SELECT /i.test(query.trim())) {
        return { toArray: () => statement.all(...args) };
      }
      statement.run(...args);
      return { toArray: () => [] };
    },
  };
  initializeRateLimitSql(sql);
  const originalNow = Date.now;
  Date.now = () => 1_000_000;
  try {
    for (let i = 0; i < 10; i += 1) assert.equal(checkAndConsumeSql(sql).allowed, true);
    assert.equal(checkAndConsumeSql(sql).allowed, false);
    assert.equal(db.prepare("SELECT COUNT(*) AS n FROM attempts").get().n, 10);
  } finally {
    Date.now = originalNow;
    db.close();
  }
});

test("expires attempts after 24 hours and reports retry-after", () => {
  const now = 5_000_000;
  const result = consumeRateLimit([now - RATE_WINDOW_MS, now - 10], now);
  assert.equal(result.allowed, true);
  const denied = consumeRateLimit(Array(10).fill(now - 1), now);
  assert.equal(denied.allowed, false);
  assert.equal(denied.retryAfter, Math.ceil((RATE_WINDOW_MS - 1) / 1000));
});

test("token and IP limits are independent under concurrent requests", async () => {
  const token = { attempts: [] };
  const ipA = { attempts: [] };
  const ipB = { attempts: [] };
  const now = 8_000_000;
  const consume = async (tokenState, ipState) => {
    const result = await consumeTokenAndIp(
      { checkAndConsume: async () => {
        const next = consumeRateLimit(tokenState.attempts, now);
        tokenState.attempts = next.attempts;
        return next;
      } },
      { checkAndConsume: async () => {
        const next = consumeRateLimit(ipState.attempts, now);
        ipState.attempts = next.attempts;
        return next;
      } },
    );
    return result;
  };
  const results = await Promise.all(
    Array.from({ length: 20 }, (_, i) => consume(token, i % 2 ? ipA : ipB)),
  );
  assert.equal(results.filter((result) => result.allowed).length, 10);
  assert.equal(results.filter((result) => !result.allowed).length, 10);
  assert.equal(ipA.attempts.length + ipB.attempts.length, 10);
});

test("limiter failure fails closed", async () => {
  let launches = 0;
  const result = await consumeTokenAndIp(
    { checkAndConsume: async () => { throw new Error("DO unavailable"); } },
    { checkAndConsume: async () => { launches += 1; return { allowed: true }; } },
  );
  assert.equal(result.unavailable, true);
  assert.equal(launches, 0);
});
