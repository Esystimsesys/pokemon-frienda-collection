import { ALL_PICKS } from "@/lib/picks";
import type { Pick } from "@/types";

/**
 * もっているピックから、つよい順の並びと おすすめの組み合わせ を作る。
 *
 * 強さの目安はポケエネ（券面に出ている総合的な強さ）。
 * ポケエネがわかっていないピックは、HP〜とくぼうの合計から目安を出す。
 * ポケエネがわかっている927件で実測したところ、合計に対する比は
 * 中央値0.465（5%点0.430／95%点0.511）と安定していたので、この係数を使う。
 */
const ENERGY_FROM_TOTAL = 0.465;

export type Ranked = {
  pick: Pick;
  count: number;
  power: number;
  /** ポケエネそのものではなく、合計から出した目安かどうか */
  estimated: boolean;
};

function powerOf(pick: Pick): { power: number; estimated: boolean } | null {
  const s = pick.stats;
  if (!s) return null;
  if (s.energy !== null) return { power: s.energy, estimated: false };
  const total = s.hp + s.attack + s.defense + s.spAttack + s.spDefense;
  return { power: Math.round(total * ENERGY_FROM_TOTAL), estimated: true };
}

/** もっているピックを つよい順 に並べる */
export function rankOwned(countOf: (id: string) => number): Ranked[] {
  const out: Ranked[] = [];
  for (const pick of ALL_PICKS) {
    const count = countOf(pick.id);
    if (count === 0) continue;
    const p = powerOf(pick);
    if (!p) continue;
    out.push({ pick, count, power: p.power, estimated: p.estimated });
  }
  return out.sort((a, b) => b.power - a.power);
}

/**
 * つよい順から、タイプがかぶらないように上から取っていく。
 * かぶらないものが無くなったら、残りはつよい順のまま足す。
 */
export function pickParty(ranked: Ranked[], size: number): Ranked[] {
  const party: Ranked[] = [];
  const used = new Set<string>();

  for (const r of ranked) {
    if (party.length >= size) break;
    if (r.pick.types.some((t) => used.has(t))) continue;
    party.push(r);
    r.pick.types.forEach((t) => used.add(t));
  }

  for (const r of ranked) {
    if (party.length >= size) break;
    if (!party.includes(r)) party.push(r);
  }

  return party;
}
