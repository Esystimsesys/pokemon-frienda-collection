import { Image } from "expo-image";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { TRAINERS_BY_SET } from "@/lib/trainers";
import type { Trainer } from "@/types";

function TrainerCard({ trainer }: { trainer: Trainer }) {
  return (
    <View style={styles.card}>
      {/* 公式の絵に名前が入っているので、下に同じ名前を出さずに読み上げ用のラベルにする */}
      <Image
        source={trainer.image}
        style={styles.portrait}
        contentFit="contain"
        transition={120}
        cachePolicy="disk"
        recyclingKey={trainer.id}
        alt={trainer.name}
        accessibilityLabel={trainer.name}
      />

      <View style={styles.rewardBox}>
        <Text style={styles.rewardTitle}>かつと もらえるよ</Text>
        <Text style={styles.rewardName}>{trainer.reward}</Text>
        <View style={styles.rewardImages}>
          {trainer.rewardImages.map((uri) => (
            <Image
              key={uri}
              source={uri}
              style={styles.rewardImage}
              contentFit="contain"
              transition={120}
              cachePolicy="disk"
              recyclingKey={uri}
            />
          ))}
        </View>
      </View>
    </View>
  );
}

export default function TrainersScreen() {
  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
      <Text style={styles.lead}>
        だんごとに たたかう トレーナーだよ。かつと きせかえアイテムが もらえる！
      </Text>

      {TRAINERS_BY_SET.map(({ key, label, trainers }) => (
        <View key={key} style={styles.group}>
          <Text style={styles.groupTitle}>{label}</Text>
          <View style={styles.row}>
            {trainers.map((t) => (
              <TrainerCard key={t.id} trainer={t} />
            ))}
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1 },
  content: { padding: 12, paddingBottom: 40, gap: 14 },
  lead: { fontSize: 13, fontWeight: "700", color: "#5A6C82", lineHeight: 20 },

  group: { gap: 8 },
  groupTitle: { fontSize: 17, fontWeight: "900", color: "#1A365D" },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 10 },

  card: {
    flexGrow: 1,
    flexBasis: 220,
    maxWidth: 340,
    backgroundColor: "#fff",
    borderRadius: 14,
    borderWidth: 3,
    borderColor: "#2B6CB0",
    padding: 12,
    alignItems: "center",
    boxShadow: "0px 2px 6px rgba(26, 54, 93, 0.07)",
    elevation: 2,
  },
  portrait: { width: "100%", aspectRatio: 290 / 298 },

  rewardBox: {
    marginTop: 10,
    width: "100%",
    borderRadius: 12,
    backgroundColor: "#FFF5EC",
    padding: 10,
    alignItems: "center",
  },
  rewardTitle: { fontSize: 12, fontWeight: "800", color: "#9C4221" },
  rewardName: {
    fontSize: 15,
    fontWeight: "900",
    color: "#C05621",
    textAlign: "center",
    marginTop: 2,
  },
  // きせかえの見本は 640x1280 のたて長。おとこのこ・おんなのこの2まいが入っている
  rewardImages: { flexDirection: "row", gap: 8, marginTop: 8, alignSelf: "stretch" },
  rewardImage: { flex: 1, aspectRatio: 640 / 1280 },
});
