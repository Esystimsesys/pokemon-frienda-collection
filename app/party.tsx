import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useMemo } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { useCollection } from "@/lib/collection";
import { TypeIcons } from "@/components/TypeIcon";
import { pickParty, rankOwned, type Ranked } from "@/lib/party";
import { groupStyle } from "@/theme/pokemonTypes";

/** 1回のバトルでピックを3まい置く */
const PARTY_SIZE = 3;

function Row({ item, rank, onPress }: { item: Ranked; rank: number; onPress: () => void }) {
  const { pick, count, power, estimated } = item;
  const grade = groupStyle(pick);

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.row, pressed && styles.pressed]}
      accessibilityRole="button"
      accessibilityLabel={`${rank}ばんめ ${pick.name} ポケエネ ${power}`}
    >
      <Text style={styles.rank}>{rank}</Text>
      <Image
        source={pick.thumb}
        style={styles.thumb}
        contentFit="contain"
        cachePolicy="disk"
        recyclingKey={pick.id}
      />
      <View style={styles.info}>
        <Text style={styles.name} numberOfLines={1}>
          {pick.name}
        </Text>
        <View style={styles.typeRow}>
          <View style={[styles.gradeChip, { backgroundColor: grade.color }]}>
            <Text style={styles.chipText}>{grade.label}</Text>
          </View>
          <TypeIcons types={pick.types} size={24} />
          {count > 1 && <Text style={styles.count}>{count}まい</Text>}
        </View>
      </View>
      <View style={styles.powerBox}>
        <Text style={styles.power}>{power}</Text>
        <Text style={styles.powerUnit}>{estimated ? "くらい" : "ポケエネ"}</Text>
      </View>
    </Pressable>
  );
}

export default function PartyScreen() {
  const router = useRouter();
  const { countOf, ready } = useCollection();

  const ranked = useMemo(() => (ready ? rankOwned(countOf) : []), [ready, countOf]);
  const party = useMemo(() => pickParty(ranked, PARTY_SIZE), [ranked]);

  if (!ready) {
    return (
      <View style={styles.loading}>
        <Text style={styles.loadingText}>よみこみちゅう…</Text>
      </View>
    );
  }

  if (ranked.length === 0) {
    return (
      <View style={styles.loading}>
        <Text style={styles.loadingText}>
          まだ ピックを とうろく していないよ。{"\n"}
          ずかんで もってる ピックを とうろく してね。
        </Text>
      </View>
    );
  }

  const open = (id: string) => router.push(`/pick/${id}`);

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>おすすめの くみあわせ</Text>
        <Text style={styles.lead}>
          バトルで つかう 3まい だよ。もってる ピックから、ポケエネが たかくて タイプが かぶらない ものを えらんだよ。
        </Text>
        {party.map((item, i) => (
          <Row key={item.pick.id} item={item} rank={i + 1} onPress={() => open(item.pick.id)} />
        ))}
      </View>

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>つよい じゅんばん</Text>
        <Text style={styles.lead}>もってる ピック {ranked.length}こ を つよい じゅんに ならべたよ。</Text>
        {ranked.slice(0, 50).map((item, i) => (
          <Row key={item.pick.id} item={item} rank={i + 1} onPress={() => open(item.pick.id)} />
        ))}
        {ranked.length > 50 && (
          <Text style={styles.moreText}>ここまでが つよい じゅんの 50こ だよ</Text>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1 },
  content: { padding: 12, paddingBottom: 40, gap: 12 },
  loading: { flex: 1, justifyContent: "center", alignItems: "center", padding: 24 },
  loadingText: {
    fontSize: 17,
    color: "#5A6C82",
    fontWeight: "700",
    textAlign: "center",
    lineHeight: 26,
  },

  card: {
    backgroundColor: "#fff",
    borderRadius: 14,
    padding: 16,
    boxShadow: "0px 2px 6px rgba(26, 54, 93, 0.07)",
    elevation: 2,
  },
  sectionTitle: { fontSize: 16, fontWeight: "800", color: "#1A365D", marginBottom: 6 },
  lead: { fontSize: 13, fontWeight: "600", color: "#5A6C82", lineHeight: 20, marginBottom: 10 },
  moreText: { fontSize: 12, fontWeight: "700", color: "#9AA8B8", textAlign: "center", marginTop: 10 },

  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingVertical: 8,
    minHeight: 60,
    borderBottomWidth: 1,
    borderBottomColor: "#E2E8F0",
  },
  pressed: { opacity: 0.6 },
  rank: {
    width: 26,
    fontSize: 16,
    fontWeight: "900",
    color: "#7C8DA3",
    textAlign: "center",
  },
  thumb: { width: 56, height: 44 },
  info: { flex: 1, gap: 4 },
  name: { fontSize: 15, fontWeight: "800", color: "#1A365D" },
  typeRow: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 4 },
  gradeChip: { borderRadius: 8, paddingHorizontal: 6, paddingVertical: 2 },
  chipText: { color: "#fff", fontSize: 10, fontWeight: "800" },
  count: { fontSize: 11, fontWeight: "700", color: "#7C8DA3", marginLeft: 2 },
  powerBox: { alignItems: "flex-end", minWidth: 56 },
  power: { fontSize: 19, fontWeight: "900", color: "#2F855A" },
  powerUnit: { fontSize: 10, fontWeight: "700", color: "#9AA8B8" },
});
