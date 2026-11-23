"""Regression coverage for gateway configuration persistence."""

from pathlib import Path

import pytest

from ohmo.gateway.config import load_gateway_config, save_gateway_config
from ohmo.gateway.models import GatewayConfig


def test_gateway_config_atomic_write_preserves_previous_config_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / ".ohmo-home"
    initial = GatewayConfig(provider_profile="codex", send_progress=True)
    path = save_gateway_config(initial, workspace=workspace)
    original = path.read_bytes()

    def fail_replace(*args: object) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr("openharness.utils.fs.os.replace", fail_replace)
    with pytest.raises(OSError, match="simulated rename failure"):
        save_gateway_config(
            GatewayConfig(provider_profile="codex", send_progress=False),
            workspace=workspace,
        )

    assert path.read_bytes() == original
    assert load_gateway_config(workspace).send_progress is True
