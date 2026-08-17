import { StyleSheet, Text, View } from "react-native";

import type { Pick } from "@/types";

/**
 * とくべつな仕組み（テラスタル・Zワザ・メガシンカ・タッグわざ・ダイマックス）と、
 * でんせつ／まぼろしのしるし。
 * 説明は公式の「アイコン・マークについて」の文言を、漢字を開いて使っている。
 */
const MECHANICS: Record<string, { color: string; text: string }> = {
  テラスタル: { color: "#7B3FBF", text: "テラスタルチャンスを せいこうさせて、バトルを ゆうりに すすめよう！" },
  Zワザ: { color: "#C8930B", text: "Zワザチャンスを せいこうさせて、バトルを ゆうりに すすめよう！" },
  メガシンカ: { color: "#C05621", text: "メガシンカチャンスを せいこうさせて、バトルを ゆうりに すすめよう！" },
  タッグわざ: { color: "#2B6CB0", text: "タッグわざチャンスを せいこうさせて、バトルを ゆうりに すすめよう！" },
  ダイマックス: { color: "#D0342C", text: "ダイマックスチャンスを せいこうさせて、バトルを ゆうりに すすめよう！" },
};

const LEGENDS: Record<string, { color: string; text: string }> = {
  でんせつ: { color: "#B7791F", text: "でんせつの ポケモンだよ" },
  まぼろし: { color: "#B83280", text: "まぼろしの ポケモンだよ" },
};

export function MechanicCard({ pick }: { pick: Pick }) {
  const m = pick.mechanic ? MECHANICS[pick.mechanic] : undefined;
  const l = pick.legend ? LEGENDS[pick.legend] : undefined;
  if (!m && !l) return null;

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>とくべつな ちから</Text>

      {l && (
        <View style={[styles.badgeRow, { borderColor: l.color }]}>
          <View style={[styles.badge, { backgroundColor: l.color }]}>
            <Text style={styles.badgeText}>{pick.legend}</Text>
          </View>
          <Text style={styles.desc}>{l.text}</Text>
        </View>
      )}

      {m && (
        <View style={[styles.badgeRow, { borderColor: m.color }]}>
          <View style={[styles.badge, { backgroundColor: m.color }]}>
            <Text style={styles.badgeText}>{pick.mechanic}</Text>
          </View>
          <View style={styles.body}>
            {pick.specialMove !== null && (
              <Text style={[styles.move, { color: m.color }]}>
                {pick.tagPartner !== null ? `${pick.tagPartner}　` : ""}
                {pick.specialMove}
              </Text>
            )}
            <Text style={styles.desc}>{m.text}</Text>
          </View>
        </View>
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
  cardTitle: { fontSize: 16, fontWeight: "800", color: "#1A365D", marginBottom: 10 },
  badgeRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10,
    borderWidth: 2,
    borderRadius: 12,
    padding: 10,
    marginBottom: 8,
  },
  badge: { borderRadius: 10, paddingHorizontal: 10, paddingVertical: 5 },
  badgeText: { color: "#fff", fontSize: 13, fontWeight: "900" },
  body: { flex: 1, gap: 2 },
  move: { fontSize: 16, fontWeight: "900" },
  desc: { flex: 1, fontSize: 12, fontWeight: "700", color: "#5A6C82", lineHeight: 18 },
});
