"""Tests for E2B sandbox backend file download behavior."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from openharness.config import Settings
from openharness.sandbox.e2b_backend import E2BSandboxSession


@pytest.mark.asyncio
async def test_read_file_binary_via_download_url_success():
    """Verify read_file_binary uses download_url with HTTP/1.1 when available."""
    session = E2BSandboxSession(settings=Settings())
    mock_sandbox = MagicMock()
    mock_sandbox.download_url.return_value = "https://mock-sandbox.e2b.app/files?path=test.mp4"
    session._sandbox = mock_sandbox

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"fake video content"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_cls.return_value = mock_client

        content = await session.read_file_binary("/home/user/artifacts/test.mp4")

        assert content == b"fake video content"
        mock_sandbox.download_url.assert_called_once_with("/home/user/artifacts/test.mp4", use_signature_expiration=3600)
        # Verify HTTP/1.1 was enforced (http2=False)
        mock_client_cls.assert_called_once()
        _, kwargs = mock_client_cls.call_args
        assert kwargs.get("http2") is False
        # files.read should NOT be called since download_url succeeded
        mock_sandbox.files.read.assert_not_called()


@pytest.mark.asyncio
async def test_read_file_binary_fallback_to_files_read_on_download_url_failure():
    """Verify read_file_binary falls back to files.read if download_url returns non-200 or raises."""
    session = E2BSandboxSession(settings=Settings())
    mock_sandbox = MagicMock()
    mock_sandbox.download_url.return_value = "https://mock-sandbox.e2b.app/files?path=test.mp4"
    mock_sandbox.files.read.return_value = bytearray(b"fallback file content")
    session._sandbox = mock_sandbox

    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_cls.return_value = mock_client

        content = await session.read_file_binary("/home/user/artifacts/test.mp4")

        assert content == b"fallback file content"
        mock_sandbox.files.read.assert_called_once_with("/home/user/artifacts/test.mp4", format="bytes")


@pytest.mark.asyncio
async def test_read_file_binary_fallback_when_download_url_not_supported():
    """Verify read_file_binary falls back to files.read if sandbox does not have download_url."""
    session = E2BSandboxSession(settings=Settings())
    mock_sandbox = MagicMock(spec=["files"])
    mock_sandbox.files.read.return_value = b"direct content"
    session._sandbox = mock_sandbox

    content = await session.read_file_binary("/home/user/artifacts/test.mp4")

    assert content == b"direct content"
    mock_sandbox.files.read.assert_called_once_with("/home/user/artifacts/test.mp4", format="bytes")
