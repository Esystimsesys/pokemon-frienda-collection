import { useWindowDimensions } from "react-native";

/**
 * よこはばが せまい（スマートフォンぐらいの）画面かどうかの さかいめ。
 *
 * もともと iPad で見る前提で作ってあり、ボタンを1列に並べたり、カード1枚に
 * 210px 使ったりしている。スマートフォンのたて（320〜430px）ではそれが入りきらないので、
 * この目安をこえるかどうかで並べ方を変える。
 *
 * 600 は iPad のたて（768）より下なので、iPad は今までどおり。
 * スマートフォンをよこ向きにすると 600 をこえるが、そのときは実際にはばが足りているので
 * 今までどおりの並べ方でよい（せまいのは たて で、そちらは上のバーが
 * スクロールで逃げることで足りている）。
 */
export const NARROW_WIDTH = 600;

export function useNarrow(): boolean {
  const { width } = useWindowDimensions();
  return width < NARROW_WIDTH;
}

/**
 * これより細いカードは「小さいカード」として、字を詰めて ＋ を出さない。
 * せまい画面で「ちいさい」「ふつう」を選ぶとここに入る。
 * ずかん一覧（app/index.tsx）と カード（src/components/PickCard.tsx）の両方で使う。
 */
export const TIGHT_CARD_WIDTH = 130;
