import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { TOTAL_IMAGES, subscribePrefetch, type PrefetchState } from "@/lib/offline";

/**
 * 画像を読み込んでいるあいだだけ、ずかんの上に細く出す。
 * 終わったら消える。じゃまにならないよう、押せる要素は置かない
 * （とめる／やり直しは「きろく」の中にある）。
 */
export function PrefetchBar() {
  const [s, setS] = useState<PrefetchState | null>(null);

  useEffect(() => subscribePrefetch(setS), []);

  if (!s || !s.running) return null;

  const pct = Math.round((s.done / TOTAL_IMAGES) * 100);

  return (
    <View style={styles.wrap}>
      <View style={styles.track}>
        <View style={[styles.fill, { width: `${pct}%` as `${number}%` }]} />
      </View>
      <Text style={styles.text}>
        えを よみこみちゅう… {s.done} / {TOTAL_IMAGES} まい
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { paddingHorizontal: 12, paddingTop: 6, paddingBottom: 4, backgroundColor: "#EAF7F5" },
  track: { height: 6, borderRadius: 3, backgroundColor: "#CFE9E4", overflow: "hidden" },
  fill: { height: "100%", backgroundColor: "#0F9B8E" },
  text: { fontSize: 11, fontWeight: "700", color: "#0F766E", marginTop: 3 },
});
