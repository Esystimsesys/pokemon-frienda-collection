import raw from "@/data/trainers.json";
import type { Trainer } from "@/types";

/** 公式のだんの順にならんでいる（scripts/parse_trainers.py の出力そのまま） */
export const ALL_TRAINERS = raw as Trainer[];

/** だんごとにまとめたもの。画面はこの単位で見出しを出す */
export const TRAINERS_BY_SET = ALL_TRAINERS.reduce<
  { key: string; label: string; trainers: Trainer[] }[]
>((groups, trainer) => {
  const last = groups[groups.length - 1];
  if (last && last.key === trainer.set) last.trainers.push(trainer);
  else groups.push({ key: trainer.set, label: trainer.setLabel, trainers: [trainer] });
  return groups;
}, []);
