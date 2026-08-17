import { Modal, Pressable, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { PICK_ASPECT, PickImage } from "@/components/PickImage";

type Props = {
  visible: boolean;
  uri: string;
  side: "front" | "back";
  name: string;
  onFlip: () => void;
  onClose: () => void;
};

/**
 * 券面を画面いっぱいに出す。
 *
 * このアプリはピンチ拡大を切ってある（子供が誤って拡大して戻せなくなるため。
 * public/index.html の viewport を参照）ので、券面を大きく見る手段がこれしかない。
 * 公式の画像は片面 1016x750 なので、iPad なら画面に合わせるだけでほぼ等倍になる。
 *
 * 絵のどこを押しても閉じる。まちがえて開いてしまった子供が、
 * ボタンを探さずに戻れるようにするため。
 */
export function PickZoom({ visible, uri, side, name, onFlip, onClose }: Props) {
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();

  // 「うらを みる」ボタンと上下の余白のぶんを残して、はいる大きさを決める
  const room = height - insets.top - insets.bottom - 120;
  const imageWidth = Math.min(width - 24, room * PICK_ASPECT);

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} accessibilityLabel="とじる">
        <Pressable
          onPress={onClose}
          style={[styles.closeButton, { top: insets.top + 12 }]}
          accessibilityRole="button"
          accessibilityLabel="とじる"
        >
          <Text style={styles.closeText}>✕</Text>
        </Pressable>

        <PickImage uri={uri} side={side} width={imageWidth} style={styles.image} />

        <Pressable
          onPress={onFlip}
          style={styles.flipButton}
          accessibilityRole="button"
          accessibilityLabel={`${name} の ${side === "front" ? "うら" : "おもて"} を みる`}
        >
          <Text style={styles.flipText}>{side === "front" ? "うらを みる" : "おもてを みる"}</Text>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(12, 20, 32, 0.94)",
    justifyContent: "center",
    alignItems: "center",
    gap: 16,
  },
  image: { borderRadius: 10 },
  closeButton: {
    position: "absolute",
    right: 12,
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: "rgba(255,255,255,0.16)",
    justifyContent: "center",
    alignItems: "center",
  },
  closeText: { color: "#fff", fontSize: 26, fontWeight: "900", lineHeight: 30 },
  flipButton: {
    backgroundColor: "#fff",
    borderRadius: 24,
    paddingHorizontal: 28,
    paddingVertical: 13,
  },
  flipText: { color: "#1A365D", fontSize: 17, fontWeight: "900" },
});
