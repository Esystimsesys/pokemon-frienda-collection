import type { PickGroup } from "@/types";

/** ポケモンのタイプ配色。ゲーム本編の慣例色に合わせている */
export const TYPE_COLORS: Record<string, string> = {
  ノーマル: "#9FA19F",
  ほのお: "#E8720C",
  みず: "#2980EF",
  でんき: "#FAC000",
  くさ: "#3DA224",
  こおり: "#3DCEF3",
  かくとう: "#E12C4F",
  どく: "#8F41CB",
  じめん: "#92501B",
  ひこう: "#82BAEF",
  エスパー: "#EF4179",
  むし: "#91A119",
  いわ: "#AFA981",
  ゴースト: "#704170",
  ドラゴン: "#4F60E2",
  あく: "#4F3F3D",
  はがね: "#60A2B9",
  フェアリー: "#EF71EF",
};

export const TYPE_ORDER = Object.keys(TYPE_COLORS);

export function typeColor(type: string | null | undefined): string {
  return (type && TYPE_COLORS[type]) || "#9FA19F";
}

/** 公式の一覧ページの見出しごとの配色。実物のピックの色味に合わせている */
export const GROUP_STYLES: Record<PickGroup, { color: string; label: string }> = {
  super: { color: "#7B3FBF", label: "★5" },
  treasure: { color: "#C8930B", label: "★4" },
  basic: { color: "#2B6CB0", label: "★2・★3" },
  parallel: { color: "#0F9B8E", label: "パラレル" },
  shiny: { color: "#E0518E", label: "いろちがい" },
  wonder: { color: "#E8720C", label: "ワンダー" },
  special: { color: "#D0342C", label: "スペシャル" },
};

export const GROUP_ORDER = Object.keys(GROUP_STYLES) as PickGroup[];

/**
 * 公式は★2と★3を1つの見出しにまとめているので、
 * バッジには分かっているぶんだけ実際の★数を出す。
 */
export function groupStyle(pick: { group: PickGroup; grade: number | null }) {
  const style = GROUP_STYLES[pick.group];
  if (pick.group === "basic" && pick.grade !== null) {
    return { ...style, label: `★${pick.grade}` };
  }
  return style;
}
