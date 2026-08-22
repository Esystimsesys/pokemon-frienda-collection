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

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
      <View style={styles.card}>
        <Text style={styles.trainerName}>
          {summary?.trainerName || connection.trainerName || "トレーナー"}
        </Text>

        {summary?.partner && (
          <Text style={styles.row}>パートナーポケモン: {summary.partner.name}</Text>
        )}
        {summary?.currentSeason && (
          <Text style={styles.row}>
            {summary.currentSeason.seasonName}の フレンダずかん: {summary.currentSeason.currentCount}/
            {summary.currentSeason.maxCount}
          </Text>
        )}
        {summary?.training && (
          <Text style={styles.row}>
            トレーニングちゅう: {summary.training.name}（EXパワー {summary.training.exPower}/
            {summary.training.exPowerThreshold}）
          </Text>
        )}
        {summary?.trainerBattle && (
          <Text style={styles.row}>
            トレーナーバトル: ハイスコア {summary.trainerBattle.highScore}
            {summary.trainerBattle.totalCount > 0 &&
              `（${summary.trainerBattle.clearedCount}/${summary.trainerBattle.totalCount} かち）`}
          </Text>
        )}
        {!!summary && (summary.medalCount > 0 || summary.charmCount > 0) && (
          <Text style={styles.row}>
            メダル {summary.medalCount}こ・チャーム {summary.charmCount}こ
          </Text>
        )}

        <Text style={styles.syncedAt}>{formatSyncedAt(connection.lastSyncedAt)}</Text>

        <TouchableOpacity
          onPress={startSync}
          activeOpacity={0.8}
          disabled={syncing || onCooldown}
          style={[styles.primaryButton, (syncing || onCooldown) && styles.buttonDisabled]}
        >
          <Text style={styles.primaryButtonText}>
            {syncing ? "どうき ちゅう…" : "どうき する"}
          </Text>
        </TouchableOpacity>
        {onCooldown && cooldownUntil && (
          <Text style={styles.webNotice}>
            きょうの どうきかいすうが いっぱいだよ。つぎは {formatClock(cooldownUntil)} いこうに
            ためしてね。
          </Text>
        )}

        {message && <Text style={styles.message}>{message}</Text>}
      </View>

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

  card: {
    backgroundColor: "#fff",
    borderRadius: 14,
    padding: 16,
    gap: 8,
    boxShadow: "0px 2px 6px rgba(26, 54, 93, 0.07)",
    elevation: 2,
  },
  trainerName: { fontSize: 20, fontWeight: "900", color: "#1A365D", marginBottom: 4 },
  row: { fontSize: 14, fontWeight: "700", color: "#334155", lineHeight: 21 },
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
  message: { marginTop: 4, fontSize: 13, fontWeight: "700", color: "#2F855A", lineHeight: 20 },

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
