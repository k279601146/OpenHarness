from __future__ import annotations

import json
from pathlib import Path

import pytest

from openharness.config.settings import Settings
from openharness.tools.base import ToolExecutionContext
from openharness.tools.config_tool import ConfigTool, ConfigToolInput


@pytest.mark.asyncio
async def test_config_show_redacts_env_and_nested_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")

    result = await ConfigTool().execute(
        ConfigToolInput(action="show"),
        ToolExecutionContext(cwd=tmp_path),
    )

    payload = json.loads(result.output)
    assert payload["api_key"] == "[REDACTED]"
    assert "sk-test-secret" not in result.output


@pytest.mark.asyncio
async def test_config_show_uses_saas_context_settings_without_loading_host_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host_config = tmp_path / "host-config"
    monkeypatch.setenv("OPENHARNESS_CONFIG_DIR", str(host_config))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-host-secret")
    context_settings = Settings(model="context-model", api_key="context-secret")

    result = await ConfigTool().execute(
        ConfigToolInput(action="show"),
        ToolExecutionContext(
            cwd=tmp_path,
            metadata={"thread_id": "thread-1", "saas_api_dir": str(tmp_path), "settings": context_settings},
        ),
    )

    payload = json.loads(result.output)
    assert payload["model"] == "context-model"
    assert payload["api_key"] == "[REDACTED]"
    assert "sk-host-secret" not in result.output
    assert "context-secret" not in result.output
    assert not host_config.exists()


@pytest.mark.asyncio
async def test_config_set_is_blocked_in_saas_context(tmp_path: Path) -> None:
    result = await ConfigTool().execute(
        ConfigToolInput(action="set", key="model", value="new-model"),
        ToolExecutionContext(
            cwd=tmp_path,
            metadata={"thread_id": "thread-1", "saas_api_dir": str(tmp_path), "settings": Settings()},
        ),
    )

    assert result.is_error
    assert "managed by the SaaS runtime" in result.output
