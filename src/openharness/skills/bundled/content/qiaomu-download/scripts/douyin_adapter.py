#!/usr/bin/env python3
"""Douyin video adapter: stealth page resolution, direct CDN stream download, and ffprobe verification."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class AdapterError(RuntimeError):
    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage


def tool(name: str) -> str:
    found = os.environ.get(f"QIAOMU_{name.upper().replace('-', '_')}_BIN") or shutil.which(name)
    if not found or not Path(found).expanduser().is_file():
        raise AdapterError("dependency", f"{name} not found")
    return str(Path(found).expanduser())


def probe_media(path: Path, expect: str = "video") -> dict[str, Any]:
    ffprobe = tool("ffprobe")
    command = [
        ffprobe, "-v", "error",
        "-show_entries", "stream=codec_type,codec_name,width,height",
        "-show_entries", "format=format_name,duration,size",
        "-of", "json", str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AdapterError("verify", f"ffprobe failed: {result.stderr.strip() or 'unknown error'}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AdapterError("verify", f"ffprobe returned invalid JSON: {result.stdout}") from exc

    streams = payload.get("streams") or []
    expected_type = "audio" if expect == "audio" else "video"
    if not any(stream.get("codec_type") == expected_type for stream in streams):
        raise AdapterError("verify", f"{path.name} has no {expected_type} stream")

    format_info = payload.get("format") or {}
    duration = float(format_info.get("duration") or 0)
    file_size = path.stat().st_size
    if duration <= 0 or file_size <= 0:
        raise AdapterError("verify", f"{path.name} has invalid duration or size")

    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})

    return {
        "path": str(path.resolve()),
        "filename": path.name,
        "bytes": file_size,
        "container": format_info.get("format_name"),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "width": video.get("width"),
        "height": video.get("height"),
        "duration_seconds": round(duration, 3),
        "created": True,
    }


def normalize_douyin_url(url: str) -> str:
    raw = url.strip().strip("<>[](){}\"'")
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").rstrip(".").lower()
    if parsed.scheme.lower() != "https":
        raise AdapterError("validate", "Douyin URL must use HTTPS")
    if not (host == "douyin.com" or host.endswith(".douyin.com") or host == "iesdouyin.com" or host.endswith(".iesdouyin.com")):
        raise AdapterError("validate", f"URL host '{host}' is not a recognized Douyin domain")
    return raw


def launch_stealth_browser():
    try:
        from cloakbrowser import launch
        return launch(headless=True, humanize=True), "cloakbrowser"
    except ImportError:
        pass
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        return browser, "playwright"
    except Exception as exc:
        raise AdapterError("dependency", f"CloakBrowser or Playwright is required for Douyin verification bypass: {exc}")


def fetch_douyin_stream_info(url: str, timeout: int = 60) -> dict[str, Any]:
    target_url = normalize_douyin_url(url)
    browser, engine = launch_stealth_browser()
    try:
        page = browser.new_page()
        page.set_viewport_size({"width": 1280, "height": 800})
        page.goto(target_url, wait_until="domcontentloaded", timeout=min(timeout * 1000, 30000))

        try:
            page.wait_for_url(re.compile(r"douyin\.com/(?:video|note)/\d+"), timeout=10000)
        except Exception:
            pass

        poll_deadline = time.monotonic() + min(timeout, 20)
        video_data = None
        while time.monotonic() < poll_deadline:
            try:
                video_data = page.evaluate("""() => {
                    const videos = Array.from(document.querySelectorAll('video'));
                    for (let idx = 0; idx < videos.length; idx++) {
                        const video = videos[idx];
                        const currentSrc = video.currentSrc || video.src || '';
                        const sources = Array.from(video.querySelectorAll('source')).map(s => s.src).filter(Boolean);
                        
                        if (currentSrc.includes('uuu_265') || currentSrc.includes('douyinstatic.com')) {
                            continue;
                        }
                        const realSources = sources.filter(s => !s.includes('uuu_265') && !s.includes('douyinstatic.com'));
                        
                        if (currentSrc || realSources.length > 0) {
                            return {
                                title: document.title || '',
                                currentSrc: currentSrc,
                                sources: realSources,
                                duration: video.duration || 0,
                                videoWidth: video.videoWidth || 0,
                                videoHeight: video.videoHeight || 0
                            };
                        }
                    }
                    return null;
                }""")
                if video_data and (video_data.get("currentSrc") or video_data.get("sources")):
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if not video_data or (not video_data.get("currentSrc") and not video_data.get("sources")):
            raise AdapterError("metadata", "could not find active video stream elements on Douyin page")

        cookies = page.context.cookies()
        cookie_dict = {c["name"]: c["value"] for c in cookies}
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())

        video_id = ""
        current_page_url = page.url
        page_url_match = re.search(r"/(?:video|note|share/video)/(\d+)", current_page_url)
        if page_url_match:
            video_id = page_url_match.group(1)

        raw_title = (video_data.get("title") or "").strip()
        title = re.sub(r"\s*-\s*抖音(?:短视频)?$", "", raw_title).strip()
        if not title:
            title = f"douyin_{video_id}" if video_id else "douyin_video"

        candidates: list[str] = []
        if video_data.get("currentSrc"):
            candidates.append(video_data["currentSrc"])
        for s in video_data.get("sources") or []:
            if s and s not in candidates:
                candidates.append(s)

        candidates = [("https:" + c if c.startswith("//") else c) for c in candidates]

        if not video_id and candidates:
            vid_match = re.search(r"[?&]__vid=(\d+)", candidates[0])
            if vid_match:
                video_id = vid_match.group(1)

        return {
            "media_id": video_id or "douyin_video",
            "title": title,
            "candidates": candidates,
            "cookie_str": cookie_str,
            "engine": engine,
            "page_url": current_page_url,
            "expected_width": video_data.get("videoWidth"),
            "expected_height": video_data.get("videoHeight"),
        }
    finally:
        browser.close()


def sanitize_filename(name: str, max_length: int = 80) -> str:
    cleaned = re.sub(r'[\/\\:*?"<>|\r\n\t]', "_", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:max_length].rstrip(". ") or "douyin_video"


def download_stream(stream_info: dict[str, Any], output_dir: Path, audio_only: bool, timeout: int) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    media_id = stream_info["media_id"]
    safe_title = sanitize_filename(stream_info["title"])
    cookie_str = stream_info["cookie_str"]
    candidates = stream_info["candidates"]

    target_video_path = output_dir / f"{safe_title} [{media_id}].mp4"
    target_audio_path = output_dir / f"{safe_title} [{media_id}].mp3"
    final_target = target_audio_path if audio_only else target_video_path

    if final_target.is_file() and final_target.stat().st_size > 0:
        try:
            verified = probe_media(final_target, "audio" if audio_only else "video")
            verified["created"] = False
            return {
                "ok": True,
                "command": "audio" if audio_only else "video",
                "platform": "Douyin",
                "url": stream_info.get("page_url"),
                "media_id": media_id,
                "title": stream_info["title"],
                "quality": f"{verified.get('height', 720)}p",
                "files": [verified],
                "cleaned_intermediate_files": [],
                "cookies_from_browser": stream_info["engine"],
                "warnings": [],
            }
        except Exception:
            pass

    last_error = None
    temp_video_file = output_dir / f".tmp_{media_id}_{int(time.time())}.mp4"

    for candidate_url in candidates:
        try:
            req = urllib.request.Request(
                candidate_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                    "Referer": "https://www.douyin.com/",
                    "Cookie": cookie_str,
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp, open(temp_video_file, "wb") as out_f:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    out_f.write(chunk)

            if temp_video_file.stat().st_size > 1024:
                probe_media(temp_video_file, "video")
                last_error = None
                break
        except Exception as exc:
            last_error = exc
            if temp_video_file.exists():
                temp_video_file.unlink()
            continue

    if not temp_video_file.exists() or temp_video_file.stat().st_size == 0:
        raise AdapterError("download", f"failed to download valid Douyin video stream: {last_error}")

    cleaned_intermediate: list[str] = []

    if audio_only:
        ffmpeg = tool("ffmpeg")
        cmd = [
            ffmpeg, "-y", "-i", str(temp_video_file),
            "-vn", "-acodec", "libmp3lame", "-q:a", "0",
            str(target_audio_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        temp_video_file.unlink()
        cleaned_intermediate.append(str(temp_video_file))
        if res.returncode != 0:
            raise AdapterError("audio_conversion", f"ffmpeg audio conversion failed: {res.stderr}")
        verified = probe_media(target_audio_path, "audio")
    else:
        if target_video_path.exists():
            target_video_path.unlink()
        temp_video_file.rename(target_video_path)
        verified = probe_media(target_video_path, "video")

    return {
        "ok": True,
        "command": "audio" if audio_only else "video",
        "platform": "Douyin",
        "url": stream_info.get("page_url"),
        "media_id": media_id,
        "title": stream_info["title"],
        "quality": f"{verified.get('height', 720)}p",
        "files": [verified],
        "cleaned_intermediate_files": cleaned_intermediate,
        "cookies_from_browser": stream_info["engine"],
        "warnings": [],
    }


def info_douyin(url: str, timeout: int = 45) -> dict[str, Any]:
    stream_info = fetch_douyin_stream_info(url, timeout=timeout)
    return {
        "ok": True,
        "command": "info",
        "id": stream_info["media_id"],
        "title": stream_info["title"],
        "platform": "Douyin",
        "webpage_url": stream_info.get("page_url") or url,
        "width": stream_info.get("expected_width"),
        "height": stream_info.get("expected_height"),
        "candidates_count": len(stream_info["candidates"]),
        "cookies_from_browser": stream_info["engine"],
        "warnings": [],
    }


def doctor_douyin(url: str | None = None) -> dict[str, Any]:
    engine = None
    try:
        import cloakbrowser
        engine = "cloakbrowser"
    except ImportError:
        try:
            import playwright
            engine = "playwright"
        except ImportError:
            pass

    has_ffprobe = shutil.which("ffprobe") is not None
    has_ffmpeg = shutil.which("ffmpeg") is not None
    ok = bool(engine and has_ffprobe and has_ffmpeg)
    res = {
        "ok": ok,
        "adapter": "douyin-stealth-browser",
        "engine": engine or "missing (cloakbrowser or playwright required)",
        "ffprobe": "available" if has_ffprobe else "missing",
        "ffmpeg": "available" if has_ffmpeg else "missing",
    }
    if url:
        try:
            res["url_normalized"] = normalize_douyin_url(url)
        except Exception as exc:
            res["url_error"] = str(exc)
            res["ok"] = False
    return res


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bundled Douyin adapter for qiaomu-download")
    commands = parser.add_subparsers(dest="command", required=True)

    doc = commands.add_parser("doctor")
    doc.add_argument("--url")

    inf = commands.add_parser("info")
    inf.add_argument("url")
    inf.add_argument("--timeout", type=int, default=60)

    dl = commands.add_parser("download")
    dl.add_argument("url")
    dl.add_argument("--dir", dest="output_dir")
    dl.add_argument("--timeout", type=int, default=120)
    dl.add_argument("--audio-only", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.command == "doctor":
            result = doctor_douyin(args.url)
        elif args.command == "info":
            result = info_douyin(args.url, args.timeout)
        else:
            output = Path(args.output_dir or Path.home() / "Downloads").expanduser().resolve()
            stream_info = fetch_douyin_stream_info(args.url, args.timeout)
            result = download_stream(stream_info, output, args.audio_only, args.timeout)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            raise SystemExit(4)
    except AdapterError as exc:
        print(json.dumps({"ok": False, "stage": exc.stage, "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(2)
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "stage": "interrupted", "error": "operation interrupted"}, ensure_ascii=False, indent=2))
        raise SystemExit(130)


if __name__ == "__main__":
    main()
