import raw from "@/data/picks.json";
import type { Pick, SetKey, Stats } from "@/types";

/** 公式の一覧ページに出てくる順のまま並べている */
export const ALL_PICKS = raw as Pick[];

export const PICK_BY_ID = new Map(ALL_PICKS.map((p) => [p.id, p]));

export const PICK_SETS: { key: SetKey; label: string }[] = [
  ...new Map(ALL_PICKS.map((p) => [p.set, { key: p.set, label: p.setLabel }])).values(),
];

export const STAT_FIELDS = [
  { key: "hp", label: "HP" },
  { key: "attack", label: "こうげき" },
  { key: "defense", label: "ぼうぎょ" },
  { key: "spAttack", label: "とくこう" },
  { key: "spDefense", label: "とくぼう" },
] as const satisfies readonly { key: keyof Stats; label: string }[];

const ALL_STATS = ALL_PICKS.map((p) => p.stats).filter((s): s is Stats => s !== null);

/** ポケエネはピックの総合的な強さの指標。図鑑内での相対位置を出すのに使う */
export const MAX_ENERGY = Math.max(
  ...ALL_STATS.map((s) => s.energy).filter((e): e is number => e !== null),
);

export const MAX_STAT = Math.max(...ALL_STATS.flatMap((s) => STAT_FIELDS.map((f) => s[f.key])));
