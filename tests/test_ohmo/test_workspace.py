from pathlib import Path

from ohmo.workspace import (
    get_bootstrap_path,
    get_gateway_config_path,
    get_identity_path,
    get_memory_index_path,
    get_soul_path,
    get_user_path,
    initialize_workspace,
    workspace_health,
)


def test_initialize_workspace_creates_expected_files(tmp_path: Path):
    workspace = tmp_path / ".ohmo-home"
    root = initialize_workspace(workspace)
    assert root == workspace
    assert get_soul_path(workspace).exists()
    assert get_user_path(workspace).exists()
    assert get_identity_path(workspace).exists()
    assert get_bootstrap_path(workspace).exists()
    assert get_memory_index_path(workspace).exists()
    assert get_gateway_config_path(workspace).exists()

    health = workspace_health(workspace)
    assert all(health.values())

    soul_text = get_soul_path(workspace).read_text(encoding="utf-8")
    user_text = get_user_path(workspace).read_text(encoding="utf-8")
    identity_text = get_identity_path(workspace).read_text(encoding="utf-8")
    bootstrap_text = get_bootstrap_path(workspace).read_text(encoding="utf-8")
    assert "Be genuinely helpful, not performatively helpful." in soul_text
    assert "Remember that access is intimacy." in soul_text
    assert "Relationship notes" in user_text
    assert "learn enough to help well, not to build a dossier" in user_text
    assert "Name: ohmo" in identity_text
    assert "first conversation" in bootstrap_text
