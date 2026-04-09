import { useState } from 'react';
import { Settings as SettingsIcon, Key, User, Folder, Maximize, Eye, EyeOff, Save, RefreshCw } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import styles from '../styles/SettingsPanel.module.css';

export function SettingsPanel() {
  const { settings, updateSettings, setPermissionMode, sessionState } = useAppStore();
  const [showApiKey, setShowApiKey] = useState(false);
  const [localApiKey, setLocalApiKey] = useState(settings.apiKey);

  const handleSave = () => {
    updateSettings({ apiKey: localApiKey });
  };

  const permissionModes = [
    { value: 'default', label: 'Default', description: 'Auto-approve safe commands' },
    { value: 'plan', label: 'Plan Mode', description: 'Review before execution' }
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
                onClick={() => setPermissionMode(mode.value)}
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
              onChange={(e) => updateSettings({ maxTurns: parseInt(e.target.value) || 100 })}
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
              onClick={() => updateSettings({ theme: 'dark' })}
            >
              🌙 Dark
            </button>
            <button
              className={`${styles.themeOption} ${settings.theme === 'light' ? styles.active : ''}`}
              onClick={() => updateSettings({ theme: 'light' })}
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
          <button className={styles.resetButton}>
            Restore Default Settings
          </button>
        </section>
      </div>
    </div>
  );
}
