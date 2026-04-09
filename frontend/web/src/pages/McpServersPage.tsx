import { useAppStore } from '../store/useAppStore';
import { Puzzle, Server, Plus, Power, Settings, Trash2 } from 'lucide-react';
import { useState } from 'react';
import styles from './PageLayout.module.css';

export function McpServersPage() {
  const { mcpServers, mcpServerConfigs, addMcpServer, removeMcpServer } = useAppStore();
  const [showAddForm, setShowAddForm] = useState(false);
  const [newServer, setNewServer] = useState({ name: '', command: '', args: '' });
  
  const connectedServers = mcpServers.filter(s => s.status === 'connected');
  
  const handleAddServer = () => {
    if (newServer.name && newServer.command) {
      addMcpServer({
        name: newServer.name,
        command: newServer.command,
        args: newServer.args.split(',').map(a => a.trim()).filter(Boolean),
        env: {}
      });
      setNewServer({ name: '', command: '', args: '' });
      setShowAddForm(false);
    }
  };
  
  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1><Puzzle size={24} /> MCP Servers</h1>
        <p>Manage Model Context Protocol server connections</p>
      </div>
      
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{connectedServers.length}</span>
          <span className={styles.statLabel}>Connected</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{mcpServers.length}</span>
          <span className={styles.statLabel}>Total Servers</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{mcpServerConfigs.length}</span>
          <span className={styles.statLabel}>Configured</span>
        </div>
      </div>
      
      <div className={styles.pageContent}>
        <div className={styles.pageToolbar}>
          <button 
            className={styles.primaryButton}
            onClick={() => setShowAddForm(!showAddForm)}
          >
            <Plus size={18} />
            Add Server
          </button>
        </div>
        
        {showAddForm && (
          <div className={styles.formCard}>
            <h3>Add New MCP Server</h3>
            <div className={styles.formGroup}>
              <label>Server Name</label>
              <input
                type="text"
                value={newServer.name}
                onChange={(e) => setNewServer({ ...newServer, name: e.target.value })}
                placeholder="my-server"
              />
            </div>
            <div className={styles.formGroup}>
              <label>Command</label>
              <input
                type="text"
                value={newServer.command}
                onChange={(e) => setNewServer({ ...newServer, command: e.target.value })}
                placeholder="node /path/to/server.js"
              />
            </div>
            <div className={styles.formGroup}>
              <label>Arguments (comma-separated)</label>
              <input
                type="text"
                value={newServer.args}
                onChange={(e) => setNewServer({ ...newServer, args: e.target.value })}
                placeholder="arg1, arg2, arg3"
              />
            </div>
            <div className={styles.formActions}>
              <button className={styles.secondaryButton} onClick={() => setShowAddForm(false)}>
                Cancel
              </button>
              <button className={styles.primaryButton} onClick={handleAddServer}>
                Add Server
              </button>
            </div>
          </div>
        )}
        
        {mcpServers.length === 0 ? (
          <div className={styles.emptyState}>
            <Server size={48} />
            <h3>No MCP servers connected</h3>
            <p>Add an MCP server to extend OpenHarness capabilities</p>
          </div>
        ) : (
          <div className={styles.gridLayout}>
            {mcpServers.map((server) => (
              <div key={server.name} className={styles.serverCard}>
                <div className={styles.serverHeader}>
                  <div className={styles.serverInfo}>
                    <Server size={20} />
                    <span className={styles.serverName}>{server.name}</span>
                  </div>
                  <span className={`${styles.status} ${styles[server.status]}`}>
                    <Power size={12} />
                    {server.status}
                  </span>
                </div>
                
                {server.tools && server.tools.length > 0 && (
                  <div className={styles.serverTools}>
                    <span className={styles.toolsLabel}>Tools: {server.tools.length}</span>
                    <div className={styles.toolTags}>
                      {server.tools.slice(0, 3).map((tool, i) => (
                        <span key={i} className={styles.toolTag}>{tool}</span>
                      ))}
                      {server.tools.length > 3 && (
                        <span className={styles.toolTag}>+{server.tools.length - 3}</span>
                      )}
                    </div>
                  </div>
                )}
                
                <div className={styles.serverActions}>
                  <button className={styles.iconButton} title="Settings">
                    <Settings size={16} />
                  </button>
                  <button 
                    className={`${styles.iconButton} ${styles.danger}`}
                    onClick={() => removeMcpServer(server.name)}
                    title="Remove"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}