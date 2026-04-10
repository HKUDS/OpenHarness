import { useState, useEffect } from 'react';
import { Plug, RefreshCw, Box, Wrench, Users, Zap, Globe, ChevronDown, ChevronUp, Settings, Power, Check } from 'lucide-react';
import styles from '../styles/PageLayout.module.css';

interface PluginSkill {
  name: string;
  description: string;
}

interface PluginCommand {
  name: string;
  description: string;
}

interface PluginAgent {
  name: string;
  description: string;
}

interface Plugin {
  name: string;
  description: string;
  version: string;
  enabled: boolean;
  path: string;
  skills: PluginSkill[];
  commands: PluginCommand[];
  agents: PluginAgent[];
  hooks_count: number;
  mcp_servers: string[];
}

interface PluginsResponse {
  plugins: Plugin[];
  total: number;
  enabled: number;
}

export function PluginsPage() {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [stats, setStats] = useState({ total: 0, enabled: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedPlugin, setExpandedPlugin] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  
  const fetchPlugins = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/plugins');
      if (!response.ok) {
        throw new Error('Failed to fetch plugins');
      }
      const data: PluginsResponse = await response.json();
      setPlugins(data.plugins);
      setStats({ total: data.total, enabled: data.enabled });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    fetchPlugins();
  }, []);
  
  const toggleExpand = (name: string) => {
    setExpandedPlugin(expandedPlugin === name ? null : name);
  };
  
  const filteredPlugins = plugins.filter(plugin => 
    searchQuery === '' || 
    plugin.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    plugin.description.toLowerCase().includes(searchQuery.toLowerCase())
  );
  
  const totalSkills = plugins.reduce((acc, p) => acc + p.skills.length, 0);
  const totalCommands = plugins.reduce((acc, p) => acc + p.commands.length, 0);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1><Plug size={24} /> Plugins</h1>
        <p>Manage OpenHarness plugins and extensions</p>
      </div>
      
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{stats.enabled}</span>
          <span className={styles.statLabel}>Enabled</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{stats.total}</span>
          <span className={styles.statLabel}>Total Plugins</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{totalSkills}</span>
          <span className={styles.statLabel}>Skills</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{totalCommands}</span>
          <span className={styles.statLabel}>Commands</span>
        </div>
      </div>
      
      <div className={styles.pageContent}>
        <div className={styles.pageToolbar}>
          <div className={styles.searchContainer}>
            <RefreshCw size={18} style={{ opacity: 0.5 }} />
            <input
              type="text"
              placeholder="Search plugins..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className={styles.searchInput}
            />
          </div>
          
          <div style={{ flex: 1 }} />
          
          <button 
            className={styles.primaryButton}
            onClick={fetchPlugins}
            disabled={loading}
          >
            <RefreshCw size={18} className={loading ? styles.spinning : ''} />
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
        
        {error && (
          <div className={styles.formCard}>
            <p style={{ color: '#ef4444' }}>Error: {error}</p>
          </div>
        )}
        
        {loading ? (
          <div className={styles.emptyState}>
            <RefreshCw size={48} className={styles.spinning} />
            <h3>Loading plugins...</h3>
          </div>
        ) : filteredPlugins.length === 0 ? (
          <div className={styles.emptyState}>
            <Plug size={48} />
            <h3>No plugins found</h3>
            <p>Install plugins to extend OpenHarness functionality</p>
          </div>
        ) : (
          <div className={styles.gridLayout}>
            {filteredPlugins.map((plugin, index) => (
              <div 
                key={plugin.name} 
                className={`${styles.pluginCardEnhanced} ${plugin.enabled ? styles.enabled : ''} ${styles.animateIn}`}
                style={{ animationDelay: `${index * 50}ms` }}
              >
                <div className={styles.pluginHeaderEnhanced}>
                  <div className={styles.pluginIconEnhanced}>
                    <Plug size={22} />
                  </div>
                  <div className={styles.pluginTitleSection}>
                    <span className={styles.pluginNameEnhanced}>
                      {plugin.name}
                      <span className={styles.pluginVersionEnhanced}>v{plugin.version}</span>
                    </span>
                    <span className={`${styles.pluginStatusEnhanced} ${plugin.enabled ? styles.enabled : styles.disabled}`}>
                      {plugin.enabled ? <><Check size={12} /> Active</> : <><Power size={12} /> Inactive</>}
                    </span>
                  </div>
                </div>
                
                <p className={styles.pluginDescriptionEnhanced}>
                  {plugin.description || 'No description available'}
                </p>
                
                {/* Stats Grid */}
                <div className={styles.pluginStatsEnhanced}>
                  <div className={styles.pluginStatEnhanced}>
                    <div className={styles.pluginStatIcon}>
                      <Box size={16} />
                    </div>
                    <span className={styles.pluginStatValue}>{plugin.skills.length}</span>
                    <span className={styles.pluginStatLabel}>Skills</span>
                  </div>
                  <div className={styles.pluginStatEnhanced}>
                    <div className={styles.pluginStatIcon}>
                      <Wrench size={16} />
                    </div>
                    <span className={styles.pluginStatValue}>{plugin.commands.length}</span>
                    <span className={styles.pluginStatLabel}>Commands</span>
                  </div>
                  <div className={styles.pluginStatEnhanced}>
                    <div className={styles.pluginStatIcon}>
                      <Users size={16} />
                    </div>
                    <span className={styles.pluginStatValue}>{plugin.agents.length}</span>
                    <span className={styles.pluginStatLabel}>Agents</span>
                  </div>
                  <div className={styles.pluginStatEnhanced}>
                    <div className={styles.pluginStatIcon}>
                      <Zap size={16} />
                    </div>
                    <span className={styles.pluginStatValue}>{plugin.hooks_count}</span>
                    <span className={styles.pluginStatLabel}>Hooks</span>
                  </div>
                </div>
                
                {/* MCP Servers */}
                {plugin.mcp_servers.length > 0 && (
                  <div style={{ marginTop: 'var(--space-2)', display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                    <Globe size={14} style={{ color: 'var(--text-tertiary)' }} />
                    {plugin.mcp_servers.map(server => (
                      <span key={server} className={styles.toolTagEnhanced} style={{ background: 'rgba(95, 115, 220, 0.15)', color: 'var(--primary-500)' }}>
                        {server}
                      </span>
                    ))}
                  </div>
                )}
                
                {/* Expand Button */}
                <button 
                  className={styles.expandButton}
                  onClick={() => toggleExpand(plugin.name)}
                >
                  {expandedPlugin === plugin.name ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  {expandedPlugin === plugin.name ? 'Hide Details' : 'Show Details'}
                </button>
                
                {/* Expanded Details */}
                {expandedPlugin === plugin.name && (
                  <div className={styles.pluginDetails}>
                    {/* Skills */}
                    {plugin.skills.length > 0 && (
                      <div className={styles.pluginDetailSection}>
                        <h4><Box size={14} /> Skills ({plugin.skills.length})</h4>
                        <ul>
                          {plugin.skills.map((skill) => (
                            <li key={skill.name}>
                              <strong>{skill.name}</strong>
                              {skill.description && <span style={{ color: 'var(--text-tertiary)', marginLeft: 'var(--space-1)' }}>— {skill.description}</span>}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    {/* Commands */}
                    {plugin.commands.length > 0 && (
                      <div className={styles.pluginDetailSection}>
                        <h4><Wrench size={14} /> Commands ({plugin.commands.length})</h4>
                        <ul>
                          {plugin.commands.map((cmd) => (
                            <li key={cmd.name}>
                              <code>/{cmd.name}</code>
                              {cmd.description && <span style={{ color: 'var(--text-tertiary)', marginLeft: 'var(--space-1)' }}>— {cmd.description}</span>}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    {/* Agents */}
                    {plugin.agents.length > 0 && (
                      <div className={styles.pluginDetailSection}>
                        <h4><Users size={14} /> Agents ({plugin.agents.length})</h4>
                        <ul>
                          {plugin.agents.map((agent) => (
                            <li key={agent.name}>
                              <strong>{agent.name}</strong>
                              {agent.description && <span style={{ color: 'var(--text-tertiary)', marginLeft: 'var(--space-1)' }}>— {agent.description}</span>}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    {/* Path */}
                    <div style={{ marginTop: 'var(--space-3)', padding: 'var(--space-2)', background: 'var(--bg-primary)', borderRadius: 'var(--radius-sm)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', fontSize: '0.75rem', color: 'var(--text-tertiary)' }}>
                        <Settings size={12} />
                        <span>Path:</span>
                        <code style={{ color: 'var(--text-secondary)' }}>{plugin.path}</code>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}