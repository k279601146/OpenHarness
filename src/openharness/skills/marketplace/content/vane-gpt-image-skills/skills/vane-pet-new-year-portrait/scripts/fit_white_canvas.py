#!/usr/bin/env python3
"""Fit an image without cropping on a white 3:4 PNG canvas."""
import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--width', type=int, default=1200)
    parser.add_argument('--height', type=int, default=1600)
    args = parser.parse_args()
    if args.width <= 0 or args.height <= 0 or args.width * 4 != args.height * 3:
        parser.error('width and height must be positive and have a 3:4 ratio')
    if args.output.suffix.lower() != '.png':
        parser.error('output must be a PNG file')
    if args.output.exists():
        parser.error('output already exists; choose a new filename')
    try:
        from PIL import Image, ImageOps
        with Image.open(args.input) as src:
            src = ImageOps.exif_transpose(src).convert('RGBA')
            src.thumbnail((args.width, args.height), Image.Resampling.LANCZOS)
            canvas = Image.new('RGB', (args.width, args.height), 'white')
            canvas.paste(src, ((args.width - src.width) // 2, (args.height - src.height) // 2), src)
            with args.output.open('xb') as output:
                canvas.save(output, format='PNG')
    except (OSError, ImportError) as exc:
        print(f'Cannot create preview: {exc}', file=sys.stderr)
        return 1
    print(f'Saved {args.output} ({args.width}x{args.height})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
