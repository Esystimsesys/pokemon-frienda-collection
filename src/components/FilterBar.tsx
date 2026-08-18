import { useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";

import { TypeIcon } from "@/components/TypeIcon";
import { CARD_SIZES, type CardSize, loadFilterOpen, saveFilterOpen } from "@/lib/filterPrefs";
import { PICK_SETS } from "@/lib/picks";
import { useNarrow } from "@/lib/responsive";
import { GROUP_ORDER, GROUP_STYLES, TYPE_COLORS, TYPE_ORDER } from "@/theme/pokemonTypes";
import type { PickGroup, SetKey } from "@/types";

export type OwnedFilter = "all" | "owned" | "missing";

export type Filters = {
  /** 選んだ だん。からっぽなら 全部。いくつでも 選べる */
  sets: SetKey[];
  group: PickGroup | null;
  /** ★の数でしぼる。group とはどちらか一方だけ使う */
  grade: number | null;
  type: string | null;
  owned: OwnedFilter;
  query: string;
};

export const EMPTY_FILTERS: Filters = {
  sets: [],
  group: null,
  grade: null,
  type: null,
  owned: "all",
  query: "",
};

type ChipProps = {
  label: string;
  active: boolean;
  color?: string;
  /** タイプのチップは、名前の左に券面とおなじマークを出す */
  icon?: string;
  onPress: () => void;
};

function Chip({ label, active, color = "#2B6CB0", icon, onPress }: ChipProps) {
  return (
    <TouchableOpacity
      onPress={onPress}
      activeOpacity={0.7}
      style={[
        styles.chip,
        icon !== undefined && styles.chipWithIcon,
        { borderColor: color },
        active && { backgroundColor: color },
      ]}
    >
      {icon !== undefined && <TypeIcon type={icon} size={22} />}
      <Text style={[styles.chipText, { color: active ? "#fff" : color }]}>{label}</Text>
    </TouchableOpacity>
  );
}

/**
 * 見出し＋チップの1行。
 * だんは13こ全部を一度に見せたいので、よこスクロールではなく折り返しにする
 * （ただし せまい画面では、折り返すと13行になって画面がぜんぶ埋まってしまうので
 *   よこスクロールに戻す。FilterBar の wrap={!narrow} を参照）。
 */
function Row({
  title,
  wrap,
  children,
}: {
  title: string;
  wrap?: boolean;
  children: React.ReactNode;
}) {
  // せまい画面では、見出しに78pxも使うとチップの置き場が無くなる
  const narrow = useNarrow();

  return (
    <View style={[styles.row, wrap && styles.rowWrap]}>
      <Text
        style={[styles.rowTitle, narrow && styles.rowTitleNarrow, wrap && styles.rowTitleWrap]}
        numberOfLines={1}
      >
        {title}
      </Text>
      {wrap ? (
        <View style={styles.rowWrapped}>{children}</View>
      ) : (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.rowScroll}
        >
          {children}
        </ScrollView>
      )}
    </View>
  );
}

type Props = {
  filters: Filters;
  onChange: (next: Filters) => void;
  /** 登録中は、ひらいていても自動でたたむ */
  compact?: boolean;
  /**
   * カードの大きさ。しぼりこみではないが、たまに変えるだけの設定なので
   * 専用の画面はつくらず、この中に置いている。
   */
  cardSize: CardSize;
  onCardSizeChange: (size: CardSize) => void;
};

export function FilterBar({ filters, onChange, compact, cardSize, onCardSizeChange }: Props) {
  // ひらいたままだと画面の半分ちかくを占めるので、ふだんはたたんでおく。
  // どちらにしていたかは覚えておく。
  const [open, setOpen] = useState(false);
  const narrow = useNarrow();

  useEffect(() => {
    loadFilterOpen().then(setOpen);
  }, []);

  const toggleOpen = () => {
    const next = !open;
    setOpen(next);
    saveFilterOpen(next);
  };

  const set = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    onChange({ ...filters, [key]: value });

  const toggle = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    onChange({ ...filters, [key]: filters[key] === value ? (null as Filters[K]) : value });

  const showChips = open && !compact;

  // たたんでいるときに、いま何でしぼっているかが分かるようにする
  const chosen = PICK_SETS.filter((s) => filters.sets.includes(s.key)).map((s) => s.label);
  const parts: string[] = [];
  // だんを4つも5つも並べると読めないので、多いときは数だけにする
  parts.push(
    chosen.length === 0
      ? "ぜんぶの だん"
      : chosen.length <= 2
        ? chosen.join("・")
        : `${chosen.length}つの だん`,
  );
  if (filters.owned === "owned") parts.push("もってる");
  if (filters.owned === "missing") parts.push("もってない");
  if (filters.grade !== null) parts.push(`★${filters.grade}`);
  if (filters.group !== null) parts.push(GROUP_STYLES[filters.group].label);
  if (filters.type !== null) parts.push(filters.type);

  return (
    <View style={styles.wrap}>
      <View style={styles.searchRow}>
        <TextInput
          value={filters.query}
          onChangeText={(t) => set("query", t)}
          placeholder="なまえ か ばんごう で さがす"
          placeholderTextColor="#9AA8B8"
          style={styles.search}
          autoCorrect={false}
          autoCapitalize="none"
          spellCheck={false}
          returnKeyType="search"
        />
        {/* clearButtonMode は iOS ネイティブ専用で web では出ないので自前で置く */}
        {filters.query.length > 0 && (
          <TouchableOpacity
            onPress={() => set("query", "")}
            style={styles.clearButton}
            accessibilityRole="button"
            accessibilityLabel="さがす もじを けす"
          >
            <Text style={styles.clearText}>✕</Text>
          </TouchableOpacity>
        )}
      </View>

      <View style={styles.headRow}>
        <Text style={styles.headLabel} numberOfLines={1}>
          {parts.join("・")}
        </Text>
        <TouchableOpacity
          onPress={toggleOpen}
          style={[styles.headButton, showChips && styles.headButtonOpen]}
          accessibilityRole="button"
        >
          <Text style={[styles.headButtonText, showChips && styles.headButtonTextOpen]}>
            {showChips ? "とじる" : "しぼりこみ"}
          </Text>
        </TouchableOpacity>
      </View>

      {showChips && (
        <>
          <Row title="もちもの">
            <Chip
              label="ぜんぶ"
              active={filters.owned === "all"}
              onPress={() => set("owned", "all")}
            />
            <Chip
              label="もってる"
              active={filters.owned === "owned"}
              color="#2F855A"
              onPress={() => set("owned", "owned")}
            />
            <Chip
              label="もってない"
              active={filters.owned === "missing"}
              color="#C05621"
              onPress={() => set("owned", "missing")}
            />
          </Row>

          <Row title="だん" wrap={!narrow}>
            <Chip
              label="ぜんぶ"
              active={filters.sets.length === 0}
              onPress={() => set("sets", [])}
            />
            {PICK_SETS.map(({ key, label }) => (
              <Chip
                key={key}
                label={label}
                active={filters.sets.includes(key)}
                onPress={() =>
                  set(
                    "sets",
                    filters.sets.includes(key)
                      ? filters.sets.filter((k) => k !== key)
                      : [...filters.sets, key],
                  )
                }
              />
            ))}
          </Row>

          <Row title="レア">
            <Chip
              label="ぜんぶ"
              active={filters.group === null && filters.grade === null}
              onPress={() => onChange({ ...filters, group: null, grade: null })}
            />
            {GROUP_ORDER.map((key) =>
              // 公式は★2と★3をまとめているが、裏面から★数が読めたので分けて選べるようにする
              key === "basic" ? (
                [3, 2].map((n) => (
                  <Chip
                    key={`grade${n}`}
                    label={`★${n}`}
                    color={GROUP_STYLES.basic.color}
                    active={filters.grade === n}
                    onPress={() =>
                      onChange({ ...filters, group: null, grade: filters.grade === n ? null : n })
                    }
                  />
                ))
              ) : (
                <Chip
                  key={key}
                  label={GROUP_STYLES[key].label}
                  color={GROUP_STYLES[key].color}
                  active={filters.group === key}
                  onPress={() =>
                    onChange({ ...filters, grade: null, group: filters.group === key ? null : key })
                  }
                />
              ),
            )}
          </Row>

          <Row title="タイプ">
            <Chip label="ぜんぶ" active={filters.type === null} onPress={() => set("type", null)} />
            {TYPE_ORDER.map((t) => (
              <Chip
                key={t}
                label={t}
                icon={t}
                color={TYPE_COLORS[t]}
                active={filters.type === t}
                onPress={() => toggle("type", t)}
              />
            ))}
          </Row>

          <Row title="おおきさ">
            {CARD_SIZES.map(({ key, label }) => (
              <Chip
                key={key}
                label={label}
                color="#7B3FBF"
                active={cardSize === key}
                onPress={() => onCardSizeChange(key)}
              />
            ))}
          </Row>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    paddingTop: 10,
    paddingBottom: 4,
    backgroundColor: "#fff",
    borderBottomWidth: 1,
    borderBottomColor: "#E2E8F0",
  },
  searchRow: { flexDirection: "row", alignItems: "center", marginHorizontal: 12, marginBottom: 8 },
  search: {
    flex: 1,
    backgroundColor: "#F2F6FB",
    borderRadius: 12,
    paddingLeft: 14,
    paddingRight: 52,
    paddingVertical: 12,
    fontSize: 16,
    color: "#1A365D",
  },
  clearButton: {
    position: "absolute",
    right: 2,
    width: 46,
    height: 46,
    justifyContent: "center",
    alignItems: "center",
  },
  clearText: { fontSize: 18, fontWeight: "900", color: "#7C8DA3" },

  headRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingHorizontal: 12,
    marginBottom: 6,
  },
  headLabel: { flex: 1, fontSize: 15, fontWeight: "900", color: "#1A365D" },
  headButton: {
    paddingHorizontal: 16,
    minHeight: 44,
    justifyContent: "center",
    borderRadius: 18,
    borderWidth: 2,
    borderColor: "#2B6CB0",
  },
  headButtonOpen: { backgroundColor: "#2B6CB0" },
  headButtonText: { fontSize: 13, fontWeight: "800", color: "#2B6CB0" },
  headButtonTextOpen: { color: "#fff" },

  row: { flexDirection: "row", alignItems: "center", marginBottom: 6 },
  // 折り返す行は見出しを上ぞろえにしないと、まん中に浮いて読みにくい
  rowWrap: { alignItems: "flex-start" },
  rowTitle: {
    width: 78,
    // よこスクロール行の中身に押されて見出しが縮み、「タ...」と切れてしまうのを防ぐ
    flexShrink: 0,
    paddingLeft: 12,
    paddingRight: 4,
    fontSize: 12,
    fontWeight: "800",
    color: "#7C8DA3",
  },
  // 「もちもの」「おおきさ」の4文字が入るぎりぎりまで詰める
  rowTitleNarrow: { width: 66, paddingLeft: 8 },
  rowTitleWrap: { paddingTop: 8 },
  rowScroll: { paddingRight: 12, gap: 6 },
  rowWrapped: {
    flex: 1,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
    paddingRight: 12,
  },
  chip: {
    borderWidth: 2,
    borderRadius: 18,
    paddingHorizontal: 14,
    // ゆびで押すので、たかさ44を確保する
    paddingVertical: 10,
    minHeight: 44,
    justifyContent: "center",
    backgroundColor: "#fff",
  },
  chipWithIcon: { flexDirection: "row", alignItems: "center", gap: 5, paddingLeft: 8 },
  chipText: { fontSize: 13, fontWeight: "800" },
});
