import { Stack, useRouter } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { StyleSheet, Text, TouchableOpacity } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { CollectionProvider } from "@/lib/collection";
import { startAutoPrefetch } from "@/lib/offline";

/**
 * ホーム画面アプリ（standalone）にはブラウザの戻るボタンが無い。
 * 履歴が無い状態で詳細などが開かれると expo-router は ← を出さないので、
 * かならず ずかん に帰れるボタンを自分で置く。
 *
 * 「1つ前の画面に戻る」ではなく、常に ずかん(index) へ直接とばす。
 * QRの読み取り成功後（スキャン画面 → トレーナー画面へ置きかえ）のように
 * 履歴が積み重なる経路だと、「1つ戻る」ではスキャン画面に戻ってしまい、
 * ボタンの表記（ずかんへ もどる）と実際の動きが食いちがっていたため。
 */
function BackToDex() {
  const router = useRouter();
  return (
    <TouchableOpacity
      onPress={() => router.replace("/")}
      activeOpacity={0.7}
      style={styles.back}
      accessibilityRole="button"
      accessibilityLabel="ずかんへ もどる"
    >
      <Text style={styles.backText}>← ずかん</Text>
    </TouchableOpacity>
  );
}

export default function RootLayout() {
  // 開いたら画像の先読みを始める。すんでいれば何もしない
  useEffect(() => {
    startAutoPrefetch();
  }, []);

  return (
    <SafeAreaProvider>
      <CollectionProvider>
        <StatusBar style="light" />
        <Stack
          screenOptions={{
            headerStyle: { backgroundColor: "#2B6CB0" },
            headerTintColor: "#fff",
            headerTitleStyle: { fontWeight: "800" },
            contentStyle: { backgroundColor: "#F2F6FB" },
          }}
        >
          {/* ずかんは画面のたてが命なので、タイトルバーを出さない。
              そのぶんの余白は index.tsx が safe area から自分でとる */}
          <Stack.Screen name="index" options={{ headerShown: false }} />
          <Stack.Screen
            name="summary"
            options={{ title: "あつめたきろく", headerLeft: () => <BackToDex /> }}
          />
          <Stack.Screen
            name="party"
            options={{ title: "おすすめパーティー", headerLeft: () => <BackToDex /> }}
          />
          <Stack.Screen
            name="trainers"
            options={{ title: "トレーナー", headerLeft: () => <BackToDex /> }}
          />
          <Stack.Screen
            name="scan"
            options={{ title: "QRを よみとる", headerLeft: () => <BackToDex /> }}
          />
          <Stack.Screen
            name="pick/[id]"
            options={{ title: "ピックのじょうほう", headerLeft: () => <BackToDex /> }}
          />
        </Stack>
      </CollectionProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  back: {
    minWidth: 44,
    minHeight: 44,
    paddingHorizontal: 8,
    justifyContent: "center",
  },
  backText: { color: "#fff", fontSize: 15, fontWeight: "800" },
});
