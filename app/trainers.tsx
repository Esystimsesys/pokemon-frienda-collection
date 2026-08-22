import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { useCollection } from "@/lib/collection";
import {
  addConfirmedPickIds,
  clearConnection,
  fetchCircleSync,
  getSyncAvailability,
  loadConnection,
  loadSummary,
  parseHomeResponse,
  parsePickDexResponse,
  saveConnection,
  saveSummary,
} from "@/lib/circle";
import type { CircleConnection, CircleSummary } from "@/types";

function formatSyncedAt(ms: number | null): string {
  if (!ms) return "まだ どうき してないよ";
  const d = new Date(ms);
  return `さいごに どうきした とき: ${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(
    d.getMinutes(),
  ).padStart(2, "0")}`;
}

function formatClock(ms: number): string {
  const d = new Date(ms);
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function ProgressBar({ value, color }: { value: number; color: string }) {
  const pct = Math.min(100, Math.max(0, value * 100));
  return (
    <View style={styles.track}>
      <View style={[styles.fill, { width: `${pct}%` as `${number}%`, backgroundColor: color }]} />
    </View>
  );
}

export default function TrainersScreen() {
  const router = useRouter();
  const { applyCircleSync } = useCollection();
  const [connection, setConnection] = useState<CircleConnection | null | undefined>(undefined);
  const [summary, setSummary] = useState<CircleSummary | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [confirmingDisconnect, setConfirmingDisconnect] = useState(false);
  const [cooldownUntil, setCooldownUntil] = useState<number | null>(null);

  useEffect(() => {
    loadConnection().then(setConnection);
    loadSummary().then(setSummary);
  }, []);

  const refreshAvailability = useCallback(async () => {
    const availability = await getSyncAvailability();
    setCooldownUntil(availability.nextAvailableAt);
  }, []);

  useEffect(() => {
    refreshAvailability();
  }, [refreshAvailability]);

  const startSync = useCallback(async () => {
    if (!connection) return;
    setMessage(null);
    setSyncing(true);

    try {
      const { homeBody, pickDexBody } = await fetchCircleSync(connection.token);
      const home = parseHomeResponse(homeBody);
      const ownedPickIds = parsePickDexResponse(pickDexBody);

      if (!home) {
        setMessage("フレンダサークルの じょうほうが うまく よみとれなかったよ。");
        return;
      }

      // ピック図鑑に反映：手で登録していない分だけ、サークル側の一覧に合わせる
      applyCircleSync(ownedPickIds);
      // 「サークルで かくにんずみ」バッジ用。一度つくと、次の同期に出てこなくなっても消さない
      await addConfirmedPickIds(ownedPickIds);

      const nextSummary: CircleSummary = {
        trainerName: home.trainerName ?? "",
        avatarType: home.avatarType ?? 0,
        partner: home.partner ?? null,
        currentSeason: home.currentSeason ?? null,
        training: home.training ?? null,
        trainerBattle: home.trainerBattle ?? null,
        medalCount: home.medalCount ?? 0,
        charmCount: home.charmCount ?? 0,
        ownedPickIds,
        syncedAt: Date.now(),
      };
      await saveSummary(nextSummary);
      setSummary(nextSummary);

      const nextConnection: CircleConnection = {
        ...connection,
        trainerName: nextSummary.trainerName || connection.trainerName,
        lastSyncedAt: nextSummary.syncedAt,
      };
      await saveConnection(nextConnection);
      setConnection(nextConnection);

      setMessage(
        ownedPickIds.length > 0
          ? `どうき したよ！ ピック図鑑に ${ownedPickIds.length}こ はんえいしたよ。`
          : "どうき したよ！",
      );
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "どうきに しっぱいしたよ。");
    } finally {
      setSyncing(false);
      refreshAvailability();
    }
  }, [connection, applyCircleSync, refreshAvailability]);

  const disconnect = useCallback(async () => {
    await clearConnection();
    setConnection(null);
    setSummary(null);
    setMessage(null);
    setConfirmingDisconnect(false);
  }, []);

  if (connection === undefined) {
    return <View style={styles.scroll} />;
  }

  if (!connection) {
    return (
      <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
        <Text style={styles.lead}>
          トレーナーピックの うらの QRコードを よみこむと、フレンダサークルの トレーナー
          じょうほうと、あつめた ピックを この 図鑑に とりこめるよ。
        </Text>
        <TouchableOpacity
          onPress={() => router.push("/scan")}
          activeOpacity={0.8}
          style={styles.primaryButton}
        >
          <Text style={styles.primaryButtonText}>QRコードを よみとる</Text>
        </TouchableOpacity>
      </ScrollView>
    );
  }

  const onCooldown = cooldownUntil !== null && !syncing;
  const trainerName = summary?.trainerName || connection.trainerName || "トレーナー";

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
      <View style={styles.hero}>
        <View style={styles.heroAvatar}>
          <Text style={styles.heroAvatarText}>{trainerName.slice(0, 1)}</Text>
        </View>
        <Text style={styles.heroName}>{trainerName}</Text>
        <Text style={styles.heroSynced}>{formatSyncedAt(connection.lastSyncedAt)}</Text>
      </View>

      <View style={styles.grid}>
        {summary?.partner && (
          <View style={[styles.statCard, { borderColor: "#E0518E" }]}>
            <Text style={[styles.statLabel, { color: "#E0518E" }]}>パートナー</Text>
            <Text style={styles.statBig} numberOfLines={1}>
              {summary.partner.name}
            </Text>
            <Text style={styles.statCaption}>せいちょう ★{summary.partner.progress}</Text>
          </View>
        )}

        {summary?.currentSeason && summary.currentSeason.maxCount > 0 && (
          <View style={[styles.statCard, { borderColor: "#2B6CB0" }]}>
            <Text style={[styles.statLabel, { color: "#2B6CB0" }]} numberOfLines={1}>
              {summary.currentSeason.seasonName}の ずかん
            </Text>
            <View style={styles.progressRow}>
              <Text style={styles.progressNum}>{summary.currentSeason.currentCount}</Text>
              <Text style={styles.progressDen}> / {summary.currentSeason.maxCount}</Text>
            </View>
            <ProgressBar
              value={summary.currentSeason.currentCount / summary.currentSeason.maxCount}
              color="#2B6CB0"
            />
          </View>
        )}

        {summary?.training && (
          <View style={[styles.statCard, { borderColor: "#C8930B" }]}>
            <Text style={[styles.statLabel, { color: "#C8930B" }]}>トレーニングちゅう</Text>
            <Text style={styles.statBig} numberOfLines={1}>
              {summary.training.name}
            </Text>
            {summary.training.exPowerThreshold > 0 && (
              <>
                <View style={styles.progressRow}>
                  <Text style={styles.progressCaption}>EXパワー</Text>
                  <Text style={styles.progressNum}>{summary.training.exPower}</Text>
                  <Text style={styles.progressDen}> / {summary.training.exPowerThreshold}</Text>
                </View>
                <ProgressBar
                  value={summary.training.exPower / summary.training.exPowerThreshold}
                  color="#C8930B"
                />
              </>
            )}
          </View>
        )}

        {summary?.trainerBattle && (
          <View style={[styles.statCard, { borderColor: "#0F9B8E" }]}>
            <Text style={[styles.statLabel, { color: "#0F9B8E" }]}>トレーナーバトル</Text>
            <Text style={styles.statBig}>{summary.trainerBattle.highScore}</Text>
            <Text style={styles.statCaption}>ハイスコア</Text>
            {summary.trainerBattle.totalCount > 0 && (
              <View style={styles.dotsRow}>
                {Array.from({ length: summary.trainerBattle.totalCount }, (_, i) => (
                  <View
                    key={i}
                    style={[
                      styles.dot,
                      i < summary.trainerBattle!.clearedCount && styles.dotOn,
                    ]}
                  />
                ))}
              </View>
            )}
          </View>
        )}

        {!!summary && (summary.medalCount > 0 || summary.charmCount > 0) && (
          <View style={[styles.statCard, styles.statCardWide, { borderColor: "#E8720C" }]}>
            <View style={styles.medalCharmRow}>
              <View style={styles.medalCharmItem}>
                <Text style={styles.statBig}>{summary.medalCount}</Text>
                <Text style={[styles.statLabel, { color: "#E8720C" }]}>メダル</Text>
              </View>
              <View style={styles.medalCharmDivider} />
              <View style={styles.medalCharmItem}>
                <Text style={styles.statBig}>{summary.charmCount}</Text>
                <Text style={[styles.statLabel, { color: "#E8720C" }]}>チャーム</Text>
              </View>
            </View>
          </View>
        )}
      </View>

      <TouchableOpacity
        onPress={startSync}
        activeOpacity={0.8}
        disabled={syncing || onCooldown}
        style={[styles.primaryButton, (syncing || onCooldown) && styles.buttonDisabled]}
      >
        <Text style={styles.primaryButtonText}>{syncing ? "どうき ちゅう…" : "どうき する"}</Text>
      </TouchableOpacity>
      {onCooldown && cooldownUntil && (
        <Text style={styles.webNotice}>
          きょうの どうきかいすうが いっぱいだよ。つぎは {formatClock(cooldownUntil)} いこうに
          ためしてね。
        </Text>
      )}
      {message && <Text style={styles.message}>{message}</Text>}

      {confirmingDisconnect ? (
        <View style={styles.confirm}>
          <Text style={styles.confirmText}>
            つながりを きるよ。もういちど つなげたいときは、また QRコードを よみとってね。
          </Text>
          <View style={styles.buttonRow}>
            <TouchableOpacity
              onPress={disconnect}
              activeOpacity={0.8}
              style={[styles.smallButton, styles.buttonDanger]}
            >
              <Text style={styles.smallButtonText}>きる</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => setConfirmingDisconnect(false)}
              activeOpacity={0.8}
              style={[styles.smallButton, styles.buttonCancel]}
            >
              <Text style={[styles.smallButtonText, styles.buttonCancelText]}>やめる</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        <TouchableOpacity onPress={() => setConfirmingDisconnect(true)} activeOpacity={0.6}>
          <Text style={styles.disconnectLink}>べつの トレーナーピックに つなぎかえる</Text>
        </TouchableOpacity>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1 },
  content: { padding: 16, paddingBottom: 40, gap: 16 },
  lead: { fontSize: 14, fontWeight: "700", color: "#5A6C82", lineHeight: 22 },

  hero: {
    backgroundColor: "#2B6CB0",
    borderRadius: 18,
    padding: 20,
    alignItems: "center",
    gap: 4,
    boxShadow: "0px 3px 8px rgba(26, 54, 93, 0.18)",
    elevation: 3,
  },
  heroAvatar: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: "rgba(255,255,255,0.22)",
    borderWidth: 2,
    borderColor: "#fff",
    justifyContent: "center",
    alignItems: "center",
    marginBottom: 6,
  },
  heroAvatarText: { color: "#fff", fontSize: 24, fontWeight: "900" },
  heroName: { fontSize: 22, fontWeight: "900", color: "#fff" },
  heroSynced: { fontSize: 12, fontWeight: "600", color: "rgba(255,255,255,0.85)", marginTop: 2 },

  grid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  statCard: {
    flexGrow: 1,
    flexBasis: "45%",
    minWidth: 150,
    backgroundColor: "#fff",
    borderRadius: 14,
    borderWidth: 2,
    padding: 14,
    gap: 4,
    boxShadow: "0px 2px 6px rgba(26, 54, 93, 0.07)",
    elevation: 2,
  },
  statCardWide: { flexBasis: "100%" },
  statLabel: { fontSize: 12, fontWeight: "800" },
  statBig: { fontSize: 20, fontWeight: "900", color: "#1A365D" },
  statCaption: { fontSize: 12, fontWeight: "700", color: "#7C8DA3" },

  progressRow: { flexDirection: "row", alignItems: "baseline", marginTop: 2 },
  progressCaption: { fontSize: 12, fontWeight: "700", color: "#7C8DA3", marginRight: 6 },
  progressNum: { fontSize: 18, fontWeight: "900", color: "#1A365D" },
  progressDen: { fontSize: 13, fontWeight: "700", color: "#94A3B8" },
  track: { height: 8, borderRadius: 4, backgroundColor: "#E2E8F0", overflow: "hidden", marginTop: 6 },
  fill: { height: "100%", borderRadius: 4 },

  dotsRow: { flexDirection: "row", gap: 5, marginTop: 6 },
  dot: { width: 14, height: 14, borderRadius: 7, backgroundColor: "#E2E8F0" },
  dotOn: { backgroundColor: "#0F9B8E" },

  medalCharmRow: { flexDirection: "row", alignItems: "center" },
  medalCharmItem: { flex: 1, alignItems: "center", gap: 2 },
  medalCharmDivider: { width: 1, height: 36, backgroundColor: "#E2E8F0" },

  syncedAt: { fontSize: 12, fontWeight: "600", color: "#94A3B8", marginTop: 8, marginBottom: 4 },

  primaryButton: {
    backgroundColor: "#2B6CB0",
    borderRadius: 16,
    paddingVertical: 14,
    alignItems: "center",
  },
  buttonDisabled: { opacity: 0.6 },
  primaryButtonText: { color: "#fff", fontSize: 15, fontWeight: "800" },
  webNotice: { fontSize: 13, fontWeight: "700", color: "#9C4221" },
  message: { marginTop: -4, fontSize: 13, fontWeight: "700", color: "#2F855A", lineHeight: 20 },

  disconnectLink: {
    fontSize: 13,
    fontWeight: "700",
    color: "#94A3B8",
    textAlign: "center",
    textDecorationLine: "underline",
  },
  confirm: {
    padding: 12,
    borderRadius: 12,
    backgroundColor: "#FFF5EC",
    gap: 10,
  },
  confirmText: { fontSize: 13, fontWeight: "700", color: "#9C4221", lineHeight: 20 },
  buttonRow: { flexDirection: "row", gap: 10 },
  smallButton: { flex: 1, borderRadius: 16, paddingVertical: 12, alignItems: "center" },
  smallButtonText: { color: "#fff", fontSize: 14, fontWeight: "800" },
  buttonDanger: { backgroundColor: "#C05621" },
  buttonCancel: { backgroundColor: "#E2E8F0" },
  buttonCancelText: { color: "#1A365D" },
});
