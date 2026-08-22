import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Animated,
  Easing,
  FlatList,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  StyleSheet,
  Text,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { EMPTY_FILTERS, FilterBar, type Filters } from "@/components/FilterBar";
import { PickCard } from "@/components/PickCard";
import { PrefetchBar } from "@/components/PrefetchBar";
import { setBrowseOrder } from "@/lib/browseOrder";
import { loadConfirmedPickIds } from "@/lib/circle";
import { useCollection } from "@/lib/collection";
import {
  type CardSize,
  DEFAULT_CARD_SIZE,
  cardTarget,
  loadCardSize,
  loadSetFilter,
  saveCardSize,
  saveSetFilter,
} from "@/lib/filterPrefs";
import { ALL_PICKS } from "@/lib/picks";
import { TIGHT_CARD_WIDTH, useNarrow } from "@/lib/responsive";
import { matchesQuery } from "@/lib/search";

export default function DexScreen() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const narrow = useNarrow();
  const { collection, adjust, ready } = useCollection();
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [registerMode, setRegisterMode] = useState(false);
  const [cardSize, setCardSize] = useState<CardSize>(DEFAULT_CARD_SIZE);
  const [confirmedPickIds, setConfirmedPickIds] = useState<Set<string>>(new Set());

  // トレーナー画面での同期をはさんで戻ってきたときに、バッジが最新になるようにする
  useFocusEffect(
    useCallback(() => {
      loadConfirmedPickIds().then(setConfirmedPickIds);
    }, []),
  );

  // 前に見ていた だん と カードの大きさ を復元する。ほかの条件は毎回まっさらでよい
  useEffect(() => {
    loadSetFilter().then((sets) => {
      if (sets.length > 0) setFilters((prev) => ({ ...prev, sets }));
    });
    loadCardSize().then(setCardSize);
  }, []);

  const changeCardSize = useCallback((size: CardSize) => {
    setCardSize(size);
    saveCardSize(size);
  }, []);

  const changeFilters = useCallback(
    (next: Filters) => {
      if (next.sets !== filters.sets) saveSetFilter(next.sets);
      setFilters(next);
    },
    [filters.sets],
  );

  /**
   * さがす欄やしぼりこみが、よこ向きだと画面の3分の1を占めてしまう。
   * 下にスクロールしているあいだは上へ逃がして、ピックが見える面積を広げる。
   * グリッドの位置がずれないよう、ヘッダーは重ねて置き、
   * リスト側は同じぶんだけ余白をとっておく。
   */
  const insets = useSafeAreaInsets();
  const [chromeHeight, setChromeHeight] = useState(0);
  const slide = useRef(new Animated.Value(0)).current;
  const lastY = useRef(0);
  const scrollY = useRef(0);
  /** いま逃がしてあるかどうか。変わったときだけアニメを動かす */
  const hidden = useRef(false);
  /**
   * 覚えておいた場所へ戻すときの行き先。戻している最中だけ数が入る。
   * ただし FlatList は描画ずみのぶんしか高さを持っていないので、遠くへは一度で飛べない。
   * 中身が伸びるたびに近づけ直す（onContentSizeChange から呼ぶ）。
   */
  const target = useRef<number | null>(null);

  const onScroll = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      const y = e.nativeEvent.contentOffset.y;
      scrollY.current = y;
      const dy = y - lastY.current;
      lastY.current = y;

      // 自分でスクロールし直している最中（まわしたとき・カードの大きさを変えたとき）は
      // 動かさない。ここで逃がしてしまうと、しぼりこみが消えて大きさを続けて選べない
      if (target.current !== null) return;

      // 上のほうに居るあいだは、かならず出しておく。
      // 小さな揺れで出たり消えたりしないよう、うごきは12pxから見る
      let next = hidden.current;
      if (y <= chromeHeight) next = false;
      else if (dy > 12) next = true;
      else if (dy < -12) next = false;

      // 同じ向きのスクロールで何度もアニメを開始し直すと、そのたびに
      // 途中から動きはじめてカクついて見える。変わったときだけ動かす
      if (next === hidden.current) return;
      hidden.current = next;
      Animated.timing(slide, {
        toValue: next ? -chromeHeight : 0,
        duration: 200,
        easing: Easing.out(Easing.quad),
        // web には native driver が無いので、true にしても警告が出るだけ
        useNativeDriver: false,
      }).start();
    },
    [chromeHeight, slide],
  );

  /**
   * まわしたときに、いま見ていたあたりへ戻す。
   * 行の高さはカードの幅で決まるので、まわすと変わる。
   * そこで「先頭に見えていたのが何枚目のピックか」を覚えておいて、
   * 新しい行の高さがわかってから、その行までスクロールし直す。
   */
  const listRef = useRef<FlatList<(typeof ALL_PICKS)[number][]>>(null);
  // 行の高さは state で持つ。まわしたあと「新しい高さが出そろってから」戻したいので、
  // ref だと変化に気づけない
  const [rowHeight, setRowHeight] = useState(0);
  // 「どのピックに戻すか」と「そのとき行が何pxだったか」。
  // 高さが変わるまで待たないと、ふるい高さで計算して見当ちがいの場所に飛ぶ
  const [pending, setPending] = useState<{ index: number; fromHeight: number } | null>(null);
  const prevColumns = useRef(0);

  // 大きさを変えると列数が変わる。まわしたときと同じ仕組みで、
  // 見ていたあたりへ戻る（下の prevColumns のところ）
  //
  // カード1枚に使う幅（target）は iPad で見て決めた値なので、スマートフォンだと
  // どの大きさを選んでも2列にしかならず、「おおきさ」を押しても何も変わらない。
  // せまい画面は手に持って近くで見るぶん小さくても見分けられるので、目安を縮めて
  // 4列〜2列を選べるようにする。
  const widthPerCard = cardTarget(cardSize) * (narrow ? 0.62 : 1);
  // よこ向きのスマートフォンはノッチのぶん左右が使えない。
  // 列数もカードの幅も、実際に置ける幅から出す
  const gridWidth = width - insets.left - insets.right;
  const columns = Math.max(2, Math.floor(gridWidth / widthPerCard));
  // グリッドの左右にも padding:6 があるので、そのぶんを引かないと右はしが切れる
  const cardWidth = (gridWidth - 12) / columns - 12;

  const visible = useMemo(
    () =>
      ALL_PICKS.filter((p) => {
        if (filters.sets.length > 0 && !filters.sets.includes(p.set)) return false;
        if (filters.group !== null && p.group !== filters.group) return false;
        if (filters.grade !== null && p.grade !== filters.grade) return false;
        if (filters.type !== null && !p.types.includes(filters.type)) return false;
        if (!matchesQuery(p, filters.query)) return false;
        return true;
      }),
    [filters],
  );

  // 所持状況は collection に依存するため、フィルタ結果とは別に絞り込む
  const liveRows = useMemo(() => {
    if (filters.owned === "all") return visible;
    const wantOwned = filters.owned === "owned";
    return visible.filter((p) => (collection[p.id] ?? 0) > 0 === wantOwned);
  }, [visible, filters.owned, collection]);

  /**
   * 登録中に「もってない」でしぼっていると、＋を押したカードがその場で消えて
   * うしろが1つずつ前に詰まる。おなじ場所を続けて押すと別のポケモンが登録されてしまうので、
   * 登録モードのあいだは並びを止めておく。
   * しぼりこみを変えたときだけ取り直す（所持数が変わっても取り直さない）。
   */
  const [frozenIds, setFrozenIds] = useState<Set<string> | null>(null);
  const liveRowsRef = useRef(liveRows);
  useEffect(() => {
    liveRowsRef.current = liveRows;
  });
  useEffect(() => {
    setFrozenIds(registerMode ? new Set(liveRowsRef.current.map((p) => p.id)) : null);
  }, [registerMode, visible, filters.owned]);

  const rows = useMemo(() => {
    if (!registerMode || frozenIds === null) return liveRows;
    return visible.filter((p) => frozenIds.has(p.id));
  }, [registerMode, frozenIds, liveRows, visible]);

  const ownedInView = useMemo(
    () => visible.filter((p) => (collection[p.id] ?? 0) > 0).length,
    [visible, collection],
  );
  const percent = visible.length ? Math.round((ownedInView / visible.length) * 100) : 0;

  // じょうほう画面で よこにスワイプしたとき、ここで見えている並びのままめくれるようにする
  useEffect(() => {
    setBrowseOrder(rows.map((p) => p.id));
  }, [rows]);

  // PickCard は memo なので、毎回あたらしい関数を渡すと全カードが再描画されてしまう
  const openPick = useCallback((id: string) => router.push(`/pick/${id}`), [router]);
  const addOne = useCallback((id: string) => adjust(id, 1), [adjust]);

  /**
   * FlatList の numColumns は途中で変えられず、変えるには key で作り直すしかない。
   * それだとタブレットをまわすたびにスクロールが先頭に戻ってしまうので、
   * 1行ぶんを1つの item にまとめて、numColumns を使わない形にしている。
   */
  const gridRows = useMemo(() => {
    const out: (typeof ALL_PICKS)[] = [];
    for (let i = 0; i < rows.length; i += columns) out.push(rows.slice(i, i + columns));
    return out;
  }, [rows, columns]);

  useEffect(() => {
    if (prevColumns.current === 0 || prevColumns.current === columns) {
      prevColumns.current = columns;
      return;
    }
    const top = Math.max(0, scrollY.current - chromeHeight - 6);
    const firstRow = rowHeight > 0 ? Math.floor(top / rowHeight) : 0;
    setPending({ index: firstRow * prevColumns.current, fromHeight: rowHeight });
    prevColumns.current = columns;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [columns]);

  const restore = useCallback(() => {
    if (target.current === null) return;
    listRef.current?.scrollToOffset({ offset: target.current, animated: false });
    // 目的の位置まで来ていたら終わり
    if (Math.abs(scrollY.current - target.current) < 4) target.current = null;
  }, []);

  useEffect(() => {
    if (pending === null || rowHeight === 0 || rowHeight === pending.fromHeight) return;
    const row = Math.floor(pending.index / columns);
    // いちばん上に居たなら上のままにする。ここで chromeHeight ぶん動かすと、
    // 見た目が跳ねたうえに、しぼりこみが上へ逃げてしまう
    target.current = row === 0 ? 0 : row * rowHeight + chromeHeight + 6;
    setPending(null);
    restore();
  }, [pending, rowHeight, columns, chromeHeight, restore]);

  const renderItem = useCallback(
    ({ item }: { item: (typeof ALL_PICKS)[number][] }) => (
      <View
        style={styles.gridRow}
        onLayout={(e) => {
          const h = e.nativeEvent.layout.height;
          setRowHeight((prev) => (Math.abs(prev - h) > 1 ? h : prev));
        }}
      >
        {item.map((pick) => (
          <PickCard
            key={pick.id}
            pick={pick}
            count={collection[pick.id] ?? 0}
            width={cardWidth}
            onPress={registerMode ? addOne : openPick}
            onAdjust={registerMode ? adjust : undefined}
            circleConfirmed={confirmedPickIds.has(pick.id)}
          />
        ))}
      </View>
    ),
    [collection, cardWidth, registerMode, addOne, openPick, adjust, confirmedPickIds],
  );

  if (!ready) {
    return (
      <View style={styles.loading}>
        <Text style={styles.loadingText}>よみこみちゅう…</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Animated.View
        style={[
          styles.chrome,
          {
            paddingTop: insets.top,
            // よこ向きのスマートフォンは、ノッチの下に文字が隠れる
            paddingLeft: insets.left,
            paddingRight: insets.right,
            transform: [{ translateY: slide }],
          },
        ]}
        onLayout={(e) => setChromeHeight(e.nativeEvent.layout.height)}
      >
      <FilterBar
        filters={filters}
        onChange={changeFilters}
        compact={registerMode}
        cardSize={cardSize}
        onCardSizeChange={changeCardSize}
      />

      {/* せまい画面では5つが1行に入らないので、
          「どれだけ あつめたか＋とうろく」と「ほかの画面へ」の2行に分ける */}
      <View style={[styles.statusBar, narrow && styles.statusBarNarrow]}>
        <View style={[styles.statusLine, narrow && styles.statusLineNarrow]}>
          <View style={styles.progressWrap}>
            {/* 958枚だと%はなかなか動かないので、あつめた枚数のほうを主役にする */}
            <Text style={styles.progressText}>
              <Text style={styles.progressBig}>{ownedInView}</Text>
              {/* せまいと「ぜんぶで…」まで入れると2行になるので、短い言い方にする */}
              {narrow ? (
                <Text> / {visible.length} こ あつめたよ！</Text>
              ) : (
                <Text> こ あつめたよ！　（ぜんぶで {visible.length} こ）</Text>
              )}
            </Text>
            <View style={styles.progressTrack}>
              {ownedInView > 0 && (
                <View style={[styles.progressFill, { width: `${Math.max(2, percent)}%` }]} />
              )}
            </View>
          </View>

          <TouchableOpacity
            onPress={() => setRegisterMode((v) => !v)}
            activeOpacity={0.8}
            style={[
              styles.modeButton,
              narrow && styles.modeButtonNarrow,
              registerMode && styles.modeButtonOn,
            ]}
          >
            {/* 状態ではなく「押したらどうなるか」を出す。ONだと何が起きるか分かりにくい */}
            <Text style={[styles.modeText, registerMode && styles.modeTextOn]} numberOfLines={1}>
              {registerMode ? "とうろく おわり" : "とうろくする"}
            </Text>
          </TouchableOpacity>
        </View>

        <View style={styles.navLine}>
          <TouchableOpacity
            onPress={() => router.push("/party")}
            activeOpacity={0.8}
            style={[styles.summaryButton, styles.partyButton, narrow && styles.summaryButtonNarrow]}
          >
            <Text style={styles.summaryText} numberOfLines={1}>
              パーティー
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            onPress={() => router.push("/trainers")}
            activeOpacity={0.8}
            style={[
              styles.summaryButton,
              styles.trainerButton,
              narrow && styles.summaryButtonNarrow,
            ]}
          >
            <Text style={styles.summaryText} numberOfLines={1}>
              トレーナー
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            onPress={() => router.push("/summary")}
            activeOpacity={0.8}
            style={[styles.summaryButton, narrow && styles.summaryButtonNarrow]}
          >
            <Text style={styles.summaryText} numberOfLines={1}>
              きろく
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      <PrefetchBar />

      {registerMode && (
        <Text style={styles.modeHint}>
          {/* カードが小さいと ＋ を置く場所が無いので、絵をタップして数える（PickCard） */}
          {cardWidth < TIGHT_CARD_WIDTH
            ? "え を タップ すると 1まい ふえるよ。まちがえたら − を おそう。"
            : "え を タップ するか ＋ を おすと 1まい ふえるよ。まちがえたら − を おそう。"}
        </Text>
      )}
      </Animated.View>

      <FlatList
        ref={listRef}
        data={gridRows}
        keyExtractor={(row) => row[0].id}
        contentContainerStyle={[
          styles.grid,
          {
            paddingTop: chromeHeight + 6,
            paddingLeft: insets.left + 6,
            paddingRight: insets.right + 6,
            // ホームバーの上に最後の行がかぶらないようにする
            paddingBottom: insets.bottom + 32,
          },
        ]}
        onScroll={onScroll}
        scrollEventThrottle={16}
        onContentSizeChange={restore}
        initialNumToRender={24}
        windowSize={7}
        removeClippedSubviews
        ListEmptyComponent={
          <View style={styles.emptyBox}>
            <Text style={styles.empty}>そのじょうけんの ピックは ないみたい</Text>
            <TouchableOpacity
              onPress={() => changeFilters(EMPTY_FILTERS)}
              activeOpacity={0.8}
              style={styles.emptyButton}
              accessibilityRole="button"
            >
              <Text style={styles.emptyButtonText}>ぜんぶ みる</Text>
            </TouchableOpacity>
          </View>
        }
        renderItem={renderItem}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  chrome: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    zIndex: 2,
    backgroundColor: "#fff",
  },
  loading: { flex: 1, justifyContent: "center", alignItems: "center" },
  loadingText: { fontSize: 18, color: "#7C8DA3", fontWeight: "700" },
  statusBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: "#fff",
    borderBottomWidth: 1,
    borderBottomColor: "#E2E8F0",
  },
  // せまいときは たて に積む。1行めが のこりの幅をとらないよう flex を切る
  statusBarNarrow: { flexDirection: "column", alignItems: "stretch", gap: 8 },
  statusLine: { flex: 1, flexDirection: "row", alignItems: "center", gap: 10 },
  statusLineNarrow: { flex: 0 },
  navLine: { flexDirection: "row", alignItems: "center", gap: 10 },
  progressWrap: { flex: 1 },
  progressText: { fontSize: 13, fontWeight: "800", color: "#1A365D", marginBottom: 4 },
  progressBig: { fontSize: 20, fontWeight: "900", color: "#2F855A" },
  progressTrack: { height: 10, borderRadius: 5, backgroundColor: "#E2E8F0", overflow: "hidden" },
  progressFill: { height: "100%", backgroundColor: "#2F855A", minWidth: 6 },
  modeButton: {
    borderWidth: 2,
    borderColor: "#C05621",
    borderRadius: 18,
    paddingHorizontal: 12,
    // 文字数が変わっても右のボタンがずれないよう、はばを固定する
    minWidth: 150,
    minHeight: 44,
    justifyContent: "center",
    alignItems: "center",
  },
  // せまいときは、あつめた数のほうに幅をゆずる。
  // ここも「とうろく おわり」が入る幅で固定して、押すたびに横がのび縮みしないようにする
  modeButtonNarrow: { minWidth: 124, paddingHorizontal: 8 },
  modeButtonOn: { backgroundColor: "#C05621" },
  modeText: { color: "#C05621", fontWeight: "800", fontSize: 13 },
  modeTextOn: { color: "#fff" },
  summaryButton: {
    backgroundColor: "#2B6CB0",
    borderRadius: 18,
    paddingHorizontal: 14,
    minHeight: 44,
    justifyContent: "center",
    alignItems: "center",
  },
  // せまいときは3つで1行を分けあう。幅がそろっていないと押しまちがえやすい
  summaryButtonNarrow: { flex: 1, paddingHorizontal: 6 },
  partyButton: { backgroundColor: "#7B3FBF" },
  trainerButton: { backgroundColor: "#0F9B8E" },
  summaryText: { color: "#fff", fontWeight: "800", fontSize: 13 },
  modeHint: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: "#FFF5EC",
    color: "#9C4221",
    fontSize: 12,
    fontWeight: "700",
  },
  grid: { padding: 6, paddingBottom: 32 },
  gridRow: { flexDirection: "row" },
  emptyBox: { alignItems: "center", marginTop: 40, gap: 16 },
  empty: { textAlign: "center", color: "#7C8DA3", fontSize: 16, fontWeight: "700" },
  emptyButton: {
    backgroundColor: "#2B6CB0",
    borderRadius: 20,
    paddingHorizontal: 28,
    paddingVertical: 14,
  },
  emptyButtonText: { color: "#fff", fontSize: 16, fontWeight: "800" },
});
