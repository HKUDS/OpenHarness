import { useAppStore } from '../store/useAppStore';
import type { AppSettings } from '../types';
import { Settings, Moon, Sun, Key, Folder, Sliders, Save, RotateCcw } from 'lucide-react';
import { useState, useEffect } from 'react';
import styles from './PageLayout.module.css';

const MODELS = [
  'claude-3-5-sonnet-20241022',
  'claude-3-opus-20240229',
  'claude-3-sonnet-20240229',
  'claude-3-haiku-20240307',
  'gemini-1-5-pro',
  'gemini-1-5-flash',
  'gpt-4-turbo-preview',
  'gpt-4-0125-preview',
  'gpt-3.5-turbo-0125'
];

const PERMISSION_MODES: { value: 'default' | 'plan' | 'full_auto'; label: string; description: string }[] = [
  { value: 'default', label: 'Default (Auto-approve safe commands)', description: 'Automatically approve safe operations' },
  { value: 'plan', label: 'Plan Mode (Review before execution)', description: 'Review all changes before applying' },
  { value: 'full_auto', label: 'Auto (Allow all tools)', description: 'Allow all tools automatically' }
];

export function SettingsPage() {
  const { settings, updateSettings, availableModels } = useAppStore();
  const [localSettings, setLocalSettings] = useState<AppSettings>(settings);
  const [saved, setSaved] = useState(false);
  
  useEffect(() => {
    setLocalSettings(settings);
  }, [settings]);
  
  const handleSave = () => {
    updateSettings(localSettings);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };
  
  const handleReset = () => {
    setLocalSettings({
      apiKey: '',
      model: 'claude-sonnet-4-6',
      permissionMode: 'default',
      theme: 'dark',
      workingDirectory: '~/workspace',
      maxTurns: 200,
      effort: 'medium',
      passes: 1,
      verbose: false,
      vimMode: false,
      fastMode: false,
    });
  };
  
  const toggleTheme = () => {
    const newTheme = localSettings.theme === 'dark' ? 'light' : 'dark';
    setLocalSettings({ ...localSettings, theme: newTheme });
    updateSettings({ theme: newTheme });
  };
  
  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1><Settings size={24} /> Settings</h1>
        <p>Configure OpenHarness preferences</p>
      </div>
      
      <div className={styles.pageContent}>
        <div className={styles.settingsSections}>
          {/* Theme Section */}
          <section className={styles.settingsSection}>
            <div className={styles.sectionHeader}>
              <h3><Moon size={18} /> Appearance</h3>
            </div>
            <div className={styles.sectionContent}>
              <div className={styles.settingItem}>
                <div className={styles.settingInfo}>
                  <span className={styles.settingLabel}>Theme</span>
                  <span className={styles.settingDescription}>
                    Choose between dark and light mode
                  </span>
                </div>
                <button 
                  className={`${styles.themeToggle} ${localSettings.theme === 'dark' ? styles.dark : styles.light}`}
                  onClick={toggleTheme}
                >
                  {localSettings.theme === 'dark' ? (
                    <><Moon size={16} /> Dark</>
                  ) : (
                    <><Sun size={16} /> Light</>
                  )}
                </button>
              </div>
            </div>
          </section>
          
          {/* API Section */}
          <section className={styles.settingsSection}>
            <div className={styles.sectionHeader}>
              <h3><Key size={18} /> API Configuration</h3>
            </div>
            <div className={styles.sectionContent}>
              <div className={styles.formGroup}>
                <label>API Key</label>
                <input
                  type="password"
                  value={localSettings.apiKey}
                  onChange={(e) => setLocalSettings({ ...localSettings, apiKey: e.target.value })}
                  placeholder="Enter your API key"
                />
              </div>
              <div className={styles.formGroup}>
                <label>Model</label>
                <select
                  value={localSettings.model}
                  onChange={(e) => setLocalSettings({ ...localSettings, model: e.target.value })}
                >
                  {(availableModels.length > 0 ? availableModels : MODELS).map(model => (
                    <option key={model} value={model}>{model}</option>
                  ))}
                </select>
              </div>
            </div>
          </section>
          
          {/* Workspace Section */}
          <section className={styles.settingsSection}>
            <div className={styles.sectionHeader}>
              <h3><Folder size={18} /> Workspace</h3>
            </div>
            <div className={styles.sectionContent}>
              <div className={styles.formGroup}>
                <label>Working Directory</label>
                <input
                  type="text"
                  value={localSettings.workingDirectory}
                  onChange={(e) => setLocalSettings({ ...localSettings, workingDirectory: e.target.value })}
                  placeholder="~/workspace"
                />
              </div>
            </div>
          </section>
          
          {/* Permission Section */}
          <section className={styles.settingsSection}>
            <div className={styles.sectionHeader}>
              <h3><Sliders size={18} /> Permissions</h3>
            </div>
            <div className={styles.sectionContent}>
              <div className={styles.formGroup}>
                <label>Permission Mode</label>
                <div className={styles.radioGroup}>
                  {PERMISSION_MODES.map(mode => (
                    <label key={mode.value} className={styles.radioItem}>
                      <input
                        type="radio"
                        name="permissionMode"
                        value={mode.value}
                        checked={localSettings.permissionMode === mode.value}
                        onChange={(e) => setLocalSettings({ ...localSettings, permissionMode: e.target.value as 'default' | 'plan' | 'full_auto' })}
                      />
                      <div className={styles.radioContent}>
                        <span className={styles.radioLabel}>{mode.label}</span>
                        <span className={styles.radioDescription}>{mode.description}</span>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
              <div className={styles.formGroup}>
                <label>Maximum Turns</label>
                <input
                  type="number"
                  value={localSettings.maxTurns}
                  onChange={(e) => setLocalSettings({ ...localSettings, maxTurns: parseInt(e.target.value) || 100 })}
                  min={1}
                  max={1000}
                />
              </div>
            </div>
          </section>
        </div>
        
        <div className={styles.settingsActions}>
          <button className={styles.secondaryButton} onClick={handleReset}>
            <RotateCcw size={16} />
            Reset to Defaults
          </button>
          <button className={styles.primaryButton} onClick={handleSave}>
            <Save size={16} />
            {saved ? 'Saved!' : 'Save Settings'}
          </button>
        </div>
      </div>
    </div>
  );
}