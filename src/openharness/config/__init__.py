"""Configuration system for OpenHarness.

Provides settings management, path resolution, and API key handling.
"""

from openharness.config.paths import (
    get_config_dir,
    get_config_file_path,
    get_data_dir,
    get_logs_dir,
    get_project_settings_file,
)
from openharness.config.settings import (
    ProviderProfile,
    Settings,
    auth_source_provider_name,
    default_auth_source_for_provider,
    default_provider_profiles,
    load_project_settings_overrides,
    load_settings,
    load_settings_for_project,
    save_settings,
    save_project_settings_overrides,
    set_project_memory_provider,
)

__all__ = [
    "ProviderProfile",
    "Settings",
    "auth_source_provider_name",
    "default_auth_source_for_provider",
    "default_provider_profiles",
    "get_config_dir",
    "get_config_file_path",
    "get_data_dir",
    "get_logs_dir",
    "get_project_settings_file",
    "load_settings",
    "load_project_settings_overrides",
    "load_settings_for_project",
    "save_settings",
    "save_project_settings_overrides",
    "set_project_memory_provider",
]
