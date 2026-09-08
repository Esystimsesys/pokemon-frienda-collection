import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";
import vm from "node:vm";
import * as core from "../src/rate-limit-core.mjs";

const require = createRequire(import.meta.url);
const ts = require("../../node_modules/typescript");
const source = ts.transpileModule(readFileSync(new URL("../src/index.js", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const storageSource = ts.transpileModule(readFileSync(new URL("../src/rate-limit-storage.mjs", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  fileName: "rate-limit-storage.js",
}).outputText;

// Run the actual handler and Durable Object against SQLite, replacing only the
// platform bindings. No browser is launched and no external service is called.
function fixture(t) {
  let now = 1_000_000_000;
  let launches = 0;
  const exports = {};
  const storageExports = {};
  const Clock = class extends Date { static now() { return now; } };
  vm.runInNewContext(storageSource, {
    exports: storageExports, Date: Clock,
    require: () => core,
  });
  class DurableObject {
    constructor(ctx, env) { this.ctx = ctx; this.env = env; }
  }
  vm.runInNewContext(source, {
    exports, URL, Response, TextEncoder, Uint8Array, crypto: webcrypto,
    Date: Clock,
    require(name) {
      if (name === "cloudflare:workers") return { DurableObject };
      if (name === "./rate-limit-core.mjs") return core;
      if (name === "./rate-limit-storage.mjs") return storageExports;
      if (name === "@cloudflare/puppeteer") return { default: { launch: async () => {
        launches += 1;
        throw new Error("test: browser deliberately not started");
      } } };
      throw new Error(`Unexpected import ${name}`);
    },
  });
  const databases = new Map();
  let objects = new Map();
  const namespace = {
    getByName(name) {
      if (!objects.has(name)) {
        let db = databases.get(name);
        if (!db) { db = new DatabaseSync(":memory:"); databases.set(name, db); }
        const ctx = {
          blockConcurrencyWhile: (fn) => fn(),
          storage: {
            sql: { exec(sql, ...args) {
              const statement = db.prepare(sql);
              if (/^SELECT/i.test(sql.trim())) return { toArray: () => statement.all(...args) };
              statement.run(...args);
              return { toArray: () => [] };
            } },
            transactionSync(fn) {
              db.exec("BEGIN");
              try { const result = fn(); db.exec("COMMIT"); return result; }
              catch (error) { db.exec("ROLLBACK"); throw error; }
            },
          },
        };
        objects.set(name, new exports.RateLimit(ctx, {}));
      }
      return objects.get(name);
    },
  };
  t.after(() => { for (const db of databases.values()) db.close(); });
  return {
    namespace,
    advance: (ms) => { now += ms; },
    restart: () => { objects = new Map(); },
    get launches() { return launches; },
    request(token = "test-token", ip = "192.0.2.1", env = { RATE_LIMIT: namespace }) {
      return exports.default.fetch(new Request(`https://worker.example/?token=${token}`, {
        headers: { Origin: "https://esystimsesys.github.io", ...(ip ? { "CF-Connecting-IP": ip } : {}) },
      }), env);
    },
  };
}

test("actual handler admits only ten concurrent attempts and does not launch on 429", async (t) => {
  const f = fixture(t);
  const results = await Promise.all(Array.from({ length: 20 }, () => f.request()));
  assert.equal(f.launches, 10);
  assert.equal(results.filter((r) => r.status === 429).length, 10);
  const denied = results.find((r) => r.status === 429);
  assert.equal(denied.headers.get("Retry-After"), "86400");
  assert.equal(denied.headers.get("Cache-Control"), "no-store");
});

test("persisted limits survive object recreation and release slots after 24 hours", async (t) => {
  const f = fixture(t);
  await f.request();
  f.advance(1000);
  for (let i = 0; i < 9; i++) await f.request();
  f.restart();
  assert.equal((await f.request()).status, 429);
  f.advance(core.RATE_WINDOW_MS - 1000);
  assert.equal((await f.request()).status, 502); // Admitted; test browser throws.
  assert.equal((await f.request()).status, 429);
  assert.equal(f.launches, 11);
});

test("changing IP cannot bypass a token limit", async (t) => {
  const f = fixture(t);
  for (let i = 0; i < 10; i++) await f.request();
  assert.equal((await f.request("test-token", "192.0.2.2")).status, 429);
  assert.equal(f.launches, 10);
});

test("changing tokens cannot bypass a shared IP limit", async (t) => {
  const f = fixture(t);
  for (let i = 0; i < 10; i++) await f.request(`token-${i}`);
  assert.equal((await f.request("new-token")).status, 429);
  assert.equal(f.launches, 10);
});

test("missing IP and unavailable limiter fail closed with no browser launch", async (t) => {
  const f = fixture(t);
  assert.equal((await f.request("test-token", "")).status, 400);
  for (const namespace of [
    { getByName() { throw new Error("binding unavailable"); } },
    { getByName() { return { checkAndConsume: async () => { throw new Error("storage unavailable"); } }; } },
  ]) {
    const response = await f.request("test-token", "192.0.2.1", { RATE_LIMIT: namespace });
    assert.equal(response.status, 503);
    assert.equal(response.headers.get("Access-Control-Allow-Origin"), "https://esystimsesys.github.io");
    assert.equal((await response.json()).error, "rate_limit_unavailable");
  }
  assert.equal(f.launches, 0);
});
