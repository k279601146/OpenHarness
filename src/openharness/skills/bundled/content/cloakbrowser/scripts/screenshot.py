#!/usr/bin/env python3
"""CLI utility to take web page or element screenshots using CloakBrowser."""

from __future__ import annotations

import argparse
import os
import sys


def parse_viewport(viewport_str: str) -> dict[str, int]:
    try:
        parts = viewport_str.lower().split("x")
        return {"width": int(parts[0]), "height": int(parts[1])}
    except Exception:
        return {"width": 1920, "height": 1080}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture page or element screenshots using CloakBrowser."
    )
    parser.add_argument("--url", required=True, help="Target URL to capture")
    parser.add_argument(
        "-o",
        "--output",
        default="screenshot.png",
        help="Output image path (default: screenshot.png)",
    )
    parser.add_argument(
        "--full-page",
        action="store_true",
        help="Capture full scrollable page screenshot",
    )
    parser.add_argument(
        "--selector",
        help="CSS selector of a specific element to screenshot",
    )
    parser.add_argument(
        "--wait-selector",
        help="Wait for a specific CSS selector before capturing",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Navigation timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--viewport",
        default="1920x1080",
        help="Viewport dimension WIDTHxHEIGHT (default: 1920x1080)",
    )
    parser.add_argument(
        "--humanize",
        action="store_true",
        help="Enable human-like interaction flags",
    )
    parser.add_argument(
        "--proxy",
        help="Proxy URL",
    )
    parser.add_argument(
        "--profile",
        help="Profile name under $CLOAKBROWSER_PROFILE_ROOT",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in headed mode (default: headless)",
    )

    args = parser.parse_args()

    try:
        from cloakbrowser import launch, launch_persistent_context
    except ImportError:
        sys.stderr.write(
            "Error: 'cloakbrowser' is not installed in the current environment.\n"
        )
        return 1

    timeout_ms = args.timeout * 1000
    headless = not args.no_headless
    viewport = parse_viewport(args.viewport)

    launch_kwargs: dict = {
        "headless": headless,
        "humanize": args.humanize,
    }
    if args.proxy:
        launch_kwargs["proxy"] = args.proxy

    browser = None
    context = None
    try:
        if args.profile:
            profile_root = os.environ.get(
                "CLOAKBROWSER_PROFILE_ROOT",
                "/home/user/.cache/openharness/cloakbrowser/profiles",
            )
            user_data_dir = os.path.join(profile_root, args.profile)
            os.makedirs(user_data_dir, exist_ok=True)
            context = launch_persistent_context(
                user_data_dir, viewport=viewport, **launch_kwargs
            )
            page = context.new_page()
        else:
            browser = launch(**launch_kwargs)
            context = browser.new_context(viewport=viewport)
            page = context.new_page()

        page.set_default_timeout(timeout_ms)
        page.goto(args.url, wait_until="networkidle", timeout=timeout_ms)

        if args.wait_selector:
            page.wait_for_selector(args.wait_selector, timeout=timeout_ms)

        out_path = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

        if args.selector:
            element = page.wait_for_selector(args.selector, timeout=timeout_ms)
            element.screenshot(path=out_path)
        else:
            page.screenshot(path=out_path, full_page=args.full_page)

        print(f"Screenshot successfully saved to: {out_path}")
        return 0

    except Exception as e:
        sys.stderr.write(f"Screenshot failed: {e}\n")
        return 1
    finally:
        if context:
            try:
                context.close()
            except Exception:
                pass
        if browser:
            try:
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
