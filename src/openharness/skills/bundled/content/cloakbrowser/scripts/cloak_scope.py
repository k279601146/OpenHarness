#!/usr/bin/env python3
"""Generate isolated CloakBrowser profile paths and fingerprint seeds."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import sys
from urllib.parse import urlparse


DEFAULT_PROFILE_ROOT = "/home/user/.cache/openharness/cloakbrowser/profiles"
DEFAULT_CACHE_DIR = "/opt/cloakbrowser-cache"
TEMPORARY_PROFILE_PARENT = "/tmp/openharness-cloakbrowser"


def _site_key(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError("--site cannot be empty")
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or raw).strip().lower()
    host = host.strip(".")
    if not host:
        raise ValueError(f"Cannot derive site host from {value!r}")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{host}{port}"


def _safe_label(value: str, *, fallback: str) -> str:
    label = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip(".-_")
    return label[:64] or fallback


def _digest(*parts: str, length: int = 16) -> str:
    joined = "\0".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:length]


def _fingerprint_seed(*parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
    number = int(digest[:16], 16) % 900_000_000_000
    return str(100_000_000_000 + number)


def _join_posix(*parts: str) -> str:
    cleaned = [str(part).strip("/") for part in parts if str(part).strip("/")]
    if not cleaned:
        return "/"
    prefix = "/" if str(parts[0]).startswith("/") else ""
    return prefix + posixpath.join(*cleaned)


def _mkdir_for_runtime(path: str) -> None:
    # The generated path is for Linux sandboxes. Avoid creating D:\home\... during local Windows checks.
    if os.name == "nt" and path.startswith("/"):
        return
    os.makedirs(path, exist_ok=True)


def _build_scope(args: argparse.Namespace) -> dict[str, object]:
    site = _site_key(args.site)
    user_id = str(args.user_id).strip()
    thread_id = str(args.thread_id or "").strip()
    if not user_id:
        raise ValueError("--user-id cannot be empty")
    if args.mode == "thread" and not thread_id:
        raise ValueError("--thread-id is required when --mode thread")

    profile_root = os.environ.get("CLOAKBROWSER_PROFILE_ROOT", DEFAULT_PROFILE_ROOT).replace("\\", "/")
    cache_dir = os.environ.get("CLOAKBROWSER_CACHE_DIR", DEFAULT_CACHE_DIR)
    user_hash = _digest("user", user_id)
    site_hash = _digest("site", site)
    site_label = _safe_label(site, fallback=site_hash)

    if args.mode == "temporary":
        seed = _fingerprint_seed("temporary", user_id, thread_id, site)
        return {
            "mode": args.mode,
            "site_key": site,
            "profile_dir": None,
            "temporary_profile_parent": TEMPORARY_PROFILE_PARENT,
            "fingerprint_seed": seed,
            "cache_dir": cache_dir,
            "launch_args": [f"--fingerprint={seed}"],
        }

    if args.mode == "thread":
        thread_hash = _digest("thread", thread_id)
        profile_dir = _join_posix(profile_root, "threads", user_hash, thread_hash, f"{site_label}-{site_hash}")
        seed = _fingerprint_seed("thread", user_id, thread_id, site)
    else:
        profile_dir = _join_posix(profile_root, "users", user_hash, f"{site_label}-{site_hash}")
        seed = _fingerprint_seed("user", user_id, site)

    if args.create:
        _mkdir_for_runtime(profile_dir)

    return {
        "mode": args.mode,
        "site_key": site,
        "profile_dir": profile_dir,
        "fingerprint_seed": seed,
        "cache_dir": cache_dir,
        "launch_args": [f"--fingerprint={seed}"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate an isolated CloakBrowser scope.")
    parser.add_argument("--site", required=True, help="Target host or URL, for example https://example.com")
    parser.add_argument("--user-id", required=True, help="Current SaaS user ID or stable user scope key")
    parser.add_argument("--thread-id", help="Current thread/workspace ID, required for --mode thread")
    parser.add_argument(
        "--mode",
        choices=("user", "thread", "temporary"),
        default="user",
        help="Profile isolation mode. Defaults to user-level persistence.",
    )
    parser.add_argument(
        "--no-create",
        action="store_false",
        dest="create",
        help="Print paths without creating persistent profile directories.",
    )
    parser.set_defaults(create=True)
    args = parser.parse_args(argv)

    try:
        result = _build_scope(args)
    except ValueError as exc:
        print(f"cloak_scope: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
