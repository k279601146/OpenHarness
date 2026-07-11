from __future__ import annotations

import ipaddress
from pathlib import Path
import socket
from urllib.parse import urljoin, urlparse, urlunparse

import httpx


class UnsafeMediaURL(ValueError):
    pass


def validate_public_http_url(raw_url: str) -> str:
    parsed = urlparse(str(raw_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise UnsafeMediaURL("Only absolute http(s) media URLs are allowed")
    if parsed.username or parsed.password or not parsed.hostname:
        raise UnsafeMediaURL("Media URL credentials and empty hosts are not allowed")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise UnsafeMediaURL("Media URL host could not be resolved") from exc
    if not addresses:
        raise UnsafeMediaURL("Media URL host could not be resolved")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.version == 6 and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise UnsafeMediaURL("Media URL resolves to a blocked address")
    netloc = parsed.hostname if parsed.port is None else f"{parsed.hostname}:{parsed.port}"
    return urlunparse((parsed.scheme, netloc, parsed.path or "/", parsed.params, parsed.query, ""))


def safe_download_bytes(
    raw_url: str,
    *,
    max_bytes: int,
    allowed_content_types: tuple[str, ...],
    timeout_seconds: float,
    max_redirects: int = 3,
) -> bytes:
    current_url = validate_public_http_url(raw_url)
    timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 10.0))
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for _ in range(max_redirects + 1):
            with client.stream("GET", current_url) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise UnsafeMediaURL("Media redirect is missing a location")
                    current_url = validate_public_http_url(urljoin(current_url, location))
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if not any(content_type == item or content_type.startswith(item) for item in allowed_content_types):
                    raise UnsafeMediaURL("Media URL returned an unsupported content type")
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > max_bytes:
                    raise UnsafeMediaURL("Media response is too large")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise UnsafeMediaURL("Media response is too large")
                    chunks.append(chunk)
                return b"".join(chunks)
    raise UnsafeMediaURL("Media URL redirected too many times")


def safe_download_image(raw_url: str, *, max_bytes: int = 15 * 1024 * 1024, timeout_seconds: float = 180.0) -> bytes:
    content = safe_download_bytes(
        raw_url,
        max_bytes=max_bytes,
        allowed_content_types=("image/", "application/octet-stream", "binary/octet-stream"),
        timeout_seconds=timeout_seconds,
    )
    if not _looks_like_image(content):
        raise UnsafeMediaURL("Downloaded media is not a supported image file")
    return content


def safe_download_video(raw_url: str, output: Path, *, max_bytes: int = 500 * 1024 * 1024) -> None:
    content = safe_download_bytes(
        raw_url,
        max_bytes=max_bytes,
        allowed_content_types=("video/", "application/octet-stream"),
        timeout_seconds=300.0,
    )
    if not _looks_like_video(content):
        raise UnsafeMediaURL("Downloaded media is not a supported video container")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)


def _looks_like_image(content: bytes) -> bool:
    if len(content) < 12:
        return False
    return (
        content.startswith(b"\x89PNG\r\n\x1a\n")
        or content.startswith(b"\xff\xd8\xff")
        or content.startswith((b"GIF87a", b"GIF89a"))
        or (content.startswith(b"RIFF") and content[8:12] == b"WEBP")
        or content.startswith(b"BM")
    )


def _looks_like_video(content: bytes) -> bool:
    if len(content) < 12:
        return False
    return content[4:8] == b"ftyp" or content[:4] == b"\x1aE\xdf\xa3"
