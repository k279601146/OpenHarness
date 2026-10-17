#!/usr/bin/env python3
"""CLI utility to fetch rendered web page content using CloakBrowser."""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch rendered HTML or text from a web page using CloakBrowser."
    )
    parser.add_argument("--url", required=True, help="Target URL to fetch")
    parser.add_argument(
        "-o", "--output", help="Output file path (default: write to stdout)"
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Extract visible body innerText instead of HTML",
    )
    parser.add_argument(
        "--wait-selector",
        help="Wait for a specific CSS selector to appear before extracting",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Navigation timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--humanize",
        action="store_true",
        help="Enable human-like interaction flags",
    )
    parser.add_argument(
        "--proxy",
        help="Proxy URL (e.g. http://user:pass@host:port or socks5://...)",
    )
    parser.add_argument(
        "--profile",
        help="Profile name under $CLOAKBROWSER_PROFILE_ROOT for session persistence",
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
            context = launch_persistent_context(user_data_dir, **launch_kwargs)
            page = context.new_page()
        else:
            browser = launch(**launch_kwargs)
            page = browser.new_page()

        page.set_default_timeout(timeout_ms)
        page.goto(args.url, wait_until="networkidle", timeout=timeout_ms)

        if args.wait_selector:
            page.wait_for_selector(args.wait_selector, timeout=timeout_ms)

        if args.text:
            content = page.evaluate("() => document.body ? document.body.innerText : ''")
        else:
            content = page.content()

        if args.output:
            out_path = os.path.abspath(args.output)
            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Content saved to: {out_path}")
        else:
            sys.stdout.write(content)
        return 0

    except Exception as e:
        sys.stderr.write(f"Fetch failed: {e}\n")
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
