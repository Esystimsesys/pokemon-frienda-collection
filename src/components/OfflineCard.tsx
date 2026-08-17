import { useEffect, useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";

import {
  OFFLINE_SUPPORTED,
  TOTAL_IMAGES,
  prefetchImages,
  stopPrefetch,
  subscribePrefetch,
  type PrefetchState,
} from "@/lib/offline";

/** 先読みぶんのおおよその大きさ。ピックのサムネイルは実測の平均 45.6KB から出している */
const APPROX_MB = 45;

export function OfflineCard() {
  const [s, setS] = useState<PrefetchState | null>(null);

  useEffect(() => subscribePrefetch(setS), []);

  if (!OFFLINE_SUPPORTED || s === null || !s.started) return null;

  const ratio = s.done / TOTAL_IMAGES;
  const complete = s.done >= TOTAL_IMAGES;

  return (
    <View style={styles.card}>
      <Text style={styles.title}>でんぱが なくても みる</Text>
      <Text style={styles.body}>
        {complete
          ? "ぜんぶの えが この タブレットに はいっているよ。でんぱが なくても ずかんが みられる！"
          : s.running
            ? `えを よみこんでいるよ。おわるまで まってね。（ぜんぶで やく ${APPROX_MB}MB）`
            : `えを ぜんぶ よみこむと、でんぱが なくても ずかんが みられるよ。（のこり ${TOTAL_IMAGES - s.done}まい）`}
      </Text>

      <View style={styles.track}>
        <View style={[styles.fill, { width: `${Math.round(ratio * 100)}%` as `${number}%` }]} />
      </View>
      <Text style={styles.count}>
        {s.done} / {TOTAL_IMAGES} まい
      </Text>

      {s.running ? (
        <TouchableOpacity onPress={stopPrefetch} activeOpacity={0.8} style={[styles.button, styles.buttonStop]}>
          <Text style={styles.buttonText}>とめる</Text>
        </TouchableOpacity>
      ) : (
        !complete && (
          <TouchableOpacity
            onPress={() => void prefetchImages()}
            activeOpacity={0.8}
            style={styles.button}
          >
            <Text style={styles.buttonText}>いま よみこむ</Text>
          </TouchableOpacity>
        )
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#fff",
    borderRadius: 14,
    padding: 16,
    boxShadow: "0px 2px 6px rgba(26, 54, 93, 0.07)",
    elevation: 2,
  },
  title: { fontSize: 16, fontWeight: "800", color: "#1A365D", marginBottom: 8 },
  body: { fontSize: 13, fontWeight: "600", color: "#5A6C82", lineHeight: 20, marginBottom: 12 },
  track: { height: 10, borderRadius: 5, backgroundColor: "#E2E8F0", overflow: "hidden" },
  fill: { height: "100%", backgroundColor: "#0F9B8E" },
  count: { fontSize: 13, fontWeight: "700", color: "#7C8DA3", marginTop: 6 },
  button: {
    marginTop: 12,
    backgroundColor: "#0F9B8E",
    borderRadius: 16,
    paddingVertical: 14,
    alignItems: "center",
  },
  buttonStop: { backgroundColor: "#C05621" },
  buttonText: { color: "#fff", fontSize: 15, fontWeight: "800" },
});
