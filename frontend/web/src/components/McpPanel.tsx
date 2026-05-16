import { useState } from 'react';
import { Puzzle, Plus, Trash2, Save, X, Server, Settings } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import styles from '../styles/McpPanel.module.css';
import type { McpServerConfig } from '../types';

export function McpPanel() {
  const { mcpServers, addMcpServer } = useAppStore();
  const [showConfig, setShowConfig] = useState(false);
  const [config, setConfig] = useState<Partial<McpServerConfig>>({
    name: '',
    command: '',
    args: [],
    url: ''
  });

  const handleAddServer = () => {
    if (config.name) {
      addMcpServer(config as McpServerConfig);
      setConfig({ name: '', command: '', args: [], url: '' });
      setShowConfig(false);
    }
  };

  return (
    <div className={styles.mcpPanel}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <Puzzle size={20} />
          <h3>MCP Servers</h3>
        </div>
        <button 
          className={styles.addButton}
          onClick={() => setShowConfig(!showConfig)}
        >
          <Plus size={18} />
        </button>
      </div>

      {showConfig && (
        <div className={styles.configForm}>
          <div className={styles.formGroup}>
            <label className={styles.label}>Server Name</label>
            <input
              type="text"
              value={config.name}
              onChange={(e) => setConfig({ ...config, name: e.target.value })}
              placeholder="e.g., github, filesystem"
              className={styles.input}
            />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.label}>Command</label>
            <input
              type="text"
              value={config.command}
              onChange={(e) => setConfig({ ...config, command: e.target.value })}
              placeholder="npx -y @modelcontextprotocol/server-..."
              className={styles.input}
            />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.label}>URL (optional)</label>
            <input
              type="url"
              value={config.url}
              onChange={(e) => setConfig({ ...config, url: e.target.value })}
              placeholder="http://localhost:3000"
              className={styles.input}
            />
          </div>
          <div className={styles.formActions}>
            <button className={styles.cancelButton} onClick={() => setShowConfig(false)}>
              <X size={16} />
              Cancel
            </button>
            <button className={styles.saveButton} onClick={handleAddServer}>
              <Save size={16} />
              Add Server
            </button>
          </div>
        </div>
      )}

      <div className={styles.servers}>
        {mcpServers.length === 0 ? (
          <div className={styles.empty}>
            <Server size={32} className={styles.emptyIcon} />
            <p>No MCP servers configured</p>
            <button className={styles.configureButton} onClick={() => setShowConfig(true)}>
              Configure Your First Server
            </button>
          </div>
        ) : (
          mcpServers.map(server => (
            <div key={server.name} className={styles.serverCard}>
              <div className={styles.serverHeader}>
                <div className={styles.serverNameWrapper}>
                  <span className={styles.serverName}>{server.name}</span>
                  <span className={`${styles.status} ${styles[server.status]}`}>
                    {server.status}
                  </span>
                </div>
                <div className={styles.serverActions}>
                  <button 
                    className={styles.deleteButton}
                    onClick={() => {}}
                    title="Remove (coming soon)"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              {server.tools && server.tools.length > 0 && (
                <div className={styles.tools}>
                  <span className={styles.toolsLabel}>Available Tools:</span>
                  <div className={styles.toolTags}>
                    {server.tools.slice(0, 8).map(tool => (
                      <span key={tool} className={styles.toolTag}>{tool}</span>
                    ))}
                    {server.tools.length > 8 && (
                      <span className={styles.more}>+{server.tools.length - 8} more</span>
                    )}
                  </div>
                </div>
              )}
              {server.config && (server.config as any).command && (
                <div className={styles.serverConfig}>
                  <div className={styles.configItem}>
                    <Settings size={12} />
                    <code>{(server.config as any).command}</code>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
