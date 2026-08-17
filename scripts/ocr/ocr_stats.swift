// 公式ピック画像のうら面から HP/ATK/DEF/SP.ATK/SP.DEF を Apple Vision で読み取る。
//
// 画像は 1016x1500 のwebpで、下半分(y=750..1500)がうら面。実測したところ、
// うら面のステータスカプセルは向き（縦ピック/横ピック）やセット（通常/ワンダー/
// スペシャル）が違っても同じ位置に出るため、固定の帯(y=1190..1400)だけを
// 切り出してOCRすれば十分だった。
//
// 数字はこのままだと英字と混同されることがある（例: "8"→"B", "0"→"D"）。
// このスクリプトは生のOCR文字列を返すだけで、英字が混じっているかどうかの
// 判定・補正は呼び出し側（fill_stats_from_ocr.py）が決定的なルールで行う。
//
// 標準入力から画像パスを1行ずつ受け取り、JSONLを標準出力へ書く。

import Foundation
import Vision
import CoreGraphics
import ImageIO

let labels = ["HP", "ATK", "DEF", "SP.ATK", "SP.DEF"]

struct Obs { var text: String; var x: CGFloat; var yTop: CGFloat; var w: CGFloat; var h: CGFloat }

/// 指定倍率で高品質補間して拡大したCGImageを返す（1の場合は元画像そのまま）
func upscale(_ image: CGImage, scale: Int) -> CGImage? {
    if scale == 1 { return image }
    let outW = image.width * scale, outH = image.height * scale
    guard let ctx = CGContext(
        data: nil, width: outW, height: outH, bitsPerComponent: 8, bytesPerRow: 0,
        space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    ) else { return nil }
    ctx.interpolationQuality = .high
    ctx.draw(image, in: CGRect(x: 0, y: 0, width: outW, height: outH))
    return ctx.makeImage()
}

/// 与えられた画像に対してOCRし、ラベル(HP/ATK/DEF/SP.ATK/SP.DEF)ごとに
/// 直下にある数字らしき観測の文字列を返す
func recognizeLabelledNumbers(_ image: CGImage, regionOriginY: CGFloat, regionH: CGFloat, W: CGFloat) -> [String: String] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    guard (try? handler.perform([request])) != nil else { return [:] }

    let items: [Obs] = (request.results ?? []).compactMap { obs in
        guard let top = obs.topCandidates(1).first else { return nil }
        let b = obs.boundingBox
        let xPix = b.minX * W
        let yTopPix = regionOriginY + (1 - (b.minY + b.height)) * regionH
        return Obs(text: top.string, x: xPix, yTop: yTopPix, w: b.width * W, h: b.height * regionH)
    }

    var found: [String: String] = [:]
    for label in labels {
        guard let labelObs = items.first(where: { $0.text == label }) else { continue }
        var best: Obs? = nil
        var bestGap: CGFloat = .greatestFiniteMagnitude
        for cand in items {
            if labels.contains(cand.text) { continue }
            let gap = cand.yTop - labelObs.yTop
            let xDiff = abs(cand.x - labelObs.x)
            if gap > 2 && gap < 40 && xDiff < 40 {
                if gap < bestGap { bestGap = gap; best = cand }
            }
        }
        if let b = best { found[label] = b.text }
    }
    return found
}

func processImage(_ path: String) -> [String: Any] {
    var result: [String: Any] = ["file": path]
    guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
          let cgImage = CGImageSourceCreateImageAtIndex(src, 0, nil) else {
        result["error"] = "load_failed"
        return result
    }
    let W = CGFloat(cgImage.width), H = CGFloat(cgImage.height)
    // うら面のステータス欄付近の帯（実測で確認した固定比率）
    let regionOriginY: CGFloat = H * (1190.0 / 1500.0)
    let regionH: CGFloat = H * (210.0 / 1500.0)
    guard let regionCrop = cgImage.cropping(to: CGRect(x: 0, y: regionOriginY, width: W, height: regionH)) else {
        result["error"] = "crop_failed"
        return result
    }

    // 同じ帯を「ネイティブ解像度・2倍・4倍」の3通りでOCRする。
    // 1回だけだと 9/5/3, 8/6 等の誤読が一定数まぎれることを実験で確認したため、
    // 3回の独立した読み取りのうち多数決で一致したものだけを後段（Python側）で
    // 信頼する（単純な文字置換での補正はしない）。
    let scales = [1, 2, 4]
    var passes: [[String: String]] = []
    for s in scales {
        guard let img = upscale(regionCrop, scale: s) else { continue }
        passes.append(recognizeLabelledNumbers(img, regionOriginY: regionOriginY, regionH: regionH, W: W))
    }

    for (label, key) in zip(labels, ["hp", "atk", "def", "spatk", "spdef"]) {
        for (i, p) in passes.enumerated() {
            result["\(key)_p\(i)"] = p[label] as Any
        }
    }
    return result
}

func jsonString(_ obj: [String: Any]) -> String {
    let data = try! JSONSerialization.data(withJSONObject: obj, options: [])
    return String(data: data, encoding: .utf8)!
}

while let line = readLine(strippingNewline: true) {
    let path = line.trimmingCharacters(in: .whitespaces)
    if path.isEmpty { continue }
    print(jsonString(processImage(path)))
}
