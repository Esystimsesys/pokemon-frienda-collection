import { CameraView, useCameraPermissions } from "expo-camera";
import { useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { extractCircleToken, saveConnection } from "@/lib/circle";

export default function ScanScreen() {
  const router = useRouter();
  const [permission, requestPermission] = useCameraPermissions();
  const [handled, setHandled] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleScanned = useCallback(
    ({ data }: { data: string }) => {
      if (handled) return;
      const token = extractCircleToken(data);
      if (!token) {
        setError("トレーナーピックの QRコードじゃ ないみたい。もういちど ためしてね。");
        return;
      }
      setHandled(true);
      setError(null);
      saveConnection({
        token,
        trainerName: "",
        trainerPickId: "",
        avatarType: 0,
        connectedAt: Date.now(),
        lastSyncedAt: null,
      }).then(() => {
        router.replace("/trainers");
      });
    },
    [handled, router],
  );

  if (!permission) {
    return <View style={styles.center} />;
  }

  if (!permission.granted) {
    return (
      <View style={styles.center}>
        <Text style={styles.message}>
          QRコードを よみとるには、カメラを つかう ゆるしが いるよ。
        </Text>
        <TouchableOpacity onPress={requestPermission} activeOpacity={0.8} style={styles.button}>
          <Text style={styles.buttonText}>カメラを ゆるす</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView
        style={StyleSheet.absoluteFill}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
        onBarcodeScanned={handled ? undefined : handleScanned}
      />
      <View style={styles.overlay} pointerEvents="none">
        <View style={styles.frame} />
      </View>
      <View style={styles.hint}>
        <Text style={styles.hintText}>
          トレーナーピックの うらに ある QRコードを、わくの なかに いれてね。
        </Text>
        {error && <Text style={styles.errorText}>{error}</Text>}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000" },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    gap: 16,
    backgroundColor: "#F2F6FB",
  },
  message: { fontSize: 15, fontWeight: "700", color: "#1A365D", textAlign: "center", lineHeight: 22 },
  button: {
    backgroundColor: "#2B6CB0",
    borderRadius: 16,
    paddingVertical: 14,
    paddingHorizontal: 28,
  },
  buttonText: { color: "#fff", fontSize: 15, fontWeight: "800" },
  overlay: { ...StyleSheet.absoluteFill, alignItems: "center", justifyContent: "center" },
  frame: {
    width: "70%",
    aspectRatio: 1,
    borderWidth: 3,
    borderColor: "#fff",
    borderRadius: 16,
  },
  hint: {
    position: "absolute",
    bottom: 40,
    left: 20,
    right: 20,
    backgroundColor: "rgba(0,0,0,0.6)",
    borderRadius: 14,
    padding: 14,
    gap: 8,
  },
  hintText: { color: "#fff", fontSize: 14, fontWeight: "700", textAlign: "center", lineHeight: 20 },
  errorText: { color: "#FEB2B2", fontSize: 13, fontWeight: "800", textAlign: "center" },
});
