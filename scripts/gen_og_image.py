#!/usr/bin/env python3
"""共有カード用の画像（OG画像）を描く。

URLをLINEやXに貼ったときに出るプレビューの絵。1200x630 は各サービス共通の推奨比率
（1.91:1）で、これを外すと勝手に切り取られる。

絵は「背景 + アプリアイコン + 名前 + 一言」だけ。**公式サイトの券面画像は絶対に載せない**
（共有カードは他人のタイムラインに出るので、権利者の画像を最も目立つ形で配ることになる）。
アイコンは gen_icons.py が描いた public/icon-512.png をそのまま貼るので、ここでは
図形を描き直さない。

gen_icons.py は外部ライブラリなしで書いているが、こちらは日本語の字を置く必要があるため
Pillow を使う（scripts/ocr/ で既に使っているもの）。

    npm run build:og
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "public"

W, H = 1200, 630
MARGIN = 96

BG = (43, 108, 176)  # アプリのあお。gen_icons.py と同じ
YELLOW = (246, 199, 68)  # ピックのきいろ
WHITE = (255, 255, 255)
PALE = (206, 226, 245)

# 5歳が使うアプリなので、角ばらない字にする
MARU = "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc"

TITLE = "フレンダピックずかん"
LEAD = "もっているピックを きろくする"
SUBTITLE = "弾・レア・タイプでしぼりこんで さがせる。\nわざ・つよさ・とくべつなちからも 見られる。"

BAND = 18  # 下端に敷くきいろの帯


def fit_font(draw: ImageDraw.ImageDraw, text: str, size: int, max_width: int) -> ImageFont.FreeTypeFont:
    """max_width に収まるまで字を小さくする。文言を変えてもはみ出さないようにするため"""
    while size > 12:
        font = ImageFont.truetype(MARU, size)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 2
    raise ValueError(f"収まらない: {text}")


def rounded_icon(path: Path, size: int, radius: int) -> Image.Image:
    """アイコンを指定サイズの角丸にして返す"""
    icon = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    icon.putalpha(mask)
    return icon


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # アイコンは右上。左は字で埋まるので、空く側に置いて釣り合いを取る
    icon = rounded_icon(OUT / "icon-512.png", 176, 40)
    img.paste(icon, (W - MARGIN - 176, 84), icon)

    inner = W - MARGIN * 2
    title_font = fit_font(d, TITLE, 92, inner)
    lead_font = fit_font(d, LEAD, 48, inner)
    sub_font = ImageFont.truetype(MARU, 34)

    d.text((MARGIN, 272), TITLE, font=title_font, fill=WHITE)
    d.text((MARGIN + 4, 396), LEAD, font=lead_font, fill=YELLOW)
    d.multiline_text((MARGIN + 4, 480), SUBTITLE, font=sub_font, fill=PALE, spacing=14)

    d.rectangle((0, H - BAND, W, H), fill=YELLOW)

    out = OUT / "og.png"
    img.save(out, optimize=True)

    right = max(
        d.textbbox((MARGIN, 272), TITLE, font=title_font)[2],
        d.multiline_textbbox((MARGIN + 4, 480), SUBTITLE, font=sub_font, spacing=14)[2],
    )
    print(f"public/og.png  {W}x{H}  {out.stat().st_size // 1024}KB  文字の右端={right}px（余白 {W - right}px）")


if __name__ == "__main__":
    main()
