import { useCallback, useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";

import {
  BACKUP_SUPPORTED,
  exportCollection,
  parseBackup,
  readBackupFile,
} from "@/lib/backup";
import { useCollection } from "@/lib/collection";

type Pending = { picks: Record<string, number>; loaded: number; skipped: number };

export function BackupCard() {
  const { collection, replaceAll, ownedCount } = useCollection();
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);

  const save = useCallback(async () => {
    setPending(null);
    const result = await exportCollection(collection);
    if (!result.ok) {
      setMessage("かきだしを やめたよ。");
      return;
    }
    setMessage("かきだしたよ。おうちの ひとに たのんで、なくさない ところに おいてもらおう。");
  }, [collection]);

  const load = useCallback(async () => {
    setMessage(null);
    setPending(null);
    const text = await readBackupFile();
    if (text === null) return;

    const parsed = parseBackup(text);
    if (!parsed.ok) {
      setMessage(parsed.reason);
      return;
    }
    setPending({ picks: parsed.picks, loaded: parsed.loaded, skipped: parsed.skipped });
  }, []);

  const confirmLoad = useCallback(() => {
    if (!pending) return;
    replaceAll(pending.picks);
    setMessage(
      pending.skipped > 0
        ? `${pending.loaded}こ よみこんだよ。わからない ピックが ${pending.skipped}こ あったので とばしたよ。`
        : `${pending.loaded}こ よみこんだよ。`,
    );
    setPending(null);
  }, [pending, replaceAll]);

  if (!BACKUP_SUPPORTED) return null;

  return (
    <View style={styles.card}>
      <Text style={styles.title}>きろくを ファイルに ほぞん</Text>
      <Text style={styles.body}>
        きろくは この タブレットの なかだけに あるよ。ときどき かきだして おくと、
        きえてしまっても もどせるよ。
      </Text>

      <View style={styles.buttonRow}>
        <TouchableOpacity onPress={save} activeOpacity={0.8} style={styles.button}>
          <Text style={styles.buttonText}>かきだす</Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={load}
          activeOpacity={0.8}
          style={[styles.button, styles.buttonLoad]}
        >
          <Text style={styles.buttonText}>よみこむ</Text>
        </TouchableOpacity>
      </View>

      {pending && (
        <View style={styles.confirm}>
          <Text style={styles.confirmText}>
            よみこむと、いまの きろく（{ownedCount}こ）は きえて、ファイルの きろく（
            {pending.loaded}こ）に なるよ。いいかな？
          </Text>
          <View style={styles.buttonRow}>
            {/* 上の「よみこむ」と同じ文字にすると、2回おしただけで通ってしまう */}
            <TouchableOpacity
              onPress={confirmLoad}
              activeOpacity={0.8}
              style={[styles.button, styles.buttonDanger]}
            >
              <Text style={styles.buttonText}>ほんとうに いれかえる</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => setPending(null)}
              activeOpacity={0.8}
              style={[styles.button, styles.buttonCancel]}
            >
              <Text style={[styles.buttonText, styles.buttonCancelText]}>やめる</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {message && <Text style={styles.message}>{message}</Text>}
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
  buttonRow: { flexDirection: "row", gap: 10 },
  button: {
    flex: 1,
    backgroundColor: "#2B6CB0",
    borderRadius: 16,
    paddingVertical: 14,
    alignItems: "center",
  },
  buttonLoad: { backgroundColor: "#5A6C82" },
  buttonDanger: { backgroundColor: "#C05621" },
  buttonCancel: { backgroundColor: "#E2E8F0" },
  buttonText: { color: "#fff", fontSize: 15, fontWeight: "800" },
  buttonCancelText: { color: "#1A365D" },
  confirm: {
    marginTop: 12,
    padding: 12,
    borderRadius: 12,
    backgroundColor: "#FFF5EC",
    gap: 10,
  },
  confirmText: { fontSize: 13, fontWeight: "700", color: "#9C4221", lineHeight: 20 },
  message: { marginTop: 12, fontSize: 13, fontWeight: "700", color: "#2F855A", lineHeight: 20 },
});
