import { useState } from 'react';
import { Settings as SettingsIcon, Key, User, Folder, Maximize, Eye, EyeOff, Save, RefreshCw } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { useBackendConnection } from '../hooks/useBackendConnection';
import styles from '../styles/SettingsPanel.module.css';

export function SettingsPanel() {
  const { settings, updateSettings, sessionState } = useAppStore();
  const { saveSettingsToBackend } = useBackendConnection();
  const [showApiKey, setShowApiKey] = useState(false);
  const [localApiKey, setLocalApiKey] = useState(settings.apiKey);

  const handleSave = () => {
    updateSettings({ apiKey: localApiKey });
  };

  const handlePermissionModeChange = (mode: string) => {
    updateSettings({ permissionMode: mode as 'plan' | 'default' | 'full_auto' });
  };

  const handleMaxTurnsChange = (value: string) => {
    const maxTurns = parseInt(value) || 100;
    updateSettings({ maxTurns });
  };

  const handleThemeChange = (theme: 'dark' | 'light') => {
    updateSettings({ theme });
  };

  const handleResetSettings = async () => {
    // Reset to defaults and sync to backend
    const defaultSettings = {
      model: 'claude-sonnet-4-6',
      permissionMode: 'default' as 'plan' | 'default' | 'full_auto',
      theme: 'dark' as 'dark' | 'light',
      maxTurns: 200,
      effort: 'medium' as 'low' | 'medium' | 'high',
      passes: 1,
      vimMode: false,
      fastMode: false,
    };
    updateSettings(defaultSettings);
    if (saveSettingsToBackend) {
      await saveSettingsToBackend({
        model: defaultSettings.model,
        permission_mode: defaultSettings.permissionMode,
        theme: defaultSettings.theme,
        max_turns: defaultSettings.maxTurns,
        effort: defaultSettings.effort,
        passes: defaultSettings.passes,
        vim_mode: defaultSettings.vimMode,
        voice_mode: defaultSettings.fastMode,
      });
    }
  };

  const permissionModes = [
    { value: 'default', label: 'Default', description: 'Auto-approve safe commands' },
    { value: 'plan', label: 'Plan Mode', description: 'Review before execution' },
    { value: 'full_auto', label: 'Auto', description: 'Allow all tools automatically' }
  ];

  return (
    <div className={styles.settingsPanel}>
      <div className={styles.header}>
        <SettingsIcon size={20} />
        <h3>Settings</h3>
      </div>

      <div className={styles.content}>
        {/* API Key Section */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <Key size={18} className={styles.sectionIcon} />
            <h4>API Configuration</h4>
          </div>
          <div className={styles.formGroup}>
            <label className={styles.label}>API Key</label>
            <div className={styles.inputWrapper}>
              <input
                type={showApiKey ? 'text' : 'password'}
                value={localApiKey}
                onChange={(e) => setLocalApiKey(e.target.value)}
                placeholder="Enter your API key"
                className={styles.input}
              />
              <button
                className={styles.toggleVisibility}
                onClick={() => setShowApiKey(!showApiKey)}
                type="button"
              >
                {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <div className={styles.buttonGroup}>
              <button className={styles.saveButton} onClick={handleSave}>
                <Save size={16} />
                Save API Key
              </button>
            </div>
          </div>
        </section>

        {/* Permission Mode Section */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <User size={18} className={styles.sectionIcon} />
            <h4>Permission Mode</h4>
          </div>
          <div className={styles.modeCards}>
            {permissionModes.map(mode => (
              <button
                key={mode.value}
                className={`${styles.modeCard} ${settings.permissionMode === mode.value ? styles.active : ''}`}
                onClick={() => handlePermissionModeChange(mode.value)}
              >
                <div className={styles.modeCardHeader}>
                  <span className={styles.modeCardTitle}>{mode.label}</span>
                  {settings.permissionMode === mode.value && (
                    <div className={styles.activeIndicator} />
                  )}
                </div>
                <p className={styles.modeCardDescription}>{mode.description}</p>
              </button>
            ))}
          </div>
          {sessionState?.permission_mode && (
            <p className={styles.currentValue}>
              Current: <span className={styles.value}>{sessionState.permission_mode}</span>
            </p>
          )}
        </section>

        {/* Working Directory Section */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <Folder size={18} className={styles.sectionIcon} />
            <h4>Working Directory</h4>
          </div>
          <div className={styles.formGroup}>
            <input
              type="text"
              value={settings.workingDirectory}
              onChange={(e) => updateSettings({ workingDirectory: e.target.value })}
              placeholder="~/workspace"
              className={styles.input}
            />
            {sessionState?.working_directory && (
              <p className={styles.currentValue}>
                Current: <span className={styles.value}>{sessionState.working_directory}</span>
              </p>
            )}
          </div>
        </section>

        {/* Max Turns Section */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <Maximize size={18} className={styles.sectionIcon} />
            <h4>Max Turns</h4>
          </div>
          <div className={styles.formGroup}>
            <input
              type="number"
              value={settings.maxTurns}
              onChange={(e) => handleMaxTurnsChange(e.target.value)}
              min="1"
              max="1000"
              className={styles.input}
            />
            <p className={styles.hint}>Maximum number of conversation turns per session</p>
            {sessionState?.max_turns && (
              <p className={styles.currentValue}>
                Current: <span className={styles.value}>{sessionState.max_turns}</span>
              </p>
            )}
          </div>
        </section>

        {/* Theme Section */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <Eye size={18} className={styles.sectionIcon} />
            <h4>Theme</h4>
          </div>
          <div className={styles.themeOptions}>
            <button
              className={`${styles.themeOption} ${settings.theme === 'dark' ? styles.active : ''}`}
              onClick={() => handleThemeChange('dark')}
            >
              🌙 Dark
            </button>
            <button
              className={`${styles.themeOption} ${settings.theme === 'light' ? styles.active : ''}`}
              onClick={() => handleThemeChange('light')}
            >
              ☀️ Light
            </button>
          </div>
        </section>

        {/* Reset Section */}
        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <RefreshCw size={18} className={styles.sectionIcon} />
            <h4>Reset Settings</h4>
          </div>
          <button className={styles.resetButton} onClick={handleResetSettings}>
            Restore Default Settings
          </button>
        </section>
      </div>
    </div>
  );
}
