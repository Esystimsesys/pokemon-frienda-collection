import { Image } from "expo-image";
import { useEffect, useMemo, useState } from "react";
import {
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

import { BackupCard } from "@/components/BackupCard";
import { OfflineCard } from "@/components/OfflineCard";
import { useCollection } from "@/lib/collection";
import { ALL_PICKS, PICK_BY_ID, PICK_SETS } from "@/lib/picks";
import { useNarrow } from "@/lib/responsive";
import { GROUP_ORDER, GROUP_STYLES, TYPE_ORDER, typeColor } from "@/theme/pokemonTypes";

function ProgressBar({ value, color }: { value: number; color: string }) {
  const pct = Math.min(100, Math.max(0, value * 100));
  return (
    <View style={styles.track}>
      <View style={[styles.fill, { width: `${pct}%` as `${number}%`, backgroundColor: color }]} />
    </View>
  );
}

export default function SummaryScreen() {
  const { ready, countOf, adjust } = useCollection();
  const narrow = useNarrow();

  const totalPicks = ALL_PICKS.length;
  const ownedPicks = useMemo(
    () => ALL_PICKS.filter((p) => countOf(p.id) > 0).length,
    [countOf],
  );
  const totalPercent = totalPicks ? Math.round((ownedPicks / totalPicks) * 100) : 0;

  const setStats = useMemo(
    () =>
      PICK_SETS.map(({ key, label }) => {
        const picks = ALL_PICKS.filter((p) => p.set === key);
        const owned = picks.filter((p) => countOf(p.id) > 0).length;
        return { key, label, owned, total: picks.length };
      }),
    [countOf],
  );

  const groupStats = useMemo(
    () =>
      GROUP_ORDER.map((key) => {
        const picks = ALL_PICKS.filter((p) => p.group === key);
        const owned = picks.filter((p) => countOf(p.id) > 0).length;
        const style = GROUP_STYLES[key];
        return { key, label: style.label, color: style.color, owned, total: picks.length };
      }),
    [countOf],
  );

  const typeStats = useMemo(
    () =>
      TYPE_ORDER.map((type) => {
        const picks = ALL_PICKS.filter((p) => p.types.includes(type));
        const owned = picks.filter((p) => countOf(p.id) > 0).length;
        return { type, owned, total: picks.length, color: typeColor(type) };
      }),
    [countOf],
  );

  /** 公式にタイプが載っていないピック。タイプ集計の数が合わない理由を画面に出すために数える */
  const unknownTypeCount = useMemo(
    () => ALL_PICKS.filter((p) => p.types.length === 0).length,
    [],
  );

  /**
   * ダブりの一覧。− を押して1まいになった行がその場で消えると、
   * 下の行が指の下にせり上がって押しまちがえる。画面を開いているあいだは行を残す。
   */
  const [shownDuplicates, setShownDuplicates] = useState<string[]>([]);
  useEffect(() => {
    if (!ready) return;
    setShownDuplicates(ALL_PICKS.filter((p) => countOf(p.id) >= 2).map((p) => p.id));
    // 開いたときの1回だけ。あとは行を増やしも減らしもしない
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  const duplicates = useMemo(
    () =>
      shownDuplicates
        .map((id) => PICK_BY_ID.get(id))
        .filter((p): p is (typeof ALL_PICKS)[number] => p !== undefined)
        .map((p) => ({ pick: p, count: countOf(p.id) })),
    [shownDuplicates, countOf],
  );

  if (!ready) {
    return (
      <View style={styles.loading}>
        <Text style={styles.loadingText}>よみこみちゅう…</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>ぜんぶで</Text>
        <View style={[styles.bigRow, narrow && styles.bigRowNarrow]}>
          <Text style={styles.bigNumber}>{ownedPicks}</Text>
          <Text style={styles.bigSlash}> / {totalPicks} こ</Text>
          <Text style={styles.bigPercent}>{totalPercent}%</Text>
        </View>
        <ProgressBar value={ownedPicks / totalPicks} color="#2F855A" />
      </View>

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>だんごとのきろく</Text>
        {setStats.map(({ key, label, owned, total }) => {
          const ratio = total ? owned / total : 0;
          const pct = Math.round(ratio * 100);
          return (
            <View key={key} style={styles.rowGroup}>
              <View style={styles.labelRow}>
                <Text style={styles.rowLabel}>{label}</Text>
                <Text style={styles.rowCount}>
                  {owned} / {total}　{pct}%
                </Text>
              </View>
              <ProgressBar value={ratio} color="#2B6CB0" />
            </View>
          );
        })}
      </View>

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>レアごとのきろく</Text>
        {groupStats.map(({ key, label, color, owned, total }) => {
          const ratio = total ? owned / total : 0;
          const pct = Math.round(ratio * 100);
          return (
            <View key={key} style={styles.rowGroup}>
              <View style={styles.labelRow}>
                <View style={[styles.gradeChip, { backgroundColor: color }]}>
                  <Text style={styles.gradeChipText}>{label}</Text>
                </View>
                <Text style={styles.rowCount}>
                  {owned} / {total}　{pct}%
                </Text>
              </View>
              <ProgressBar value={ratio} color={color} />
            </View>
          );
        })}
      </View>

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>タイプごとのもちかず</Text>
        <View style={styles.typeGrid}>
          {typeStats.map(({ type, owned, total, color }) => (
            <View key={type} style={[styles.typeCell, { borderColor: color }]}>
              <View style={[styles.typeHeader, { backgroundColor: color }]}>
                <Text style={styles.typeLabel}>{type}</Text>
              </View>
              <Text style={styles.typeCount}>
                {owned} / {total}
              </Text>
            </View>
          ))}
        </View>
        {/* 公式にタイプが載っていないぶんがあるので、合計が958にならない理由を書いておく */}
        {unknownTypeCount > 0 && (
          <Text style={styles.noteText}>
            タイプが まだ わからない ピックが {unknownTypeCount}こ あるよ。
            その ピックは タイプで さがしても でてこないよ。
          </Text>
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>ダブり</Text>
        {duplicates.length === 0 ? (
          <Text style={styles.emptyText}>ダブりはありません</Text>
        ) : (
          duplicates.map(({ pick, count }) => {
            return (
              <View
                key={pick.id}
                style={[styles.dupRow, narrow && styles.dupRowNarrow, count < 2 && styles.dupRowDone]}
              >
                <Image
                  source={pick.thumb}
                  style={[styles.dupImage, narrow && styles.dupImageNarrow]}
                  contentFit="contain"
                  cachePolicy="disk"
                />
                <View style={styles.dupInfo}>
                  <Text style={styles.dupName} numberOfLines={1}>
                    {pick.name}
                  </Text>
                  <Text style={styles.dupLabel}>
                    {pick.setLabel}　{pick.id}
                  </Text>
                </View>
                <View style={[styles.dupControls, narrow && styles.dupControlsNarrow]}>
                  <TouchableOpacity
                    onPress={() => adjust(pick.id, -1)}
                    style={styles.adjButton}
                    activeOpacity={0.7}
                    accessibilityRole="button"
                    accessibilityLabel={`${pick.name} をへらす`}
                  >
                    <Text style={styles.adjButtonText}>−</Text>
                  </TouchableOpacity>
                  <Text style={[styles.dupCount, narrow && styles.dupCountNarrow]}>{count}</Text>
                  <TouchableOpacity
                    onPress={() => adjust(pick.id, 1)}
                    style={styles.adjButton}
                    activeOpacity={0.7}
                    accessibilityRole="button"
                    accessibilityLabel={`${pick.name} をふやす`}
                  >
                    <Text style={styles.adjButtonText}>＋</Text>
                  </TouchableOpacity>
                </View>
              </View>
            );
          })
        )}
      </View>

      <BackupCard />
      <OfflineCard />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1 },
  content: { padding: 12, paddingBottom: 40, gap: 12 },
  loading: { flex: 1, justifyContent: "center", alignItems: "center" },
  loadingText: { fontSize: 18, color: "#7C8DA3", fontWeight: "700" },

  card: {
    backgroundColor: "#fff",
    borderRadius: 14,
    padding: 16,
    boxShadow: "0px 2px 6px rgba(26, 54, 93, 0.07)",
    elevation: 2,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: "800",
    color: "#1A365D",
    marginBottom: 12,
  },

  bigRow: {
    flexDirection: "row",
    alignItems: "flex-end",
    marginBottom: 10,
  },
  // 320px幅だと「958こ 100%」まで並んだときにはみ出すので、せまい画面では折り返す
  bigRowNarrow: { flexWrap: "wrap" },
  bigNumber: { fontSize: 52, fontWeight: "900", color: "#2F855A", lineHeight: 58 },
  bigSlash: { fontSize: 22, fontWeight: "800", color: "#1A365D", paddingBottom: 6 },
  bigPercent: {
    fontSize: 20,
    fontWeight: "800",
    color: "#7C8DA3",
    paddingBottom: 6,
    marginLeft: 10,
  },

  track: {
    height: 10,
    borderRadius: 5,
    backgroundColor: "#E2E8F0",
    overflow: "hidden",
  },
  fill: { height: "100%" },

  rowGroup: { marginBottom: 10 },
  labelRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 4,
  },
  // 「エクストレジャー1だん」のような長いだんの名前があり、space-betweenの相手（%表示）と
  // 幅を取りあってはみ出すことがあるので縮められるようにしておく
  rowLabel: { fontSize: 14, fontWeight: "700", color: "#1A365D", flexShrink: 1 },
  rowCount: { fontSize: 13, fontWeight: "700", color: "#7C8DA3" },

  gradeChip: {
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  gradeChipText: { color: "#fff", fontWeight: "800", fontSize: 13 },

  typeGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  typeCell: {
    borderWidth: 2,
    borderRadius: 10,
    overflow: "hidden",
    minWidth: 72,
  },
  typeHeader: {
    paddingHorizontal: 6,
    paddingVertical: 3,
    alignItems: "center",
  },
  typeLabel: { color: "#fff", fontWeight: "800", fontSize: 12 },
  typeCount: {
    textAlign: "center",
    fontSize: 13,
    fontWeight: "700",
    color: "#1A365D",
    paddingVertical: 4,
  },

  emptyText: { fontSize: 14, color: "#7C8DA3", fontWeight: "700", textAlign: "center", paddingVertical: 8 },
  noteText: { marginTop: 12, fontSize: 12, fontWeight: "700", color: "#7C8DA3", lineHeight: 18 },

  // ダブりでなくなった行。すぐには消さず、うすくして残す
  dupRowDone: { opacity: 0.45 },
  dupRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: "#E2E8F0",
  },
  // せまい画面では画像とボタンぶんの幅の取りぶんが大きく、名前がほぼ読めなくなるので詰める
  dupRowNarrow: { gap: 6 },
  dupImage: { width: 52, height: 42 },
  dupImageNarrow: { width: 40, height: 32 },
  dupInfo: { flex: 1 },
  dupName: { fontSize: 14, fontWeight: "800", color: "#1A365D" },
  dupLabel: { fontSize: 11, color: "#7C8DA3", fontWeight: "600" },
  dupControls: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  dupControlsNarrow: { gap: 2 },
  adjButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "#2B6CB0",
    justifyContent: "center",
    alignItems: "center",
  },
  adjButtonText: { color: "#fff", fontSize: 22, fontWeight: "900", lineHeight: 26 },
  dupCount: {
    fontSize: 20,
    fontWeight: "900",
    color: "#1A365D",
    minWidth: 32,
    textAlign: "center",
  },
  dupCountNarrow: { minWidth: 22 },
});
