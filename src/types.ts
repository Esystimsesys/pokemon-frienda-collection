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

/**
 * トレーナーピックのQRから読みとった、フレンダサークルとの つながり。
 * token は QR の `s=` パラメータそのもの（フレンダサークル側の本人確認キー）。
 */
export type CircleConnection = {
  token: string;
  trainerName: string;
  trainerPickId: string;
  avatarType: number;
  connectedAt: number;
  lastSyncedAt: number | null;
};

/** 同期のたびに フレンダサークルから取ってくる、トレーナーの現在のようす */
export type CircleSummary = {
  trainerName: string;
  avatarType: number;
  partner: {
    name: string;
    progress: number;
  } | null;
  currentSeason: {
    seasonName: string;
    currentCount: number;
    maxCount: number;
  } | null;
  /** トレーニング中のポケモン。複数いる（ホームには「いま育てている1体」しか入っていない） */
  training: {
    name: string;
    /** 券面の番号。ローカル図鑑にあれば Pick.id と一致する */
    pickId: string;
    exPower: number;
    exPowerThreshold: number;
    /** いま重点的に育てている1体かどうか */
    isCurrentTarget: boolean;
    /** ローカル図鑑に無いピック用に、サークルから持ち帰った画像（data URI） */
    image: string | null;
  }[];
  trainerBattle: {
    highScore: number;
    clearedCount: number;
    totalCount: number;
  } | null;
  medalCount: number;
  charmCount: number;
  /** ピック図鑑に反映できた（ローカルの Pick.id と一致した）所持ピックのID一覧 */
  ownedPickIds: string[];
  /**
   * トレーナー・パートナー・トレーニング中ピック・メダルの画像（data URI）。
   * サークル側がホットリンクを拒否するため、Worker が本物のブラウザで
   * 実際に受けとった画像をそのまま持ち帰ったもの。無ければ null
   */
  images: {
    trainerAvatar: string | null;
    partner: string | null;
    medalIcon: string | null;
  };
  /** チャームの画像（data URI）の一覧 */
  charmImages: string[];
  syncedAt: number;
};
