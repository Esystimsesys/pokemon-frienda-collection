import { Image } from "expo-image";
import { StyleSheet, View, type StyleProp, type ViewStyle } from "react-native";

/**
 * 公式のピック画像は1枚の中に上下でおもて・うらが入っている（1016 x 1500）。
 * 片面だけを出したいので、半分の高さで切り抜いて、うらのときは上にずらす。
 */
const FULL_WIDTH = 1016;
const HALF_HEIGHT = 750;
export const PICK_ASPECT = FULL_WIDTH / HALF_HEIGHT;

type Props = {
  uri: string;
  side: "front" | "back";
  width: number;
  dim?: boolean;
  style?: StyleProp<ViewStyle>;
};

export function PickImage({ uri, side, width, dim, style }: Props) {
  const height = width / PICK_ASPECT;

  return (
    <View style={[{ width, height }, styles.clip, style]}>
      <Image
        source={uri}
        style={{
          width,
          height: height * 2,
          marginTop: side === "back" ? -height : 0,
          opacity: dim ? 0.45 : 1,
        }}
        contentFit="fill"
        transition={150}
        cachePolicy="disk"
        recyclingKey={uri}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  clip: { overflow: "hidden" },
});
