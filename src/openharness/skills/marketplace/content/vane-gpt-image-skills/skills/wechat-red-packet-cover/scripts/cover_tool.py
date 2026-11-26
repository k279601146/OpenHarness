#!/usr/bin/env python3
"""Prepare a static cover and produce a clearly illustrative red-packet preview."""

import argparse
from io import BytesIO
from pathlib import Path
import sys

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    sys.exit("Pillow is required: python3 -m pip install Pillow")

SIZE = (957, 1278)
LIMIT = 500_000


def load_cover(path):
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original).convert("RGBA")
    image = ImageOps.fit(image, SIZE, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    background = Image.new("RGBA", SIZE, "white")
    return Image.alpha_composite(background, image).convert("RGB")


def separate_paths(source, target):
    if Path(source).resolve() == Path(target).resolve():
        raise ValueError("Input and output must be different files")


def export(source, target):
    separate_paths(source, target)
    if Path(target).suffix.lower() not in (".jpg", ".jpeg"):
        raise ValueError("Export output must end in .jpg or .jpeg")
    image = load_cover(source)
    best = None
    # Encoding sizes are not guaranteed to be monotonic; choose the highest
    # quality that actually fits, without assuming a binary-search ordering.
    for quality in range(95, 19, -1):
        buf = BytesIO()
        image.save(buf, format="JPEG", quality=quality, optimize=True, subsampling=0 if quality >= 90 else 2)
        if buf.tell() <= LIMIT:
            best = (quality, buf.getvalue())
            break
    if best is None:
        raise ValueError("Cannot fit this image within 500,000 bytes at acceptable quality")
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    Path(target).write_bytes(best[1])
    print(f"Exported {target}: {SIZE[0]}x{SIZE[1]}, {len(best[1])} bytes, JPEG quality {best[0]}")


def font_path(user_font):
    if user_font:
        if not Path(user_font).is_file():
            raise ValueError(f"Font not found: {user_font}")
        return user_font
    paths = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    ]
    return next((p for p in paths if Path(p).is_file()), None)


def preview(source, target, name, greeting, font):
    separate_paths(source, target)
    if Path(target).suffix.lower() != ".png":
        raise ValueError("Preview output must end in .png")
    selected_font = font_path(font)
    if not selected_font:
        raise ValueError("No Chinese font found. Supply --font /path/to/chinese-font.ttf")
    image = load_cover(source).convert("RGBA")
    w, h = image.size
    draw = ImageDraw.Draw(image)
    # The curve and button are a generic, illustrative composition, not an
    # official WeChat layout. Keep the cover image itself unmodified on disk.
    curve = []
    for x in range(w + 1):
        t = (x - w / 2) / (w / 2)
        curve.append((x, int(h * (0.74 - 0.055 * t * t))))
    draw.polygon(curve + [(w, h), (0, h)], fill=(194, 38, 38, 255))
    draw.line(curve, fill=(229, 159, 88, 255), width=4)
    cx, cy = w // 2, int(h * 0.745)
    radius = 92
    draw.ellipse((cx-radius-5, cy-radius-5, cx+radius+5, cy+radius+5), fill="#e2a548")
    draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), fill="#f7d58a", outline="#ffedbd", width=4)
    button_font = ImageFont.truetype(selected_font, 94)
    draw.text((cx, cy-2), "开", font=button_font, fill="#704527", anchor="mm")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((cx-39, 48, cx+39, 126), radius=15, fill="#eeeeee")
    draw.ellipse((cx-15, 61, cx+15, 91), fill="#999999")
    draw.ellipse((cx-26, 89, cx+26, 120), fill="#999999")
    font_name = ImageFont.truetype(selected_font, 31)
    font_greeting = ImageFont.truetype(selected_font, 32)
    draw.text((cx, 151), name[:18], font=font_name, fill="white", anchor="mm", stroke_width=2, stroke_fill="#333333")
    draw.text((cx, 207), greeting[:22], font=font_greeting, fill="white", anchor="mm", stroke_width=2, stroke_fill="#333333")
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(target, format="PNG", optimize=True)
    print(f"Preview saved {target} ({w}x{h}); illustrative, not an official WeChat preview")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="Crop and export a compliant-size JPEG")
    exp.add_argument("input")
    exp.add_argument("output")
    prev = sub.add_parser("preview", help="Overlay an illustrative red packet interface")
    prev.add_argument("input")
    prev.add_argument("output")
    prev.add_argument("--name", default="微信用户")
    prev.add_argument("--greeting", default="恭喜发财，大吉大利")
    prev.add_argument("--font")
    args = parser.parse_args()
    try:
        if args.command == "export":
            export(args.input, args.output)
        else:
            preview(args.input, args.output, args.name, args.greeting, args.font)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
