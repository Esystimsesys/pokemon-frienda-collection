export type Move = {
  name: string;
  type: string | null;
};

export type Stats = {
  /**
   * ポケエネ。裏面には印字がなく、表面にしか出ていないので読み取れていないピックがある。
   * 旧データから引けたものだけ数値が入る。
   */
  energy: number | null;
  hp: number;
  attack: number;
  defense: number;
  spAttack: number;
  spDefense: number;
  /**
   * すばやさ。裏面に矢印アイコンが何個埋まっているかで示される1〜5の段階値
   * （★のグレードと同じ仕組み）で、具体的な数値の印字は無い。
   * ファンサイト（ポケエネ/HP等と全件突き合わせて検証ずみ）から取り込んだもので、
   * 向こうにピックが無い分は null のまま。
   */
  speed: number | null;
};

/**
 * 公式サイトのページ単位（"1" や "bt5" や "wonder"）。
 * 新しいだんが出たときにここを直さなくていいよう、あえて値を並べていない。
 * 実際にどのだんがあるかは picks.json から作る PICK_SETS を見ること。
 */
export type SetKey = string;

/** 公式の一覧ページで束ねられている見出し */
export type PickGroup =
  | "super"
  | "treasure"
  | "basic"
  | "parallel"
  | "shiny"
  | "wonder"
  | "special";

export type Pick = {
  /** 全だんを通して一意。公式の画像ファイル名と一致する */
  id: string;
  /** ピック券面の番号表記。ワンダー／スペシャルは W / P だけ */
  no: string;
  set: SetKey;
  setLabel: string;
  setOrder: number;
  name: string;
  group: PickGroup;
  /** ★の数。公式が★2と★3をまとめて載せている分は null */
  grade: number | null;
  /** 公式画像。上半分が表面、下半分が裏面 */
  image: string;
  /** 表面だけの小さい画像 */
  thumb: string;
  types: string[];
  moves: Move[];
  /** 公式にステータス掲載がないピックは null */
  stats: Stats | null;
  /** とくべつな仕組み。普通のピックは null */
  mechanic: Mechanic | null;
  /** 仕組みで使う2つめのわざ。テラバースト、キョダイゴクエン など */
  specialMove: string | null;
  /** タッグわざの相手ポケモン。タッグわざ以外は null */
  tagPartner: string | null;
  /** でんせつ／まぼろしのアイコン。読み取れていないものは null */
  legend: Legend | null;
};

/**
 * 券面についているとくべつな仕組みのマーク。
 * 公式の「アイコン・マークについて」で定義されているもの。
 * 裏面の2つめのわざの行から読み取っている（メガシンカだけは1行目）。
 */
export type Mechanic = "テラスタル" | "Zワザ" | "メガシンカ" | "タッグわざ" | "ダイマックス";

/** でんせつ／まぼろしのポケモンに付くアイコン。読み取れなかったものは null */
export type Legend = "でんせつ" | "まぼろし";

/** ピックID -> 所持枚数。0枚のものはキーごと持たない */
export type Collection = Record<string, number>;

/** だんごとに出てくる、たたかう相手のトレーナー。1〜3だんとワンダー／スペシャルには居ない */
export type Trainer = {
  /** だん + 出てくる順。例: bt5-2 */
  id: string;
  set: SetKey;
  setLabel: string;
  setOrder: number;
  /** そのだんの中で何人目か */
  order: number;
  name: string;
  image: string;
  /** 勝つともらえるきせかえアイテムの名前 */
  reward: string;
  /** きせかえアイテムの見本の画像 */
  rewardImages: string[];
};
