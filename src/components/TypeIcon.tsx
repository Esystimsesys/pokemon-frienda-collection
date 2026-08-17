import { Image } from "expo-image";
import { StyleSheet, Text, View } from "react-native";

import { typeColor } from "@/theme/pokemonTypes";

/**
 * 券面とおなじタイプのマーク。
 * scripts/ocr/export_type_icons.py が公式の裏面（わざ欄1行目）から切り出したもの。
 * 1タイプ25枚ぶんを位置合わせして重ねてあるので、18個の大きさと余白がそろっている。
 * 18個で360KBしかないので、ピック画像とちがってアプリに入れてしまってよい。
 */
const ICONS: Record<string, number> = {
  ノーマル: require("../../assets/types/normal.png"),
  ほのお: require("../../assets/types/fire.png"),
  みず: require("../../assets/types/water.png"),
  でんき: require("../../assets/types/electric.png"),
  くさ: require("../../assets/types/grass.png"),
  こおり: require("../../assets/types/ice.png"),
  かくとう: require("../../assets/types/fighting.png"),
  どく: require("../../assets/types/poison.png"),
  じめん: require("../../assets/types/ground.png"),
  ひこう: require("../../assets/types/flying.png"),
  エスパー: require("../../assets/types/psychic.png"),
  むし: require("../../assets/types/bug.png"),
  いわ: require("../../assets/types/rock.png"),
  ゴースト: require("../../assets/types/ghost.png"),
  ドラゴン: require("../../assets/types/dragon.png"),
  あく: require("../../assets/types/dark.png"),
  はがね: require("../../assets/types/steel.png"),
  フェアリー: require("../../assets/types/fairy.png"),
};

type Props = {
  type: string | null;
  size?: number;
  /** マークのよこに 名前 も出す */
  withLabel?: boolean;
  dim?: boolean;
};

export function TypeIcon({ type, size = 24, withLabel, dim }: Props) {
  const icon = type ? ICONS[type] : undefined;

  if (!icon) {
    // タイプがわからないピック用。マークが無いので色つきの丸で代用する
    return (
      <View
        style={[
          styles.fallback,
          { width: size, height: size, borderRadius: size / 4, backgroundColor: typeColor(type) },
          dim && styles.dim,
        ]}
      >
        <Text style={[styles.fallbackMark, { fontSize: size * 0.6 }]}>?</Text>
      </View>
    );
  }

  const image = (
    <Image
      source={icon}
      style={[{ width: size, height: size }, dim && styles.dim]}
      contentFit="contain"
      accessibilityLabel={type ?? undefined}
      alt={type ?? undefined}
    />
  );

  if (!withLabel) return image;

  return (
    <View style={styles.row}>
      {image}
      <Text style={[styles.label, { color: typeColor(type) }]}>{type}</Text>
    </View>
  );
}

/** ならんだタイプをまとめて出す */
export function TypeIcons({
  types,
  size = 24,
  withLabel,
  dim,
}: {
  types: string[];
  size?: number;
  withLabel?: boolean;
  dim?: boolean;
}) {
  return (
    <View style={styles.list}>
      {types.map((t) => (
        <TypeIcon key={t} type={t} size={size} withLabel={withLabel} dim={dim} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { flexDirection: "row", alignItems: "center", gap: 4, flexWrap: "wrap" },
  row: { flexDirection: "row", alignItems: "center", gap: 4 },
  label: { fontSize: 12, fontWeight: "800" },
  dim: { opacity: 0.45 },
  fallback: { justifyContent: "center", alignItems: "center" },
  fallbackMark: { color: "#fff", fontWeight: "900" },
});
