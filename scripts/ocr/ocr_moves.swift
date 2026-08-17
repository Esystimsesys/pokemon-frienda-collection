// 公式ピック画像のうら面から、わざ欄1行目の「英語名」と「日本語名」を Apple Vision で読み取る。
//
// ステータス数字（ocr_stats.swift）と違い、切り出し位置は固定比率では決められない。
// うら面のわざ欄はカードによって数ピクセルずれるので、QRコードの切り出しシンボルを
// アンカーにして位置を出す必要がある（header_ocr.find_anchor）。その計算は Python 側に
// あるので、このツールは「どこを切り出すか」を標準入力で受け取るだけにしている。
//
// わざ欄1行目は上段に英語名（小さい色つき文字）、下段に日本語名（大きい黒文字）が
// 並んでいる。どちらの行に属するかは文字の高さ方向の位置で決まるので、ここでは判定せず、
// 認識した文字列とその位置をそのまま返す。行の切り分けと突き合わせは呼び出し側
// （move_ocr.py）が決定的なルールで行う。
//
// 数字と同じく、1回のOCRだけでは誤読がまぎれる。日本語のわざ名でまちがえるのは
// ほぼ濁点と半濁点の取りちがえ（ブ↔プ、が↔か）で、これは拡大のしかたによって
// 出たり出なかったりする。そこで同じ切り出しを「拡大率×補間のしかた」を変えて
// 何通りも読み、全部で同じ文字列になったものだけを信頼する（判定は呼び出し側）。
//
// 標準入力からJSONLを1行ずつ受け取り、JSONLを標準出力へ書く。
//   入力: {"id":"1-1-001","file":"...webp","x":420,"y":1090,"w":330,"h":54}
//   出力: {"id":"1-1-001","passes":[[{"t":"Collision Course","x":0.1,"y":0.1,"w":0.5,"h":0.3}],...]}
// 出力の座標は切り出し枠を1.0とした相対値で、y は上が0。passes の並びは VARIANTS と同じ。

import Foundation
import Vision
import CoreGraphics
import ImageIO

/// 同じ切り出しをこの組み合わせで独立に読む。
///   scale  : 拡大率。等倍は日本語の小さい文字がつぶれて読めないので入れていない。
///   smooth : true なら高品質補間（なめらか）、false なら補間なし（かくかく）。
///            濁点の見えかたがこの2つでかなり変わるので、両方を混ぜている。
///   gray   : true ならグレースケールにしてから拡大する。帯の地色が濃いピックでの
///            見えかたが変わる。
let VARIANTS: [(scale: Int, smooth: Bool, gray: Bool)] = [
    (2, true, false), (4, true, false), (6, true, false),
    (2, false, false), (4, false, false), (8, false, false),
    (6, true, true),
]

struct Request: Decodable {
    let id: String
    let file: String
    let x: Int
    let y: Int
    let w: Int
    let h: Int
}

/// 指定倍率で拡大したCGImageを返す
func upscale(_ image: CGImage, scale: Int, smooth: Bool, gray: Bool) -> CGImage? {
    let outW = image.width * scale, outH = image.height * scale
    let space = gray ? CGColorSpaceCreateDeviceGray() : CGColorSpaceCreateDeviceRGB()
    let info = gray ? CGImageAlphaInfo.none.rawValue : CGImageAlphaInfo.premultipliedLast.rawValue
    guard let ctx = CGContext(
        data: nil, width: outW, height: outH, bitsPerComponent: 8, bytesPerRow: 0,
        space: space, bitmapInfo: info
    ) else { return nil }
    ctx.interpolationQuality = smooth ? .high : .none
    ctx.draw(image, in: CGRect(x: 0, y: 0, width: outW, height: outH))
    return ctx.makeImage()
}

/// 1枚ぶんOCRして、認識できた文字列とその位置（切り出し枠を1.0とした相対値）を返す
func recognize(_ image: CGImage) -> [[String: Any]] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    // わざ名は日本語。英語名も同じ行にあるが、ja-JP のままで両方読める。
    request.recognitionLanguages = ["ja-JP"]
    // 実在しない語への「補正」でわざ名が別の語に化けるのを防ぐ
    request.usesLanguageCorrection = false
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    guard (try? handler.perform([request])) != nil else { return [] }

    return (request.results ?? []).compactMap { obs in
        guard let top = obs.topCandidates(1).first else { return nil }
        let b = obs.boundingBox
        // Vision の y は下が0なので、上が0になるように反転する
        return [
            "t": top.string,
            "x": b.minX,
            "y": 1 - (b.minY + b.height),
            "w": b.width,
            "h": b.height,
        ] as [String: Any]
    }
}

func processRequest(_ req: Request) -> [String: Any] {
    var result: [String: Any] = ["id": req.id]
    guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: req.file) as CFURL, nil),
          let cgImage = CGImageSourceCreateImageAtIndex(src, 0, nil) else {
        result["error"] = "load_failed"
        return result
    }
    guard let crop = cgImage.cropping(to: CGRect(x: req.x, y: req.y, width: req.w, height: req.h)) else {
        result["error"] = "crop_failed"
        return result
    }

    var passes: [[[String: Any]]] = []
    for v in VARIANTS {
        guard let img = upscale(crop, scale: v.scale, smooth: v.smooth, gray: v.gray) else { continue }
        passes.append(recognize(img))
    }
    result["passes"] = passes
    return result
}

func jsonString(_ obj: [String: Any]) -> String {
    let data = try! JSONSerialization.data(withJSONObject: obj, options: [])
    return String(data: data, encoding: .utf8)!
}

let decoder = JSONDecoder()
while let line = readLine(strippingNewline: true) {
    let trimmed = line.trimmingCharacters(in: .whitespaces)
    if trimmed.isEmpty { continue }
    guard let req = try? decoder.decode(Request.self, from: Data(trimmed.utf8)) else {
        print(jsonString(["id": "", "error": "bad_input"]))
        continue
    }
    print(jsonString(processRequest(req)))
}
