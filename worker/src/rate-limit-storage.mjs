import { consumeRateLimit } from "./rate-limit-core.mjs";

export function initializeRateLimitSql(sql) {
  sql.exec("CREATE TABLE IF NOT EXISTS attempts (at INTEGER NOT NULL)");
  sql.exec("CREATE INDEX IF NOT EXISTS attempts_lookup ON attempts (at)");
}

export function checkAndConsumeSql(sql) {
  const now = Date.now();
  sql.exec("DELETE FROM attempts WHERE at <= ?", now - 24 * 60 * 60 * 1000);
  const rows = sql.exec("SELECT at FROM attempts ORDER BY at").toArray();
  const decision = consumeRateLimit(rows.map((row) => Number(row.at)), now);
  if (decision.allowed) sql.exec("INSERT INTO attempts (at) VALUES (?)", now);
  return decision;
}
