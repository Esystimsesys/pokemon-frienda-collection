import { Image } from "expo-image";
import { memo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { PickImage } from "@/components/PickImage";
import { TypeIcons } from "@/components/TypeIcon";
import { TIGHT_CARD_WIDTH } from "@/lib/responsive";
import { groupStyle } from "@/theme/pokemonTypes";
import type { Pick } from "@/types";

type Props = {
  pick: Pick;
  count: number;
  width: number;
  onPress: (id: string) => void;
  /** 登録モードのときだけ渡す。カードの下に ＋ と − を出す */
  onAdjust?: (id: string, delta: number) => void;
  /** フレンダサークルの同期で「持っている」と確認できたピックか */
  circleConfirmed?: boolean;
};

function PickCardBase({ pick, count, width, onPress, onAdjust, circleConfirmed }: Props) {
  const owned = count > 0;
  const grade = groupStyle(pick);
  /**
   * せまい画面で「ちいさい」「ふつう」を選ぶと、カードがここまで細くなる。
   * そのままの字の大きさだと「アローラサンドパン」のような長い名前が
   * ほとんど読めないので、小さいカードのときだけ字を詰める。
   */
  const tight = width < TIGHT_CARD_WIDTH;
  // ごくまれに公式にサムネイルが無いピックがある（p053-ayNdxXS8）。
  // そのときは大きい画像の表面を切り出して出す。
  const [thumbFailed, setThumbFailed] = useState(false);

  return (
    <View
      style={[
        styles.card,
        { width, borderColor: owned ? grade.color : "#D6DEE8" },
        owned && styles.cardOwned,
      ]}
    >
      {/* ＋ − ボタンは Pressable の入れ子を避けるため、こちらの外に置いている */}
      <Pressable
        onPress={() => onPress(pick.id)}
        style={({ pressed }) => pressed && styles.pressed}
        accessibilityRole="button"
        accessibilityLabel={`${pick.name} ${grade.label} ${owned ? `${count}まい` : "みしゅうとく"}${
          owned && circleConfirmed ? " フレンダサークルで かくにんずみ" : ""
        }`}
      >
        <View style={[styles.gradeBar, { backgroundColor: owned ? grade.color : "#C3CDDA" }]}>
          <Text style={[styles.gradeText, !owned && styles.gradeTextDim]}>{grade.label}</Text>
          {count > 1 && (
            <View style={styles.countBadge}>
              <Text style={styles.countText}>{count}</Text>
            </View>
          )}
        </View>

        <View style={styles.imageBox}>
          {thumbFailed ? (
            <PickImage
              uri={pick.image}
              side="front"
              width={width - 6}
              dim={!owned}
            />
          ) : (
            <Image
              source={pick.thumb}
              style={[styles.image, !owned && styles.imageDim]}
              contentFit="contain"
              transition={120}
              cachePolicy="disk"
              recyclingKey={pick.id}
              onError={() => setThumbFailed(true)}
            />
          )}
          {/* 「?」は絵の上に大きく重ねない。登録のときは実物の絵と見くらべるので */}
          {!owned && (
            <View style={styles.unownedBadge}>
              <Text style={styles.unownedMark}>?</Text>
            </View>
          )}
          {owned && circleConfirmed && (
            <View style={styles.circleBadge} accessibilityElementsHidden>
              <Text style={styles.circleBadgeMark}>✓</Text>
            </View>
          )}
        </View>

        <Text style={[styles.name, tight && styles.nameTight, !owned && styles.nameDim]} numberOfLines={1}>
          {pick.name}
        </Text>

        {/* 同じ名前のピックが何枚もあるので、券面の番号で見わけられるようにする */}
        <Text style={[styles.pickNo, tight && styles.pickNoTight]} numberOfLines={1}>
          {pick.id}
        </Text>

        <View style={[styles.typeRow, tight && styles.typeRowTight]}>
          <TypeIcons types={pick.types} size={tight ? 20 : 26} dim={!owned} />
        </View>
      </Pressable>

      {onAdjust && (
        <View style={[styles.adjustRow, tight && styles.adjustRowTight]}>
          <Pressable
            onPress={() => onAdjust(pick.id, -1)}
            disabled={count === 0}
            style={({ pressed }) => [
              styles.adjustButton,
              styles.adjustMinus,
              count === 0 && styles.adjustDisabled,
              pressed && styles.pressed,
            ]}
            accessibilityRole="button"
            accessibilityLabel={`${pick.name} をへらす`}
          >
            <Text style={styles.adjustText}>−</Text>
          </Pressable>

          {/* 小さいカードに ＋ − 数 の3つを並べると、どのボタンも ゆびの幅に足りない。
              ふやすのは絵をタップすればできるので、まちがい直しの − だけを大きく置く。
              数は 2まい以上なら 上の帯にバッジで出ている */}
          {!tight && (
            <>
              <Text style={styles.adjustCount}>{count}</Text>

              <Pressable
                onPress={() => onAdjust(pick.id, 1)}
                style={({ pressed }) => [styles.adjustButton, pressed && styles.pressed]}
                accessibilityRole="button"
                accessibilityLabel={`${pick.name} をふやす`}
              >
                <Text style={styles.adjustText}>＋</Text>
              </Pressable>
            </>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#fff",
    borderRadius: 14,
    borderWidth: 3,
    margin: 6,
    paddingBottom: 8,
    overflow: "hidden",
  },
  cardOwned: {
    boxShadow: "0px 3px 6px rgba(26, 54, 93, 0.18)",
    elevation: 3,
  },
  pressed: { opacity: 0.7, transform: [{ scale: 0.97 }] },
  gradeBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 8,
    paddingVertical: 3,
    minHeight: 22,
  },
  gradeText: { color: "#fff", fontWeight: "800", fontSize: 12 },
  // 未所持のうすい灰色の帯に白文字だとコントラストが足りない
  gradeTextDim: { color: "#3F5064" },
  countBadge: {
    backgroundColor: "rgba(255,255,255,0.95)",
    borderRadius: 10,
    minWidth: 22,
    alignItems: "center",
    paddingHorizontal: 5,
  },
  countText: { fontWeight: "900", fontSize: 12, color: "#1A365D" },
  imageBox: {
    // 公式のサムネイルは よこ長（430x326）と たて長（186x300）の2種類ある。
    // どちらも入るよう、その中間のかたちにしてある
    aspectRatio: 1.25,
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: "#F7FAFD",
  },
  // 券面をできるだけ大きく見せたいので、枠いっぱいまで使う（contentFit は contain）
  image: { width: "100%", height: "100%" },
  // うすくしすぎると、登録のときに手もとの実物と見くらべられない
  imageDim: { opacity: 0.45 },
  unownedBadge: {
    position: "absolute",
    top: 4,
    right: 4,
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: "rgba(255,255,255,0.92)",
    justifyContent: "center",
    alignItems: "center",
  },
  unownedMark: { fontSize: 15, fontWeight: "900", color: "#7C8DA3" },
  circleBadge: {
    position: "absolute",
    top: 4,
    left: 4,
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: "#2F855A",
    justifyContent: "center",
    alignItems: "center",
  },
  circleBadgeMark: { fontSize: 13, fontWeight: "900", color: "#fff" },
  name: {
    fontSize: 14,
    fontWeight: "800",
    color: "#1A365D",
    textAlign: "center",
    marginTop: 6,
    paddingHorizontal: 4,
  },
  nameTight: { fontSize: 11, marginTop: 4, paddingHorizontal: 2 },
  nameDim: { color: "#7C8DA3" },
  pickNo: {
    fontSize: 10,
    fontWeight: "700",
    color: "#9AA8B8",
    textAlign: "center",
    marginTop: 1,
    paddingHorizontal: 4,
  },
  pickNoTight: { fontSize: 9, paddingHorizontal: 2 },
  typeRow: { flexDirection: "row", justifyContent: "center", marginTop: 5, minHeight: 26 },
  typeRowTight: { marginTop: 3, minHeight: 20 },

  adjustRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    marginTop: 8,
    paddingHorizontal: 6,
  },
  adjustRowTight: { marginTop: 6, paddingHorizontal: 4 },
  adjustButton: {
    flex: 1,
    height: 44,
    borderRadius: 12,
    backgroundColor: "#2F855A",
    justifyContent: "center",
    alignItems: "center",
  },
  adjustMinus: { backgroundColor: "#C05621" },
  adjustDisabled: { backgroundColor: "#D6DEE8" },
  adjustText: { color: "#fff", fontSize: 22, fontWeight: "900", lineHeight: 26 },
  adjustCount: {
    fontSize: 20,
    fontWeight: "900",
    color: "#1A365D",
    minWidth: 28,
    textAlign: "center",
  },
});

export const PickCard = memo(PickCardBase);
