"""The plugin's YAML + Python load the way the Dify plugin runtime loads them."""

import os
from pathlib import Path

import pytest
from dify_plugin import DifyPluginEnv
from dify_plugin.core.plugin_registration import PluginRegistration

from busabase_dify.client import PLUGIN_VERSION

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def registration(monkeypatch: pytest.MonkeyPatch) -> PluginRegistration:
    monkeypatch.chdir(PLUGIN_ROOT)  # the runtime resolves manifest paths from the cwd
    return PluginRegistration(DifyPluginEnv())


def test_manifest_and_every_tool_load(registration):
    assert str(registration.configuration.version) == PLUGIN_VERSION
    assert registration.configuration.author == "busabase"
    (provider,) = registration.tools_configuration
    names = sorted(tool.identity.name for tool in provider.tools)
    assert names == sorted(
        [
            "list_bases",
            "list_records",
            "find_records",
            "get_record",
            "create_record",
            "update_record",
            "list_nodes",
            "search_nodes",
            "get_node",
            "read_node_lines",
            "create_folder",
            "create_doc",
            "update_doc",
            "list_files",
            "read_file",
            "write_file",
            "search_playbooks",
            "get_playbook",
            "search_workspace",
        ]
    )
    for tool in provider.tools:
        assert registration.get_tool_cls("busabase", tool.identity.name) is not None
        assert tool.description.llm, tool.identity.name
        assert tool.identity.label.zh_hans != tool.identity.label.en_us, tool.identity.name
        assert tool.description.human.zh_hans, tool.identity.name
        for parameter in tool.parameters:
            name = f"{tool.identity.name}.{parameter.name}"
            assert parameter.llm_description, name
            assert parameter.label.zh_hans and parameter.human_description.zh_hans, name
            for option in parameter.options or []:
                assert option.label.zh_hans, f"{name}={option.value}"


def test_every_tool_file_is_registered():
    """A tools/*.yaml that is not listed in the provider would silently never load."""
    listed = set((PLUGIN_ROOT / "provider" / "busabase.yaml").read_text().split())
    for path in (PLUGIN_ROOT / "tools").glob("*.yaml"):
        assert f"tools/{path.name}" in listed, path.name


def test_requirements_and_pyproject_agree():
    requirements = (PLUGIN_ROOT / "requirements.txt").read_text().split()
    pyproject = (PLUGIN_ROOT / "pyproject.toml").read_text()
    for requirement in requirements:
        assert f'"{requirement}"' in pyproject, requirement
    assert os.path.exists(PLUGIN_ROOT / "PRIVACY.md")
