import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import vm from "node:vm";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const picks = JSON.parse(readFileSync(new URL("../src/data/picks.json", import.meta.url)));
const pickModule = {
  PICK_BY_ID: new Map(picks.map((p) => [p.id, p])),
  PICK_SETS: [...new Set(picks.map((p) => p.set))].map((key) => ({ key })),
};

function load(file, storage = {}, extra = {}) {
  const exports = {};
  const source = readFileSync(new URL(`../src/lib/${file}.ts`, import.meta.url), "utf8");
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, {
    exports, URL, Date, ...extra,
    require(name) {
      if (name === "@react-native-async-storage/async-storage") return { default: storage };
      if (name === "@/lib/picks") return pickModule;
      throw new Error(`Unexpected import: ${name}`);
    },
  });
  return exports;
}

const circle = load("circle");
const dex = (entries) => JSON.stringify({ params: { seasonDexStateList: [
  { gradeDexStateList: [{ pPickDexStateList: entries }] },
] } });

test("invalid or incomplete sync payloads stop before an empty collection can be applied", () => {
  const invalid = ["not-json", "{}", "null", '{"params":{"error":"expired"}}',
    JSON.stringify({ params: { seasonDexStateList: {} } }),
    JSON.stringify({ params: { seasonDexStateList: [null] } }),
    JSON.stringify({ params: { seasonDexStateList: [{ gradeDexStateList: [{}] }] } }),
    dex([{ getState: "2", img: [picks[0].id] }]),
    dex([{ getState: 2 }]),
    dex([{ getState: 2, img: [picks[0].id] }, null]),
  ];
  for (const body of invalid) assert.throws(() => circle.parsePickDexResponse(body), /きろくは かえずに/);
});

test("valid empty dex and owned/unowned/unknown picks retain their semantics", () => {
  assert.equal(circle.parsePickDexResponse(dex([])).length, 0);
  assert.equal(circle.parsePickDexResponse('{"params":{"seasonDexStateList":[]}}').length, 0);
  const ids = circle.parsePickDexResponse(dex([
    { getState: 1, img: [picks[1].id] },
    { getState: 2, img: [picks[0].id] },
    { getState: 3, img: [picks[0].id] },
    { getState: 2, img: ["digital-only"] },
  ]));
  assert.deepEqual([...ids], [picks[0].id]);
});

test("server rate limit produces a readable message", async () => {
  const api = load("circle", { getItem: async () => null, setItem: async () => {} }, {
    fetch: async () => ({ status: 429 }),
  });
  await assert.rejects(api.fetchCircleSync("test"), /どうきかいすうが いっぱい/);
});

test("clearing a migrated set filter survives reload and later selections", async () => {
  const values = new Map([["frienda.filter.set.v1", picks[0].set]]);
  const storage = {
    getItem: async (key) => values.get(key) ?? null,
    setItem: async (key, value) => { values.set(key, value); },
  };
  let prefs = load("filterPrefs", storage);
  assert.deepEqual([...await prefs.loadSetFilter()], [picks[0].set]);
  prefs.saveSetFilter([]);
  prefs = load("filterPrefs", storage);
  assert.deepEqual([...await prefs.loadSetFilter()], []);
  prefs.saveSetFilter([picks[0].set]);
  assert.deepEqual([...await load("filterPrefs", storage).loadSetFilter()], [picks[0].set]);
});
