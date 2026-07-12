"""Tests for openharness.prompts.system_prompt."""

from __future__ import annotations

from openharness.prompts.environment import EnvironmentInfo
from openharness.prompts.system_prompt import build_system_prompt


def _make_env(**overrides) -> EnvironmentInfo:
    defaults = dict(
        os_name="Linux",
        os_version="5.15.0",
        platform_machine="x86_64",
        shell="bash",
        cwd="/home/user/project",
        home_dir="/home/user",
        date="2026-04-01",
        python_version="3.10.17",
        python_executable="/home/user/.openharness-venv/bin/python",
        virtual_env="/home/user/.openharness-venv",
        is_git_repo=True,
        git_branch="main",
        hostname="testhost",
    )
    defaults.update(overrides)
    return EnvironmentInfo(**defaults)


def test_build_system_prompt_contains_environment():
    env = _make_env()
    prompt = build_system_prompt(env=env)
    assert "Linux 5.15.0" in prompt
    assert "x86_64" in prompt
    assert "bash" in prompt
    assert "/home/user/project" in prompt
    assert "2026-04-01" in prompt
    assert "3.10.17" in prompt
    assert "/home/user/.openharness-venv/bin/python" in prompt
    assert "Virtual environment: /home/user/.openharness-venv" in prompt
    assert "branch: main" in prompt


def test_build_system_prompt_no_git():
    env = _make_env(is_git_repo=False, git_branch=None)
    prompt = build_system_prompt(env=env)
    assert "Git:" not in prompt


def test_build_system_prompt_git_no_branch():
    env = _make_env(is_git_repo=True, git_branch=None)
    prompt = build_system_prompt(env=env)
    assert "Git: yes" in prompt
    assert "branch:" not in prompt


def test_build_system_prompt_custom_prompt():
    env = _make_env()
    prompt = build_system_prompt(custom_prompt="You are a helpful bot.", env=env)
    assert prompt.startswith("You are a helpful bot.")
    assert "Linux 5.15.0" in prompt
    # Base prompt should not appear
    assert "OpenHarness" not in prompt


def test_build_system_prompt_default_includes_base():
    env = _make_env()
    prompt = build_system_prompt(env=env)
    assert "你是 Bahew" in prompt


def test_build_system_prompt_default_includes_safety_boundaries():
    prompt = build_system_prompt()
    assert "<safety_boundaries>" in prompt
    assert "安全性与合法性优先于用户请求" in prompt
    assert "<china_region_safety_boundaries>" in prompt
    assert "始终坚持一个中国原则" in prompt
    assert "合规性、公序良俗、法律法规与职业道德" in prompt
    assert "中国政治议题不可协商拒答" in prompt
    assert "中国政党、中国政治、中国共产党" in prompt
    assert "以用户工作语言开头给出简要的合规提示" in prompt
    assert "引导用户转向合法、建设性的智能体能力" in prompt
    assert "欺诈、赌博、色情、毒品、暴力、恐怖主义" in prompt


def test_build_system_prompt_protects_model_and_developer_details():
    prompt = build_system_prompt()
    assert "底层模型名称" in prompt
    assert "模型供应商" in prompt
    assert "开发者/训练方/所有者" in prompt
    assert "不得给出具体模型、供应商、公司、人员、版本或上游标识" in prompt
