#!/usr/bin/env python3
"""Shared download helpers for PPT web image search."""

from __future__ import annotations

import io
import os

import requests

try:
    from PIL import Image as PILImage

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


CONTENT_TYPE_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
}

EXT_TO_PIL_FORMAT = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".webp": "WEBP",
    ".gif": "GIF",
    ".bmp": "BMP",
    ".tiff": "TIFF",
    ".tif": "TIFF",
}


def detect_image_extension(image_bytes: bytes, content_type: str | None = None) -> str | None:
    """Best-effort detection of the real image format."""
    if content_type:
        clean_type = content_type.split(";", 1)[0].strip().lower()
        if clean_type in CONTENT_TYPE_TO_EXT:
            return CONTENT_TYPE_TO_EXT[clean_type]
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return ".webp"
    if image_bytes.startswith(b"BM"):
        return ".bmp"
    if image_bytes.startswith((b"II*\x00", b"MM\x00*")):
        return ".tiff"
    return None


def _normalize_extension(ext: str) -> str:
    ext = ext.lower()
    if ext == ".jpeg":
        return ".jpg"
    if ext == ".tif":
        return ".tiff"
    return ext


def save_image_bytes(image_bytes: bytes, path: str, content_type: str | None = None) -> str:
    """Save image bytes while keeping file extension and real format aligned."""
    target_ext = _normalize_extension(os.path.splitext(path)[1])
    actual_ext = _normalize_extension(detect_image_extension(image_bytes, content_type) or "")
    if not target_ext:
        raise ValueError(f"Output path must include an image extension: {path}")
    if actual_ext and target_ext == actual_ext:
        with open(path, "wb") as f:
            f.write(image_bytes)
        print(f"  File saved to: {path}")
        report_resolution(path)
        return path
    if not HAS_PIL:
        actual_label = actual_ext or "unknown"
        raise RuntimeError(
            f"Image format mismatch for {path}: target extension is {target_ext}, "
            f"but the actual image bytes are {actual_label}. "
            "Install Pillow to enable automatic format conversion."
        )
    target_format = EXT_TO_PIL_FORMAT.get(target_ext)
    if not target_format:
        raise ValueError(f"Unsupported output image extension: {target_ext}")
    image = PILImage.open(io.BytesIO(image_bytes))
    if target_format == "JPEG" and image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGB")
    image.save(path, format=target_format)
    if actual_ext and actual_ext != target_ext:
        print(f"  Converted:    {actual_ext} -> {target_ext}")
    print(f"  File saved to: {path}")
    report_resolution(path)
    return path


def report_resolution(path: str) -> None:
    """Try to report image resolution using Pillow."""
    if not HAS_PIL:
        return
    try:
        img = PILImage.open(path)
        print(f"  Resolution:   {img.size[0]}x{img.size[1]}")
    except Exception:
        pass


def download_image(url: str, path: str, headers: dict | None = None, timeout: int = 180) -> str:
    """Download an image URL and save it to disk."""
    response = requests.get(url, headers=headers or {}, timeout=timeout)
    response.raise_for_status()
    return save_image_bytes(
        response.content,
        path,
        content_type=response.headers.get("Content-Type"),
    )
