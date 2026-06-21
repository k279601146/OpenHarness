#!/usr/bin/env python3
"""Unified video generation CLI for OpenHarness videogen."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from videogen_runtime import VideogenProviderError, emit_metadata, run_video


DEFAULT_OUTPUT_PATH = "output/videogen/output.mp4"


def _die(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(2)


def _prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return args.prompt
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    _die("--prompt or --prompt-file is required")
    return ""


def _output_paths(args: argparse.Namespace) -> list[Path]:
    count = max(int(args.n or 1), 1)
    if args.out_dir:
        out_dir = Path(args.out_dir)
        return [out_dir / f"video_{index}.mp4" for index in range(1, count + 1)]
    out = Path(args.out)
    if out.suffix == "":
        out = out.with_suffix(".mp4")
    if count == 1:
        return [out]
    return [out.with_name(f"{out.stem}-{index}{out.suffix}") for index in range(1, count + 1)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified OpenHarness video generation CLI")
    parser.add_argument("command", choices=["generate", "image-to-video", "first-last-frame", "reference-to-video"])
    parser.add_argument("--prompt")
    parser.add_argument("--prompt-file")
    parser.add_argument("--model")
    parser.add_argument("--provider")
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--images", action="append", default=[])
    parser.add_argument("--video", action="append", default=[])
    parser.add_argument("--videos", action="append", default=[])
    parser.add_argument("--first-frame")
    parser.add_argument("--last-frame")
    parser.add_argument("--reference-file", action="append", dest="reference_files", default=[])
    parser.add_argument("--duration-seconds", type=int)
    parser.add_argument("--duration", type=int)
    parser.add_argument("--aspect-ratio")
    parser.add_argument("--resolution")
    parser.add_argument("--quality")
    parser.add_argument("--mode")
    parser.add_argument("--generate-audio", action="store_true")
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument("--out", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--out-dir")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    prompt = _prompt(args)
    outputs = _output_paths(args)
    try:
        metadata = run_video(args, outputs, prompt)
    except VideogenProviderError as exc:
        _die(str(exc))
    emit_metadata(metadata)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
