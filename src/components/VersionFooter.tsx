import { StyleSheet, Text, View } from "react-native";

import { BUILD_SHA, BUILD_TIME } from "@/lib/version";

function formatBuildTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(
    d.getMinutes(),
  )}`;
}

/** デプロイ後にキャッシュが切りかわっているかを確認するための、目立たない足あと */
export function VersionFooter() {
  return (
    <View style={styles.wrap}>
      <Text style={styles.text}>
        バージョン: {BUILD_SHA ? BUILD_SHA.slice(0, 7) : "ローカル開発版"}
        {BUILD_TIME ? `（${formatBuildTime(BUILD_TIME)} ビルド）` : ""}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: "center", paddingVertical: 6 },
  text: { fontSize: 11, fontWeight: "600", color: "#B8C2CE" },
});
