import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { PanResponder, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { PickImage } from "@/components/PickImage";
import { neighbours } from "@/lib/browseOrder";
import { useCollection } from "@/lib/collection";
import { MAX_ENERGY, MAX_STAT, PICK_BY_ID, STAT_FIELDS } from "@/lib/picks";
import { MechanicCard } from "@/components/MechanicCard";
import { TypeIcon, TypeIcons } from "@/components/TypeIcon";
import { groupStyle, typeColor } from "@/theme/pokemonTypes";

export default function PickDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { countOf, adjust } = useCollection();
  const [side, setSide] = useState<"front" | "back">("front");
  const [heroWidth, setHeroWidth] = useState(0);
  const pick = id ? PICK_BY_ID.get(id) : undefined;

  const { prev, next } = useMemo(() => neighbours(id ?? ""), [id]);

  // 別のピックへ移ったら、表面から見せる
  useEffect(() => {
    setSide("front");
  }, [id]);

  /**
   * よこにスワイプして前後のピックへ。
   * たてのスクロールを邪魔しないよう、よこの動きのほうが大きいときだけ受けとる。
   * 並びは ずかんで見えていたものと同じ（src/lib/browseOrder.ts）。
   */
  const go = useRef<(to: string | null) => void>(() => {});
  go.current = (to) => {
    if (to) router.replace(`/pick/${to}`);
  };

  const pan = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_e, g) =>
        Math.abs(g.dx) > 24 && Math.abs(g.dx) > Math.abs(g.dy) * 1.5,
      onPanResponderRelease: (_e, g) => {
        if (g.dx > 60) go.current(prevRef.current);
        else if (g.dx < -60) go.current(nextRef.current);
      },
    }),
  ).current;

  // PanResponder は作り直さないので、前後のIDは ref ごしに見る
  const prevRef = useRef<string | null>(null);
  const nextRef = useRef<string | null>(null);
  prevRef.current = prev;
  nextRef.current = next;

  if (!pick) {
    return (
      <View style={styles.missing}>
        <Text style={styles.missingText}>ピックが みつかりません</Text>
      </View>
    );
  }

  const count = countOf(pick.id);
  const grade = groupStyle(pick);
  const { stats } = pick;

  return (
    <ScrollView contentContainerStyle={styles.content} {...pan.panHandlers}>
      <View
        style={[styles.hero, { borderColor: grade.color }]}
        onLayout={(e) => setHeroWidth(e.nativeEvent.layout.width)}
      >
        <View style={[styles.gradeBar, { backgroundColor: grade.color }]}>
          <Text style={styles.gradeText}>{grade.label}</Text>
          <Text style={styles.gradeText}>
            {pick.setLabel}　{pick.id}
          </Text>
        </View>

        <View style={styles.heroBody}>
          <TouchableOpacity
            onPress={() => go.current(prev)}
            disabled={!prev}
            style={[styles.arrow, !prev && styles.arrowOff]}
            accessibilityRole="button"
            accessibilityLabel="まえの ピック"
          >
            <Text style={styles.arrowText}>‹</Text>
          </TouchableOpacity>

          {heroWidth > 0 && (
            <PickImage uri={pick.image} side={side} width={heroWidth - 96} style={styles.image} />
          )}

          <TouchableOpacity
            onPress={() => go.current(next)}
            disabled={!next}
            style={[styles.arrow, !next && styles.arrowOff]}
            accessibilityRole="button"
            accessibilityLabel="つぎの ピック"
          >
            <Text style={styles.arrowText}>›</Text>
          </TouchableOpacity>
        </View>

        <TouchableOpacity
          onPress={() => setSide((s) => (s === "front" ? "back" : "front"))}
          activeOpacity={0.8}
          style={[styles.flipButton, { backgroundColor: grade.color }]}
          accessibilityRole="button"
        >
          <Text style={styles.flipText}>
            {side === "front" ? "うらを みる" : "おもてを みる"}
          </Text>
        </TouchableOpacity>

        <Text style={styles.name}>{pick.name}</Text>

        <View style={styles.typeRow}>
          <TypeIcons types={pick.types} size={40} withLabel />
        </View>
      </View>

      <MechanicCard pick={pick} />


      {/* ステータス欄が無いピックにも わざ はあるので、強さ とは切りはなして出す */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>わざ</Text>
        {pick.moves.length === 0 ? (
          <Text style={styles.hintText}>「うらを みる」を おすと、わざが かいて あるよ</Text>
        ) : (
          pick.moves.map((m) => (
            <View key={m.name} style={styles.moveRow}>
              <TypeIcon type={m.type} size={32} />
              <Text style={styles.moveName}>{m.name === "不明" ? "まだ わからない" : m.name}</Text>
            </View>
          ))
        )}
      </View>

      {stats ? (
        <>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>つよさ</Text>

            {/* ポケエネは裏面に印字が無いので、わかっているピックだけ出す */}
            {stats.energy !== null && (
              <>
                <View style={styles.energyRow}>
                  <Text style={styles.energyLabel}>ポケエネ</Text>
                  <Text style={styles.energyValue}>{stats.energy}</Text>
                </View>
                <View style={styles.track}>
                  <View
                    style={[
                      styles.fill,
                      {
                        width: `${Math.round((stats.energy / MAX_ENERGY) * 100)}%`,
                        backgroundColor: grade.color,
                      },
                    ]}
                  />
                </View>
              </>
            )}

            {/* すばやさは裏面と同じく、矢印が何個ぬられているかで見せる */}
            {stats.speed !== null && (
              <View style={styles.speedRow}>
                <Text style={styles.speedLabel}>すばやさ</Text>
                <View style={styles.speedArrows}>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <Text
                      key={n}
                      style={[styles.speedArrow, n <= stats.speed! && styles.speedArrowOn]}
                    >
                      ▶
                    </Text>
                  ))}
                </View>
              </View>
            )}

            <View style={styles.statList}>
              {STAT_FIELDS.map((f) => (
                <View key={f.key} style={styles.statRow}>
                  <Text style={styles.statLabel}>{f.label}</Text>
                  <Text style={styles.statValue}>{stats[f.key]}</Text>
                  <View style={styles.statTrack}>
                    <View
                      style={[
                        styles.fill,
                        {
                          width: `${Math.round((stats[f.key] / MAX_STAT) * 100)}%`,
                          backgroundColor: typeColor(pick.types[0]),
                        },
                      ]}
                    />
                  </View>
                </View>
              ))}
            </View>
          </View>
        </>
      ) : (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>つよさ</Text>
          <Text style={styles.hintText}>
            このピックには つよさが かいて ないよ
          </Text>
        </View>
      )}

      {/* さいごに置く。見るときは わざ と 強さ が先で、かぞえるのは そのあと */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>もってるまいすう</Text>
        <View style={styles.counterRow}>
          <TouchableOpacity
            onPress={() => adjust(pick.id, -1)}
            disabled={count === 0}
            activeOpacity={0.7}
            style={[styles.counterButton, styles.minus, count === 0 && styles.counterDisabled]}
          >
            <Text style={styles.counterSign}>−</Text>
          </TouchableOpacity>

          <View style={styles.countBox}>
            <Text style={[styles.countValue, count === 0 && styles.countZero]}>{count}</Text>
            <Text style={styles.countUnit}>まい</Text>
          </View>

          <TouchableOpacity
            onPress={() => adjust(pick.id, 1)}
            activeOpacity={0.7}
            style={[styles.counterButton, styles.plus]}
          >
            <Text style={styles.counterSign}>＋</Text>
          </TouchableOpacity>
        </View>
        <Text style={[styles.ownedLabel, { color: count > 0 ? "#2F855A" : "#C05621" }]}>
          {count > 0 ? "もってる！" : "まだ もってない"}
        </Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: 12, paddingBottom: 40, gap: 12, maxWidth: 720, width: "100%", alignSelf: "center" },
  missing: { flex: 1, justifyContent: "center", alignItems: "center" },
  missingText: { fontSize: 18, fontWeight: "800", color: "#7C8DA3" },

  hero: { backgroundColor: "#fff", borderRadius: 16, borderWidth: 3, overflow: "hidden", paddingBottom: 14 },
  gradeBar: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  gradeText: { color: "#fff", fontWeight: "800", fontSize: 13 },
  image: { alignSelf: "center" },
  heroBody: { flexDirection: "row", alignItems: "center", marginTop: 10 },
  arrow: {
    width: 44,
    height: 72,
    justifyContent: "center",
    alignItems: "center",
  },
  arrowOff: { opacity: 0.15 },
  arrowText: { fontSize: 40, fontWeight: "900", color: "#7C8DA3", lineHeight: 44 },
  flipButton: {
    alignSelf: "center",
    marginTop: 12,
    borderRadius: 22,
    paddingHorizontal: 26,
    paddingVertical: 12,
  },
  flipText: { color: "#fff", fontSize: 17, fontWeight: "900" },
  name: { fontSize: 26, fontWeight: "900", color: "#1A365D", textAlign: "center", marginTop: 12 },
  typeRow: { flexDirection: "row", justifyContent: "center", gap: 8, marginTop: 10 },
  typeChip: { borderRadius: 10, paddingHorizontal: 12, paddingVertical: 5 },
  typeChipText: { color: "#fff", fontWeight: "800", fontSize: 13 },

  card: { backgroundColor: "#fff", borderRadius: 16, padding: 14 },
  cardTitle: { fontSize: 15, fontWeight: "900", color: "#7C8DA3", marginBottom: 10 },
  hintText: { fontSize: 16, fontWeight: "700", color: "#1A365D", lineHeight: 24 },

  counterRow: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 22 },
  counterButton: { width: 68, height: 68, borderRadius: 34, justifyContent: "center", alignItems: "center" },
  minus: { backgroundColor: "#C05621" },
  plus: { backgroundColor: "#2F855A" },
  counterDisabled: { opacity: 0.3 },
  counterSign: { color: "#fff", fontSize: 34, fontWeight: "900", lineHeight: 38 },
  countBox: { flexDirection: "row", alignItems: "baseline", gap: 4, minWidth: 96, justifyContent: "center" },
  countValue: { fontSize: 46, fontWeight: "900", color: "#1A365D" },
  countZero: { color: "#C3CDDA" },
  countUnit: { fontSize: 16, fontWeight: "800", color: "#7C8DA3" },
  ownedLabel: { textAlign: "center", marginTop: 10, fontSize: 16, fontWeight: "900" },

  moveRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  moveName: { fontSize: 18, fontWeight: "800", color: "#1A365D" },

  energyRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" },
  energyLabel: { fontSize: 14, fontWeight: "800", color: "#1A365D" },
  energyValue: { fontSize: 22, fontWeight: "900", color: "#1A365D" },
  speedRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 12,
  },
  speedLabel: { fontSize: 14, fontWeight: "800", color: "#1A365D" },
  speedArrows: { flexDirection: "row", gap: 2 },
  speedArrow: { fontSize: 20, color: "#D6DEE8" },
  speedArrowOn: { color: "#E8B21C" },
  track: { height: 12, borderRadius: 6, backgroundColor: "#E2E8F0", overflow: "hidden", marginTop: 6 },
  fill: { height: "100%", borderRadius: 6 },

  statList: { marginTop: 14, gap: 8 },
  statRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  statLabel: { width: 64, fontSize: 13, fontWeight: "800", color: "#7C8DA3" },
  statValue: { width: 38, fontSize: 15, fontWeight: "900", color: "#1A365D", textAlign: "right" },
  statTrack: { flex: 1, height: 10, borderRadius: 5, backgroundColor: "#E2E8F0", overflow: "hidden" },
});
