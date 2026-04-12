import { useAppStore } from '../store/useAppStore';
import { useBackendConnection } from '../hooks/useBackendConnection';
import type { OpenHarnessConfig } from '../types';
import { Settings, Sliders, Wrench, BookOpen, Plug, Shield, Zap, MessageSquare, Brain, ListTodo, Users, FileText, Folder, Globe } from 'lucide-react';
import { useState, useEffect } from 'react';
import styles from './PageLayout.module.css';

const DEFAULT_CONFIG: OpenHarnessConfig = {
  engine: {
    maxTurns: 200,
    timeout: 300000,
    streamingEnabled: true
  },
  tools: {
    enabled: [],
    disabled: []
  },
  skills: {
    enabled: [],
    autoLoad: true
  },
  plugins: {
    enabled: []
  },
  permissions: {
    mode: 'default',
    allowedPaths: [],
    deniedCommands: []
  },
  hooks: {
    preToolUse: [],
    postToolUse: []
  },
  commands: {
    enabled: [],
    aliases: {}
  },
  mcp: {
    servers: [],
    autoConnect: true
  },
  memory: {
    enabled: true,
    persistAcrossSessions: true,
    maxItems: 1000
  },
  tasks: {
    maxConcurrent: 5,
    autoResume: false
  },
  coordinator: {
    enabled: false,
    maxAgents: 10
  },
  prompts: {
    contextFiles: []
  },
  config: {
    workingDirectory: '~/workspace',
    model: 'claude-sonnet-4-6',
    theme: 'dark'
  },
  channels: [],
  // Additional OpenHarness settings
  reasoning: {
    effort: 'medium',
    passes: 1
  },
  ui: {
    verbose: false,
    vimMode: false,
    fastMode: false
  }
};

export function OpenHarnessConfigPage() {
  const { openHarnessConfig, setOpenHarnessConfig, updateSettings } = useAppStore();
  const { sendConfig } = useBackendConnection();
  const [localConfig, setLocalConfig] = useState<OpenHarnessConfig>(openHarnessConfig || DEFAULT_CONFIG);
  const [activeSection, setActiveSection] = useState<string>('engine');
  const [saved, setSaved] = useState(false);
  
  // Initialize local config from store on mount and when store changes
  useEffect(() => {
    if (openHarnessConfig) {
      setLocalConfig(openHarnessConfig);
    }
  }, [openHarnessConfig]);
  
  // Load config from localStorage on mount if store is empty
  useEffect(() => {
    if (!openHarnessConfig) {
      const stored = localStorage.getItem('openharness-openharness-config');
      if (stored) {
        try {
          const parsedConfig = JSON.parse(stored);
          setLocalConfig(parsedConfig);
          setOpenHarnessConfig(parsedConfig);
        } catch (e) {
          console.error('Failed to parse stored OpenHarness config:', e);
        }
      }
    }
  }, []);
  
  const handleSave = () => {
    setOpenHarnessConfig(localConfig);
    // Sync with settings
    updateSettings({
      model: localConfig.config.model,
      workingDirectory: localConfig.config.workingDirectory,
      theme: localConfig.config.theme,
      maxTurns: localConfig.engine.maxTurns,
      permissionMode: localConfig.permissions.mode === 'auto' ? 'full_auto' : localConfig.permissions.mode
    });
    // Sync permission mode to backend
    if (sendConfig) {
      sendConfig({ permission_mode: localConfig.permissions.mode });
    }
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };
  
  const handleReset = () => {
    setLocalConfig(DEFAULT_CONFIG);
  };
  
  const updateSection = <K extends keyof OpenHarnessConfig>(
    section: K,
    updates: Partial<OpenHarnessConfig[K]>
  ) => {
    setLocalConfig(prev => ({
      ...prev,
      [section]: { ...prev[section], ...updates }
    }));
  };
  
  const sections = [
    { id: 'engine', label: 'Engine', icon: Sliders },
    { id: 'reasoning', label: 'Reasoning', icon: Brain },
    { id: 'ui', label: 'UI', icon: Settings },
    { id: 'tools', label: 'Tools', icon: Wrench },
    { id: 'skills', label: 'Skills', icon: BookOpen },
    { id: 'plugins', label: 'Plugins', icon: Plug },
    { id: 'permissions', label: 'Permissions', icon: Shield },
    { id: 'hooks', label: 'Hooks', icon: Zap },
    { id: 'commands', label: 'Commands', icon: MessageSquare },
    { id: 'mcp', label: 'MCP', icon: Globe },
    { id: 'memory', label: 'Memory', icon: Brain },
    { id: 'tasks', label: 'Tasks', icon: ListTodo },
    { id: 'coordinator', label: 'Coordinator', icon: Users },
    { id: 'prompts', label: 'Prompts', icon: FileText },
    { id: 'config', label: 'Config', icon: Folder },
  ];
  
  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1><Settings size={24} /> OpenHarness Configuration</h1>
        <p>Configure all aspects of your OpenHarness instance</p>
      </div>
      
      <div className={styles.configLayout}>
        <aside className={styles.configSidebar}>
          {sections.map(section => {
            const Icon = section.icon;
            return (
              <button
                key={section.id}
                className={`${styles.configNavItem} ${activeSection === section.id ? styles.active : ''}`}
                onClick={() => setActiveSection(section.id)}
              >
                <Icon size={18} />
                {section.label}
              </button>
            );
          })}
        </aside>
        
        <main className={styles.configContent}>
          {/* Engine Section */}
          {activeSection === 'engine' && (
            <section className={styles.configSection}>
              <h3>Engine Configuration</h3>
              <p className={styles.sectionDescription}>Configure the agent loop behavior</p>
              
              <div className={styles.formGroup}>
                <label>Maximum Turns</label>
                <input
                  type="number"
                  value={localConfig.engine.maxTurns}
                  onChange={(e) => updateSection('engine', { maxTurns: parseInt(e.target.value) || 200 })}
                  min={1}
                  max={1000}
                />
              </div>
              
              <div className={styles.formGroup}>
                <label>Timeout (ms)</label>
                <input
                  type="number"
                  value={localConfig.engine.timeout}
                  onChange={(e) => updateSection('engine', { timeout: parseInt(e.target.value) || 300000 })}
                  min={1000}
                />
              </div>
              
              <div className={styles.formGroup}>
                <label className={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={localConfig.engine.streamingEnabled}
                    onChange={(e) => updateSection('engine', { streamingEnabled: e.target.checked })}
                  />
                  Enable Streaming
                </label>
              </div>
            </section>
          )}
          
          {/* Reasoning Section */}
          {activeSection === 'reasoning' && (
            <section className={styles.configSection}>
              <h3>Reasoning Settings</h3>
              <p className={styles.sectionDescription}>Configure reasoning effort and iteration count</p>
              
              <div className={styles.formGroup}>
                <label>Effort Level</label>
                <select
                  value={localConfig.reasoning.effort}
                  onChange={(e) => updateSection('reasoning', { effort: e.target.value as 'low' | 'medium' | 'high' })}
                >
                  <option value="low">Low (Fast, minimal reasoning)</option>
                  <option value="medium">Medium (Balanced)</option>
                  <option value="high">High (Deep reasoning)</option>
                </select>
              </div>
              
              <div className={styles.formGroup}>
                <label>Passes (Iterations)</label>
                <input
                  type="number"
                  value={localConfig.reasoning.passes}
                  onChange={(e) => updateSection('reasoning', { passes: parseInt(e.target.value) || 1 })}
                  min={1}
                  max={10}
                />
              </div>
            </section>
          )}
          
          {/* UI Section */}
          {activeSection === 'ui' && (
            <section className={styles.configSection}>
              <h3>UI Settings</h3>
              <p className={styles.sectionDescription}>Configure UI behavior and modes</p>
              
              <div className={styles.formGroup}>
                <label className={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={localConfig.ui.verbose}
                    onChange={(e) => updateSection('ui', { verbose: e.target.checked })}
                  />
                  Verbose Mode (Show detailed output)
                </label>
              </div>
              
              <div className={styles.formGroup}>
                <label className={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={localConfig.ui.vimMode}
                    onChange={(e) => updateSection('ui', { vimMode: e.target.checked })}
                  />
                  Vim Mode (Keyboard navigation)
                </label>
              </div>
              
              <div className={styles.formGroup}>
                <label className={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={localConfig.ui.fastMode}
                    onChange={(e) => updateSection('ui', { fastMode: e.target.checked })}
                  />
                  Fast Mode (Reduced animations)
                </label>
              </div>
            </section>
          )}
          
          {/* Permissions Section */}
          {activeSection === 'permissions' && (
            <section className={styles.configSection}>
              <h3>Permissions</h3>
              <p className={styles.sectionDescription}>Configure safety and permission modes</p>
              
              <div className={styles.formGroup}>
                <label>Permission Mode</label>
                <select
                  value={localConfig.permissions.mode}
                  onChange={(e) => updateSection('permissions', { mode: e.target.value as 'default' | 'plan' | 'auto' })}
                >
                  <option value="default">Default (Auto-approve safe commands)</option>
                  <option value="plan">Plan Mode (Review before execution)</option>
                  <option value="auto">Auto (Approve all without prompting)</option>
                </select>
              </div>
              
              <div className={styles.formGroup}>
                <label>Allowed Paths (one per line)</label>
                <textarea
                  value={localConfig.permissions.allowedPaths.join('\n')}
                  onChange={(e) => updateSection('permissions', { allowedPaths: e.target.value.split('\n').filter(Boolean) })}
                  placeholder="/home/user/workspace&#10;/home/user/projects"
                  rows={4}
                />
              </div>
              
              <div className={styles.formGroup}>
                <label>Denied Commands (one per line)</label>
                <textarea
                  value={localConfig.permissions.deniedCommands.join('\n')}
                  onChange={(e) => updateSection('permissions', { deniedCommands: e.target.value.split('\n').filter(Boolean) })}
                  placeholder="rm -rf&#10;sudo"
                  rows={4}
                />
              </div>
            </section>
          )}
          
          {/* Memory Section */}
          {activeSection === 'memory' && (
            <section className={styles.configSection}>
              <h3>Memory</h3>
              <p className={styles.sectionDescription}>Configure persistent memory settings</p>
              
              <div className={styles.formGroup}>
                <label className={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={localConfig.memory.enabled}
                    onChange={(e) => updateSection('memory', { enabled: e.target.checked })}
                  />
                  Enable Memory
                </label>
              </div>
              
              <div className={styles.formGroup}>
                <label className={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={localConfig.memory.persistAcrossSessions}
                    onChange={(e) => updateSection('memory', { persistAcrossSessions: e.target.checked })}
                  />
                  Persist Across Sessions
                </label>
              </div>
              
              <div className={styles.formGroup}>
                <label>Maximum Items</label>
                <input
                  type="number"
                  value={localConfig.memory.maxItems}
                  onChange={(e) => updateSection('memory', { maxItems: parseInt(e.target.value) || 1000 })}
                  min={1}
                  max={10000}
                />
              </div>
            </section>
          )}
          
          {/* Tasks Section */}
          {activeSection === 'tasks' && (
            <section className={styles.configSection}>
              <h3>Tasks</h3>
              <p className={styles.sectionDescription}>Configure background task management</p>
              
              <div className={styles.formGroup}>
                <label>Maximum Concurrent Tasks</label>
                <input
                  type="number"
                  value={localConfig.tasks.maxConcurrent}
                  onChange={(e) => updateSection('tasks', { maxConcurrent: parseInt(e.target.value) || 5 })}
                  min={1}
                  max={20}
                />
              </div>
              
              <div className={styles.formGroup}>
                <label className={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={localConfig.tasks.autoResume}
                    onChange={(e) => updateSection('tasks', { autoResume: e.target.checked })}
                  />
                  Auto Resume Tasks on Startup
                </label>
              </div>
            </section>
          )}
          
          {/* MCP Section */}
          {activeSection === 'mcp' && (
            <section className={styles.configSection}>
              <h3>MCP (Model Context Protocol)</h3>
              <p className={styles.sectionDescription}>Configure MCP server connections</p>
              
              <div className={styles.formGroup}>
                <label className={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={localConfig.mcp.autoConnect}
                    onChange={(e) => updateSection('mcp', { autoConnect: e.target.checked })}
                  />
                  Auto-connect to MCP Servers
                </label>
              </div>
            </section>
          )}
          
          {/* Coordinator Section */}
          {activeSection === 'coordinator' && (
            <section className={styles.configSection}>
              <h3>Multi-Agent Coordinator</h3>
              <p className={styles.sectionDescription}>Configure multi-agent team coordination</p>
              
              <div className={styles.formGroup}>
                <label className={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={localConfig.coordinator.enabled}
                    onChange={(e) => updateSection('coordinator', { enabled: e.target.checked })}
                  />
                  Enable Multi-Agent Mode
                </label>
              </div>
              
              <div className={styles.formGroup}>
                <label>Maximum Agents</label>
                <input
                  type="number"
                  value={localConfig.coordinator.maxAgents}
                  onChange={(e) => updateSection('coordinator', { maxAgents: parseInt(e.target.value) || 10 })}
                  min={1}
                  max={50}
                />
              </div>
            </section>
          )}
          
          {/* Skills Section */}
          {activeSection === 'skills' && (
            <section className={styles.configSection}>
              <h3>Skills</h3>
              <p className={styles.sectionDescription}>Configure on-demand skill loading</p>
              
              <div className={styles.formGroup}>
                <label className={styles.checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={localConfig.skills.autoLoad}
                    onChange={(e) => updateSection('skills', { autoLoad: e.target.checked })}
                  />
                  Auto-load Skills
                </label>
              </div>
            </section>
          )}
          
          {/* Config Section */}
          {activeSection === 'config' && (
            <section className={styles.configSection}>
              <h3>General Configuration</h3>
              <p className={styles.sectionDescription}>Basic OpenHarness settings</p>
              
              <div className={styles.formGroup}>
                <label>Working Directory</label>
                <input
                  type="text"
                  value={localConfig.config.workingDirectory}
                  onChange={(e) => updateSection('config', { workingDirectory: e.target.value })}
                  placeholder="~/workspace"
                />
              </div>
              
              <div className={styles.formGroup}>
                <label>Default Model</label>
                <input
                  type="text"
                  value={localConfig.config.model}
                  onChange={(e) => updateSection('config', { model: e.target.value })}
                  placeholder="claude-3-5-sonnet-20241022"
                />
              </div>
              
              <div className={styles.formGroup}>
                <label>Theme</label>
                <select
                  value={localConfig.config.theme}
                  onChange={(e) => updateSection('config', { theme: e.target.value as 'dark' | 'light' })}
                >
                  <option value="dark">Dark</option>
                  <option value="light">Light</option>
                </select>
              </div>
            </section>
          )}
          
          {/* Placeholder for other sections */}
          {['tools', 'plugins', 'hooks', 'commands', 'prompts'].includes(activeSection) && (
            <section className={styles.configSection}>
              <h3>{sections.find(s => s.id === activeSection)?.label}</h3>
              <p className={styles.sectionDescription}>
                Configuration for {activeSection} is managed through the dedicated panels.
              </p>
              <div className={styles.infoBox}>
                <p>Use the sidebar navigation to access detailed {activeSection} management.</p>
              </div>
            </section>
          )}
          
          <div className={styles.configActions}>
            <button className={styles.secondaryButton} onClick={handleReset}>
              Reset to Defaults
            </button>
            <button className={styles.primaryButton} onClick={handleSave}>
              {saved ? 'Saved!' : 'Save Configuration'}
            </button>
          </div>
        </main>
      </div>
    </div>
  );
}